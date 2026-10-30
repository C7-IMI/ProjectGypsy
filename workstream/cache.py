#!/usr/bin/env python3
"""Content-addressed action cache and bounded parallel scheduler for Gypsy Studio.

Two reusable pieces for the runners in orchestrator.py and toolpacks.py:

1. A local, content-addressed action cache under <state_dir>/cache (gitignored):
   descriptors keyed on manifest/action identity, argv/args, cwd, platform, tool versions,
   declared artifact paths and SHA-256 input hashes. Entries store artifact bytes in
   content-addressed blobs (SHA-256) and a small JSON entry. A hit restores the declared
   artifacts atomically; a failure or timeout is never cached.
   Opt-in only: an action caches only when its manifest/step declares a cache object:

       "cache": {
         "enabled": true,
         "inputs": ["assets/source.txt"],
         "artifacts": ["artifacts/out.bin"],
         "toolVersions": {"blender": "5.2.3"}
       }

   inputs and artifacts are explicit repo-relative paths; artifacts may not use globs
   because a cache must restore exact files. enabled defaults to true; the runner's
   --no-cache switch disables the cache for a whole run and --force bypasses a lookup.

2. A bounded parallel scheduler (run_parallel) used for opt-in parallel slices and
   toolpack actions. It preserves input ordering, caps workers (MAX_WORKERS), and cancels
   not-yet-started items after the first failure; already-running items finish.

This module is standard library only, opens no network connection and writes only under
the cache directory.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import tempfile
import threading
import time
import uuid
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

SCHEMA = "gypsy.cache/v1"
ENTRY_SCHEMA = "gypsy.cache-entry/v1"
STATS_SCHEMA = "gypsy.cache-stats/v1"
KEY_SCHEMA = "gypsy.cache-key/v1"
CONFIG_KEYS = frozenset({"enabled", "inputs", "artifacts", "toolVersions"})
MAX_WORKERS = 8
OUTPUT_LIMIT = 4000
GLOB_CHARS = frozenset("*?[")


class CacheError(ValueError):
    """A cache configuration or path is invalid, or the cache cannot be read/written."""


# -- small helpers -----------------------------------------------------------


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def _clip(text, limit: int = OUTPUT_LIMIT) -> str:
    if not text:
        return ""
    value = str(text)
    if len(value) <= limit:
        return value
    return "...[truncated]...\n" + value[-limit:]


def _atomic_write_bytes(path: Path, data: bytes) -> None:
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


def _atomic_write_json(path: Path, payload) -> None:
    _atomic_write_bytes(path, json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8") + b"\n")


def _relative_error(value, *, label: str, allow_glob: bool = False):
    if not isinstance(value, str) or not value.strip():
        return f"{label} must be a non-empty repo-relative path string"
    try:
        path = Path(value)
    except (TypeError, ValueError):
        return f"{label} is not a usable path"
    if path.is_absolute() or path.drive or path.root:
        return f"{label} must be relative, not absolute"
    if ".." in path.parts:
        return f"{label} must not escape with '..'"
    if not allow_glob and any(character in value for character in GLOB_CHARS):
        return f"{label} must name an exact file, not a glob"
    return None


def _safe_target(project_root, relative, *, label: str) -> Path:
    project_root = Path(project_root).expanduser().resolve()
    error = _relative_error(relative, label=label)
    if error:
        raise CacheError(error)
    target = (project_root / Path(relative)).resolve()
    if target != project_root and not target.is_relative_to(project_root):
        raise CacheError(f"{label} resolves outside the project root: {relative!r}")
    return target


# -- cache configuration (opt-in, declarative) -------------------------------


def validate_config(value, *, label: str = "cache") -> list:
    """Return schema errors for an opt-in cache object; empty means valid."""
    if not isinstance(value, dict):
        return [f"{label} must be an object (opt-in), not {type(value).__name__}"]
    errors = []
    unknown = sorted(set(value) - CONFIG_KEYS)
    if unknown:
        errors.append(
            f"{label}: unknown key(s) {', '.join(repr(item) for item in unknown)}; "
            "allowed: " + ", ".join(sorted(CONFIG_KEYS))
        )
    enabled = value.get("enabled", True)
    if not isinstance(enabled, bool):
        errors.append(f"{label}: enabled must be true or false")
    for key in ("inputs", "artifacts"):
        entries = value.get(key)
        if not isinstance(entries, list):
            errors.append(f"{label}: {key} must be a list of repo-relative paths")
            continue
        seen = set()
        for index, entry in enumerate(entries):
            error = _relative_error(
                entry, label=f"{label}: {key}[{index}]", allow_glob=False
            )
            if error:
                errors.append(error)
            elif entry in seen:
                errors.append(f"{label}: {key} repeats {entry!r}")
            else:
                seen.add(entry)
    tool_versions = value.get("toolVersions", {})
    if not isinstance(tool_versions, dict):
        errors.append(f"{label}: toolVersions must be an object of name -> version")
    else:
        for name, version in tool_versions.items():
            if not isinstance(name, str) or not name.strip():
                errors.append(f"{label}: toolVersions names must be non-empty strings")
            if not isinstance(version, str) or not version.strip():
                errors.append(f"{label}: toolVersions[{name!r}] must be a non-empty string")
    return errors


def resolve_config(value, *, project_root, label: str = "cache") -> dict:
    """Validate an opt-in cache object and return its normalised form."""
    errors = validate_config(value, label=label)
    if errors:
        raise CacheError("; ".join(errors))
    project_root = Path(project_root).expanduser().resolve()
    inputs = [Path(entry).as_posix() for entry in value.get("inputs", [])]
    artifacts = [Path(entry).as_posix() for entry in value.get("artifacts", [])]
    for entry in inputs:
        _safe_target(project_root, entry, label=f"{label}: input")
    for entry in artifacts:
        _safe_target(project_root, entry, label=f"{label}: artifact")
    return {
        "enabled": bool(value.get("enabled", True)),
        "inputs": inputs,
        "artifacts": artifacts,
        "toolVersions": {
            str(name): str(version) for name, version in (value.get("toolVersions") or {}).items()
        },
    }


# -- keys and input hashes ---------------------------------------------------


def platform_info() -> dict:
    return {
        "system": platform.system(),
        "machine": platform.machine(),
        "pythonVersion": platform.python_version(),
        "pythonImplementation": platform.python_implementation(),
    }


def input_hashes(project_root, inputs) -> dict:
    """Hash every declared input (missing inputs record exists=false, safely)."""
    project_root = Path(project_root).expanduser().resolve()
    hashes = {}
    for relative in inputs:
        target = _safe_target(project_root, relative, label=f"cache input {relative!r}")
        if target.is_file():
            hashes[Path(relative).as_posix()] = {
                "exists": True,
                "sha256": _sha256_file(target),
                "bytes": target.stat().st_size,
            }
        else:
            hashes[Path(relative).as_posix()] = {
                "exists": False,
                "sha256": None,
                "bytes": None,
            }
    return hashes


def action_key(
    *,
    identity,
    argv,
    cwd,
    inputs,
    artifacts,
    tool_versions=None,
    extra=None,
) -> tuple:
    """Return (key, descriptor) for one cacheable action."""
    descriptor = {
        "schema": KEY_SCHEMA,
        "identity": identity,
        "argv": [str(item) for item in (argv or [])],
        "cwd": str(Path(cwd).resolve()) if cwd else "",
        "platform": platform_info(),
        "toolVersions": dict(tool_versions or {}),
        "inputs": inputs or {},
        "artifacts": [Path(item).as_posix() for item in (artifacts or [])],
    }
    if extra:
        descriptor["extra"] = extra
    key = _sha256_bytes(_canonical(descriptor))
    return key, descriptor


# -- the cache ---------------------------------------------------------------


def _remote_module():
    try:  # imported as workstream.cache
        from . import remote_cache as module
    except ImportError:  # imported with workstream/ on sys.path
        try:
            import remote_cache as module
        except ImportError:
            return None
    return module


def _remote_client_from_env():
    """Build a RemoteCacheClient only when both remote-cache env variables are set."""
    module = _remote_module()
    if module is None:
        return None
    config = module.config_from_env()
    if config is None:
        return None
    try:
        return module.RemoteCacheClient(config["url"], config["token"])
    except module.RemoteCacheError as exc:
        raise CacheError(
            "invalid remote cache configuration: " + str(exc)
        ) from exc


def _safe_url(url):
    if not url:
        return None
    parts = urlsplit(str(url))
    host = parts.hostname or ""
    port = ":" + str(parts.port) if parts.port else ""
    path = parts.path.rstrip("/")
    return parts.scheme + "://" + host + port + path


class ActionCache:
    """A local content-addressed action cache rooted at <state_dir>/cache.

    The local cache is always primary. When remote is given (or both remote-cache env
    variables are set), a local miss falls back to the remote cache and a successful local
    store is pushed best-effort to it. Remote failures never fail a run; they are counted
    and reported honestly in stats(). Pass remote=False to force local-only behaviour.
    """

    def __init__(self, state_dir, *, enabled: bool = True, remote=None):
        self.state_dir = Path(state_dir)
        self.cache_dir = self.state_dir / "cache"
        self.entries_dir = self.cache_dir / "entries"
        self.blobs_dir = self.cache_dir / "blobs"
        self.stats_path = self.cache_dir / "stats.json"
        self.enabled = bool(enabled)
        self._lock = threading.Lock()
        self._last_remote_error = None
        if remote is None:
            self.remote = _remote_client_from_env()
        elif remote is False:
            self.remote = None
        else:
            self.remote = remote
        if self.remote is not None:
            required = ("get_entry", "put_entry", "get_blob", "put_blob", "status")
            if not all(callable(getattr(self.remote, name, None)) for name in required):
                raise CacheError(
                    "remote must provide get_entry/put_entry/get_blob/put_blob/status"
                )

    # -- stats ---------------------------------------------------------
    def _load_stats(self) -> dict:
        default = {
            "schema": STATS_SCHEMA,
            "hits": 0,
            "misses": 0,
            "stores": 0,
            "restores": 0,
            "bytesStored": 0,
            "remoteHits": 0,
            "remoteStores": 0,
            "remoteErrors": 0,
            "lastUpdated": None,
        }
        if not self.stats_path.is_file():
            return default
        try:
            data = json.loads(self.stats_path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return default
        if not isinstance(data, dict) or data.get("schema") != STATS_SCHEMA:
            return default
        for key in (
            "hits",
            "misses",
            "stores",
            "restores",
            "bytesStored",
            "remoteHits",
            "remoteStores",
            "remoteErrors",
        ):
            if not isinstance(data.get(key), int):
                data[key] = default[key]
        return data

    def _bump(self, **deltas) -> None:
        if not self.enabled:
            return
        with self._lock:
            stats = self._load_stats()
            for key, value in deltas.items():
                stats[key] = int(stats.get(key, 0)) + int(value)
            stats["lastUpdated"] = utc_now_iso()
            try:
                _atomic_write_json(self.stats_path, stats)
            except OSError:
                pass  # stats are observability, not a correctness gate

    def counters(self) -> dict:
        stats = self._load_stats()
        return {
            key: int(stats.get(key, 0))
            for key in (
                "hits",
                "misses",
                "stores",
                "restores",
                "bytesStored",
                "remoteHits",
                "remoteStores",
                "remoteErrors",
            )
        }

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
            "cacheDir": str(self.cache_dir),
            "enabled": self.enabled,
            "counters": self.counters(),
            "entries": entries,
            "blobs": blobs,
            "blobBytes": blob_bytes,
            "remote": self.remote_info(),
            "lastUpdated": self._load_stats().get("lastUpdated"),
        }

    def remote_info(self, *, ping=False) -> dict:
        """Token-free description of the remote cache configuration and counters."""
        info = {
            "enabled": self.remote is not None,
            "url": _safe_url(getattr(self.remote, "url", None)),
            "counters": {
                "hits": self.counters()["remoteHits"],
                "stores": self.counters()["remoteStores"],
                "errors": self.counters()["remoteErrors"],
            },
            "lastError": self._last_remote_error,
        }
        if ping and self.remote is not None:
            info["status"] = self.remote.status()
        return info

    def remote_status(self) -> dict:
        """A live (network) status for the CLI; disabled remote returns a reason."""
        if self.remote is None:
            return {
                "enabled": False,
                "reason": "remote cache is not configured (set GYPSY_REMOTE_CACHE_URL and GYPSY_REMOTE_CACHE_TOKEN)",
            }
        status = dict(self.remote.status())
        status["enabled"] = True
        status["url"] = _safe_url(status.get("url") or getattr(self.remote, "url", None))
        return status

    # -- entries -------------------------------------------------------
    def _entry_path(self, key: str) -> Path:
        return self.entries_dir / (key + ".json")

    def _blob_path(self, digest: str) -> Path:
        return self.blobs_dir / digest

    @staticmethod
    def _entry_matches(entry, key) -> bool:
        if (
            not isinstance(entry, dict)
            or entry.get("schema") != ENTRY_SCHEMA
            or entry.get("key") != key
            or not isinstance(entry.get("artifacts"), list)
        ):
            return False
        for artifact in entry["artifacts"]:
            if not isinstance(artifact, dict):
                return False
            digest = artifact.get("sha256")
            if not isinstance(digest, str) or len(digest) != 64:
                return False
            if isinstance(artifact.get("bytes"), bool) or not isinstance(
                artifact.get("bytes"), int
            ):
                return False
        return True

    def _lookup_local(self, key):
        path = self._entry_path(key)
        if not path.is_file():
            return None
        try:
            entry = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return None
        if not self._entry_matches(entry, key):
            return None
        for artifact in entry["artifacts"]:
            digest = artifact["sha256"]
            blob = self._blob_path(digest)
            if not blob.is_file():
                return None
            try:
                if (
                    blob.stat().st_size != artifact["bytes"]
                    or _sha256_file(blob) != digest
                ):
                    return None
            except OSError:
                return None
        return entry

    def _fetch_remote_entry(self, key):
        """Materialise a remote entry and its blobs locally; None on any failure."""
        try:
            entry = self.remote.get_entry(key)
        except Exception as exc:  # remote failures never break a run
            self._last_remote_error = _clip(str(exc), 300)
            self._bump(remoteErrors=1)
            return None
        if entry is None:
            return None
        if not self._entry_matches(entry, key):
            self._last_remote_error = "remote entry failed local validation"
            self._bump(remoteErrors=1)
            return None
        for artifact in entry["artifacts"]:
            digest = artifact["sha256"]
            blob = self._blob_path(digest)
            if blob.is_file():
                try:
                    if (
                        blob.stat().st_size == artifact["bytes"]
                        and _sha256_file(blob) == digest
                    ):
                        continue
                except OSError:
                    pass
            try:
                data = self.remote.get_blob(digest)
            except Exception as exc:
                self._last_remote_error = _clip(str(exc), 300)
                self._bump(remoteErrors=1)
                return None
            if (
                data is None
                or len(data) != artifact["bytes"]
                or _sha256_bytes(data) != digest
            ):
                self._last_remote_error = (
                    "remote blob missing or failed SHA-256 verification"
                )
                self._bump(remoteErrors=1)
                return None
            try:
                _atomic_write_bytes(blob, data)
            except OSError as exc:
                self._last_remote_error = _clip(
                    "could not materialise remote blob: " + str(exc), 300
                )
                self._bump(remoteErrors=1)
                return None
        try:
            _atomic_write_json(self._entry_path(key), entry)
        except OSError as exc:
            self._last_remote_error = _clip(
                "could not store remote entry locally: " + str(exc), 300
            )
            self._bump(remoteErrors=1)
            return None
        return entry

    def lookup(self, key: str):
        """Return a verified entry (local first, then remote), or None; count hit/miss."""
        if not self.enabled:
            return None
        entry = self._lookup_local(key)
        if entry is not None:
            self._bump(hits=1)
            return entry
        if self.remote is not None:
            remote_entry = self._fetch_remote_entry(key)
            if remote_entry is not None:
                self._bump(hits=1, remoteHits=1)
                return remote_entry
        self._bump(misses=1)
        return None

    def store(
        self,
        key: str,
        *,
        descriptor,
        project_root,
        artifacts,
        result=None,
    ):
        """Store an action result; return the entry summary or None when not cacheable."""
        if not self.enabled:
            return None
        project_root = Path(project_root).expanduser().resolve()
        entries = []
        stored_bytes = 0
        for relative in artifacts:
            target = _safe_target(project_root, relative, label=f"cache artifact {relative!r}")
            if not target.is_file():
                return None  # an incomplete result is never cached
            try:
                data = target.read_bytes()
            except OSError:
                return None
            digest = _sha256_bytes(data)
            blob = self._blob_path(digest)
            if not blob.is_file():
                try:
                    _atomic_write_bytes(blob, data)
                except OSError:
                    return None
                stored_bytes += len(data)
            entries.append(
                {"path": Path(relative).as_posix(), "sha256": digest, "bytes": len(data)}
            )
        created = utc_now_iso()
        entry = {
            "schema": ENTRY_SCHEMA,
            "key": key,
            "descriptor": descriptor,
            "createdAt": created,
            "artifacts": entries,
            "result": result or {},
        }
        try:
            _atomic_write_json(self._entry_path(key), entry)
        except OSError:
            return None
        self._bump(stores=1, bytesStored=stored_bytes)
        if self.remote is not None:
            self._push_remote(key, entries)
        return {"key": key, "createdAt": created, "artifacts": entries}

    def _push_remote(self, key: str, artifacts) -> None:
        """Best-effort push of blobs then the entry; failures are counted, not raised."""
        try:
            for artifact in artifacts:
                digest = artifact["sha256"]
                data = self._blob_path(digest).read_bytes()
                self.remote.put_blob(digest, data)
            entry = json.loads(self._entry_path(key).read_text(encoding="utf-8-sig"))
            self.remote.put_entry(key, entry)
        except Exception as exc:
            self._last_remote_error = _clip(str(exc), 300)
            self._bump(remoteErrors=1)
            return
        self._bump(remoteStores=1)

    def restore(self, entry, project_root):
        """Restore an entry's artifacts; return (ok, restored_paths, error)."""
        if not self.enabled:
            return False, [], "cache is disabled"
        project_root = Path(project_root).expanduser().resolve()
        restored = []
        for artifact in entry.get("artifacts") or []:
            if not isinstance(artifact, dict):
                return False, [], "cache entry artifact is malformed"
            relative = artifact.get("path")
            digest = artifact.get("sha256")
            try:
                target = _safe_target(
                    project_root, relative, label=f"cache artifact {relative!r}"
                )
            except CacheError as exc:
                return False, [], str(exc)
            blob = self._blob_path(str(digest))
            try:
                data = blob.read_bytes()
            except OSError:
                return False, [], f"cache blob missing for {relative!r}"
            if _sha256_bytes(data) != digest:
                return False, [], f"cache blob corrupt for {relative!r}"
            try:
                _atomic_write_bytes(target, data)
            except OSError as exc:
                return False, [], f"could not restore {relative!r}: {exc}"
            restored.append(Path(relative).as_posix())
        self._bump(restores=1)
        return True, restored, None

    def entries(self) -> list:
        output = []
        if not self.entries_dir.is_dir():
            return output
        for path in sorted(self.entries_dir.glob("*.json")):
            try:
                entry = json.loads(path.read_text(encoding="utf-8-sig"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                continue
            if not isinstance(entry, dict):
                continue
            artifacts = entry.get("artifacts") or []
            output.append(
                {
                    "key": entry.get("key") or path.stem,
                    "createdAt": entry.get("createdAt"),
                    "artifacts": len(artifacts),
                    "bytes": sum(int(item.get("bytes") or 0) for item in artifacts if isinstance(item, dict)),
                    "identity": (entry.get("descriptor") or {}).get("identity"),
                }
            )
        return output

    def clear(self) -> dict:
        entries = self.stats()["entries"]
        blobs = 0
        blob_bytes = 0
        if self.blobs_dir.is_dir():
            for path in self.blobs_dir.iterdir():
                if path.is_file():
                    blobs += 1
                    try:
                        blob_bytes += path.stat().st_size
                    except OSError:
                        pass
        try:
            if self.cache_dir.exists():
                shutil.rmtree(self.cache_dir)
        except OSError as exc:
            raise CacheError(f"could not clear cache {self.cache_dir}: {exc}") from exc
        return {
            "cleared": True,
            "cacheDir": str(self.cache_dir),
            "entries": entries,
            "blobs": blobs,
            "blobBytes": blob_bytes,
        }


# -- bounded parallel scheduler ---------------------------------------------


def worker_count(value) -> int:
    """Validate and return a worker count in 1..MAX_WORKERS."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise CacheError("max_workers must be an integer between 1 and %d" % MAX_WORKERS)
    if value < 1 or value > MAX_WORKERS:
        raise CacheError(
            "max_workers must be between 1 and %d (bounded worker pool)" % MAX_WORKERS
        )
    return value


def _passed(result) -> bool:
    return isinstance(result, dict) and result.get("passed") is True


def run_parallel(items, worker, *, max_workers=1, cancel_on_failure=True) -> dict:
    """Run worker(index, item) for every item with a bounded pool.

    Results are returned in input order. After the first failed result, not-yet-started
    items are cancelled (already-running work finishes). Cancellation is cooperative and
    pending-only; it is not a process kill.

    Returns {"results": [...ordered, None for cancelled...], "cancelled": bool,
             "cancelledIndices": [...], "workers": N}.
    """
    items = list(items)
    workers = worker_count(max_workers)
    total = len(items)
    results = [None] * total
    cancelled_indices = []
    cancelled = False
    if workers == 1:
        for index, item in enumerate(items):
            if cancelled:
                cancelled_indices.append(index)
                continue
            results[index] = worker(index, item)
            if cancel_on_failure and not _passed(results[index]):
                cancelled = True
        return {
            "results": results,
            "cancelled": cancelled,
            "cancelledIndices": cancelled_indices,
            "workers": 1,
        }

    next_index = 0
    running = {}
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="gypsy-parallel") as pool:
        while next_index < total or running:
            while next_index < total and len(running) < workers and not cancelled:
                future = pool.submit(worker, next_index, items[next_index])
                running[future] = next_index
                next_index += 1
            if not running:
                break
            done, _ = wait(running, return_when=FIRST_COMPLETED)
            for future in done:
                index = running.pop(future)
                results[index] = future.result()
                if cancel_on_failure and not _passed(results[index]):
                    cancelled = True
    for index in range(total):
        if results[index] is None:
            cancelled_indices.append(index)
    return {
        "results": results,
        "cancelled": cancelled,
        "cancelledIndices": cancelled_indices,
        "workers": workers,
    }


def counters_delta(before: dict, after: dict) -> dict:
    """Difference between two counters() snapshots (used in state JSON)."""
    keys = ("hits", "misses", "stores", "restores", "bytesStored")
    return {key: int(after.get(key, 0)) - int(before.get(key, 0)) for key in keys}
