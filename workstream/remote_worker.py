#!/usr/bin/env python3
"""TLS remote worker protocol with an explicit read-only allowlist (ADR-020 successor).

This module is a small, honest remote-execution protocol, not a general remote command
runner. A TLS coordinator holds an in-memory job queue; a worker claims a job, creates a
temporary isolated git worktree of the repository at HEAD, runs exactly one allowlisted
read-only action with a temporary state directory, returns result JSON and artifact hashes,
and removes the worktree. The main checkout is never the execution root.

Safety properties:

* TLS only, both sides: the coordinator wraps its listening socket in a TLS context with a
  minimum of TLS 1.2 and a certificate/private-key pair; the client requires https, verifies
  the certificate against a supplied CA file and checks the hostname. There is no plaintext
  fallback and no "verify=False" path.
* Required bearer token: every endpoint (including health) rejects a missing or wrong token
  with 401. Tokens are compared in constant time and are never written to logs or results.
* Jobs are ids, not commands. The only accepted shapes are
  {"toolpack": "hero.wayfarer", "action": "validate"} and {"probe": "godot|unity|ue5|flax"}.
  The coordinator allowlists the pairs; argv, cwd, shell, env and extra keys are rejected
  with 400. The worker re-validates the same allowlist before running anything.
* The worker only runs the committed manifest action in an isolated git worktree created
  from the coordinator repository's HEAD with a temporary state directory; the working tree
  and index of the main checkout are not touched. If git worktree creation fails the job
  fails; there is no fallback to executing in the main checkout.
* Job lifecycle: queued -> claimed -> completed|failed, with expired and cancelled terminal
  states, FIFO claims, duplicate-claim prevention, idempotency keys for submission, idempotent
  duplicate completion, bounded request/result sizes, and JSON errors with clear states.

Not claimed: arbitrary remote command execution, durable job persistence across coordinator
restarts, multi-user authorisation (one shared bearer token), remote artifact upload (only
SHA-256/bytes are returned), or worker attestation beyond TLS server verification.

Tests generate an ephemeral self-signed certificate at test time (see
generate_self_signed_cert, which uses the installed cryptography package); no key is
committed. The module itself uses only the standard library at runtime.
"""
from __future__ import annotations

import hashlib
import hmac
import http.client
import ipaddress
import json
import os
import secrets
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

SCHEMA = "gypsy.remote-worker/v1"
JOB_SCHEMA = "gypsy.remote-worker-job/v1"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8768
DEFAULT_JOB_TIMEOUT = 120.0
MIN_JOB_TIMEOUT = 1.0
MAX_JOB_TIMEOUT = 600.0
MAX_REQUEST_BYTES = 1_048_576
MAX_RESPONSE_BYTES = 2_097_152
HEX_ID_RE = __import__("re").compile(r"^[0-9a-f]{32}$")
HEX_SHA_RE = __import__("re").compile(r"^[0-9a-f]{64}$")

ALLOWED_TOOLPACK_ACTIONS = frozenset({("hero.wayfarer", "validate")})
ALLOWED_PROBES = frozenset({"godot", "unity", "ue5", "flax"})


class RemoteWorkerError(RuntimeError):
    """The coordinator is misconfigured, unreachable, or returned an invalid response."""

    def __init__(self, message, *, status=None, code=None):
        super().__init__(message)
        self.status = status
        self.code = code


class RemoteWorkerAuthError(RemoteWorkerError):
    """The coordinator rejected the bearer token."""


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def validate_token(token) -> str:
    if not isinstance(token, str) or not token.strip():
        raise RemoteWorkerError("a non-empty bearer token is required")
    if len(token) < 8:
        raise RemoteWorkerError("the bearer token must be at least 8 characters")
    if any(character.isspace() for character in token):
        raise RemoteWorkerError("the bearer token must not contain whitespace")
    return token


def is_loopback(host) -> bool:
    text = str(host or "").strip()
    if text == "localhost":
        return True
    try:
        return ipaddress.ip_address(text).is_loopback
    except ValueError:
        return False


# -- TLS helpers -------------------------------------------------------------


def generate_self_signed_cert(directory, *, common_name="127.0.0.1", days=1) -> dict:
    """Generate an ephemeral self-signed certificate for local tests/evidence.

    Uses the cryptography package when available (it is installed here); the runtime
    protocol itself never needs it. No key is ever committed.
    """
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RemoteWorkerError(
            "generating a self-signed certificate requires the cryptography package"
        ) from exc

    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    certfile = directory / "cert.pem"
    keyfile = directory / "key.pem"
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = datetime.now(timezone.utc)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, str(common_name))])
    san = [x509.IPAddress(ipaddress.ip_address("127.0.0.1")), x509.DNSName("localhost")]
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(secrets.randbits(63) or 1)
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=int(days)))
        .add_extension(x509.SubjectAlternativeName(san), critical=False)
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False
        )
        .sign(key, hashes.SHA256())
    )
    keyfile.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    certfile.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    return {"cert": str(certfile), "key": str(keyfile)}


def make_server_tls_context(certfile, keyfile) -> ssl.SSLContext:
    certfile, keyfile = Path(certfile), Path(keyfile)
    if not certfile.is_file() or not keyfile.is_file():
        raise RemoteWorkerError("coordinator certificate/key files are missing")
    try:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(certfile=str(certfile), keyfile=str(keyfile))
    except (OSError, ssl.SSLError) as exc:
        raise RemoteWorkerError("could not load the coordinator TLS certificate: " + str(exc)) from exc
    return context


def make_client_tls_context(cafile) -> ssl.SSLContext:
    cafile = Path(cafile)
    if not cafile.is_file():
        raise RemoteWorkerError("client CA file is missing: " + str(cafile))
    try:
        context = ssl.create_default_context(cafile=str(cafile))
    except (OSError, ssl.SSLError) as exc:
        raise RemoteWorkerError("could not load the client CA file: " + str(exc)) from exc
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    return context


def _split_https_url(url):
    text = str(url or "").strip().rstrip("/")
    parts = urlsplit(text)
    if parts.scheme != "https":
        raise RemoteWorkerError(
            "the coordinator URL must be https:// (there is no plaintext fallback)"
        )
    if not parts.hostname:
        raise RemoteWorkerError("the coordinator URL has no host")
    if parts.path not in ("", "/"):
        raise RemoteWorkerError("the coordinator URL must not include a path")
    try:
        port = parts.port or 443
    except ValueError as exc:
        raise RemoteWorkerError("the coordinator URL has an invalid port") from exc
    return parts.hostname, int(port)


# -- request validation ------------------------------------------------------


def _job_id(value) -> str:
    text = str(value or "")
    if not HEX_ID_RE.match(text):
        raise RemoteWorkerError("job id must be 32 lowercase hexadecimal characters")
    return text


def _relative_path(value, *, label) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RemoteWorkerError(label + " must be a non-empty repo-relative path")
    path = Path(value)
    if path.is_absolute() or path.drive or path.root or ".." in path.parts:
        raise RemoteWorkerError(label + " must be repo-relative without '..'")
    return path.as_posix()


def _validate_job_request(request) -> dict:
    """Validate a submitted job shape; only allowlisted ids, never commands."""
    if not isinstance(request, dict):
        raise RemoteWorkerError("job request must be a JSON object")
    has_toolpack = "toolpack" in request or "action" in request
    has_probe = "probe" in request
    if has_toolpack and has_probe:
        raise RemoteWorkerError("job request must name either a toolpack action or a probe")
    if has_toolpack:
        allowed = {"toolpack", "action", "timeoutSeconds", "idempotencyKey"}
        unknown = sorted(set(request) - allowed)
        if unknown:
            raise RemoteWorkerError(
                "job request has keys that are not allowed: " + ", ".join(unknown)
                + " (argv/cwd/shell/env are never accepted)"
            )
        toolpack = request.get("toolpack")
        action = request.get("action")
        if not isinstance(toolpack, str) or not isinstance(action, str):
            raise RemoteWorkerError("toolpack and action must be strings")
        if (toolpack, action) not in ALLOWED_TOOLPACK_ACTIONS:
            raise RemoteWorkerError(
                "toolpack action " + repr((toolpack, action)) + " is not allowlisted"
            )
        return {"toolpack": toolpack, "action": action}
    if has_probe:
        allowed = {"probe", "timeoutSeconds", "idempotencyKey"}
        unknown = sorted(set(request) - allowed)
        if unknown:
            raise RemoteWorkerError(
                "job request has keys that are not allowed: " + ", ".join(unknown)
                + " (argv/cwd/shell/env are never accepted)"
            )
        probe = request.get("probe")
        if not isinstance(probe, str) or probe not in ALLOWED_PROBES:
            raise RemoteWorkerError("probe " + repr(probe) + " is not allowlisted")
        return {"probe": probe}
    raise RemoteWorkerError(
        "job request must be {\"toolpack\": ..., \"action\": ...} or {\"probe\": ...}"
    )


def _validate_completion(payload, *, max_bytes) -> dict:
    if not isinstance(payload, dict):
        raise RemoteWorkerError("completion payload must be a JSON object")
    allowed = {"passed", "result", "artifacts", "error", "worker"}
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise RemoteWorkerError("completion payload has unknown keys: " + ", ".join(unknown))
    passed = payload.get("passed")
    if not isinstance(passed, bool):
        raise RemoteWorkerError("completion passed must be true or false")
    result = payload.get("result")
    if result is None:
        result = {}
    if not isinstance(result, dict):
        raise RemoteWorkerError("completion result must be a JSON object")
    artifacts = payload.get("artifacts")
    if artifacts is None:
        artifacts = []
    if not isinstance(artifacts, list):
        raise RemoteWorkerError("completion artifacts must be a list")
    clean_artifacts = []
    for index, artifact in enumerate(artifacts):
        label = "artifacts[" + str(index) + "]"
        if not isinstance(artifact, dict):
            raise RemoteWorkerError(label + " must be an object")
        unknown_artifact = sorted(set(artifact) - {"path", "sha256", "bytes"})
        if unknown_artifact:
            raise RemoteWorkerError(label + " has unknown keys: " + ", ".join(unknown_artifact))
        path = _relative_path(artifact.get("path"), label=label + ".path")
        digest = artifact.get("sha256")
        if not isinstance(digest, str) or not HEX_SHA_RE.match(digest):
            raise RemoteWorkerError(label + ".sha256 must be 64 lowercase hex characters")
        size = artifact.get("bytes")
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise RemoteWorkerError(label + ".bytes must be an integer >= 0")
        clean_artifacts.append({"path": path, "sha256": digest, "bytes": size})
    error = payload.get("error")
    if error is not None:
        if not isinstance(error, str):
            raise RemoteWorkerError("completion error must be a string or null")
        error = error[:2000]
    try:
        encoded = json.dumps(
            {"passed": passed, "result": result, "artifacts": clean_artifacts, "error": error},
            ensure_ascii=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise RemoteWorkerError("completion payload is not JSON-serialisable: " + str(exc))
    if len(encoded) > max_bytes:
        raise RemoteWorkerError("completion payload exceeds the " + str(max_bytes) + " byte limit")
    return {
        "passed": passed,
        "result": result,
        "artifacts": clean_artifacts,
        "error": error,
    }


# -- coordinator -------------------------------------------------------------


class _JobError(Exception):
    def __init__(self, message, *, status=400, code=None):
        super().__init__(message)
        self.status = status
        self.code = code


class RemoteWorkerCoordinator:
    """A TLS-only, token-authenticated coordinator for allowlisted read-only jobs."""

    def __init__(
        self,
        repo_root,
        *,
        token,
        certfile,
        keyfile,
        host=DEFAULT_HOST,
        port=DEFAULT_PORT,
        default_timeout=DEFAULT_JOB_TIMEOUT,
        max_job_timeout=MAX_JOB_TIMEOUT,
        max_request_bytes=MAX_REQUEST_BYTES,
        verbose=False,
    ):
        self.repo_root = Path(repo_root).resolve()
        self.token = validate_token(token)
        self.host = str(host or DEFAULT_HOST)
        self.port = int(port)
        if not 0 <= self.port <= 65535:
            raise RemoteWorkerError("port must be between 0 and 65535")
        if not is_loopback(self.host):
            raise RemoteWorkerError(
                "refusing to bind " + self.host + ": the worker coordinator is loopback-only"
            )
        self.default_timeout = float(default_timeout)
        if not MIN_JOB_TIMEOUT <= self.default_timeout <= float(max_job_timeout):
            raise RemoteWorkerError("default_timeout is outside the allowed range")
        self.max_job_timeout = float(max_job_timeout)
        self.max_request_bytes = max(1024, int(max_request_bytes))
        self.verbose = bool(verbose)
        self._server_context = make_server_tls_context(certfile, keyfile)
        self._lock = threading.Lock()
        self._jobs = {}
        self._idempotency = {}
        self._httpd = None
        self._thread = None
        self.bound_host = None
        self.bound_port = None

    # -- lifecycle -----------------------------------------------------
    def start(self):
        if self._httpd is not None:
            return self
        handler = _handler_for(self)
        coordinator = self

        class _Server(ThreadingHTTPServer):
            daemon_threads = True
            allow_reuse_address = True

            def handle_error(self, request, client_address):
                # TLS handshake failures and dropped clients are client errors, not crashes.
                return

        try:
            self._httpd = _Server((self.host, self.port), handler)
            self._httpd.socket = self._server_context.wrap_socket(
                self._httpd.socket, server_side=True
            )
        except (OSError, ssl.SSLError) as exc:
            raise RemoteWorkerError("could not start the coordinator: " + str(exc)) from exc
        self.bound_host, self.bound_port = self._httpd.server_address[:2]
        self._thread = threading.Thread(
            target=self._httpd.serve_forever,
            name="gypsy-remote-worker-coordinator",
            daemon=True,
        )
        self._thread.start()
        return self

    @property
    def url(self) -> str:
        if self._httpd is None:
            raise RemoteWorkerError("coordinator has not started")
        return "https://" + str(self.bound_host) + ":" + str(self.bound_port)

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

    def __enter__(self):
        return self.start()

    def __exit__(self, exc_type, exc, tb):
        self.stop()
        return False

    def status(self) -> dict:
        with self._lock:
            self._sweep()
            counts = {}
            for job in self._jobs.values():
                counts[job["state"]] = counts.get(job["state"], 0) + 1
            return {
                "schema": SCHEMA,
                "status": "ok",
                "url": self.url,
                "host": self.bound_host,
                "port": self.bound_port,
                "loopback": is_loopback(str(self.bound_host)),
                "tls": "required",
                "auth": "bearer",
                "jobs": counts,
                "allowlist": {
                    "toolpackActions": sorted(
                        [list(pair) for pair in ALLOWED_TOOLPACK_ACTIONS]
                    ),
                    "probes": sorted(ALLOWED_PROBES),
                },
            }

    # -- helpers -------------------------------------------------------
    def _sweep(self):
        now = time.time()
        for job in self._jobs.values():
            if job["state"] in ("queued", "claimed") and now >= job["expiresAtEpoch"]:
                job["state"] = "expired"
                job["error"] = "job expired before completion"
                job["updatedAt"] = utc_now_iso()

    def _get_locked(self, job_id):
        job = self._jobs.get(job_id)
        if job is None:
            raise _JobError("unknown job " + repr(job_id), status=404, code="unknown_job")
        return job

    def _public(self, job) -> dict:
        return {
            "schema": JOB_SCHEMA,
            "id": job["id"],
            "kind": job["kind"],
            "request": dict(job["request"]),
            "state": job["state"],
            "createdAt": job["createdAt"],
            "updatedAt": job["updatedAt"],
            "expiresAt": job["expiresAt"],
            "timeoutSeconds": job["timeoutSeconds"],
            "claimedBy": job["claimedBy"],
            "claimedAt": job["claimedAt"],
            "completedAt": job["completedAt"],
            "result": job["result"],
            "error": job["error"],
        }

    # -- job operations (called by the HTTP handler) -------------------
    def submit(self, payload) -> tuple:
        try:
            request = _validate_job_request(payload)
            idempotency_key = payload.get("idempotencyKey")
            if idempotency_key is not None:
                if (
                    not isinstance(idempotency_key, str)
                    or not 1 <= len(idempotency_key) <= 128
                ):
                    raise RemoteWorkerError(
                        "idempotencyKey must be a string of 1..128 characters"
                    )
            timeout = payload.get("timeoutSeconds")
            if timeout is None:
                timeout = self.default_timeout
            if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
                raise RemoteWorkerError("timeoutSeconds must be a number")
            timeout = float(timeout)
            if not MIN_JOB_TIMEOUT <= timeout <= self.max_job_timeout:
                raise RemoteWorkerError(
                    "timeoutSeconds must be between "
                    + str(int(MIN_JOB_TIMEOUT))
                    + " and "
                    + str(int(self.max_job_timeout))
                )
        except RemoteWorkerError as exc:
            raise _JobError(str(exc), status=400, code="invalid_job") from exc

        with self._lock:
            self._sweep()
            if idempotency_key is not None:
                existing_id = self._idempotency.get(idempotency_key)
                if existing_id is not None and existing_id in self._jobs:
                    return 200, {
                        "job": self._public(self._jobs[existing_id]),
                        "idempotent": True,
                    }
            now = time.time()
            job = {
                "id": uuid.uuid4().hex,
                "kind": "toolpack" if "toolpack" in request else "probe",
                "request": request,
                "state": "queued",
                "createdAt": utc_now_iso(),
                "updatedAt": utc_now_iso(),
                "expiresAtEpoch": now + timeout,
                "expiresAt": utc_now_iso(),
                "timeoutSeconds": timeout,
                "claimedBy": None,
                "claimedAt": None,
                "completedAt": None,
                "result": None,
                "error": None,
            }
            job["expiresAt"] = datetime.fromtimestamp(
                job["expiresAtEpoch"], tz=timezone.utc
            ).astimezone().isoformat(timespec="seconds")
            self._jobs[job["id"]] = job
            if idempotency_key is not None:
                self._idempotency[idempotency_key] = job["id"]
            return 201, {"job": self._public(job)}

    def claim(self, payload) -> tuple:
        worker = (payload or {}).get("worker") if isinstance(payload, dict) else None
        if worker is not None and (
            not isinstance(worker, str) or not worker.strip() or len(worker) > 64
        ):
            raise _JobError("worker must be a string of 1..64 characters", status=400)
        with self._lock:
            self._sweep()
            queued = [
                job for job in self._jobs.values() if job["state"] == "queued"
            ]
            queued.sort(key=lambda job: (job["createdAt"], job["id"]))
            if not queued:
                return 200, {"job": None}
            job = queued[0]
            job["state"] = "claimed"
            job["claimedBy"] = worker or "worker"
            job["claimedAt"] = utc_now_iso()
            job["updatedAt"] = utc_now_iso()
            return 200, {"job": self._public(job)}

    def get_job(self, job_id) -> tuple:
        try:
            job_id = _job_id(job_id)
        except RemoteWorkerError as exc:
            raise _JobError(str(exc), status=400) from exc
        with self._lock:
            self._sweep()
            return 200, {"job": self._public(self._get_locked(job_id))}

    def list_jobs(self) -> tuple:
        with self._lock:
            self._sweep()
            jobs = sorted(self._jobs.values(), key=lambda job: job["createdAt"])
            counts = {}
            for job in jobs:
                counts[job["state"]] = counts.get(job["state"], 0) + 1
            return 200, {
                "schema": SCHEMA,
                "jobs": [self._public(job) for job in jobs],
                "counts": counts,
            }

    def complete(self, job_id, payload) -> tuple:
        try:
            job_id = _job_id(job_id)
        except RemoteWorkerError as exc:
            raise _JobError(str(exc), status=400) from exc
        try:
            clean = _validate_completion(payload, max_bytes=self.max_request_bytes)
        except RemoteWorkerError as exc:
            raise _JobError(str(exc), status=400, code="invalid_completion") from exc
        with self._lock:
            self._sweep()
            job = self._get_locked(job_id)
            if job["state"] in ("completed", "failed"):
                return 200, {"job": self._public(job), "idempotent": True}
            if job["state"] == "cancelled":
                raise _JobError(
                    "job was cancelled; completion is rejected",
                    status=409,
                    code="cancelled",
                )
            if job["state"] == "expired":
                raise _JobError(
                    "job expired; completion is rejected",
                    status=409,
                    code="expired",
                )
            if job["state"] != "claimed":
                raise _JobError(
                    "job is " + job["state"] + "; it must be claimed before completion",
                    status=409,
                    code="not_claimed",
                )
            job["state"] = "completed" if clean["passed"] else "failed"
            job["result"] = {
                "passed": clean["passed"],
                "result": clean["result"],
                "artifacts": clean["artifacts"],
                "error": clean["error"],
            }
            job["error"] = None if clean["passed"] else (clean["error"] or "job failed")
            job["completedAt"] = utc_now_iso()
            job["updatedAt"] = job["completedAt"]
            return 200, {"job": self._public(job)}

    def cancel(self, job_id) -> tuple:
        try:
            job_id = _job_id(job_id)
        except RemoteWorkerError as exc:
            raise _JobError(str(exc), status=400) from exc
        with self._lock:
            self._sweep()
            job = self._get_locked(job_id)
            if job["state"] == "cancelled":
                return 200, {"job": self._public(job), "idempotent": True}
            if job["state"] in ("completed", "failed", "expired"):
                raise _JobError(
                    "job is " + job["state"] + "; it cannot be cancelled",
                    status=409,
                    code="terminal_state",
                )
            job["state"] = "cancelled"
            job["error"] = "cancelled by the coordinator"
            job["updatedAt"] = utc_now_iso()
            return 200, {"job": self._public(job)}


def _handler_for(coordinator: RemoteWorkerCoordinator):
    class CoordinatorHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, format, *args):  # noqa: A002 - stdlib signature
            if coordinator.verbose:
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

        def _error(self, code, message, *, error_code=None):
            self.close_connection = True
            payload = {"error": message}
            if error_code:
                payload["code"] = error_code
            self._send_json(code, payload)

        def _authorized(self) -> bool:
            header = self.headers.get("Authorization", "")
            if not header.startswith("Bearer "):
                return False
            provided = header[len("Bearer "):].strip()
            return bool(provided) and hmac.compare_digest(provided, coordinator.token)

        def _read_json(self, limit: int):
            if self.headers.get("Transfer-Encoding"):
                self._error(411, "Content-Length is required; chunked bodies are refused")
                return None, False
            raw_length = self.headers.get("Content-Length")
            if raw_length is None:
                self._error(411, "Content-Length is required")
                return None, False
            try:
                length = int(raw_length)
            except (TypeError, ValueError):
                self._error(400, "Content-Length must be an integer")
                return None, False
            if length < 0:
                self._error(400, "Content-Length must not be negative")
                return None, False
            if length > limit:
                self._error(413, "request body exceeds the " + str(limit) + " byte limit")
                return None, False
            data = self.rfile.read(length)
            if len(data) != length:
                self._error(400, "request body was shorter than Content-Length")
                return None, False
            if not data:
                return {}, True
            try:
                payload = json.loads(data.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                self._error(400, "request body must be valid JSON")
                return None, False
            if not isinstance(payload, dict):
                self._error(400, "request body must be a JSON object")
                return None, False
            return payload, True

        def _path(self) -> str:
            return urlsplit(self.path).path.rstrip("/") or "/"

        def _guard(self) -> bool:
            if not self._authorized():
                self._error(401, "a valid bearer token is required")
                return False
            return True

        # -- GET -------------------------------------------------------
        def do_GET(self):
            if not self._guard():
                return
            path = self._path()
            if path == "/v1/health":
                self._send_json(200, coordinator.status())
                return
            if path == "/v1/jobs":
                code, payload = coordinator.list_jobs()
                self._send_json(code, payload)
                return
            parts = path.split("/")
            if len(parts) == 4 and parts[1] == "v1" and parts[2] == "jobs":
                try:
                    code, payload = coordinator.get_job(parts[3])
                except _JobError as exc:
                    self._error(exc.status, str(exc), error_code=exc.code)
                else:
                    self._send_json(code, payload)
                return
            self._error(404, "not found")

        # -- POST ------------------------------------------------------
        def do_POST(self):
            if not self._guard():
                return
            path = self._path()
            payload, ok = self._read_json(coordinator.max_request_bytes)
            if not ok:
                return
            try:
                if path == "/v1/jobs":
                    code, response = coordinator.submit(payload)
                elif path == "/v1/jobs/claim":
                    code, response = coordinator.claim(payload)
                else:
                    parts = path.split("/")
                    if (
                        len(parts) == 5
                        and parts[1] == "v1"
                        and parts[2] == "jobs"
                        and parts[4] == "complete"
                    ):
                        code, response = coordinator.complete(parts[3], payload)
                    elif (
                        len(parts) == 5
                        and parts[1] == "v1"
                        and parts[2] == "jobs"
                        and parts[4] == "cancel"
                    ):
                        code, response = coordinator.cancel(parts[3])
                    else:
                        self._error(404, "not found")
                        return
            except _JobError as exc:
                self._error(exc.status, str(exc), error_code=exc.code)
                return
            self._send_json(code, response)

        def do_PUT(self):
            self._error(405, "method not allowed")

        def do_DELETE(self):
            self._error(405, "method not allowed")

        def do_PATCH(self):
            self._error(405, "method not allowed")

    return CoordinatorHandler


# -- client ------------------------------------------------------------------


class RemoteWorkerClient:
    """A TLS-verifying, token-authenticated client for the coordinator."""

    def __init__(self, url, token, cafile, *, timeout=30.0, max_response_bytes=MAX_RESPONSE_BYTES):
        self.host, self.port = _split_https_url(url)
        self.url = "https://" + self.host + ":" + str(self.port)
        self.token = validate_token(token)
        self.cafile = str(cafile)
        self._context = make_client_tls_context(cafile)
        self.timeout = float(timeout)
        self.max_response_bytes = max(1024, int(max_response_bytes))

    def _request(self, method, path, payload=None):
        body = None
        headers = {
            "Authorization": "Bearer " + self.token,
            "Accept": "application/json",
        }
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        connection = http.client.HTTPSConnection(
            self.host,
            self.port,
            context=self._context,
            timeout=self.timeout,
        )
        try:
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            status = response.status
            data = response.read(self.max_response_bytes + 1)
        except ssl.SSLError as exc:
            raise RemoteWorkerError(
                "TLS certificate verification failed: " + str(exc)
            ) from exc
        except (ConnectionError, OSError, http.client.HTTPException) as exc:
            raise RemoteWorkerError(
                "coordinator unreachable or TLS handshake failed: " + str(exc)
            ) from exc
        finally:
            connection.close()
        if len(data) > self.max_response_bytes:
            raise RemoteWorkerError("coordinator response exceeded the response limit")
        try:
            parsed = json.loads(data.decode("utf-8")) if data else {}
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise RemoteWorkerError("coordinator response was not JSON")
        if status == 401:
            raise RemoteWorkerAuthError("unauthorized: the bearer token was rejected", status=401)
        if status >= 400:
            message = "HTTP " + str(status)
            code = None
            if isinstance(parsed, dict):
                if parsed.get("error"):
                    message += ": " + str(parsed["error"])[:300]
                code = parsed.get("code")
            raise RemoteWorkerError(message, status=status, code=code)
        if not isinstance(parsed, dict):
            raise RemoteWorkerError("coordinator response was not a JSON object")
        return parsed

    def health(self) -> dict:
        return self._request("GET", "/v1/health")

    def submit(
        self,
        *,
        toolpack=None,
        action=None,
        probe=None,
        timeout_seconds=None,
        idempotency_key=None,
    ) -> dict:
        payload = {}
        if probe is not None:
            payload["probe"] = probe
        else:
            payload["toolpack"] = toolpack
            payload["action"] = action
        if timeout_seconds is not None:
            payload["timeoutSeconds"] = timeout_seconds
        if idempotency_key is not None:
            payload["idempotencyKey"] = idempotency_key
        return self._request("POST", "/v1/jobs", payload)

    def claim(self, worker=None) -> dict:
        payload = {"worker": worker} if worker is not None else {}
        response = self._request("POST", "/v1/jobs/claim", payload)
        return response.get("job")

    def complete(self, job_id, *, passed, result=None, artifacts=None, error=None) -> dict:
        payload = {
            "passed": passed,
            "result": result or {},
            "artifacts": artifacts or [],
            "error": error,
        }
        return self._request(
            "POST", "/v1/jobs/" + _job_id(job_id) + "/complete", payload
        )

    def cancel(self, job_id) -> dict:
        return self._request("POST", "/v1/jobs/" + _job_id(job_id) + "/cancel", {})

    def get_job(self, job_id) -> dict:
        response = self._request("GET", "/v1/jobs/" + _job_id(job_id))
        return response.get("job")

    def list_jobs(self) -> dict:
        return self._request("GET", "/v1/jobs")


# -- worker ------------------------------------------------------------------


class RemoteWorker:
    """Claims allowlisted jobs, runs them in an isolated git worktree, reports hashes."""

    def __init__(
        self,
        repo_root,
        client: RemoteWorkerClient,
        *,
        worker_name=None,
        keep_worktree=False,
        runner=None,
        max_runtime=None,
    ):
        self.repo_root = Path(repo_root).resolve()
        self.client = client
        self.worker_name = worker_name or ("worker-" + str(os.getpid()))
        self.keep_worktree = bool(keep_worktree)
        self.runner = runner
        self.max_runtime = None if max_runtime is None else max(0.05, float(max_runtime))

    # -- execution -----------------------------------------------------
    def run_once(self):
        """Claim at most one job, run it, report the result. Returns a status dict."""
        job = self.client.claim(worker=self.worker_name)
        if job is None:
            return {"claimed": False, "job": None}
        timeout_seconds = float(job.get("timeoutSeconds") or DEFAULT_JOB_TIMEOUT)
        if self.max_runtime is not None:
            timeout_seconds = min(timeout_seconds, self.max_runtime)
        try:
            result = self._execute(job, timeout_seconds)
        except Exception as exc:  # a worker failure becomes a failed job, not a crash
            result = {
                "passed": False,
                "result": {},
                "artifacts": [],
                "error": type(exc).__name__ + ": " + str(exc),
            }
        try:
            current = self.client.get_job(job["id"])
        except RemoteWorkerError:
            current = {"state": "unknown"}
        if current.get("state") == "cancelled":
            return {
                "claimed": True,
                "cancelled": True,
                "job": current,
                "result": result,
            }
        try:
            completed = self.client.complete(
                job["id"],
                passed=bool(result.get("passed")),
                result=result.get("result") or {},
                artifacts=result.get("artifacts") or [],
                error=result.get("error"),
            )
        except RemoteWorkerError as exc:
            return {
                "claimed": True,
                "completed": False,
                "job": current,
                "result": result,
                "error": str(exc),
            }
        return {
            "claimed": True,
            "completed": True,
            "job": completed.get("job", completed),
            "result": result,
        }

    def _validate_job(self, job) -> dict:
        request = job.get("request")
        canonical = _validate_job_request(request)
        if job.get("kind") == "probe" and "probe" not in canonical:
            raise RemoteWorkerError("job kind/request mismatch")
        if job.get("kind") == "toolpack" and "toolpack" not in canonical:
            raise RemoteWorkerError("job kind/request mismatch")
        return canonical

    def _execute(self, job, timeout_seconds) -> dict:
        request = self._validate_job(job)
        started = time.time()
        self._remaining_timeout = float(timeout_seconds)
        temp_root = Path(tempfile.mkdtemp(prefix="gypsy-remote-worker-"))
        worktree = None
        try:
            if "toolpack" in request:
                worktree = self._create_worktree(temp_root)
                state_dir = temp_root / "state"
                return self._run_with_deadline(
                    lambda: self._run_toolpack(request, worktree, state_dir),
                    timeout_seconds,
                )
            state_dir = temp_root / "state"
            return self._run_with_deadline(
                lambda: self._run_probe(request, state_dir),
                timeout_seconds,
            )
        finally:
            self._cleanup(worktree, temp_root)
            duration = round(time.time() - started, 3)
            # duration is attached by the caller-visible result path below when present
            self.last_duration = duration

    @staticmethod
    def _clean_git_env():
        """Remove hook/ambient Git overrides so worktree commands target the repo normally."""
        return {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}


    def _create_worktree(self, temp_root: Path) -> Path:
        target = temp_root / "worktree"
        command = ["git", "worktree", "add", "--detach", str(target), "HEAD"]
        last_error = ""
        for attempt in range(3):
            try:
                completed = subprocess.run(
                    command,
                    cwd=str(self.repo_root),
                    env=self._clean_git_env(),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=120,
                    shell=False,
                )
            except (OSError, subprocess.SubprocessError) as exc:
                raise RemoteWorkerError("could not create the isolated worktree: " + str(exc))
            if completed.returncode == 0:
                return target
            last_error = (completed.stderr or completed.stdout or "").strip()[:500]
            # Git worktree creation can race a concurrent prune/index update. Retry
            # transient lock/path errors; do not hide deterministic failures.
            lowered = last_error.lower()
            if "index.lock" not in lowered and "no such file or directory" not in lowered:
                break
            time.sleep(0.15 * (attempt + 1))
        raise RemoteWorkerError("could not create the isolated worktree: " + last_error)

    def _cleanup(self, worktree, temp_root: Path) -> None:
        if worktree is not None:
            for command in (
                ["git", "worktree", "remove", "--force", str(worktree)],
                ["git", "worktree", "prune"],
            ):
                try:
                    subprocess.run(
                        command,
                        cwd=str(self.repo_root),
                        env=self._clean_git_env(),
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        timeout=120,
                        shell=False,
                    )
                except (OSError, subprocess.SubprocessError):
                    pass
        if self.keep_worktree:
            return
        for _ in range(3):
            shutil.rmtree(temp_root, ignore_errors=True)
            if not temp_root.exists():
                return
            time.sleep(0.1)

    def _run_with_deadline(self, func, timeout: float) -> dict:
        box = {}

        def target():
            try:
                box["value"] = func()
            except BaseException as exc:  # forwarded to the caller thread
                box["error"] = exc

        thread = threading.Thread(target=target, daemon=True)
        thread.start()
        thread.join(timeout=max(0.05, float(timeout)))
        if thread.is_alive():
            return {
                "passed": False,
                "timedOut": True,
                "result": {},
                "artifacts": [],
                "error": "worker timeout after " + format(timeout, "g") + "s",
            }
        if "error" in box:
            raise box["error"]
        value = box.get("value")
        if not isinstance(value, dict):
            return {
                "passed": False,
                "result": {},
                "artifacts": [],
                "error": "worker runner returned no result",
            }
        return value

    def _run_toolpack(self, request, worktree: Path, state_dir: Path) -> dict:
        if self.runner is not None:
            return self.runner(request, worktree, state_dir)
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import toolpacks  # noqa: PLC0415 - lazy so the module imports without toolpacks

        toolpack_id = request["toolpack"]
        action_id = request["action"]
        manifest_path = worktree / "toolpacks" / (toolpack_id + ".json")
        if not manifest_path.is_file():
            raise RemoteWorkerError("toolpack manifest is missing from the worktree")
        manifest = toolpacks.load_manifest(manifest_path)
        errors = toolpacks.validate_manifest(manifest)
        if errors:
            raise RemoteWorkerError("toolpack manifest is invalid: " + "; ".join(errors))
        action = None
        for candidate in manifest["actions"]:
            if candidate.get("id") == action_id:
                action = candidate
                break
        if action is None:
            raise RemoteWorkerError(
                "toolpack " + repr(toolpack_id) + " has no action " + repr(action_id)
            )
        if (toolpack_id, action_id) not in ALLOWED_TOOLPACK_ACTIONS:
            raise RemoteWorkerError("toolpack action is not allowlisted")
        action_timeout = float(action.get("timeout") or toolpacks.DEFAULT_TIMEOUT)
        scale = min(1.0, max(0.01, float(self._remaining_timeout) / action_timeout)) if getattr(self, "_remaining_timeout", None) else 1.0
        result = toolpacks.run_action(
            manifest,
            action_id,
            project_root=worktree,
            state_dir=state_dir,
            timeout_scale=scale,
        )
        artifacts = [
            {
                "path": entry["path"],
                "sha256": entry["sha256"],
                "bytes": entry["bytes"],
            }
            for entry in result.get("artifacts") or []
            if entry.get("exists")
        ]
        safe = {
            "toolpack": toolpack_id,
            "action": action_id,
            "passed": bool(result.get("passed")),
            "exit": result.get("exit"),
            "seconds": result.get("seconds"),
            "timedOut": bool(result.get("timedOut")),
            "errors": list(result.get("errors") or []),
            "validators": [
                {
                    "id": validator.get("id"),
                    "artifact": validator.get("artifact"),
                    "target": validator.get("target"),
                    "passed": validator.get("passed"),
                    "error": validator.get("error"),
                }
                for validator in result.get("validators") or []
            ],
        }
        return {
            "passed": bool(result.get("passed")),
            "result": safe,
            "artifacts": artifacts,
            "error": (result.get("errors") or [None])[0],
        }

    def _run_probe(self, request, state_dir: Path) -> dict:
        if self.runner is not None:
            return self.runner(request, None, state_dir)
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import gypsy  # noqa: PLC0415 - lazy

        probe_id = request["probe"]
        if probe_id not in ALLOWED_PROBES:
            raise RemoteWorkerError("probe is not allowlisted")
        evidence = gypsy.probe_engines()
        record = (evidence.get("engines") or {}).get(probe_id)
        return {
            "passed": isinstance(record, dict),
            "result": {
                "probe": probe_id,
                "engine": record,
                "machine": evidence.get("machine"),
            },
            "artifacts": [],
            "error": None if isinstance(record, dict) else "probe produced no result",
        }


def main(argv=None) -> int:
    """Small module smoke entry point (the CLI is deliberately not wired in gypsy.py)."""
    parser = __import__("argparse").ArgumentParser(
        description="TLS remote worker coordinator (loopback, allowlisted read-only jobs)"
    )
    parser.add_argument("--cert", required=True)
    parser.add_argument("--key", required=True)
    parser.add_argument("--token-env", default="GYPSY_REMOTE_WORKER_TOKEN")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--repo", default=".")
    args = parser.parse_args(argv)
    token = os.environ.get(args.token_env, "")
    if not token:
        print("ERROR: " + args.token_env + " must be set", file=sys.stderr)
        return 1
    try:
        coordinator = RemoteWorkerCoordinator(
            Path(args.repo),
            token=token,
            certfile=args.cert,
            keyfile=args.key,
            host=args.host,
            port=args.port,
        ).start()
    except RemoteWorkerError as exc:
        print("ERROR: " + str(exc), file=sys.stderr)
        return 1
    print("remote worker coordinator listening on " + coordinator.url + " (TLS required)")
    try:
        coordinator.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        coordinator.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
