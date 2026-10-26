#!/usr/bin/env python3
"""Isolated declarative extensions for Gypsy Studio (docs/ADR-003-workstream-architecture.md).

ADR-003 permits a missing capability to be added as an isolated extension, never by editing
the orchestrator core. This module is the safe pipeline for that: it discovers extension
directories, validates their declarative manifest and capability, confines entrypoints and
declared paths to the extension directory, runs fixed argv commands with no shell, applies a
timeout, supports dry-run, and keeps an explicit review/registration gate in a lockfile.

Layout (the default root is extensions/ in this checkout):

    extensions/
      README.md
      gypsy.lock.json                  explicit registration/review record
      example.hello/
        extension.json                 declarative manifest (schema below)
        capability.json                gypsy.capability/v1 manifest for this extension
        run.py                         entrypoint referenced by a fixed argv
        README.md

Manifest schema gypsy.extension/v1:

    {
      "schema": "gypsy.extension/v1",
      "id": "example.hello",           directory name and lowercase id
      "version": "1.0.0",              semantic version pin
      "apiVersion": "1",               extension API version
      "name": "Example hello",
      "description": "one line",
      "license": "MIT",
      "author": "optional",
      "capability": "extension.example.hello",
      "entrypoints": {
        "hello": {
          "description": "print a marker",
          "argv": ["python", "run.py", "--action", "hello"],
          "timeout": 10
        }
      },
      "tests": [
        {"id": "hello-passes", "action": "hello", "expectExit": 0,
         "stdoutContains": "EXTENSION_HELLO_OK"},
        {"id": "fail-is-detected", "action": "fail", "expectExit": "nonzero",
         "stderrContains": "EXTENSION_EXPECTED_FAILURE"}
      ],
      "permissions": {"network": false, "reads": ["."], "writes": []}
    }

Safety rules enforced by this module:

* The extension root may be extensions/ or an out-of-checkout directory; it may never be
  workstream/ or another core directory, and an extension directory is a direct child.
* id equals the directory name. apiVersion is 1; version is semantic.
* capability.json is required, must be gypsy.capability/v1, and its id must equal the
  manifest capability.
* argv is a non-empty JSON list. A shell string is never parsed: commands run with
  shell=False and an explicit list. argv[0] is python (resolved to the running interpreter)
  or a relative executable inside the extension directory. A python entrypoint names a
  relative .py file inside the extension directory.
* Absolute paths, '..' segments, symlinks, shell control operators and shell interpreter
  names are rejected in the manifest. Declared read/write paths must stay inside the
  extension directory.
* The extension is executed with its own directory as cwd, a sanitised environment and
  bytecode writing disabled. Run evidence is written under extensions/.state/ (ignored).
* Execution can be optionally contained by a Windows Job Object (contain=True or
  GYPSY_EXTENSION_CONTAIN=1): kill-on-job-close, an active-process limit and memory limits,
  and a timeout terminates the whole job (process tree). On non-Windows, or when the Job
  Object API is unavailable, the run falls back to uncontained execution and reports the
  containment state honestly. This is resource containment, not a filesystem/network sandbox.
* Every manifest must declare a negative test (expectExit: 'nonzero'). extension test runs
  the declared tests and fails when the negative test unexpectedly succeeds.
* extension register --accept is the review gate: it hashes the whole extension tree and
  writes entries to extensions/gypsy.lock.json. run refuses unregistered, disabled, or
  changed extensions. reload --accept re-reviews changes; disable and remove are the
  reversible off-switch and removal path.

Honest limits: this is a Python-level safety pipeline, not a kernel sandbox. A reviewed
extension is executable code and can still perform any operation its process is allowed to
perform; the containment rules cover manifest paths, entrypoints, cwd and pipeline writes,
not every runtime syscall. Permissions (network and read/write declarations) are review
metadata, not enforced. An extension must not mutate its own registered tree; outputs belong
under GYPSY_EXTENSION_STATE. A plain timeout kills the direct child only; opt-in Job Object
containment additionally terminates the job's process tree on timeout and at job close, with
job resource limits. Containment is not a filesystem/network sandbox and not a security
boundary against code acting within its OS rights. Arbitrary dependency installation and
destructive actions remain explicit operator decisions.

Public API is used by gypsy extension ... in workstream/gypsy.py.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = "gypsy.extension/v1"
API_VERSION = "1"
LOCK_SCHEMA = "gypsy.extension-lock/v1"
CAPABILITY_SCHEMA = "gypsy.capability/v1"
STATE_SCHEMA = "gypsy.extension-state/v1"
DEFAULT_TIMEOUT = 60.0
MAX_TIMEOUT = 300.0
OUTPUT_LIMIT = 4000

CONTAINMENT_ENV = "GYPSY_EXTENSION_CONTAIN"
CONTAINMENT_BACKEND = "windows-job-object"
DEFAULT_CONTAINMENT_LIMITS = {
    "killOnJobClose": True,
    "activeProcessLimit": 8,
    "processMemoryMb": 2048,
    "jobMemoryMb": 4096,
    "cpuSeconds": None,
}

ID_RE = re.compile(r"^[a-z][a-z0-9._-]{0,63}$")
SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$"
)

MANIFEST_KEYS = frozenset(
    {
        "schema",
        "id",
        "version",
        "apiVersion",
        "name",
        "description",
        "license",
        "author",
        "capability",
        "entrypoints",
        "tests",
        "permissions",
    }
)
ENTRYPOINT_KEYS = frozenset({"description", "argv", "timeout"})
TEST_KEYS = frozenset(
    {"id", "action", "expectExit", "stdoutContains", "stderrContains"}
)
PERMISSION_KEYS = frozenset({"network", "reads", "writes"})
CAPABILITY_MATURITY = frozenset({"stable", "partial", "experimental", "planned", "blocked"})
CAPABILITY_KEYS = frozenset(
    {
        "schema",
        "file",
        "tool",
        "id",
        "layer",
        "kind",
        "maturity",
        "description",
        "requires",
        "inputs",
        "outputs",
        "checks",
        "provenance",
    }
)

SHELL_OPERATORS = ("&&", "||", ";", "|", "\x60", "$(", ">", "<", "\0", "\n", "\r")
SHELL_NAMES = frozenset(
    {
        "cmd",
        "cmd.exe",
        "powershell",
        "powershell.exe",
        "pwsh",
        "pwsh.exe",
        "bash",
        "bash.exe",
        "sh",
        "sh.exe",
        "zsh",
        "fish",
        "csh",
        "ksh",
        "wsl",
        "wsl.exe",
        "start",
    }
)
EXCLUDED_DIRS = frozenset({".state", "__pycache__", ".git"})
EXCLUDED_SUFFIXES = frozenset({".pyc", ".pyo"})

REPO_ROOT = Path(__file__).resolve().parents[1]
EXTENSIONS_ROOT = REPO_ROOT / "extensions"
PROTECTED_DIRS = (
    "workstream",
    "docs",
    "game",
    "assets",
    "scripts",
    "slices",
    "toolpacks",
    "tools",
    "templates",
    "design",
    "unity",
    "build",
    "artifacts",
    ".git",
    ".github",
    ".githooks",
)


class ExtensionError(ValueError):
    """An extension is missing, invalid, unregistered, stale, or unsafe to run."""


class Extension:
    """A validated extension: manifest, capability, file ledger and hashes."""

    def __init__(self, directory, manifest, capability, manifest_sha256, capability_sha256, files):
        self.directory = Path(directory).resolve()
        self.manifest = manifest
        self.capability = capability
        self.manifest_sha256 = manifest_sha256
        self.capability_sha256 = capability_sha256
        self.files = list(files)
        self.tree_sha256 = tree_hash(self.files)

    @property
    def id(self) -> str:
        return self.manifest["id"]

    @property
    def version(self) -> str:
        return self.manifest["version"]

    @property
    def capability_id(self) -> str:
        return self.manifest["capability"]

    @property
    def actions(self) -> dict:
        return self.manifest["entrypoints"]

    def info(self) -> dict:
        return {
            "id": self.id,
            "version": self.version,
            "name": self.manifest.get("name"),
            "apiVersion": self.manifest.get("apiVersion"),
            "capability": self.capability_id,
            "directory": display_path(self.directory),
            "manifestSha256": self.manifest_sha256,
            "capabilitySha256": self.capability_sha256,
            "treeSha256": self.tree_sha256,
            "files": len(self.files),
            "actions": sorted(self.actions),
            "tests": len(self.manifest.get("tests") or []),
        }


# -- small helpers -----------------------------------------------------------


def _iso_now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_sha256(value) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return _sha256_bytes(payload)


def _atomic_write_json(path: Path, payload) -> None:
    """Write JSON atomically: a temp file in the same directory, then os.replace."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    descriptor, temp_name = tempfile.mkstemp(
        prefix="." + path.stem + "-", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except BaseException:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def _as_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return str(value)


def _clip(text) -> str:
    value = _as_text(text)
    if len(value) <= OUTPUT_LIMIT:
        return value
    return "...[truncated]...\n" + value[-OUTPUT_LIMIT:]


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def display_path(path) -> str:
    """Render a path relative to this checkout when possible, POSIX-style."""
    path = Path(path)
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except (OSError, ValueError):
        return str(path)


# -- root and path containment ----------------------------------------------


def ensure_root(root=None, *, create: bool = False) -> Path:
    """Resolve and validate an extension root; never accept a core source directory."""
    candidate = Path(root).expanduser() if root else EXTENSIONS_ROOT
    resolved = candidate.resolve()
    for name in PROTECTED_DIRS:
        protected = (REPO_ROOT / name).resolve()
        if resolved == protected or resolved.is_relative_to(protected):
            raise ExtensionError(
                f"extension root {display_path(resolved)} is inside a protected core "
                f"directory ({name}); extensions may not modify the core"
            )
    if resolved.is_relative_to(REPO_ROOT) and resolved != EXTENSIONS_ROOT:
        raise ExtensionError(
            "inside this checkout the extension root is extensions/ only; "
            f"refusing {display_path(resolved)}"
        )
    if resolved.exists() and not resolved.is_dir():
        raise ExtensionError(f"extension root is not a directory: {resolved}")
    if create:
        resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def resolve_within(root, relative, *, label: str = "path", must_exist: bool = False) -> Path:
    """Resolve a relative path and refuse absolute, drive or '..' escapes."""
    root = Path(root).expanduser().resolve()
    if not isinstance(relative, (str, os.PathLike)):
        raise ExtensionError(f"{label} must be a relative path string")
    text = str(relative)
    if not text.strip():
        raise ExtensionError(f"{label} must be a non-empty relative path")
    try:
        rel = Path(text)
    except (TypeError, ValueError) as exc:
        raise ExtensionError(f"{label} is not a usable path: {exc}") from exc
    if rel.is_absolute() or rel.drive or rel.root:
        raise ExtensionError(f"{label} must be relative, not absolute: {text!r}")
    if ".." in rel.parts:
        raise ExtensionError(f"{label} must not escape with '..': {text!r}")
    target = (root / rel).resolve()
    if target != root and not target.is_relative_to(root):
        raise ExtensionError(f"{label} resolves outside {root.name}/: {text!r}")
    if must_exist and not target.exists():
        raise ExtensionError(f"{label} does not exist: {text!r}")
    return target


def _check_relative_declaration(value, *, label: str):
    if not isinstance(value, str) or not value.strip():
        return f"{label} must be a non-empty relative path string"
    try:
        path = Path(value)
    except (TypeError, ValueError):
        return f"{label} is not a usable path"
    if path.is_absolute() or path.drive or path.root:
        return f"{label} must be relative, not absolute"
    if ".." in path.parts:
        return f"{label} must not escape with '..'"
    return None


def _token_error(token, *, label: str):
    """Reject a shell control string or an escaping path in an argv token."""
    if not isinstance(token, str):
        return f"{label} must be a string"
    if not token:
        return f"{label} must not be empty"
    for operator in SHELL_OPERATORS:
        if operator in token:
            return (
                f"{label} contains the shell control string {operator!r}; "
                "argv is executed directly and must not be a shell string"
            )
    if ".." in token:
        return f"{label} must not contain '..'"
    try:
        path = Path(token)
    except (TypeError, ValueError):
        return f"{label} is not a usable argument"
    if path.is_absolute() or path.drive or path.root:
        return f"{label} must not be an absolute path"
    return None


def _validate_argv(argv, directory, *, label: str) -> list:
    errors = []
    if not isinstance(argv, list) or not argv:
        return [
            f"{label} must be a non-empty list of strings "
            "(an explicit argv, never a shell string)"
        ]
    if isinstance(argv[0], str) and argv[0].casefold() not in ("python", "python.exe"):
        if Path(argv[0]).name.casefold() in SHELL_NAMES:
            return [
                f"{label}[0]: shell interpreter {argv[0]!r} is not allowed; "
                "name a relative executable inside the extension"
            ]
    for position, token in enumerate(argv):
        error = _token_error(token, label=f"{label}[{position}]")
        if error:
            errors.append(error)
    if errors:
        return errors

    executable = argv[0]
    if executable.casefold() in ("python", "python.exe"):
        if len(argv) < 2:
            errors.append(
                f"{label}: a python entrypoint must name a relative .py script as argv[1]"
            )
            return errors
        script = argv[1]
        if script.startswith("-"):
            errors.append(
                f"{label}[1]: interpreter options such as -c/-m are not allowed; "
                "name a script file inside the extension"
            )
            return errors
        try:
            target = resolve_within(directory, script, label=f"{label}[1]")
        except ExtensionError as exc:
            errors.append(str(exc))
            return errors
        if target.suffix.lower() != ".py":
            errors.append(f"{label}[1] must name a .py script inside the extension")
        if not target.is_file():
            errors.append(f"{label}[1] script does not exist: {script!r}")
        return errors

    name = Path(executable).name.casefold()
    if name in SHELL_NAMES:
        errors.append(
            f"{label}[0]: shell interpreter {executable!r} is not allowed; "
            "name a relative executable inside the extension"
        )
        return errors
    try:
        target = resolve_within(directory, executable, label=f"{label}[0]")
    except ExtensionError as exc:
        errors.append(str(exc))
        return errors
    if not target.is_file():
        errors.append(f"{label}[0] executable does not exist: {executable!r}")
    return errors


# -- file ledger -------------------------------------------------------------


def tree_hash(files) -> str:
    digest = hashlib.sha256()
    for entry in files:
        digest.update(entry["path"].encode("utf-8"))
        digest.update(b"\0")
        digest.update(entry["sha256"].encode("ascii"))
        digest.update(b"\0")
        digest.update(str(entry["bytes"]).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def _scan_tree(directory: Path):
    """Hash every extension file; reject symlinks and skip generated state."""
    directory = Path(directory).resolve()
    files = []
    errors = []
    for current, dirnames, filenames in os.walk(directory, followlinks=False):
        current_path = Path(current)
        kept = []
        for name in sorted(dirnames):
            child = current_path / name
            relative = child.relative_to(directory).as_posix()
            if child.is_symlink():
                errors.append(f"symlink directory is not allowed: {relative}")
                continue
            if name in EXCLUDED_DIRS:
                continue
            kept.append(name)
        dirnames[:] = kept
        for name in sorted(filenames):
            child = current_path / name
            relative = child.relative_to(directory).as_posix()
            if child.is_symlink():
                errors.append(f"symlink file is not allowed: {relative}")
                continue
            if child.suffix.lower() in EXCLUDED_SUFFIXES:
                continue
            try:
                size = child.stat().st_size
                digest = _sha256_file(child)
            except OSError as exc:
                errors.append(f"unreadable file {relative}: {exc}")
                continue
            files.append({"path": relative, "sha256": digest, "bytes": size})
    files.sort(key=lambda entry: entry["path"])
    return files, errors


# -- manifest and capability validation -------------------------------------


def load_manifest(path) -> dict:
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise ExtensionError(f"{path}: unreadable: {exc}") from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ExtensionError(f"{path}: invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ExtensionError(f"{path}: manifest must be a JSON object")
    return data


def validate_manifest(manifest, *, directory=None) -> list:
    """Return schema errors for a manifest; empty means valid."""
    if not isinstance(manifest, dict):
        return ["manifest must be a JSON object"]
    errors = []
    unknown = sorted(set(manifest) - MANIFEST_KEYS)
    if unknown:
        errors.append(
            "unknown top-level key(s) "
            + ", ".join(repr(item) for item in unknown)
            + "; allowed: "
            + ", ".join(sorted(MANIFEST_KEYS))
        )
    if manifest.get("schema") != SCHEMA:
        errors.append(f"schema must be {SCHEMA!r}, found {manifest.get('schema')!r}")

    extension_id = manifest.get("id")
    if not isinstance(extension_id, str) or not ID_RE.match(extension_id):
        errors.append(
            "id must be a lowercase id of letters, digits, '.', '_' or '-' "
            "(starting with a letter, at most 64 characters)"
        )
    elif directory is not None and Path(directory).name != extension_id:
        errors.append(
            f"id {extension_id!r} must equal the extension directory name "
            f"{Path(directory).name!r}"
        )

    version = manifest.get("version")
    if not isinstance(version, str) or not SEMVER_RE.match(version):
        errors.append("version must be a semantic version such as 1.0.0")
    if manifest.get("apiVersion") != API_VERSION:
        errors.append(
            f"apiVersion must be {API_VERSION!r}, found {manifest.get('apiVersion')!r}"
        )
    for key in ("name", "description", "license"):
        value = manifest.get(key)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{key} must be a non-empty string")
    if "author" in manifest and not isinstance(manifest["author"], str):
        errors.append("author must be a string when present")

    capability = manifest.get("capability")
    if not isinstance(capability, str) or not ID_RE.match(capability):
        errors.append("capability must be a lowercase capability id")

    entrypoints = manifest.get("entrypoints")
    if not isinstance(entrypoints, dict) or not entrypoints:
        errors.append("entrypoints must be a non-empty object of action id -> command")
        entrypoints = {}
    for action_id, spec in entrypoints.items():
        label = f"entrypoints[{action_id!r}]"
        if not isinstance(action_id, str) or not ID_RE.match(action_id):
            errors.append(f"{label}: action id is not a valid id")
            continue
        if not isinstance(spec, dict):
            errors.append(f"{label} must be an object")
            continue
        unknown = sorted(set(spec) - ENTRYPOINT_KEYS)
        if unknown:
            errors.append(
                f"{label}: unknown key(s) "
                + ", ".join(repr(item) for item in unknown)
                + "; allowed: "
                + ", ".join(sorted(ENTRYPOINT_KEYS))
            )
        if not isinstance(spec.get("description"), str) or not spec.get("description", "").strip():
            errors.append(f"{label}: description must be a non-empty string")
        if "timeout" in spec:
            timeout = spec["timeout"]
            if (
                not _is_number(timeout)
                or not math.isfinite(timeout)
                or timeout <= 0
                or timeout > MAX_TIMEOUT
            ):
                errors.append(
                    f"{label}: timeout must be a number of seconds in (0, {MAX_TIMEOUT:g}]"
                )
        if directory is None:
            argv = spec.get("argv")
            if not isinstance(argv, list) or not argv:
                errors.append(
                    f"{label}: argv must be a non-empty list of strings "
                    "(an explicit argv, never a shell string)"
                )
            else:
                for position, token in enumerate(argv):
                    error = _token_error(token, label=f"{label}: argv[{position}]")
                    if error:
                        errors.append(error)
        else:
            errors.extend(
                _validate_argv(spec.get("argv"), directory, label=f"{label}: argv")
            )

    tests = manifest.get("tests")
    if not isinstance(tests, list) or not tests:
        errors.append(
            "tests must be a non-empty list and must include a negative test "
            "(expectExit: 'nonzero')"
        )
        tests = []
    seen_tests = set()
    negative = 0
    for index, test in enumerate(tests):
        label = f"tests[{index}]"
        if not isinstance(test, dict):
            errors.append(f"{label} must be an object")
            continue
        unknown = sorted(set(test) - TEST_KEYS)
        if unknown:
            errors.append(
                f"{label}: unknown key(s) "
                + ", ".join(repr(item) for item in unknown)
                + "; allowed: "
                + ", ".join(sorted(TEST_KEYS))
            )
        test_id = test.get("id")
        if not isinstance(test_id, str) or not ID_RE.match(test_id):
            errors.append(f"{label}: id must be a valid id")
        elif test_id in seen_tests:
            errors.append(f"{label}: duplicate test id {test_id!r}")
        else:
            seen_tests.add(test_id)
        action = test.get("action")
        if not isinstance(action, str) or action not in entrypoints:
            errors.append(f"{label}: action {action!r} is not a declared entrypoint")
        expected = test.get("expectExit")
        if expected == "nonzero":
            negative += 1
        elif expected != 0 or isinstance(expected, bool):
            errors.append(
                f"{label}: expectExit must be 0 or 'nonzero'; found {expected!r}"
            )
        for key in ("stdoutContains", "stderrContains"):
            if key in test and (not isinstance(test[key], str) or not test[key]):
                errors.append(f"{label}: {key} must be a non-empty string")
    if tests and negative == 0:
        errors.append(
            "tests must include at least one negative test with expectExit 'nonzero' "
            "(a pipeline that cannot detect failure is not a test)"
        )

    permissions = manifest.get("permissions")
    if permissions is not None:
        if not isinstance(permissions, dict):
            errors.append("permissions must be an object")
        else:
            unknown = sorted(set(permissions) - PERMISSION_KEYS)
            if unknown:
                errors.append(
                    "permissions: unknown key(s) "
                    + ", ".join(repr(item) for item in unknown)
                    + "; allowed: "
                    + ", ".join(sorted(PERMISSION_KEYS))
                )
            if "network" in permissions and not isinstance(permissions["network"], bool):
                errors.append("permissions.network must be true or false")
            for key in ("reads", "writes"):
                if key not in permissions:
                    continue
                values = permissions[key]
                if not isinstance(values, list):
                    errors.append(f"permissions.{key} must be a list of relative paths")
                    continue
                for position, value in enumerate(values):
                    error = _check_relative_declaration(
                        value, label=f"permissions.{key}[{position}]"
                    )
                    if error:
                        errors.append(error)
                    elif directory is not None:
                        try:
                            resolve_within(directory, value, label=f"permissions.{key}[{position}]")
                        except ExtensionError as exc:
                            errors.append(str(exc))
    return errors


def load_capability(directory) -> dict:
    path = Path(directory) / "capability.json"
    if not path.is_file():
        raise ExtensionError(f"{path.name} is missing from {Path(directory).name}/")
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise ExtensionError(f"{path}: unreadable: {exc}") from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ExtensionError(f"{path}: invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ExtensionError(f"{path}: capability manifest must be a JSON object")
    return data


def validate_capability(capability, *, expected_id=None) -> list:
    if not isinstance(capability, dict):
        return ["capability manifest must be a JSON object"]
    errors = []
    unknown = sorted(set(capability) - CAPABILITY_KEYS)
    if unknown:
        errors.append(
            "capability: unknown key(s) "
            + ", ".join(repr(item) for item in unknown)
            + "; allowed: "
            + ", ".join(sorted(CAPABILITY_KEYS))
        )
    if capability.get("schema") != CAPABILITY_SCHEMA:
        errors.append(
            f"capability schema must be {CAPABILITY_SCHEMA!r}, "
            f"found {capability.get('schema')!r}"
        )
    capability_id = capability.get("id")
    if not isinstance(capability_id, str) or not ID_RE.match(capability_id):
        errors.append("capability id must be a lowercase capability id")
    elif expected_id is not None and capability_id != expected_id:
        errors.append(
            f"capability id {capability_id!r} must match manifest capability "
            f"{expected_id!r}"
        )
    if capability.get("layer") != "extension":
        errors.append("capability layer must be 'extension' for an isolated extension")
    if not isinstance(capability.get("kind"), str) or not capability.get("kind", "").strip():
        errors.append("capability kind must be a non-empty string")
    if capability.get("maturity") not in CAPABILITY_MATURITY:
        errors.append(
            f"capability maturity {capability.get('maturity')!r} must be one of "
            f"{sorted(CAPABILITY_MATURITY)}"
        )
    if (
        not isinstance(capability.get("description"), str)
        or not capability.get("description", "").strip()
    ):
        errors.append("capability description must be a non-empty string")
    for key in ("requires", "inputs", "outputs", "checks"):
        if not isinstance(capability.get(key), (list, dict)):
            errors.append(f"capability {key} must be a list or object")
    if not isinstance(capability.get("provenance"), dict):
        errors.append("capability provenance must be an object")
    return errors


def load_extension(directory, *, root=None) -> Extension:
    """Load and fully validate one extension directory."""
    raw = Path(directory)
    if raw.is_symlink():
        raise ExtensionError(f"extension directory may not be a symlink: {raw}")
    directory = raw.resolve()
    if not directory.is_dir():
        raise ExtensionError(f"extension directory does not exist: {directory}")
    if directory.is_relative_to(REPO_ROOT) and not directory.is_relative_to(EXTENSIONS_ROOT):
        raise ExtensionError(
            "extension directories inside this checkout must live under extensions/"
        )
    if root is not None:
        root = ensure_root(root)
        if directory.parent != root:
            raise ExtensionError(
                f"extension {directory.name!r} must be a direct child of {display_path(root)}"
            )
    manifest_path = directory / "extension.json"
    if not manifest_path.is_file():
        raise ExtensionError(f"extension.json is missing from {directory.name}/")
    manifest = load_manifest(manifest_path)
    errors = validate_manifest(manifest, directory=directory)
    capability = None
    try:
        capability = load_capability(directory)
    except ExtensionError as exc:
        errors.append(str(exc))
    if capability is not None:
        expected = manifest.get("capability") if isinstance(manifest.get("capability"), str) else None
        errors.extend(validate_capability(capability, expected_id=expected))
    files, file_errors = _scan_tree(directory)
    errors.extend(file_errors)
    if errors:
        raise ExtensionError(f"{directory.name}: " + "; ".join(errors))
    return Extension(
        directory,
        manifest,
        capability,
        _canonical_sha256(manifest),
        _canonical_sha256(capability),
        files,
    )


# -- discovery ---------------------------------------------------------------


def scan(root=None) -> dict:
    """Discover extension directories under root without running anything."""
    root = ensure_root(root)
    entries = []
    root_errors = []
    if not root.exists():
        return {
            "root": root,
            "display": display_path(root),
            "entries": [],
            "errors": ["extension root does not exist"],
        }
    try:
        children = sorted(path for path in root.iterdir() if path.is_dir())
    except OSError as exc:
        raise ExtensionError(f"cannot read extension root {display_path(root)}: {exc}") from exc
    for child in children:
        if child.name in EXCLUDED_DIRS or child.name.startswith("."):
            continue
        manifest_path = child / "extension.json"
        if not manifest_path.is_file():
            continue
        entry = {
            "id": child.name,
            "directory": child,
            "manifestPath": manifest_path,
            "manifest": None,
            "capability": None,
            "extension": None,
            "errors": [],
        }
        try:
            entry["manifest"] = load_manifest(manifest_path)
        except ExtensionError as exc:
            entry["errors"].append(str(exc))
        try:
            entry["capability"] = load_capability(child)
        except ExtensionError as exc:
            entry["errors"].append(str(exc))
        try:
            entry["extension"] = load_extension(child, root=root)
        except ExtensionError as exc:
            message = str(exc)
            prefix = child.name + ": "
            if message.startswith(prefix):
                message = message[len(prefix):]
            entry["errors"].append(message)
            entry["errors"] = _dedupe(entry["errors"])
        entries.append(entry)
    return {"root": root, "display": display_path(root), "entries": entries, "errors": root_errors}


def _dedupe(values):
    seen = set()
    output = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output


def _entry_by_id(data: dict, extension_id: str) -> dict:
    for entry in data["entries"]:
        if entry["id"] == extension_id:
            return entry
    known = ", ".join(sorted(entry["id"] for entry in data["entries"])) or "none"
    raise ExtensionError(f"unknown extension {extension_id!r}; have: {known}")


# -- lockfile ----------------------------------------------------------------


def lock_path(root=None) -> Path:
    root = ensure_root(root)
    return root / "gypsy.lock.json"


def _empty_lock() -> dict:
    return {"schema": LOCK_SCHEMA, "updated": None, "extensions": {}}


def load_lock(root=None) -> dict:
    path = lock_path(root)
    if not path.exists():
        return _empty_lock()
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise ExtensionError(f"{path}: unreadable lockfile: {exc}") from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ExtensionError(f"{path}: invalid lockfile JSON: {exc}") from exc
    if not isinstance(data, dict) or data.get("schema") != LOCK_SCHEMA:
        raise ExtensionError(f"{path}: lockfile schema must be {LOCK_SCHEMA!r}")
    extensions = data.get("extensions")
    if not isinstance(extensions, dict):
        raise ExtensionError(f"{path}: lockfile 'extensions' must be an object")
    for key, value in extensions.items():
        if not isinstance(key, str) or not isinstance(value, dict):
            raise ExtensionError(f"{path}: lock entry {key!r} must be an object")
        if value.get("id") != key:
            raise ExtensionError(f"{path}: lock entry {key!r} must carry the matching id")
        for flag in ("accepted", "enabled"):
            if flag in value and not isinstance(value[flag], bool):
                raise ExtensionError(
                    f"{path}: lock entry {key!r} {flag} must be true or false"
                )
    return data


def save_lock(root, lock: dict) -> None:
    lock = dict(lock)
    lock["schema"] = LOCK_SCHEMA
    lock["updated"] = _iso_now()
    _atomic_write_json(lock_path(root), lock)


def _status(extension: Extension, lock: dict) -> dict:
    entry = (lock.get("extensions") or {}).get(extension.id)
    if not entry:
        return {"state": "unregistered", "reason": "not registered; review then register --accept"}
    if not entry.get("accepted"):
        return {"state": "unregistered", "reason": "lock entry was not accepted"}
    if not entry.get("enabled", True):
        return {"state": "disabled", "reason": "disabled; register --accept to re-enable"}
    if entry.get("manifestSha256") != extension.manifest_sha256:
        return {"state": "stale", "reason": "extension.json changed since registration"}
    if entry.get("treeSha256") != extension.tree_sha256:
        return {"state": "stale", "reason": "extension files changed since registration"}
    return {"state": "registered", "reason": None}


def _assert_runnable(extension: Extension, lock: dict) -> None:
    status = _status(extension, lock)
    if status["state"] != "registered":
        raise ExtensionError(
            f"extension {extension.id!r} is {status['state']}: {status['reason']} "
            f"(review with 'gypsy extension show {extension.id}', then "
            f"'gypsy extension register {extension.id} --accept')"
        )


def _review(extension: Extension) -> dict:
    manifest = extension.manifest
    permissions = manifest.get("permissions") or {}
    tests = manifest.get("tests") or []
    return {
        "id": extension.id,
        "version": extension.version,
        "capability": extension.capability_id,
        "entrypoints": sorted(extension.actions),
        "tests": len(tests),
        "negativeTests": sum(1 for test in tests if test.get("expectExit") == "nonzero"),
        "permissions": {
            "network": bool(permissions.get("network", False)),
            "reads": list(permissions.get("reads") or []),
            "writes": list(permissions.get("writes") or []),
        },
        "files": len(extension.files),
        "manifestSha256": extension.manifest_sha256,
        "treeSha256": extension.tree_sha256,
    }


def _lock_entry(extension: Extension, previous=None) -> dict:
    entry = {
        "id": extension.id,
        "version": extension.version,
        "capability": extension.capability_id,
        "directory": extension.directory.name,
        "manifest": "extension.json",
        "manifestSha256": extension.manifest_sha256,
        "capabilitySha256": extension.capability_sha256,
        "treeSha256": extension.tree_sha256,
        "files": extension.files,
        "accepted": True,
        "acceptedAt": _iso_now(),
        "enabled": True,
        "review": _review(extension),
    }
    if previous and previous.get("treeSha256") and previous.get("treeSha256") != extension.tree_sha256:
        entry["previousTreeSha256"] = previous["treeSha256"]
    return entry


# -- lifecycle: register, reload, disable, remove ----------------------------


def register(
    root=None,
    extension_ids=None,
    *,
    accept: bool = False,
    dry_run: bool = False,
    require_registered: bool = False,
) -> dict:
    """Register reviewed extensions, or preview the review when accept is false."""
    root = ensure_root(root)
    data = scan(root)
    by_id = {entry["id"]: entry for entry in data["entries"]}
    requested = list(extension_ids or [])
    if requested:
        missing = [item for item in requested if item not in by_id]
        if missing:
            raise ExtensionError(
                "unknown extension(s): " + ", ".join(missing) + "; have: "
                + (", ".join(sorted(by_id)) or "none")
            )
        invalid = {
            item: by_id[item]["errors"] for item in requested if by_id[item]["errors"]
        }
        if invalid:
            raise ExtensionError(
                "cannot register invalid extension(s): "
                + "; ".join(f"{key}: {', '.join(value)}" for key, value in invalid.items())
            )
        selected = requested
    else:
        invalid = {
            entry["id"]: entry["errors"] for entry in data["entries"] if entry["errors"]
        }
        if invalid:
            raise ExtensionError(
                "cannot register all extensions while invalid ones exist; "
                "name valid extension ids explicitly: "
                + "; ".join(f"{key}: {', '.join(value)}" for key, value in invalid.items())
            )
        selected = sorted(by_id)
    if not selected:
        raise ExtensionError("no extensions found to register")

    lock = load_lock(root)
    locked = lock.get("extensions") or {}
    reviews = []
    plans = []
    for extension_id in selected:
        extension = by_id[extension_id]["extension"]
        if extension is None:
            raise ExtensionError(f"cannot register invalid extension {extension_id!r}")
        previous = locked.get(extension_id)
        if require_registered and not previous:
            raise ExtensionError(
                f"extension {extension_id!r} is not registered; use register, not reload"
            )
        changed = (
            previous is None
            or previous.get("manifestSha256") != extension.manifest_sha256
            or previous.get("treeSha256") != extension.tree_sha256
            or not previous.get("enabled", True)
        )
        reviews.append(_review(extension))
        plans.append(
            {
                "id": extension_id,
                "changed": changed,
                "previousTreeSha256": (previous or {}).get("treeSha256"),
                "treeSha256": extension.tree_sha256,
                "enabled": bool(previous.get("enabled", True)) if previous else False,
            }
        )

    result = {
        "root": display_path(root),
        "lockPath": display_path(lock_path(root)),
        "accept": bool(accept),
        "dryRun": bool(dry_run),
        "reviews": reviews,
        "plans": plans,
        "registered": [],
        "unchanged": [],
        "requiresAcceptance": not accept,
        "passed": False,
    }
    if not accept:
        raise ExtensionError(
            "registration requires explicit review acceptance: inspect the review with "
            "'gypsy extension show <id>' or 'gypsy extension register <id> --accept --dry-run', "
            "then rerun with --accept"
        )
    if dry_run:
        result["passed"] = True
        return result

    updated = dict(locked)
    for extension_id in selected:
        extension = by_id[extension_id]["extension"]
        previous = locked.get(extension_id)
        unchanged = (
            previous is not None
            and previous.get("manifestSha256") == extension.manifest_sha256
            and previous.get("treeSha256") == extension.tree_sha256
            and previous.get("enabled", True)
            and previous.get("accepted")
        )
        if unchanged:
            result["unchanged"].append(extension_id)
            continue
        updated[extension_id] = _lock_entry(extension, previous)
        result["registered"].append(extension_id)
    lock["extensions"] = dict(sorted(updated.items()))
    save_lock(root, lock)
    result["passed"] = True
    result["lock"] = load_lock(root)
    return result


def reload(root=None, extension_ids=None, *, accept: bool = False, dry_run: bool = False) -> dict:
    """Re-review and re-register already registered extensions after a change."""
    root = ensure_root(root)
    lock = load_lock(root)
    locked = lock.get("extensions") or {}
    selected = list(extension_ids or [])
    if not selected:
        selected = sorted(locked)
    if not selected:
        raise ExtensionError("no registered extensions to reload")
    missing = [item for item in selected if item not in locked]
    if missing:
        raise ExtensionError(
            "cannot reload unregistered extension(s): " + ", ".join(missing)
            + "; use register --accept first"
        )
    result = register(
        root,
        selected,
        accept=accept,
        dry_run=dry_run,
        require_registered=True,
    )
    result["reloaded"] = list(selected)
    return result


def disable(root=None, extension_id=None, *, dry_run: bool = False) -> dict:
    root = ensure_root(root)
    if not isinstance(extension_id, str) or not extension_id:
        raise ExtensionError("disable requires an extension id")
    lock = load_lock(root)
    entry = (lock.get("extensions") or {}).get(extension_id)
    if entry is None:
        raise ExtensionError(f"extension {extension_id!r} is not registered")
    was_enabled = bool(entry.get("enabled", True))
    result = {
        "id": extension_id,
        "disabled": True,
        "wasEnabled": was_enabled,
        "changed": was_enabled,
        "dryRun": bool(dry_run),
        "lockPath": display_path(lock_path(root)),
    }
    if dry_run or not was_enabled:
        return result
    entry["enabled"] = False
    entry["disabledAt"] = _iso_now()
    lock["extensions"] = dict(sorted((lock.get("extensions") or {}).items()))
    save_lock(root, lock)
    return result


def remove(root=None, extension_id=None, *, delete: bool = False, dry_run: bool = False) -> dict:
    root = ensure_root(root)
    if not isinstance(extension_id, str) or not extension_id:
        raise ExtensionError("remove requires an extension id")
    if not ID_RE.match(extension_id):
        raise ExtensionError(f"invalid extension id {extension_id!r}")
    raw = root / extension_id
    if raw.is_symlink():
        raise ExtensionError("refusing to remove a symlinked extension directory")
    directory = raw.resolve()
    if directory.parent != root:
        raise ExtensionError("remove only accepts a direct child extension directory")
    if directory.exists() and not directory.is_dir():
        raise ExtensionError(f"extension path is not a directory: {directory}")
    lock = load_lock(root)
    entry = (lock.get("extensions") or {}).get(extension_id)
    if entry is None and not directory.exists():
        raise ExtensionError(
            f"extension {extension_id!r} is neither registered nor present in {display_path(root)}"
        )
    result = {
        "id": extension_id,
        "unregistered": entry is not None,
        "directory": display_path(directory),
        "deletedDirectory": False,
        "delete": bool(delete),
        "dryRun": bool(dry_run),
        "lockPath": display_path(lock_path(root)),
    }
    if dry_run:
        return result
    if delete and directory.exists():
        shutil.rmtree(directory)
        result["deletedDirectory"] = True
        state_dir = root / ".state" / "extensions" / extension_id
        if state_dir.exists() and state_dir.is_relative_to(root / ".state"):
            shutil.rmtree(state_dir, ignore_errors=True)
    if entry is not None:
        lock["extensions"].pop(extension_id, None)
        save_lock(root, lock)
    return result


# -- execution ---------------------------------------------------------------


def _find_action(extension: Extension, action_id: str) -> dict:
    action = extension.actions.get(action_id)
    if not isinstance(action, dict):
        known = ", ".join(sorted(extension.actions)) or "none"
        raise ExtensionError(
            f"extension {extension.id!r} has no action {action_id!r}; have: {known}"
        )
    return action


def _build_plan(extension: Extension, action_id: str, *, timeout_override=None) -> dict:
    action = _find_action(extension, action_id)
    argv = list(action["argv"])
    if argv[0].casefold() in ("python", "python.exe"):
        script = resolve_within(
            extension.directory, argv[1], label="entrypoint script", must_exist=True
        )
        resolved = [sys.executable, str(script)] + argv[2:]
    else:
        executable = resolve_within(
            extension.directory, argv[0], label="entrypoint executable", must_exist=True
        )
        resolved = [str(executable)] + argv[1:]
    timeout = float(action.get("timeout") or DEFAULT_TIMEOUT)
    if timeout_override is not None:
        try:
            override = float(timeout_override)
        except (TypeError, ValueError) as exc:
            raise ExtensionError("timeout override must be a number") from exc
        if not math.isfinite(override) or override <= 0:
            raise ExtensionError("timeout override must be a positive finite number")
        timeout = min(timeout, override)
    if not math.isfinite(timeout) or timeout <= 0 or timeout > MAX_TIMEOUT:
        raise ExtensionError(f"timeout must be in (0, {MAX_TIMEOUT:g}] seconds")
    state_root = extension.directory.parent / ".state" / "extensions" / extension.id
    env = {
        key: value
        for key, value in os.environ.items()
        if key.upper()
        not in {"PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP", "PYTHONUSERBASE"}
    }
    env.update(
        {
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONIOENCODING": "utf-8",
            "PYTHONNOUSERSITE": "1",
            "GYPSY_EXTENSION_ID": extension.id,
            "GYPSY_EXTENSION_VERSION": extension.version,
            "GYPSY_EXTENSION_ROOT": str(extension.directory),
            "GYPSY_EXTENSION_STATE": str(state_root),
        }
    )
    return {
        "argv": resolved,
        "declaredArgv": argv,
        "cwd": str(extension.directory),
        "timeout": timeout,
        "env": env,
        "stateRoot": state_root,
        "action": action_id,
    }


def _check_plan_tree(extension: Extension) -> None:
    files, errors = _scan_tree(extension.directory)
    if errors:
        raise ExtensionError("extension tree is unsafe: " + "; ".join(errors))
    current = tree_hash(files)
    if current != extension.tree_sha256:
        raise ExtensionError(
            "extension files changed after validation; review and reload before running"
        )


def _run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6]


def _execute(plan: dict) -> dict:
    started = time.time()
    started_at = _iso_now()
    try:
        completed = subprocess.run(
            list(plan["argv"]),
            cwd=plan["cwd"],
            env=plan["env"],
            shell=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=float(plan["timeout"]),
        )
        output = {
            "exit": completed.returncode,
            "stdout": _clip(completed.stdout),
            "stderr": _clip(completed.stderr),
            "timedOut": False,
            "error": None,
        }
    except subprocess.TimeoutExpired as exc:
        output = {
            "exit": None,
            "stdout": _clip(exc.stdout),
            "stderr": _clip(exc.stderr),
            "timedOut": True,
            "error": f"timeout after {float(plan['timeout']):g}s",
        }
    except FileNotFoundError as exc:
        output = {
            "exit": None,
            "stdout": "",
            "stderr": "",
            "timedOut": False,
            "error": f"command not found: {exc}",
        }
    except OSError as exc:
        output = {
            "exit": None,
            "stdout": "",
            "stderr": "",
            "timedOut": False,
            "error": f"could not run command: {exc}",
        }
    output["startedAt"] = started_at
    output["finishedAt"] = _iso_now()
    output["seconds"] = round(time.time() - started, 3)
    return output


# -- opt-in OS process containment (Windows Job Objects) --------------------


def _containment_unavailable_reason() -> str:
    if sys.platform != "win32":
        return (
            "Windows Job Objects are unavailable on "
            + sys.platform
            + "; the run is not contained (direct-child timeout only)"
        )
    return (
        "Windows Job Object containment could not be initialised; "
        "the run is not contained (direct-child timeout only)"
    )


def _containment_env_requested() -> bool:
    value = os.environ.get(CONTAINMENT_ENV, "").strip().casefold()
    return value in ("1", "true", "yes", "on")


def _containment_requested(explicit=None) -> bool:
    """Resolve containment: an explicit bool wins; otherwise the environment opts in."""
    if explicit is not None:
        return bool(explicit)
    return _containment_env_requested()


def _empty_containment(requested=False, reason=None) -> dict:
    return {
        "requested": bool(requested),
        "applied": False,
        "backend": "none",
        "platform": sys.platform,
        "limits": None,
        "reason": reason,
    }


def _applied_containment(limits) -> dict:
    return {
        "requested": True,
        "applied": True,
        "backend": CONTAINMENT_BACKEND,
        "platform": sys.platform,
        "limits": dict(limits or DEFAULT_CONTAINMENT_LIMITS),
        "reason": None,
    }


def containment_support() -> dict:
    """Report whether OS process containment is available, its backend and its defaults.

    available is true only on Windows when the Job Object API initialises. The claims block
    states explicitly that this is not a filesystem or network sandbox.
    """
    api = _job_api()
    available = api is not None
    return {
        "available": available,
        "platform": sys.platform,
        "backend": CONTAINMENT_BACKEND if available else "none",
        "reason": None if available else _containment_unavailable_reason(),
        "envVariable": CONTAINMENT_ENV,
        "defaultLimits": dict(DEFAULT_CONTAINMENT_LIMITS),
        "claims": {
            "filesystemSandbox": False,
            "networkSandbox": False,
            "resourceLimits": available,
            "processTreeKillOnTimeout": available,
        },
    }


def _containment_plan(requested: bool) -> dict:
    """Describe planned containment for a dry run."""
    support = containment_support()
    return {
        "requested": bool(requested),
        "available": support["available"],
        "backend": support["backend"],
        "platform": support["platform"],
        "limits": support["defaultLimits"] if requested and support["available"] else None,
        "reason": None if not requested else support["reason"],
    }


class _WindowsJobFactory:
    """Kernel32 function table and limit structures; built once, only on Windows."""

    JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
    LIMIT_PROCESS_TIME = 0x00000002
    LIMIT_ACTIVE_PROCESS = 0x00000008
    LIMIT_PROCESS_MEMORY = 0x00000100
    LIMIT_JOB_MEMORY = 0x00000200
    LIMIT_KILL_ON_JOB_CLOSE = 0x00002000

    def __init__(self):
        import ctypes
        from ctypes import wintypes

        self.ctypes = ctypes
        self.wintypes = wintypes

        class _BasicLimits(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_longlong),
                ("PerJobUserTimeLimit", ctypes.c_longlong),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class _IoCounters(ctypes.Structure):
            _fields_ = [
                ("ReadOperationCount", ctypes.c_ulonglong),
                ("WriteOperationCount", ctypes.c_ulonglong),
                ("OtherOperationCount", ctypes.c_ulonglong),
                ("ReadTransferCount", ctypes.c_ulonglong),
                ("WriteTransferCount", ctypes.c_ulonglong),
                ("OtherTransferCount", ctypes.c_ulonglong),
            ]

        class _ExtendedLimits(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", _BasicLimits),
                ("IoInfo", _IoCounters),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        self._basic_limits = _BasicLimits
        self._extended_limits = _ExtendedLimits

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        kernel32.SetInformationJobObject.restype = wintypes.BOOL
        kernel32.SetInformationJobObject.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
        ]
        kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
        kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel32.TerminateJobObject.restype = wintypes.BOOL
        kernel32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        kernel32.QueryInformationJobObject.restype = wintypes.BOOL
        kernel32.QueryInformationJobObject.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
        ]
        kernel32.CloseHandle.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.IsProcessInJob.restype = wintypes.BOOL
        kernel32.IsProcessInJob.argtypes = [
            wintypes.HANDLE,
            wintypes.HANDLE,
            ctypes.POINTER(wintypes.BOOL),
        ]
        self._kernel32 = kernel32

    def last_error(self) -> int:
        return int(self.ctypes.get_last_error())

    def create(self, limits=None) -> "_WindowsJob":
        merged = dict(DEFAULT_CONTAINMENT_LIMITS)
        if limits:
            merged.update(limits)
        active = int(merged.get("activeProcessLimit") or 0)
        process_mb = int(merged.get("processMemoryMb") or 0)
        job_mb = int(merged.get("jobMemoryMb") or 0)
        cpu = merged.get("cpuSeconds")
        if active < 0 or process_mb < 0 or job_mb < 0:
            raise ExtensionError("containment limits must not be negative")
        if cpu is not None and (not _is_number(cpu) or cpu <= 0):
            raise ExtensionError(
                "containment cpuSeconds must be a positive number or null"
            )

        handle = self._kernel32.CreateJobObjectW(None, None)
        if not handle:
            raise ExtensionError(
                "CreateJobObjectW failed with error " + str(self.last_error())
            )
        info = self._extended_limits()
        basic = info.BasicLimitInformation
        flags = 0
        if merged.get("killOnJobClose", True):
            flags |= self.LIMIT_KILL_ON_JOB_CLOSE
        if active:
            flags |= self.LIMIT_ACTIVE_PROCESS
            basic.ActiveProcessLimit = active
        if process_mb:
            flags |= self.LIMIT_PROCESS_MEMORY
            info.ProcessMemoryLimit = process_mb * 1024 * 1024
        if job_mb:
            flags |= self.LIMIT_JOB_MEMORY
            info.JobMemoryLimit = job_mb * 1024 * 1024
        if cpu:
            flags |= self.LIMIT_PROCESS_TIME
            basic.PerProcessUserTimeLimit = int(float(cpu) * 10_000_000)
        basic.LimitFlags = flags
        ok = self._kernel32.SetInformationJobObject(
            handle,
            self.JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
            self.ctypes.byref(info),
            self.ctypes.sizeof(info),
        )
        if not ok:
            error = self.last_error()
            self._kernel32.CloseHandle(handle)
            raise ExtensionError(
                "SetInformationJobObject failed with error " + str(error)
            )
        return _WindowsJob(self, handle, merged)

    def assign(self, job_handle, process_handle) -> bool:
        return bool(
            self._kernel32.AssignProcessToJobObject(job_handle, process_handle)
        )

    def in_job(self, process_handle, job_handle) -> bool:
        flag = self.wintypes.BOOL()
        ok = self._kernel32.IsProcessInJob(
            process_handle, job_handle, self.ctypes.byref(flag)
        )
        return bool(ok and flag.value)

    def terminate(self, job_handle, exit_code=1) -> bool:
        return bool(self._kernel32.TerminateJobObject(job_handle, int(exit_code)))

    def close(self, job_handle) -> None:
        if job_handle:
            self._kernel32.CloseHandle(job_handle)

    def query(self, job_handle) -> dict:
        info = self._extended_limits()
        returned = self.wintypes.DWORD(0)
        ok = self._kernel32.QueryInformationJobObject(
            job_handle,
            self.JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
            self.ctypes.byref(info),
            self.ctypes.sizeof(info),
            self.ctypes.byref(returned),
        )
        if not ok:
            raise ExtensionError(
                "QueryInformationJobObject failed with error " + str(self.last_error())
            )
        basic = info.BasicLimitInformation
        return {
            "limitFlags": int(basic.LimitFlags),
            "activeProcessLimit": int(basic.ActiveProcessLimit),
            "processMemoryLimitBytes": int(info.ProcessMemoryLimit),
            "jobMemoryLimitBytes": int(info.JobMemoryLimit),
            "perProcessUserTimeLimit100ns": int(basic.PerProcessUserTimeLimit),
            "peakProcessMemoryBytes": int(info.PeakProcessMemoryUsed),
            "peakJobMemoryBytes": int(info.PeakJobMemoryUsed),
        }


class _WindowsJob:
    """A created Job Object. close() triggers kill-on-close, so it always reaps the tree."""

    def __init__(self, factory: _WindowsJobFactory, handle, limits):
        self._factory = factory
        self._handle = handle
        self._limits = dict(limits)
        self._closed = False

    def assign(self, process) -> None:
        if self._closed or not self._handle:
            raise ExtensionError("containment job is already closed")
        handle = getattr(process, "_handle", None)
        if not handle:
            raise ExtensionError("containment job cannot see the child process handle")
        if not self._factory.assign(self._handle, int(handle)):
            raise ExtensionError(
                "AssignProcessToJobObject failed with error "
                + str(self._factory.last_error())
            )

    def in_job(self, process) -> bool:
        handle = getattr(process, "_handle", None)
        if not handle or self._closed or not self._handle:
            return False
        return self._factory.in_job(int(handle), self._handle)

    def terminate(self, exit_code: int = 1) -> None:
        if self._closed or not self._handle:
            return
        self._factory.terminate(self._handle, exit_code)

    def close(self) -> None:
        if self._closed or not self._handle:
            return
        handle = self._handle
        self._handle = None
        self._closed = True
        self._factory.close(handle)

    def info(self) -> dict:
        if self._closed or not self._handle:
            raise ExtensionError("containment job is already closed")
        return self._factory.query(self._handle)

    @property
    def limits(self) -> dict:
        return dict(self._limits)


_WINDOWS_JOB_FACTORY = None
_WINDOWS_JOB_FACTORY_READY = False


def _job_api():
    """Return the Job Object factory, or None when this platform cannot provide it."""
    global _WINDOWS_JOB_FACTORY, _WINDOWS_JOB_FACTORY_READY
    if _WINDOWS_JOB_FACTORY_READY:
        return _WINDOWS_JOB_FACTORY
    _WINDOWS_JOB_FACTORY_READY = True
    if sys.platform != "win32":
        return None
    try:
        _WINDOWS_JOB_FACTORY = _WindowsJobFactory()
    except Exception:  # an unavailable kernel32 API is a fallback, not a crash
        _WINDOWS_JOB_FACTORY = None
    return _WINDOWS_JOB_FACTORY


def _containment_output(
    started,
    started_at,
    *,
    exit_code,
    stdout,
    stderr,
    timed_out,
    error,
    job: _WindowsJob,
) -> dict:
    return {
        "exit": exit_code,
        "stdout": _clip(stdout),
        "stderr": _clip(stderr),
        "timedOut": bool(timed_out),
        "error": error,
        "startedAt": started_at,
        "finishedAt": _iso_now(),
        "seconds": round(time.time() - started, 3),
        "containment": _applied_containment(job.limits),
    }


def _read_capture(path) -> str:
    try:
        text = Path(path).read_bytes().decode("utf-8", "replace")
    except OSError:
        return ""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _execute_contained(plan: dict) -> dict:
    """Run one plan inside a Windows Job Object; a timeout terminates the whole job.

    Output is captured through temporary files rather than pipes. A grandchild inherits pipe
    handles and would otherwise keep communicate() waiting after the direct child exits, which
    would turn a fast action into a false timeout; file capture is not affected.
    """
    api = _job_api()
    if api is None:  # run_extension checks support; defensive only
        raise ExtensionError(_containment_unavailable_reason())
    job = api.create()
    process = None
    started = time.time()
    started_at = _iso_now()
    timed_out = False
    error = None
    exit_code = None
    popen_error = None
    stdout = stderr = ""
    with tempfile.TemporaryDirectory(prefix="gypsy-extension-run-") as capture_dir:
        stdout_path = Path(capture_dir) / "stdout.bin"
        stderr_path = Path(capture_dir) / "stderr.bin"
        try:
            with open(stdout_path, "wb") as stdout_handle, open(
                stderr_path, "wb"
            ) as stderr_handle:
                try:
                    process = subprocess.Popen(
                        list(plan["argv"]),
                        cwd=plan["cwd"],
                        env=plan["env"],
                        shell=False,
                        stdout=stdout_handle,
                        stderr=stderr_handle,
                    )
                except FileNotFoundError as exc:
                    popen_error = f"command not found: {exc}"
                except OSError as exc:
                    popen_error = f"could not run command: {exc}"
                if process is not None:
                    try:
                        job.assign(process)
                    except ExtensionError:
                        process.kill()
                        try:
                            process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            pass
                        raise
                    try:
                        process.wait(timeout=float(plan["timeout"]))
                    except subprocess.TimeoutExpired:
                        timed_out = True
                        job.terminate(1)
                        try:
                            process.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait()
                    exit_code = None if timed_out else process.returncode
                    error = (
                        "timeout after " + format(float(plan["timeout"]), "g") + "s"
                        if timed_out
                        else None
                    )
        finally:
            job.close()
        if popen_error is None:
            stdout = _read_capture(stdout_path)
            stderr = _read_capture(stderr_path)
    if popen_error is not None:
        error = popen_error
    return _containment_output(
        started,
        started_at,
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        timed_out=timed_out,
        error=error,
        job=job,
    )


def _execute_action(
    extension: Extension,
    action_id: str,
    *,
    timeout_override=None,
    record: bool = True,
    contain=None,
) -> dict:
    _check_plan_tree(extension)
    plan = _build_plan(extension, action_id, timeout_override=timeout_override)
    if _containment_requested(contain):
        if _job_api() is None:
            result = _execute(plan)
            result["containment"] = _empty_containment(
                requested=True, reason=_containment_unavailable_reason()
            )
        else:
            result = _execute_contained(plan)
    else:
        result = _execute(plan)
        result["containment"] = _empty_containment(
            requested=False,
            reason="containment not requested; a timeout kills the direct child only",
        )
    result["passed"] = bool(result["exit"] == 0 and not result["timedOut"] and not result["error"])
    result["extension"] = extension.id
    result["version"] = extension.version
    result["action"] = action_id
    result["treeSha256"] = extension.tree_sha256
    result["manifestSha256"] = extension.manifest_sha256
    result["command"] = {
        "argv": plan["argv"],
        "declaredArgv": plan["declaredArgv"],
        "cwd": plan["cwd"],
        "timeoutSeconds": plan["timeout"],
    }
    if record:
        run_id = _run_id()
        document = {
            "schema": STATE_SCHEMA,
            "extension": extension.id,
            "version": extension.version,
            "action": action_id,
            "runId": run_id,
            "generated": _iso_now(),
            "treeSha256": extension.tree_sha256,
            "manifestSha256": extension.manifest_sha256,
            "command": result["command"],
            "startedAt": result["startedAt"],
            "finishedAt": result["finishedAt"],
            "seconds": result["seconds"],
            "exit": result["exit"],
            "timedOut": result["timedOut"],
            "stdout": result["stdout"],
            "stderr": result["stderr"],
            "passed": result["passed"],
            "containment": result.get("containment"),
            "errors": [result["error"]] if result["error"] else [],
        }
        state_path = plan["stateRoot"] / f"{action_id}-{run_id}.json"
        _atomic_write_json(state_path, document)
        result["statePath"] = str(state_path)
    return result


def run_extension(
    root=None,
    extension_id=None,
    action_id=None,
    *,
    dry_run: bool = False,
    timeout=None,
    contain=None,
) -> dict:
    """Run a registered, enabled, unchanged extension action (or preview it).

    contain=True runs the action inside a Windows Job Object (kill-on-close, active-process
    and memory limits, whole-job kill on timeout). contain=None follows the
    GYPSY_EXTENSION_CONTAIN environment switch; contain=False keeps direct-child behaviour.
    """
    root = ensure_root(root)
    if not isinstance(extension_id, str) or not extension_id:
        raise ExtensionError("run requires an extension id")
    if not isinstance(action_id, str) or not action_id:
        raise ExtensionError("run requires an action id")
    data = scan(root)
    entry = _entry_by_id(data, extension_id)
    if entry["errors"]:
        raise ExtensionError(f"{extension_id}: " + "; ".join(entry["errors"]))
    extension = entry["extension"]
    lock = load_lock(root)
    status = _status(extension, lock)
    containment_requested = _containment_requested(contain)
    if not dry_run:
        _assert_runnable(extension, lock)
    if dry_run:
        _check_plan_tree(extension)
        plan = _build_plan(extension, action_id, timeout_override=timeout)
        return {
            "dryRun": True,
            "executed": False,
            "ok": True,
            "passed": None,
            "extension": extension.id,
            "version": extension.version,
            "action": action_id,
            "status": status,
            "containment": _containment_plan(containment_requested),
            "plan": {
                "argv": plan["argv"],
                "declaredArgv": plan["declaredArgv"],
                "cwd": plan["cwd"],
                "timeoutSeconds": plan["timeout"],
                "stateRoot": str(plan["stateRoot"]),
            },
            "treeSha256": extension.tree_sha256,
        }
    result = _execute_action(
        extension, action_id, timeout_override=timeout, contain=contain
    )
    result["status"] = status
    return result


def test_extension(root=None, extension_id=None, *, contain=None) -> dict:
    """Run the manifest's declared tests, including the required negative test.

    contain behaves as in run_extension: True uses the Windows Job Object, None follows the
    GYPSY_EXTENSION_CONTAIN switch and False keeps direct-child behaviour.
    """
    root = ensure_root(root)
    if not isinstance(extension_id, str) or not extension_id:
        raise ExtensionError("test requires an extension id")
    data = scan(root)
    entry = _entry_by_id(data, extension_id)
    if entry["errors"]:
        raise ExtensionError(f"{extension_id}: " + "; ".join(entry["errors"]))
    extension = entry["extension"]
    lock = load_lock(root)
    status = _status(extension, lock)
    containment_requested = _containment_requested(contain)
    results = []
    for test in extension.manifest["tests"]:
        action_id = test["action"]
        result = _execute_action(extension, action_id, contain=contain)
        failures = []
        expected = test["expectExit"]
        actual = result["exit"]
        if expected == 0:
            if actual != 0:
                failures.append(f"expected exit 0, got {actual!r}")
        else:
            if actual is None:
                failures.append(
                    "expected a nonzero exit, got a timeout or invocation failure"
                )
            elif actual == 0:
                failures.append("expected a nonzero exit, got 0")
        if "stdoutContains" in test and test["stdoutContains"] not in result["stdout"]:
            failures.append(f"stdout does not contain {test['stdoutContains']!r}")
        if "stderrContains" in test and test["stderrContains"] not in result["stderr"]:
            failures.append(f"stderr does not contain {test['stderrContains']!r}")
        results.append(
            {
                "id": test["id"],
                "action": action_id,
                "expectedExit": expected,
                "actualExit": actual,
                "timedOut": result["timedOut"],
                "passed": not failures,
                "errors": failures,
                "stdout": result["stdout"],
                "stderr": result["stderr"],
                "containment": result.get("containment"),
                "statePath": result.get("statePath"),
            }
        )
    negative = sum(1 for test in extension.manifest["tests"] if test["expectExit"] == "nonzero")
    applied = next(
        (
            item["containment"]
            for item in results
            if item.get("containment") and item["containment"].get("applied")
        ),
        None,
    )
    return {
        "extension": extension.id,
        "version": extension.version,
        "status": status,
        "treeSha256": extension.tree_sha256,
        "containment": applied or _containment_plan(containment_requested),
        "tests": results,
        "count": len(results),
        "negativeTests": negative,
        "passed": bool(results) and all(item["passed"] for item in results) and negative > 0,
    }


# -- read-only views ---------------------------------------------------------


def list_extensions(root=None) -> dict:
    root = ensure_root(root)
    data = scan(root)
    lock_errors = []
    try:
        lock = load_lock(root)
    except ExtensionError as exc:
        lock_errors.append(str(exc))
        lock = _empty_lock()
    rows = []
    for entry in data["entries"]:
        extension = entry["extension"]
        if extension is None:
            rows.append(
                {
                    "id": entry["id"],
                    "version": (entry["manifest"] or {}).get("version"),
                    "status": "invalid",
                    "enabled": None,
                    "registered": False,
                    "actions": [],
                    "tests": 0,
                    "errors": entry["errors"],
                }
            )
            continue
        status = _status(extension, lock)
        rows.append(
            {
                "id": extension.id,
                "version": extension.version,
                "status": status["state"],
                "statusReason": status["reason"],
                "enabled": bool(
                    ((lock.get("extensions") or {}).get(extension.id) or {}).get(
                        "enabled", False
                    )
                ),
                "registered": extension.id in (lock.get("extensions") or {}),
                "actions": sorted(extension.actions),
                "tests": len(extension.manifest.get("tests") or []),
                "directory": display_path(extension.directory),
                "treeSha256": extension.tree_sha256,
                "errors": entry["errors"],
            }
        )
    return {
        "root": data["display"],
        "lockPath": display_path(lock_path(root)),
        "extensions": rows,
        "errors": list(data["errors"]) + list(lock_errors),
    }


def show_extension(root=None, extension_id=None) -> dict:
    root = ensure_root(root)
    if not isinstance(extension_id, str) or not extension_id:
        raise ExtensionError("show requires an extension id")
    data = scan(root)
    entry = _entry_by_id(data, extension_id)
    lock_errors = []
    try:
        lock = load_lock(root)
    except ExtensionError as exc:
        lock_errors.append(str(exc))
        lock = _empty_lock()
    result = {
        "id": entry["id"],
        "directory": display_path(entry["directory"]),
        "manifestPath": display_path(entry["manifestPath"]),
        "errors": list(entry["errors"]) + list(lock_errors),
    }
    extension = entry["extension"]
    if extension is not None:
        result.update(
            {
                "extension": extension.info(),
                "manifest": extension.manifest,
                "capability": extension.capability,
                "files": extension.files,
                "status": _status(extension, lock),
                "lockEntry": (lock.get("extensions") or {}).get(extension.id),
            }
        )
    else:
        result["manifest"] = entry["manifest"]
        result["capability"] = entry["capability"]
        result["status"] = {"state": "invalid", "reason": "validation failed"}
    return result


def validate_extensions(root=None, extension_id=None) -> dict:
    root = ensure_root(root)
    lock = None
    lock_error = None
    try:
        lock = load_lock(root)
    except ExtensionError as exc:
        lock_error = str(exc)
    if extension_id:
        try:
            data = scan(root)
            entry = _entry_by_id(data, extension_id)
        except ExtensionError as exc:
            return {
                "passed": False,
                "root": display_path(root),
                "checked": 0,
                "extensions": [],
                "errors": [str(exc)],
                "warnings": [],
            }
        entries = [entry]
    else:
        data = scan(root)
        entries = data["entries"]
    errors = list(data.get("errors") or [])
    if lock_error:
        errors.append(lock_error)
    warnings = []
    checked = []
    for entry in entries:
        item = {
            "id": entry["id"],
            "directory": display_path(entry["directory"]),
            "passed": not entry["errors"],
            "errors": list(entry["errors"]),
            "warnings": [],
        }
        extension = entry["extension"]
        if extension is not None and lock is not None:
            status = _status(extension, lock)
            if status["state"] == "stale":
                item["warnings"].append(
                    f"registered tree is stale: {status['reason']}; run reload --accept"
                )
            elif status["state"] == "unregistered" and extension.id not in (
                lock.get("extensions") or {}
            ):
                item["warnings"].append("not registered; run register --accept after review")
            elif status["state"] == "disabled":
                item["warnings"].append("disabled")
        warnings.extend(item["warnings"])
        checked.append(item)
        if not item["passed"]:
            errors.extend(f"{entry['id']}: {message}" for message in entry["errors"])
    if lock is not None:
        known = {entry["id"] for entry in entries}
        for locked_id in sorted((lock.get("extensions") or {})):
            if locked_id not in known:
                errors.append(
                    f"lockfile references missing extension {locked_id!r}; run remove "
                    f"{locked_id} after review"
                )
    return {
        "passed": not errors,
        "root": display_path(root),
        "checked": len(checked),
        "extensions": checked,
        "errors": _dedupe(errors),
        "warnings": _dedupe(warnings),
    }


# -- human renderers (the CLI may print these) -------------------------------


def render_list(data: dict) -> str:
    lines = [f"extension root: {data['root']}", f"lockfile: {data['lockPath']}"]
    if data["errors"]:
        for error in data["errors"]:
            lines.append(f"ERROR {error}")
    rows = data["extensions"]
    lines.append(f"extensions: {len(rows)}")
    for row in rows:
        lines.append(
            f"{row['id']:24} {str(row.get('version') or '-'):10} "
            f"{row['status']:12} actions: {', '.join(row.get('actions') or []) or '-'}"
        )
        if row.get("statusReason"):
            lines.append(f"  {row['statusReason']}")
        if row.get("errors"):
            lines.append("  ERROR " + "; ".join(row["errors"]))
    return "\n".join(lines)


def render_show(data: dict) -> str:
    extension = data.get("extension")
    lines = [f"{data['id']} - {data['directory']}"]
    if extension:
        lines.append(
            f"version: {extension['version']} | api: {extension['apiVersion']} | "
            f"capability: {extension['capability']}"
        )
        lines.append(f"name: {extension['name']} | status: {data['status']['state']}")
        lines.append(
            f"manifest: {extension['manifestSha256']}\ntree: {extension['treeSha256']} "
            f"({extension['files']} files)"
        )
        manifest = data.get("manifest") or {}
        lines.append(f"description: {manifest.get('description')}")
        lines.append(f"license: {manifest.get('license')}")
        lines.append("entrypoints:")
        for action_id, spec in sorted((manifest.get("entrypoints") or {}).items()):
            lines.append(
                f"  {action_id}: timeout {spec.get('timeout', DEFAULT_TIMEOUT)}s | "
                f"argv {json.dumps(spec.get('argv'))}"
            )
        lines.append("tests:")
        for test in manifest.get("tests") or []:
            lines.append(
                f"  {test.get('id')}: action {test.get('action')} | "
                f"expectExit {test.get('expectExit')!r}"
            )
        permissions = manifest.get("permissions") or {}
        lines.append(
            "permissions: network={} reads={} writes={}".format(
                bool(permissions.get("network", False)),
                permissions.get("reads") or [],
                permissions.get("writes") or [],
            )
        )
        lines.append("files:")
        for entry in data.get("files") or []:
            lines.append(f"  {entry['path']} {entry['bytes']} bytes {entry['sha256'][:16]}...")
        lock_entry = data.get("lockEntry")
        if lock_entry:
            lines.append(
                f"lock: accepted {lock_entry.get('acceptedAt')} | "
                f"enabled={lock_entry.get('enabled', True)} | "
                f"tree={lock_entry.get('treeSha256')}"
            )
        else:
            lines.append("lock: not registered (run register --accept after review)")
    else:
        lines.append(f"status: {data['status']['state']}")
        lines.append("manifest: " + json.dumps(data.get("manifest"), indent=2))
    if data.get("errors"):
        for error in data["errors"]:
            lines.append(f"ERROR {error}")
    return "\n".join(lines)


def render_validate(data: dict) -> str:
    lines = [f"extension root: {data['root']} | checked {data['checked']}"]
    for item in data.get("extensions") or []:
        state = "PASS" if item["passed"] else "FAIL"
        lines.append(f"{state} {item['id']}")
        for error in item["errors"]:
            lines.append(f"  ERROR {error}")
        for warning in item.get("warnings") or []:
            lines.append(f"  WARN {warning}")
    for error in data.get("errors") or []:
        lines.append(f"ERROR {error}")
    lines.append(f"validate: {'PASS' if data['passed'] else 'FAIL'}")
    return "\n".join(lines)


def _render_containment_line(containment) -> str:
    if not containment:
        return "containment: unknown"
    if containment.get("applied"):
        limits = containment.get("limits") or {}
        return (
            "containment: applied "
            + str(containment.get("backend"))
            + " (kill-on-close, active process limit "
            + str(limits.get("activeProcessLimit"))
            + ", process memory "
            + str(limits.get("processMemoryMb"))
            + " MB, job memory "
            + str(limits.get("jobMemoryMb"))
            + " MB)"
        )
    if "available" in containment:
        if containment.get("requested") and containment.get("available"):
            return (
                "containment: would apply "
                + str(containment.get("backend"))
                + " "
                + json.dumps(containment.get("limits") or {}, sort_keys=True)
            )
        if containment.get("requested"):
            return (
                "containment: requested but unavailable - "
                + str(containment.get("reason"))
            )
        return "containment: not requested (direct-child timeout only)"
    if containment.get("requested"):
        return "containment: requested but NOT applied - " + str(
            containment.get("reason")
        )
    return "containment: not requested (direct-child timeout only)"


def render_test(data: dict) -> str:
    lines = [f"extension {data['extension']} {data['version']} | status {data['status']['state']}"]
    for test in data.get("tests") or []:
        state = "PASS" if test["passed"] else "FAIL"
        lines.append(
            f"{state} {test['id']}: action {test['action']} expected "
            f"{test['expectedExit']!r}, got {test['actualExit']!r}"
        )
        for error in test["errors"]:
            lines.append(f"  ERROR {error}")
    lines.append(
        f"tests: {data['count']} | negative {data['negativeTests']} | "
        f"{'PASS' if data['passed'] else 'FAIL'}"
    )
    lines.append(_render_containment_line(data.get("containment")))
    return "\n".join(lines)


def render_register(data: dict) -> str:
    label = "reload" if data.get("reloaded") is not None else "register"
    lines = [
        f"{label}{' (dry run)' if data.get('dryRun') else ''}: "
        f"root {data['root']} | lockfile {data['lockPath']}"
    ]
    for review in data.get("reviews") or []:
        lines.append(
            f"review {review['id']} {review['version']} | capability {review['capability']} | "
            f"actions {', '.join(review['entrypoints'])} | tests {review['tests']} "
            f"(negative {review['negativeTests']}) | files {review['files']}"
        )
        permissions = review.get("permissions") or {}
        lines.append(
            f"  network={permissions.get('network')} reads={permissions.get('reads')} "
            f"writes={permissions.get('writes')}"
        )
    if data.get("registered"):
        lines.append("registered: " + ", ".join(data["registered"]))
    if data.get("unchanged"):
        lines.append("unchanged: " + ", ".join(data["unchanged"]))
    lines.append("lockfile updated" if not data.get("dryRun") else "lockfile not written (dry run)")
    return "\n".join(lines)


def render_run(data: dict) -> str:
    if data.get("dryRun"):
        plan = data["plan"]
        return "\n".join(
            [
                f"DRY RUN extension {data['extension']} {data['version']} action {data['action']}",
                f"status: {data['status']['state']}",
                f"cwd: {plan['cwd']}",
                f"timeout: {plan['timeoutSeconds']}s",
                f"argv: {json.dumps(plan['argv'])}",
                _render_containment_line(data.get("containment")),
                "not executed",
            ]
        )
    lines = [
        f"{'PASS' if data.get('passed') else 'FAIL'} extension {data['extension']} "
        f"{data['version']} action {data['action']} | exit {data.get('exit')} | "
        f"{data.get('seconds')}s | timeout={data.get('timedOut')}",
        f"cwd: {data['command']['cwd']}",
        f"argv: {json.dumps(data['command']['argv'])}",
        _render_containment_line(data.get("containment")),
        f"state: {data.get('statePath')}",
    ]
    if data.get("stdout"):
        lines.append("stdout:\n" + data["stdout"].rstrip())
    if data.get("stderr"):
        lines.append("stderr:\n" + data["stderr"].rstrip())
    if data.get("error"):
        lines.append("ERROR " + data["error"])
    return "\n".join(lines)


def render_disable(data: dict) -> str:
    lines = [
        f"{'DRY RUN ' if data.get('dryRun') else ''}extension {data['id']} disabled"
        f" (was enabled={data['wasEnabled']})"
    ]
    if data.get("changed") and not data.get("dryRun"):
        lines.append("lockfile updated")
    return "\n".join(lines)


def render_remove(data: dict) -> str:
    lines = [
        f"{'DRY RUN ' if data.get('dryRun') else ''}extension {data['id']} "
        + ("deleted" if data.get("deletedDirectory") else "unregistered"),
        f"directory: {data['directory']}",
        f"lockfile: {data['lockPath']}",
    ]
    return "\n".join(lines)
