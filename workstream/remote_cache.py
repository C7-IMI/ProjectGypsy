#!/usr/bin/env python3
"""Loopback-first authenticated HTTP remote cache for Gypsy Studio.

The local content-addressed action cache in cache.py can share entries and blobs across
machines/checkouts through this small, dependency-free HTTP service. It is deliberately
narrow and safe:

* Loopback by default. Binding a non-loopback address is refused unless a caller passes
  allow_non_loopback=True (the CLI never does).
* A required bearer token. The server refuses to start without a non-empty token; every
  /v1/... endpoint rejects a missing or wrong token (constant-time comparison). /healthz is
  the only unauthenticated endpoint and returns liveness only, never cache contents.
* Two exact resource types: entries (/v1/entries/<64 lowercase hex>) and blobs
  (/v1/blobs/<sha256 hex>). There is no shell, no arbitrary command, no URL fetching and no
  path traversal: ids are validated by regex and files live in fixed subdirectories.
* SHA-256 is verified on both sides: blob PUT must match the id, blob GET hashes the stored
  bytes before serving, and the client verifies every blob it receives.
* Bodies are bounded (entry JSON and blob bytes), Content-Length is required and chunked
  transfer is refused. Errors are small JSON documents without stack traces or secrets.
* No TLS: this is a loopback development cache, not an internet service. The bearer token
  is read from the environment and is never printed by the server or client.

Layout on the server root:

    <root>/entries/<key>.json    cache entry documents (gypsy.cache-entry/v1)
    <root>/blobs/<sha256>        raw artifact bytes

CLI (wired in gypsy.py):

    python workstream/gypsy.py cache serve [--host 127.0.0.1] [--port 8767] [--root DIR]
    python workstream/gypsy.py cache remote [--json]

Environment: GYPSY_REMOTE_CACHE_URL (for the client), GYPSY_REMOTE_CACHE_TOKEN (both).
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import os
import re
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

SCHEMA = "gypsy.remote-cache/v1"
ENTRY_SCHEMA = "gypsy.cache-entry/v1"
ENV_URL = "GYPSY_REMOTE_CACHE_URL"
ENV_TOKEN = "GYPSY_REMOTE_CACHE_TOKEN"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8767
MAX_ENTRY_BYTES = 1_048_576
MAX_BLOB_BYTES = 33_554_432
HEX_RE = re.compile(r"^[0-9a-f]{64}$")


class RemoteCacheError(RuntimeError):
    """The remote cache is misconfigured, unreachable, or returned an invalid response."""

    def __init__(self, message, *, status=None):
        super().__init__(message)
        self.status = status


class RemoteCacheAuthError(RemoteCacheError):
    """The remote cache rejected the bearer token."""


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def is_loopback(host) -> bool:
    text = str(host or "").strip()
    if text in ("localhost",):
        return True
    try:
        return ipaddress.ip_address(text).is_loopback
    except ValueError:
        return False


def validate_key(value, *, label="key") -> str:
    if not isinstance(value, str) or not HEX_RE.match(value):
        raise RemoteCacheError(
            label + " must be 64 lowercase hexadecimal characters"
        )
    return value


def validate_digest(value, *, label="sha256") -> str:
    return validate_key(value, label=label)


def validate_token(token) -> str:
    if not isinstance(token, str) or not token.strip():
        raise RemoteCacheError("a non-empty bearer token is required")
    if len(token) < 8:
        raise RemoteCacheError("the bearer token must be at least 8 characters")
    if any(character.isspace() for character in token):
        raise RemoteCacheError("the bearer token must not contain whitespace")
    return token


def _entry_error(key: str, entry) -> str:
    if not isinstance(entry, dict):
        return "entry must be a JSON object"
    if entry.get("schema") != ENTRY_SCHEMA:
        return "entry schema must be " + ENTRY_SCHEMA
    if entry.get("key") != key:
        return "entry key does not match the URL key"
    artifacts = entry.get("artifacts")
    if not isinstance(artifacts, list):
        return "entry artifacts must be a list"
    for item in artifacts:
        if not isinstance(item, dict):
            return "entry artifact must be an object"
        path = item.get("path")
        if not isinstance(path, str) or not path.strip():
            return "entry artifact path must be a non-empty string"
        relative = Path(path)
        if relative.is_absolute() or relative.drive or ".." in relative.parts:
            return "entry artifact path must be repo-relative without '..'"
        if not isinstance(item.get("sha256"), str) or not HEX_RE.match(item["sha256"]):
            return "entry artifact sha256 must be 64 lowercase hexadecimal characters"
        if isinstance(item.get("bytes"), bool) or not isinstance(item.get("bytes"), int) or item["bytes"] < 0:
            return "entry artifact bytes must be an integer >= 0"
    result = entry.get("result")
    if result is not None and not isinstance(result, dict):
        return "entry result must be an object when present"
    return ""


def _atomic_write(path: Path, data: bytes) -> None:
    import os
    import tempfile

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(
        prefix="." + path.stem + "-", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except BaseException:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


class RemoteCacheStore:
    """The server-side content-addressed store under one root directory."""

    def __init__(self, root, *, max_entry_bytes=MAX_ENTRY_BYTES, max_blob_bytes=MAX_BLOB_BYTES):
        self.root = Path(root)
        self.entries_dir = self.root / "entries"
        self.blobs_dir = self.root / "blobs"
        self.max_entry_bytes = max(1024, int(max_entry_bytes))
        self.max_blob_bytes = max(1024, int(max_blob_bytes))
        self._lock = threading.Lock()
        self._puts = 0
        self._gets = 0
        self._errors = 0
        for directory in (self.entries_dir, self.blobs_dir):
            directory.mkdir(parents=True, exist_ok=True)

    def _entry_path(self, key: str) -> Path:
        return self.entries_dir / (key + ".json")

    def _blob_path(self, digest: str) -> Path:
        return self.blobs_dir / digest

    def put_blob(self, digest: str, data: bytes) -> bool:
        with self._lock:
            if len(data) > self.max_blob_bytes:
                self._errors += 1
                raise RemoteCacheError(
                    "blob exceeds the %d byte limit" % self.max_blob_bytes, status=413
                )
            if _sha256(data) != digest:
                self._errors += 1
                raise RemoteCacheError("blob sha256 does not match the URL id", status=400)
            try:
                _atomic_write(self._blob_path(digest), data)
            except OSError:
                self._errors += 1
                raise RemoteCacheError("could not store the blob", status=500)
            self._puts += 1
            return True

    def get_blob(self, digest: str):
        """Return (bytes, error). A hash mismatch is a safe error, never corrupt bytes."""
        with self._lock:
            path = self._blob_path(digest)
            if not path.is_file():
                self._gets += 1
                return None, "missing"
            try:
                data = path.read_bytes()
            except OSError:
                self._errors += 1
                return None, "unreadable"
            if _sha256(data) != digest:
                self._errors += 1
                return None, "corrupt"
            self._gets += 1
            return data, None

    def put_entry(self, key: str, entry: dict) -> bool:
        error = _entry_error(key, entry)
        if error:
            with self._lock:
                self._errors += 1
            raise RemoteCacheError(error, status=400)
        payload = json.dumps(entry, ensure_ascii=False).encode("utf-8")
        with self._lock:
            if len(payload) > self.max_entry_bytes:
                self._errors += 1
                raise RemoteCacheError(
                    "entry exceeds the %d byte limit" % self.max_entry_bytes, status=413
                )
            try:
                _atomic_write(self._entry_path(key), payload)
            except OSError:
                self._errors += 1
                raise RemoteCacheError("could not store the entry", status=500)
            self._puts += 1
            return True

    def get_entry(self, key: str):
        """Return (entry, error)."""
        path = self._entry_path(key)
        with self._lock:
            if not path.is_file():
                self._gets += 1
                return None, "missing"
            try:
                data = path.read_text(encoding="utf-8-sig")
            except (OSError, UnicodeDecodeError):
                self._errors += 1
                return None, "unreadable"
        try:
            entry = json.loads(data)
        except json.JSONDecodeError:
            self._errors += 1
            return None, "corrupt"
        error = _entry_error(key, entry)
        if error:
            self._errors += 1
            return None, "corrupt"
        return entry, None

    def stats(self) -> dict:
        entries = 0
        blobs = 0
        blob_bytes = 0
        if self.entries_dir.is_dir():
            entries = len(list(self.entries_dir.glob("*.json")))
        if self.blobs_dir.is_dir():
            for path in self.blobs_dir.iterdir():
                if path.is_file():
                    blobs += 1
                    try:
                        blob_bytes += path.stat().st_size
                    except OSError:
                        pass
        return {
            "schema": SCHEMA,
            "root": str(self.root),
            "entries": entries,
            "blobs": blobs,
            "blobBytes": blob_bytes,
            "puts": self._puts,
            "gets": self._gets,
            "errors": self._errors,
        }


def _handler_for(store: RemoteCacheStore, token: str, verbose: bool):
    class RemoteCacheHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "GypsyRemoteCache/1"

        def log_message(self, format, *args):  # noqa: A002 - stdlib signature
            if verbose:
                super().log_message(format, *args)

        # -- helpers ---------------------------------------------------
        def _send_json(self, code, payload):
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            if code == 401:
                self.send_header("WWW-Authenticate", "Bearer")
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def _send_bytes(self, code, data: bytes):
            self.send_response(code)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def _error(self, code, message):
            # Close the connection on errors: an oversized or malformed body may be unread,
            # and a keep-alive reuse of that socket would corrupt the next request.
            self.close_connection = True
            self._send_json(code, {"error": message})

        def _authorized(self) -> bool:
            header = self.headers.get("Authorization", "")
            if not header.startswith("Bearer "):
                return False
            provided = header[len("Bearer "):].strip()
            if not provided:
                return False
            return hmac.compare_digest(provided, token)

        def _read_body(self, limit: int):
            if self.headers.get("Transfer-Encoding"):
                self._error(411, "Content-Length is required; chunked bodies are refused")
                return None
            raw_length = self.headers.get("Content-Length")
            if raw_length is None:
                self._error(411, "Content-Length is required")
                return None
            try:
                length = int(raw_length)
            except (TypeError, ValueError):
                self._error(400, "Content-Length must be an integer")
                return None
            if length < 0:
                self._error(400, "Content-Length must not be negative")
                return None
            if length > limit:
                self._error(413, "request body exceeds the %d byte limit" % limit)
                return None
            data = self.rfile.read(length)
            if len(data) != length:
                self._error(400, "request body was shorter than Content-Length")
                return None
            return data

        def _path(self) -> str:
            return urlsplit(self.path).path

        # -- GET -------------------------------------------------------
        def do_GET(self):
            path = self._path()
            if path == "/healthz":
                self._send_json(
                    200,
                    {
                        "schema": SCHEMA,
                        "status": "ok",
                        "service": "remote-cache",
                        "time": utc_now_iso(),
                    },
                )
                return
            if not path.startswith("/v1/"):
                self._error(404, "not found")
                return
            if not self._authorized():
                self._error(401, "a valid bearer token is required")
                return
            if path == "/v1/stats":
                self._send_json(200, store.stats())
                return
            parts = path.split("/")
            if len(parts) == 4 and parts[2] == "entries":
                try:
                    key = validate_key(parts[3], label="entry key")
                except RemoteCacheError as exc:
                    self._error(400, str(exc))
                    return
                entry, error = store.get_entry(key)
                if error == "missing":
                    self._error(404, "entry not found")
                elif error:
                    self._error(500, "stored entry is " + error)
                else:
                    self._send_json(200, entry)
                return
            if len(parts) == 4 and parts[2] == "blobs":
                try:
                    digest = validate_digest(parts[3], label="blob sha256")
                except RemoteCacheError as exc:
                    self._error(400, str(exc))
                    return
                data, error = store.get_blob(digest)
                if error == "missing":
                    self._error(404, "blob not found")
                elif error:
                    self._error(500, "stored blob is " + error)
                else:
                    self._send_bytes(200, data)
                return
            self._error(404, "not found")

        # -- PUT -------------------------------------------------------
        def do_PUT(self):
            path = self._path()
            if not path.startswith("/v1/"):
                self._error(404, "not found")
                return
            if not self._authorized():
                self._error(401, "a valid bearer token is required")
                return
            parts = path.split("/")
            if len(parts) == 4 and parts[2] == "entries":
                try:
                    key = validate_key(parts[3], label="entry key")
                except RemoteCacheError as exc:
                    self._error(400, str(exc))
                    return
                body = self._read_body(store.max_entry_bytes)
                if body is None:
                    return
                try:
                    entry = json.loads(body.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    self._error(400, "entry body must be valid JSON")
                    return
                try:
                    store.put_entry(key, entry)
                except RemoteCacheError as exc:
                    self._error(exc.status or 400, str(exc))
                else:
                    self._send_json(201, {"stored": True, "key": key})
                return
            if len(parts) == 4 and parts[2] == "blobs":
                try:
                    digest = validate_digest(parts[3], label="blob sha256")
                except RemoteCacheError as exc:
                    self._error(400, str(exc))
                    return
                body = self._read_body(store.max_blob_bytes)
                if body is None:
                    return
                try:
                    store.put_blob(digest, body)
                except RemoteCacheError as exc:
                    self._error(exc.status or 400, str(exc))
                else:
                    self._send_json(201, {"stored": True, "sha256": digest})
                return
            self._error(404, "not found")

        def do_POST(self):
            self._error(405, "method not allowed")

        def do_DELETE(self):
            self._error(405, "method not allowed")

    return RemoteCacheHandler


class RemoteCacheServer:
    """A loopback-first authenticated HTTP remote cache server."""

    def __init__(
        self,
        root,
        *,
        token,
        host=DEFAULT_HOST,
        port=DEFAULT_PORT,
        max_entry_bytes=MAX_ENTRY_BYTES,
        max_blob_bytes=MAX_BLOB_BYTES,
        verbose=False,
    ):
        self.root = Path(root)
        self.token = validate_token(token)
        self.host = str(host or DEFAULT_HOST)
        self.port = int(port)
        if not 0 <= self.port <= 65535:
            raise RemoteCacheError("port must be between 0 and 65535")
        if not is_loopback(self.host):
            raise RemoteCacheError(
                "refusing to bind " + self.host + ": the remote cache is loopback-only"
            )
        self.store = RemoteCacheStore(
            self.root, max_entry_bytes=max_entry_bytes, max_blob_bytes=max_blob_bytes
        )
        self.verbose = bool(verbose)
        self._httpd = None
        self._thread = None
        self.bound_host = None
        self.bound_port = None

    def start(self):
        if self._httpd is not None:
            return self
        handler = _handler_for(self.store, self.token, self.verbose)

        class _Server(ThreadingHTTPServer):
            daemon_threads = True
            allow_reuse_address = True

        try:
            self._httpd = _Server((self.host, self.port), handler)
        except OSError as exc:
            raise RemoteCacheError("could not bind " + self.host + ":" + str(self.port) + ": " + str(exc))
        self.bound_host, self.bound_port = self._httpd.server_address[:2]
        self._thread = threading.Thread(
            target=self._httpd.serve_forever,
            name="gypsy-remote-cache",
            daemon=True,
        )
        self._thread.start()
        return self

    @property
    def url(self) -> str:
        if self._httpd is None:
            raise RemoteCacheError("server has not started")
        return "http://" + str(self.bound_host) + ":" + str(self.bound_port)

    def serve_forever(self):
        if self._httpd is None:
            self.start()
        try:
            self._httpd.serve_forever()
        finally:
            self.stop()

    def stop(self):
        httpd, thread = self._httpd, self._thread
        self._httpd = None
        self._thread = None
        if httpd is not None:
            try:
                httpd.shutdown()
            except Exception:
                pass
            try:
                httpd.server_close()
            except Exception:
                pass
        if thread is not None and thread.is_alive():
            thread.join(timeout=5)
        return {"stopped": True}

    def status(self) -> dict:
        stats = self.store.stats()
        return {
            "schema": SCHEMA,
            "url": self.url,
            "host": self.bound_host,
            "port": self.bound_port,
            "loopback": is_loopback(str(self.bound_host)),
            "auth": "bearer",
            "entries": stats["entries"],
            "blobs": stats["blobs"],
            "blobBytes": stats["blobBytes"],
        }

    def __enter__(self):
        return self.start()

    def __exit__(self, exc_type, exc, tb):
        self.stop()
        return False


class RemoteCacheClient:
    """A small authenticated HTTP client for RemoteCacheServer."""

    def __init__(
        self,
        url,
        token,
        *,
        timeout=10.0,
        max_entry_bytes=MAX_ENTRY_BYTES,
        max_blob_bytes=MAX_BLOB_BYTES,
    ):
        text = str(url or "").strip().rstrip("/")
        if not (text.startswith("http://") or text.startswith("https://")):
            raise RemoteCacheError("remote cache URL must start with http:// or https://")
        self.url = text
        self.token = validate_token(token)
        self.timeout = float(timeout)
        self.max_entry_bytes = max(1024, int(max_entry_bytes))
        self.max_blob_bytes = max(1024, int(max_blob_bytes))
        self.last_error = None

    def _request(self, method, path, *, data=None, content_type=None):
        headers = {"Authorization": "Bearer " + self.token, "Accept": "application/json"}
        if content_type:
            headers["Content-Type"] = content_type
        request = Request(
            self.url + path,
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                return response.status, response.read()
        except HTTPError as exc:
            body = b""
            try:
                body = exc.read()[:2000]
            except Exception:
                pass
            finally:
                try:
                    exc.close()
                except Exception:
                    pass
            message = "HTTP " + str(exc.code)
            try:
                payload = json.loads(body.decode("utf-8", "replace"))
                if isinstance(payload, dict) and payload.get("error"):
                    message += ": " + str(payload["error"])[:200]
            except (UnicodeDecodeError, json.JSONDecodeError):
                pass
            if exc.code == 401:
                raise RemoteCacheAuthError(message, status=401)
            raise RemoteCacheError(message, status=exc.code)
        except (URLError, TimeoutError, OSError) as exc:
            reason = getattr(exc, "reason", exc)
            raise RemoteCacheError("remote cache unreachable: " + str(reason))

    def health(self) -> dict:
        status, body = self._request("GET", "/healthz")
        try:
            data = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise RemoteCacheError("health response was not JSON")
        if status != 200 or not isinstance(data, dict):
            raise RemoteCacheError("health check failed")
        return data

    def get_entry(self, key: str):
        validate_key(key, label="entry key")
        try:
            status, body = self._request("GET", "/v1/entries/" + key)
        except RemoteCacheError as exc:
            if exc.status == 404:
                return None
            raise
        try:
            entry = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise RemoteCacheError("remote entry was not JSON")
        if not isinstance(entry, dict):
            raise RemoteCacheError("remote entry was not an object")
        return entry

    def put_entry(self, key: str, entry) -> bool:
        validate_key(key, label="entry key")
        body = json.dumps(entry, ensure_ascii=False).encode("utf-8")
        if len(body) > self.max_entry_bytes:
            raise RemoteCacheError(
                "entry exceeds the %d byte client limit" % self.max_entry_bytes
            )
        status, _ = self._request(
            "PUT",
            "/v1/entries/" + key,
            data=body,
            content_type="application/json",
        )
        return bool(status in (200, 201))

    def get_blob(self, digest: str):
        validate_digest(digest, label="blob sha256")
        try:
            status, body = self._request("GET", "/v1/blobs/" + digest)
        except RemoteCacheError as exc:
            if exc.status == 404:
                return None
            raise
        if _sha256(body) != digest:
            raise RemoteCacheError("remote blob failed SHA-256 verification")
        return body

    def put_blob(self, digest: str, data) -> bool:
        validate_digest(digest, label="blob sha256")
        data = bytes(data)
        if len(data) > self.max_blob_bytes:
            raise RemoteCacheError(
                "blob exceeds the %d byte client limit" % self.max_blob_bytes
            )
        if _sha256(data) != digest:
            raise RemoteCacheError("blob does not match its sha256 id")
        status, _ = self._request(
            "PUT",
            "/v1/blobs/" + digest,
            data=data,
            content_type="application/octet-stream",
        )
        return bool(status in (200, 201))

    def stats(self) -> dict:
        status, body = self._request("GET", "/v1/stats")
        try:
            data = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise RemoteCacheError("stats response was not JSON")
        if not isinstance(data, dict):
            raise RemoteCacheError("stats response was not an object")
        return data

    def status(self) -> dict:
        result = {
            "schema": SCHEMA,
            "enabled": True,
            "url": self.url,
            "tokenPresent": bool(self.token),
            "reachable": False,
            "authenticated": False,
            "health": None,
            "stats": None,
            "error": None,
        }
        try:
            result["health"] = self.health()
            result["reachable"] = True
        except RemoteCacheError as exc:
            result["error"] = str(exc)
            return result
        try:
            result["stats"] = self.stats()
            result["authenticated"] = True
        except RemoteCacheAuthError:
            result["error"] = "unauthorized: the bearer token was rejected"
        except RemoteCacheError as exc:
            result["error"] = str(exc)
        return result


def config_from_env(env=None):
    """Return {"url","token"} only when both remote-cache environment variables are set."""
    env = env if env is not None else os.environ
    url = str(env.get(ENV_URL, "") or "").strip()
    token = str(env.get(ENV_TOKEN, "") or "").strip()
    if not url or not token:
        return None
    return {"url": url, "token": token}


def env_summary(env=None) -> dict:
    """A token-free description of the remote-cache environment for status output."""
    env = env if env is not None else os.environ
    url = str(env.get(ENV_URL, "") or "").strip()
    token = str(env.get(ENV_TOKEN, "") or "").strip()
    return {
        "urlVariable": ENV_URL,
        "tokenVariable": ENV_TOKEN,
        "url": url or None,
        "urlPresent": bool(url),
        "tokenPresent": bool(token),
        "enabled": bool(url and token),
    }
