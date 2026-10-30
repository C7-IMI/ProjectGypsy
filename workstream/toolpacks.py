#!/usr/bin/env python3
"""Phase-3 toolpack runner and artifact validators (docs/ADR-003-workstream-architecture.md).

A toolpack is a JSON manifest for one tool (or one small tool chain): its declared tools and
licence, an ordered list of actions (explicit argv commands) and toolpack-level validators
that every action's declared artifacts must pass. This module loads and strictly validates
manifests, executes actions without a shell, validates and hashes the artifacts, and persists
provenance atomically. Standard library only.

Schema gypsy.toolpack/v1:

    {
      "schema": "gypsy.toolpack/v1",
      "id": "blender-export",
      "name": "Blender glTF export",
      "tools": [{"name": "Blender", "version": "5.2.3"}, "glTF-Transform 4.5.1"],
      "license": "GPL-3.0-or-later (Blender); MIT (glTF-Transform)",
      "actions": [
        {"id": "export",
         "argv": ["blender", "--background", "--python", "export.py"],
         "cwd": ".", "timeout": 240,
         "artifacts": ["artifacts/export/*.glb"],
         "args": {"asset": "golden"}}
      ],
      "validators": [
        {"id": "glb-v2", "kind": "glb", "artifact": "artifacts/export/*.glb"}
      ]
    }

The top-level keys are exactly schema, id, name, tools, license, actions and validators.
Unknown top-level keys are validation errors. validators is optional (default: empty list).

Action keys are exactly id, argv, cwd, timeout, artifacts and args; unknown action keys are
validation errors.

* argv - required, a non-empty list of non-empty strings. It is authoritative and is run
  directly with shell=False; a shell string is never parsed.
* cwd - repo-relative directory, default ".". Absolute paths, drives and ".." are errors.
* timeout - seconds, positive finite number, default DEFAULT_TIMEOUT.
* artifacts - repo-relative paths, default empty. The last segment may be a single glob
  ("*.png"), expanded with pathlib; "**" recursion and wildcards in other segments are
  errors. A declaration that matches nothing is a missing artifact and fails the action.
* args - optional JSON object recorded verbatim in provenance; it is never merged into argv.

Validators are toolpack-level and apply to the declared artifacts of every action. Common
keys are id, kind and artifact (plus the kind-specific keys below); unknown keys are errors.

    kind    extra keys                              check
    ------  --------------------------------------  ---------------------------------------
    file    minBytes (int >= 0)                     exists; optional byte-size floor
    json    checks (non-empty list)                 each check has a dotted "path" plus
                                                    exactly one of equals, exists (bool) or
                                                    gte (number)
    text    contains (non-empty string)             UTF-8 text contains the string
    wav     minSeconds (number), minRms (> 0)       RIFF/WAVE 16-bit PCM; duration and
                                                    normalised RMS (0..1 of int16 full
                                                    scale); other encodings fail clearly
    png     minWidth, minHeight (int > 0)           PNG signature and IHDR dimensions
    glb     (none)                                  binary glTF magic and version 2

A validator whose artifact pattern matches none of an action's declared artifacts is not run
for that action. A validator that matches a declared-but-missing literal artifact fails, and
a declaration that matches nothing is a missing artifact, so the action fails either way.
Validators run after the command whether it passed or failed, so a failed run still records
what it produced.

Execution and provenance:

* Commands run with subprocess.run(..., shell=False, capture_output=True, text=True,
  encoding="utf-8", errors="replace", timeout=...). There are no retries and no model call.
* After an action every declared artifact is hash-recorded (SHA-256, bytes, exists). One
  atomic JSON state document (temp file plus os.replace) is written to
  <state_dir>/toolpacks/<toolpack>-<action>-<runId>.json with schema
  gypsy.toolpack-state/v1, the toolpack id, action, command, exit, timings, artifacts,
  validators and the declared licence/tools.
* run_toolpack runs the actions in manifest order, stops at the first failed action and
  writes one aggregate state document to <state_dir>/toolpacks/<toolpack>-<runId>.json. It
  carries the per-action summaries and the flattened artifact ledger and is the run's one
  statePath. Failures are returned in the result dict, never raised as SystemExit.

Public API:

    SCHEMA, STATE_SCHEMA, DEFAULT_TIMEOUT, VALIDATOR_KINDS, OUTPUT_LIMIT, ToolpackError
    load_manifest(path) -> dict
    validate_manifest(manifest) -> list[str]
    load_all(directory) -> dict[str, dict]
    run_action(manifest, action_id, *, project_root, state_dir, timeout_scale=1.0,
               cache=None, cache_enabled=True, force=False) -> dict
    run_toolpack(manifest, *, project_root, state_dir, timeout_scale=1.0, max_workers=1,
                 cache=None, cache_enabled=True, force=False) -> dict

An action may opt into the local content-addressed action cache with a "cache" object
(inputs, artifacts, optional toolVersions). A hit restores the declared artifacts and re-runs
the validators instead of the command; only a passing action is cached. run_toolpack(
max_workers=N) runs actions with the bounded parallel scheduler (opt-in for independent
actions) and keeps deterministic action order.
"""
from __future__ import annotations

import fnmatch
import hashlib
import json
import math
import os
import re
import struct
import subprocess
import tempfile
import time
import uuid
import wave
from datetime import datetime, timezone
from pathlib import Path

try:  # imported as workstream.toolpacks
    from . import cache as cache_spec
except ImportError:  # imported with workstream/ on sys.path (the CLI does this)
    import cache as cache_spec

SCHEMA = "gypsy.toolpack/v1"
STATE_SCHEMA = "gypsy.toolpack-state/v1"
DEFAULT_TIMEOUT = 300.0
OUTPUT_LIMIT = 4000
ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
VALIDATOR_KINDS = frozenset({"file", "json", "text", "wav", "png", "glb"})
GLOB_CHARS = frozenset("*?[")
MANIFEST_KEYS = frozenset(
    {"schema", "id", "name", "tools", "license", "actions", "validators"}
)
ACTION_KEYS = frozenset({"id", "argv", "cwd", "timeout", "artifacts", "args", "cache"})
VALIDATOR_COMMON_KEYS = frozenset({"id", "kind", "artifact"})
VALIDATOR_KIND_KEYS = {
    "file": frozenset({"minBytes"}),
    "json": frozenset({"checks"}),
    "text": frozenset({"contains"}),
    "wav": frozenset({"minSeconds", "minRms"}),
    "png": frozenset({"minWidth", "minHeight"}),
    "glb": frozenset(),
}
MISSING = object()


class ToolpackError(ValueError):
    """A toolpack manifest is unreadable, invalid, or names something that does not exist."""


# -- small helpers -----------------------------------------------------------


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(moment: datetime) -> str:
    return moment.isoformat(timespec="seconds")


def _run_id(moment: datetime) -> str:
    return moment.strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6]


def _clip(text) -> str:
    if not text:
        return ""
    value = str(text)
    if len(value) <= OUTPUT_LIMIT:
        return value
    return "...[truncated]...\n" + value[-OUTPUT_LIMIT:]


def _as_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return str(value)


def _manifest_sha256(manifest) -> str:
    payload = json.dumps(
        manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _atomic_write_json(path: Path, payload) -> None:
    """Write JSON to *path* atomically: temp file in the same directory, then replace."""
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


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _positive_scale(value) -> float:
    if isinstance(value, bool):
        raise ValueError("timeout_scale must be a positive number")
    try:
        scale = float(value)
    except (TypeError, ValueError):
        raise ValueError("timeout_scale must be a positive number") from None
    if not math.isfinite(scale) or scale <= 0:
        raise ValueError("timeout_scale must be a positive number")
    return scale


def _path_error(value, *, label, allow_glob=False):
    """Return a human-readable error for a bad repo-relative path, else None."""
    if not isinstance(value, str) or not value.strip():
        return f"{label} must be a non-empty repo-relative path string"
    try:
        path = Path(value)
    except (TypeError, ValueError):
        return f"{label} is not a usable path"
    if path.is_absolute() or path.anchor:
        return f"{label} must be repo-relative (no drive, root or absolute path)"
    if ".." in path.parts:
        return f"{label} must not escape the project root with '..'"
    parts = list(path.parts)
    for index, part in enumerate(parts):
        if not any(character in part for character in GLOB_CHARS):
            continue
        if not allow_glob:
            return f"{label} must be a literal repo-relative path (no glob)"
        if index != len(parts) - 1:
            return f"{label} may use a glob only in its last segment"
        if "**" in part:
            return f"{label} does not support recursive '**' globs"
    return None


# -- loading -----------------------------------------------------------------


def load_manifest(path) -> dict:
    """Load one toolpack JSON manifest.

    Raises ToolpackError when the file is unreadable, not JSON, or not a JSON object. This
    does not validate the schema; call validate_manifest for that.
    """
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise ToolpackError(f"{path}: unreadable: {exc}") from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ToolpackError(f"{path}: invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ToolpackError(f"{path}: manifest must be a JSON object")
    return data


def load_all(directory) -> dict:
    """Load every JSON manifest in *directory*, keyed by manifest id.

    Files are read in sorted file-name order. Raises ToolpackError on an unreadable file,
    invalid JSON, a missing string id or a duplicate id.
    """
    directory = Path(directory)
    if not directory.is_dir():
        raise ToolpackError(f"{directory}: toolpack directory does not exist")
    manifests: dict = {}
    for path in sorted(directory.glob("*.json")):
        manifest = load_manifest(path)
        toolpack_id = manifest.get("id")
        if not isinstance(toolpack_id, str) or not toolpack_id:
            raise ToolpackError(f"{path.name}: manifest has no string id")
        if toolpack_id in manifests:
            raise ToolpackError(f"{path.name}: duplicate toolpack id {toolpack_id!r}")
        manifests[toolpack_id] = manifest
    return manifests


# -- manifest validation -----------------------------------------------------


def _validate_action(action, index: int, seen_ids: set) -> list:
    label = f"actions[{index}]"
    if not isinstance(action, dict):
        return [f"{label} must be an object"]
    errors = []
    unknown = sorted(set(action) - ACTION_KEYS)
    if unknown:
        errors.append(
            f"{label}: unknown key(s) {', '.join(repr(item) for item in unknown)}; "
            f"allowed: {', '.join(sorted(ACTION_KEYS))}"
        )
    action_id = action.get("id")
    if not isinstance(action_id, str) or not ID_PATTERN.match(action_id):
        errors.append(
            f"{label}: id must be a 1-64 character string of letters, digits, '.', '_' or '-'"
        )
    elif action_id in seen_ids:
        errors.append(f"{label}: duplicate action id {action_id!r}")
    else:
        seen_ids.add(action_id)

    argv = action.get("argv")
    if not isinstance(argv, list) or not argv:
        errors.append(
            f"{label}: argv must be a non-empty list of strings (an explicit argv, never a shell string)"
        )
    else:
        for position, argument in enumerate(argv):
            if not isinstance(argument, str):
                errors.append(f"{label}: argv[{position}] must be a string")
            elif not argument:
                errors.append(f"{label}: argv[{position}] must not be empty")

    if "cwd" in action:
        error = _path_error(action["cwd"], label=f"{label}: cwd")
        if error:
            errors.append(error)

    if "timeout" in action:
        timeout = action["timeout"]
        if not _is_number(timeout) or not math.isfinite(timeout) or timeout <= 0:
            errors.append(f"{label}: timeout must be a positive number of seconds")

    if "artifacts" in action:
        artifacts = action["artifacts"]
        if not isinstance(artifacts, list):
            errors.append(f"{label}: artifacts must be a list of repo-relative paths")
        else:
            for position, artifact in enumerate(artifacts):
                error = _path_error(
                    artifact, label=f"{label}: artifacts[{position}]", allow_glob=True
                )
                if error:
                    errors.append(error)

    if "args" in action and not isinstance(action["args"], dict):
        errors.append(f"{label}: args must be an object")
    if "cache" in action:
        errors.extend(
            cache_spec.validate_config(action["cache"], label=f"{label}: cache")
        )
    return errors


def _validate_json_checks(validator, label: str) -> list:
    errors = []
    checks = validator.get("checks")
    if not isinstance(checks, list) or not checks:
        return [f"{label}: checks must be a non-empty list"]
    for index, check in enumerate(checks):
        check_label = f"{label}: checks[{index}]"
        if not isinstance(check, dict):
            errors.append(f"{check_label} must be an object")
            continue
        unknown = sorted(set(check) - {"path", "equals", "exists", "gte"})
        if unknown:
            errors.append(
                f"{check_label}: unknown key(s) {', '.join(repr(item) for item in unknown)}; "
                "allowed: equals, exists, gte, path"
            )
        path = check.get("path")
        if (
            not isinstance(path, str)
            or not path
            or any(segment == "" for segment in path.split("."))
        ):
            errors.append(
                f"{check_label}: path must be a non-empty dotted path such as 'asset.version'"
            )
        operators = [key for key in ("equals", "exists", "gte") if key in check]
        if len(operators) != 1:
            errors.append(
                f"{check_label}: must have exactly one of 'equals', 'exists' or 'gte'"
            )
        elif operators[0] == "exists" and not isinstance(check["exists"], bool):
            errors.append(f"{check_label}: exists must be true or false")
        elif operators[0] == "gte" and not _is_number(check["gte"]):
            errors.append(f"{check_label}: gte must be a number")
    return errors


def _validate_validator(validator, index: int, seen_ids: set) -> list:
    label = f"validators[{index}]"
    if not isinstance(validator, dict):
        return [f"{label} must be an object"]
    errors = []
    kind = validator.get("kind")
    if kind not in VALIDATOR_KINDS:
        errors.append(
            f"{label}: unknown kind {kind!r}; choose one of {sorted(VALIDATOR_KINDS)}"
        )
        allowed = set(VALIDATOR_COMMON_KEYS)
    else:
        allowed = set(VALIDATOR_COMMON_KEYS) | set(VALIDATOR_KIND_KEYS[kind])
    unknown = sorted(set(validator) - allowed)
    if unknown:
        errors.append(
            f"{label}: unknown key(s) {', '.join(repr(item) for item in unknown)}; "
            f"allowed: {', '.join(sorted(allowed))}"
        )
    validator_id = validator.get("id")
    if not isinstance(validator_id, str) or not ID_PATTERN.match(validator_id):
        errors.append(
            f"{label}: id must be a 1-64 character string of letters, digits, '.', '_' or '-'"
        )
    elif validator_id in seen_ids:
        errors.append(f"{label}: duplicate validator id {validator_id!r}")
    else:
        seen_ids.add(validator_id)
    error = _path_error(
        validator.get("artifact"), label=f"{label}: artifact", allow_glob=True
    )
    if error:
        errors.append(error)
    if kind not in VALIDATOR_KINDS:
        return errors
    if kind == "file":
        minimum = validator.get("minBytes")
        if "minBytes" in validator and (
            isinstance(minimum, bool)
            or not isinstance(minimum, int)
            or minimum < 0
        ):
            errors.append(f"{label}: minBytes must be an integer >= 0")
    elif kind == "json":
        errors.extend(_validate_json_checks(validator, label))
    elif kind == "text":
        contains = validator.get("contains")
        if not isinstance(contains, str) or not contains:
            errors.append(f"{label}: contains must be a non-empty string")
    elif kind == "wav":
        if "minSeconds" in validator and (
            not _is_number(validator["minSeconds"])
            or not math.isfinite(validator["minSeconds"])
            or validator["minSeconds"] < 0
        ):
            errors.append(f"{label}: minSeconds must be a number >= 0")
        if "minRms" in validator and (
            not _is_number(validator["minRms"])
            or not math.isfinite(validator["minRms"])
            or validator["minRms"] <= 0
        ):
            errors.append(f"{label}: minRms must be a number greater than 0")
    elif kind == "png":
        for key in ("minWidth", "minHeight"):
            if key in validator:
                value = validator[key]
                if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                    errors.append(f"{label}: {key} must be an integer greater than 0")
    return errors


def validate_manifest(manifest) -> list:
    """Return a list of human-readable schema errors; empty means valid."""
    if not isinstance(manifest, dict):
        return ["manifest must be a JSON object"]
    errors = []
    unknown = sorted(set(manifest) - MANIFEST_KEYS)
    if unknown:
        errors.append(
            f"unknown top-level key(s) {', '.join(repr(item) for item in unknown)}; "
            f"allowed: {', '.join(sorted(MANIFEST_KEYS))}"
        )
    if manifest.get("schema") != SCHEMA:
        errors.append(f"schema must be {SCHEMA!r}, found {manifest.get('schema')!r}")
    toolpack_id = manifest.get("id")
    if not isinstance(toolpack_id, str) or not ID_PATTERN.match(toolpack_id):
        errors.append(
            "id must be a 1-64 character string of letters, digits, '.', '_' or '-'"
        )
    name = manifest.get("name")
    if not isinstance(name, str) or not name.strip():
        errors.append("name must be a non-empty string")
    tools = manifest.get("tools")
    if not isinstance(tools, list):
        errors.append("tools must be a list of strings or objects")
    else:
        for index, tool in enumerate(tools):
            if isinstance(tool, str):
                if not tool.strip():
                    errors.append(f"tools[{index}] must be a non-empty string")
            elif not isinstance(tool, dict):
                errors.append(f"tools[{index}] must be a string or an object")
    license_value = manifest.get("license")
    if not isinstance(license_value, str) or not license_value.strip():
        errors.append("license must be a non-empty string")

    actions = manifest.get("actions")
    if not isinstance(actions, list) or not actions:
        errors.append("actions must be a non-empty list")
        actions = actions if isinstance(actions, list) else []
    seen_actions: set = set()
    for index, action in enumerate(actions):
        errors.extend(_validate_action(action, index, seen_actions))

    validators = manifest.get("validators", [])
    if not isinstance(validators, list):
        errors.append("validators must be a list of objects")
        validators = []
    seen_validators: set = set()
    for index, validator in enumerate(validators):
        errors.extend(_validate_validator(validator, index, seen_validators))
    return errors


def _require_valid(manifest) -> None:
    if not isinstance(manifest, dict):
        raise ToolpackError("manifest must be a JSON object")
    errors = validate_manifest(manifest)
    if errors:
        raise ToolpackError("invalid toolpack manifest: " + "; ".join(errors))


# -- artifact hashing and validators ----------------------------------------


def _hash_file(path: Path) -> dict:
    digest = hashlib.sha256()
    size = 0
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return {"exists": True, "sha256": digest.hexdigest(), "bytes": size}


def _expand_artifacts(specs, project_root: Path) -> list:
    """Expand declared artifact paths (single trailing glob allowed) into ledger entries."""
    entries = []
    for spec in specs:
        rel = Path(spec).as_posix()
        parts = list(Path(spec).parts)
        last = parts[-1] if parts else ""
        if any(character in last for character in GLOB_CHARS):
            parent = Path(*parts[:-1]) if len(parts) > 1 else Path(".")
            matches = []
            try:
                matches = sorted(
                    path for path in (project_root / parent).glob(last) if path.is_file()
                )
            except (OSError, ValueError):
                matches = []
            if not matches:
                entries.append(
                    {
                        "path": rel,
                        "declaredAs": rel,
                        "exists": False,
                        "sha256": None,
                        "bytes": None,
                    }
                )
                continue
            for match in matches:
                try:
                    match_rel = match.relative_to(project_root).as_posix()
                except ValueError:
                    match_rel = match.as_posix()
                entry = _hash_file(match)
                entry["path"] = match_rel
                entry["declaredAs"] = rel
                entries.append(entry)
        else:
            path = project_root / spec
            entry = {
                "path": rel,
                "declaredAs": rel,
                "exists": path.is_file(),
                "sha256": None,
                "bytes": None,
            }
            if entry["exists"]:
                entry.update(_hash_file(path))
            entries.append(entry)
    return entries


def _short(value) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        text = repr(value)
    return text if len(text) <= 160 else text[:157] + "..."


def _lookup(document, dotted: str):
    current = document
    for segment in dotted.split("."):
        if isinstance(current, dict):
            if segment not in current:
                return MISSING
            current = current[segment]
        elif isinstance(current, list):
            try:
                index = int(segment)
            except (TypeError, ValueError):
                return MISSING
            if index < 0 or index >= len(current):
                return MISSING
            current = current[index]
        else:
            return MISSING
    return current


def _check_file(path: Path, validator) -> tuple:
    size = path.stat().st_size
    details = {"bytes": size}
    minimum = validator.get("minBytes")
    if minimum is not None:
        details["minBytes"] = minimum
        if size < minimum:
            return False, f"file is {size} bytes, below minBytes {minimum}", details
    return True, None, details


def _check_json(path: Path, validator) -> tuple:
    try:
        document = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError) as exc:
        return False, f"unreadable JSON: {exc}", {}
    except json.JSONDecodeError as exc:
        return False, f"invalid JSON: {exc}", {}
    failures = []
    checks = validator.get("checks") or []
    for check in checks:
        dotted = check.get("path", "")
        actual = _lookup(document, dotted)
        if "equals" in check:
            expected = check["equals"]
            if actual is MISSING:
                failures.append(f"{dotted}: missing (expected {_short(expected)})")
            elif actual != expected:
                failures.append(
                    f"{dotted}: expected {_short(expected)}, found {_short(actual)}"
                )
        elif "exists" in check:
            expected = bool(check["exists"])
            present = actual is not MISSING
            if present != expected:
                failures.append(
                    f"{dotted}: expected exists={expected}, found exists={present}"
                )
        elif "gte" in check:
            expected = check["gte"]
            if actual is MISSING:
                failures.append(f"{dotted}: missing (expected >= {_short(expected)})")
            elif isinstance(actual, bool) or not isinstance(actual, (int, float)):
                failures.append(
                    f"{dotted}: expected a number >= {_short(expected)}, found {_short(actual)}"
                )
            elif actual < expected:
                failures.append(
                    f"{dotted}: expected >= {_short(expected)}, found {_short(actual)}"
                )
    details = {"checks": len(checks), "failed": len(failures)}
    return not failures, ("; ".join(failures) or None), details


def _check_text(path: Path, validator) -> tuple:
    try:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError as exc:
        return False, f"unreadable text: {exc}", {}
    needle = validator["contains"]
    details = {"chars": len(text), "contains": needle}
    if needle not in text:
        return False, f"text does not contain {_short(needle)}", details
    return True, None, details


def _check_wav(path: Path, validator) -> tuple:
    try:
        with wave.open(str(path), "rb") as handle:
            channels = handle.getnchannels()
            sample_width = handle.getsampwidth()
            frame_rate = handle.getframerate()
            frame_count = handle.getnframes()
            compression = handle.getcomptype()
            frames = handle.readframes(frame_count)
    except (wave.Error, OSError, EOFError) as exc:
        return False, f"unreadable WAV: {exc}", {}
    if compression != "NONE" or sample_width != 2:
        return (
            False,
            "unsupported WAV: expected 16-bit PCM "
            f"(comptype=NONE, sampwidth=2); got comptype={compression!r}, "
            f"sampwidth={sample_width}, channels={channels}, framerate={frame_rate}",
            {
                "comptype": compression,
                "sampwidth": sample_width,
                "channels": channels,
                "framerate": frame_rate,
            },
        )
    seconds = (frame_count / float(frame_rate)) if frame_rate else 0.0
    details = {
        "seconds": round(seconds, 6),
        "channels": channels,
        "framerate": frame_rate,
        "frames": frame_count,
    }
    minimum_seconds = validator.get("minSeconds")
    if minimum_seconds is not None:
        details["minSeconds"] = minimum_seconds
        if seconds < minimum_seconds:
            return (
                False,
                f"WAV is {seconds:.3f}s, below minSeconds {minimum_seconds:g}",
                details,
            )
    if "minRms" in validator:
        usable = frames[: len(frames) - (len(frames) % 2)]
        total = 0
        count = 0
        for (sample,) in struct.iter_unpack("<h", usable):
            total += sample * sample
            count += 1
        rms = (math.sqrt(total / count) / 32768.0) if count else 0.0
        details["rms"] = round(rms, 6)
        details["minRms"] = validator["minRms"]
        if rms < validator["minRms"]:
            return (
                False,
                f"WAV RMS {rms:.4f} is below minRms {validator['minRms']:g}",
                details,
            )
    return True, None, details


def _check_png(path: Path, validator) -> tuple:
    try:
        with open(path, "rb") as handle:
            header = handle.read(24)
    except OSError as exc:
        return False, f"unreadable PNG: {exc}", {}
    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
        return False, "not a PNG: bad signature", {}
    if header[8:12] != b"\x00\x00\x00\x0d" or header[12:16] != b"IHDR":
        return False, "not a PNG: first chunk is not a 13-byte IHDR", {}
    width = int.from_bytes(header[16:20], "big")
    height = int.from_bytes(header[20:24], "big")
    details = {"width": width, "height": height}
    if validator.get("minWidth") is not None and width < validator["minWidth"]:
        return (
            False,
            f"PNG width {width} is below minWidth {validator['minWidth']}",
            details,
        )
    if validator.get("minHeight") is not None and height < validator["minHeight"]:
        return (
            False,
            f"PNG height {height} is below minHeight {validator['minHeight']}",
            details,
        )
    return True, None, details


def _check_glb(path: Path, validator) -> tuple:
    try:
        with open(path, "rb") as handle:
            header = handle.read(12)
    except OSError as exc:
        return False, f"unreadable GLB: {exc}", {}
    if len(header) < 12 or header[:4] != b"glTF":
        return False, "not a GLB: bad magic (expected 'glTF')", {}
    version = int.from_bytes(header[4:8], "little")
    details = {"version": version}
    if version != 2:
        return False, f"GLB version must be 2, found {version}", details
    return True, None, details


_CHECKS = {
    "file": _check_file,
    "json": _check_json,
    "text": _check_text,
    "wav": _check_wav,
    "png": _check_png,
    "glb": _check_glb,
}


def _validator_targets(validator, artifacts) -> list:
    pattern = Path(validator["artifact"]).as_posix()
    has_glob = any(character in pattern for character in GLOB_CHARS)
    targets = []
    seen = set()
    for entry in artifacts:
        path = entry["path"]
        matched = fnmatch.fnmatchcase(path, pattern) if has_glob else path == pattern
        if not matched and not entry["exists"] and entry["declaredAs"] == pattern:
            matched = True
        if matched and path not in seen:
            seen.add(path)
            targets.append(entry)
    return targets


def _check_validator(validator, entry, project_root: Path) -> dict:
    result = {
        "id": validator["id"],
        "kind": validator["kind"],
        "artifact": Path(validator["artifact"]).as_posix(),
        "target": entry["path"],
        "passed": False,
        "error": None,
        "details": {},
    }
    if not entry["exists"]:
        result["error"] = f"artifact missing: {entry['path']}"
        return result
    path = project_root / entry["path"]
    if not path.is_file():
        result["error"] = f"artifact missing: {entry['path']}"
        return result
    try:
        passed, error, details = _CHECKS[validator["kind"]](path, validator)
    except Exception as exc:  # noqa: BLE001 - a validator failure is state, not a crash
        passed = False
        error = f"{validator['kind']} validator error: {type(exc).__name__}: {exc}"
        details = {}
    result["passed"] = bool(passed)
    result["error"] = error
    result["details"] = details
    return result


def _run_validators(validators, artifacts, project_root: Path) -> list:
    results = []
    for validator in validators:
        for entry in _validator_targets(validator, artifacts):
            results.append(_check_validator(validator, entry, project_root))
    return results


# -- command execution -------------------------------------------------------


def _execute(argv, cwd: Path, timeout: float) -> dict:
    started = time.time()
    try:
        completed = subprocess.run(
            list(argv),
            cwd=str(cwd),
            shell=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=float(timeout),
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "exit": None,
            "stdout": _clip(_as_text(exc.stdout)),
            "stderr": _clip(_as_text(exc.stderr)),
            "seconds": round(time.time() - started, 3),
            "timedOut": True,
            "error": f"timeout after {float(timeout):g}s",
        }
    except FileNotFoundError as exc:
        return {
            "exit": None,
            "stdout": "",
            "stderr": "",
            "seconds": round(time.time() - started, 3),
            "timedOut": False,
            "error": f"command not found: {exc}",
        }
    except OSError as exc:
        return {
            "exit": None,
            "stdout": "",
            "stderr": "",
            "seconds": round(time.time() - started, 3),
            "timedOut": False,
            "error": f"could not run command: {exc}",
        }
    return {
        "exit": completed.returncode,
        "stdout": _clip(completed.stdout),
        "stderr": _clip(completed.stderr),
        "seconds": round(time.time() - started, 3),
        "timedOut": False,
        "error": None,
    }


def _action_state_path(state_dir: Path, toolpack_id: str, action_id: str, run_id: str) -> Path:
    return Path(state_dir) / "toolpacks" / f"{toolpack_id}-{action_id}-{run_id}.json"


def _toolpack_state_path(state_dir: Path, toolpack_id: str, run_id: str) -> Path:
    return Path(state_dir) / "toolpacks" / f"{toolpack_id}-{run_id}.json"


# -- public runners ----------------------------------------------------------


def _cache_action_argv(action: dict) -> list:
    try:
        args = json.dumps(
            action.get("args") or {},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
    except (TypeError, ValueError):
        args = repr(action.get("args"))
    return [str(token) for token in action.get("argv") or []] + [args]


def run_action(
    manifest,
    action_id,
    *,
    project_root,
    state_dir,
    timeout_scale=1.0,
    cache=None,
    cache_enabled=True,
    force=False,
) -> dict:
    """Execute one action of *manifest* and return a JSON-safe result dict.

    The command runs with shell=False, then the declared artifacts are hashed and the
    toolpack validators that target them are run. Durable provenance is written atomically
    to <state_dir>/toolpacks/<toolpack>-<action>-<runId>.json and returned as statePath.
    An action with a "cache" object is cached by identity/argv/cwd/platform/tool versions/
    input hashes: a hit restores the declared artifacts and re-runs the validators instead of
    the command, and only a passing action is stored. cache=ActionCache shares one cache
    across a parallel run; cache_enabled=False disables it; force=True bypasses the lookup.
    Raises ToolpackError for an invalid manifest, an invalid cache config or an unknown action
    id; a failed command is a result with passed=False, never an exception.
    """
    _require_valid(manifest)
    scale = _positive_scale(timeout_scale)
    actions = manifest["actions"]
    action = None
    for candidate in actions:
        if candidate.get("id") == action_id:
            action = candidate
            break
    if action is None:
        raise ToolpackError(
            f"toolpack {manifest['id']!r} has no action {action_id!r}"
        )

    project_root = Path(project_root).resolve()
    state_dir = Path(state_dir)
    if cache is not None and not isinstance(cache, cache_spec.ActionCache):
        raise ValueError("cache must be a cache.ActionCache instance or None")
    cache_obj = cache if cache is not None else cache_spec.ActionCache(
        state_dir, enabled=bool(cache_enabled)
    )
    cache_config = None
    if action.get("cache") is not None:
        try:
            cache_config = cache_spec.resolve_config(
                action["cache"],
                project_root=project_root,
                label=f"action {action_id!r} cache",
            )
        except cache_spec.CacheError as exc:
            raise ToolpackError(str(exc)) from exc

    started_moment = _utc_now()
    started_clock = time.time()
    run_id = _run_id(started_moment)
    toolpack_id = manifest["id"]
    cwd_rel = Path(action.get("cwd") or ".").as_posix()
    cwd_path = (project_root / cwd_rel).resolve()
    if not cwd_path.is_relative_to(project_root):
        raise ToolpackError(
            f"action {action_id!r}: cwd {cwd_rel!r} escapes the project root"
        )
    timeout = float(action.get("timeout") or DEFAULT_TIMEOUT) * scale
    manifest_sha = _manifest_sha256(manifest)

    cache_key = None
    cache_descriptor = None
    cache_restored = []
    cache_error = None
    cache_active = bool(
        cache_config and cache_config["enabled"] and cache_obj.enabled
    )
    if cache_config is not None and not cache_obj.enabled:
        cache_error = "cache disabled for this run"
    elif cache_config is not None and not cache_config["enabled"]:
        cache_error = "cache disabled by the action manifest"
    if cache_active:
        cache_inputs = cache_spec.input_hashes(
            project_root, cache_config["inputs"]
        )
        cache_key, cache_descriptor = cache_spec.action_key(
            identity={
                "kind": "toolpack-action",
                "toolpack": toolpack_id,
                "action": action_id,
                "manifestSha256": manifest_sha,
            },
            argv=_cache_action_argv(action),
            cwd=cwd_rel,
            inputs=cache_inputs,
            artifacts=cache_config["artifacts"],
            tool_versions=cache_config["toolVersions"],
            extra={"tools": manifest.get("tools")},
        )
        if not force:
            cached_entry = cache_obj.lookup(cache_key)
            if cached_entry is not None:
                restored_ok, restored_paths, restore_error = cache_obj.restore(
                    cached_entry, project_root
                )
                if restored_ok:
                    artifacts = _expand_artifacts(
                        action.get("artifacts") or [], project_root
                    )
                    validators = _run_validators(
                        manifest.get("validators") or [], artifacts, project_root
                    )
                    if all(item["passed"] for item in validators):
                        finished_moment = _utc_now()
                        stored_result = cached_entry.get("result") or {}
                        hit_document = {
                            "schema": STATE_SCHEMA,
                            "scope": "action",
                            "toolpack": toolpack_id,
                            "toolpackName": manifest.get("name"),
                            "action": action_id,
                            "runId": run_id,
                            "manifestSha256": manifest_sha,
                            "generated": _iso(finished_moment),
                            "startedAt": _iso(started_moment),
                            "finishedAt": _iso(finished_moment),
                            "durationSeconds": round(time.time() - started_clock, 3),
                            "passed": True,
                            "timedOut": False,
                            "seconds": 0.0,
                            "timeoutSeconds": timeout,
                            "command": {
                                "argv": list(action["argv"]),
                                "cwd": cwd_rel,
                                "cacheHit": True,
                            },
                            "exit": 0,
                            "stdout": stored_result.get("stdout")
                            or "cache hit: restored "
                            + str(len(restored_paths))
                            + " artifact(s)",
                            "stderr": stored_result.get("stderr") or "",
                            "args": action.get("args") or {},
                            "artifacts": artifacts,
                            "validators": validators,
                            "license": manifest.get("license"),
                            "tools": manifest.get("tools"),
                            "cache": {
                                "key": cache_key,
                                "hit": True,
                                "stored": False,
                                "restored": restored_paths,
                                "error": None,
                            },
                            "errors": [],
                        }
                        state_path = _action_state_path(
                            state_dir, toolpack_id, action_id, run_id
                        )
                        _atomic_write_json(state_path, hit_document)
                        hit_result = dict(hit_document)
                        hit_result["statePath"] = str(state_path)
                        return hit_result
                    cache_error = "restored artifacts failed validators"
                else:
                    cache_error = restore_error

    if cwd_path.is_dir():
        command = _execute(action["argv"], cwd_path, timeout)
    else:
        command = {
            "exit": None,
            "stdout": "",
            "stderr": "",
            "seconds": 0.0,
            "timedOut": False,
            "error": f"cwd does not exist: {cwd_rel}",
        }
    artifacts = _expand_artifacts(action.get("artifacts") or [], project_root)
    validators = _run_validators(
        manifest.get("validators") or [], artifacts, project_root
    )

    errors = []
    if command["error"]:
        errors.append(command["error"])
    elif command["exit"] != 0:
        errors.append(f"command exited {command['exit']}")
    missing = [entry["path"] for entry in artifacts if not entry["exists"]]
    if missing:
        errors.append("missing declared artifact(s): " + ", ".join(missing))
    failed_validators = [
        f"{validator['id']} on {validator['target']}: {validator['error']}"
        for validator in validators
        if not validator["passed"]
    ]
    if failed_validators:
        errors.append("failed validator(s): " + "; ".join(failed_validators))
    passed = not errors

    cache_info = None
    if cache_config is not None:
        cache_stored = False
        if passed and cache_active and cache_key:
            stored_entry = cache_obj.store(
                cache_key,
                descriptor=cache_descriptor,
                project_root=project_root,
                artifacts=cache_config["artifacts"],
                result={
                    "exit": command["exit"],
                    "stdout": command["stdout"],
                    "stderr": command["stderr"],
                    "seconds": command["seconds"],
                },
            )
            cache_stored = stored_entry is not None
        cache_info = {
            "key": cache_key,
            "hit": False,
            "stored": cache_stored,
            "restored": [],
            "error": cache_error,
        }

    document = {
        "schema": STATE_SCHEMA,
        "scope": "action",
        "toolpack": toolpack_id,
        "toolpackName": manifest.get("name"),
        "action": action_id,
        "runId": run_id,
        "manifestSha256": manifest_sha,
        "generated": _iso(_utc_now()),
        "startedAt": _iso(started_moment),
        "finishedAt": _iso(_utc_now()),
        "durationSeconds": round(time.time() - started_clock, 3),
        "passed": passed,
        "timedOut": command["timedOut"],
        "seconds": command["seconds"],
        "timeoutSeconds": timeout,
        "command": {
            "argv": list(action["argv"]),
            "cwd": cwd_rel,
        },
        "exit": command["exit"],
        "stdout": command["stdout"],
        "stderr": command["stderr"],
        "args": action.get("args") or {},
        "artifacts": artifacts,
        "validators": validators,
        "license": manifest.get("license"),
        "tools": manifest.get("tools"),
        "errors": errors,
    }
    if cache_info is not None:
        document["cache"] = cache_info
    state_path = _action_state_path(state_dir, toolpack_id, action_id, run_id)
    _atomic_write_json(state_path, document)
    result = dict(document)
    result["statePath"] = str(state_path)
    return result


def _action_summary(action_id, result=None, *, note=None) -> dict:
    if result is None:
        return {
            "action": action_id,
            "status": "not-run",
            "passed": None,
            "exit": None,
            "seconds": 0.0,
            "timedOut": False,
            "statePath": None,
            "artifacts": 0,
            "validators": 0,
            "label": note or "not run",
            "errors": [],
            "cache": None,
        }
    return {
        "action": action_id,
        "status": "passed" if result.get("passed") else "failed",
        "passed": result.get("passed"),
        "exit": result.get("exit"),
        "seconds": result.get("seconds"),
        "timedOut": result.get("timedOut"),
        "statePath": result.get("statePath"),
        "artifacts": len(result.get("artifacts") or []),
        "validators": len(result.get("validators") or []),
        "label": None,
        "errors": list(result.get("errors") or []),
        "cache": result.get("cache"),
    }


def run_toolpack(
    manifest,
    *,
    project_root,
    state_dir,
    timeout_scale=1.0,
    max_workers=1,
    cache=None,
    cache_enabled=True,
    force=False,
) -> dict:
    """Run every action of *manifest* and return one aggregate result dict.

    max_workers=1 keeps manifest order and stops at the first failed action (later actions
    are not-run). max_workers=2..8 runs the actions through the bounded parallel scheduler,
    which is opt-in for independent actions: results keep manifest order and a failure
    cancels actions that have not started yet. Action state documents are written per action
    and one aggregate document (the run's one statePath) carries the artifact ledger, the
    per-action summaries, the parallel status and the cache counter delta. Raises
    ToolpackError for an invalid manifest before running anything.
    """
    _require_valid(manifest)
    scale = _positive_scale(timeout_scale)
    try:
        workers = cache_spec.worker_count(max_workers)
    except cache_spec.CacheError as exc:
        raise ToolpackError(str(exc)) from exc
    project_root = Path(project_root).resolve()
    state_dir = Path(state_dir)
    if cache is not None and not isinstance(cache, cache_spec.ActionCache):
        raise ValueError("cache must be a cache.ActionCache instance or None")
    cache_obj = cache if cache is not None else cache_spec.ActionCache(
        state_dir, enabled=bool(cache_enabled)
    )
    cache_before = cache_obj.counters()
    started_moment = _utc_now()
    started_clock = time.time()
    run_id = _run_id(started_moment)
    toolpack_id = manifest["id"]
    actions = manifest["actions"]

    summaries = []
    artifacts = []
    validators = []
    errors = []
    cancelled_actions = []
    parallel_cancelled = False

    def _absorb(action_id: str, result: dict) -> None:
        for entry in result.get("artifacts") or []:
            artifacts.append({"action": action_id, **entry})
        for validator in result.get("validators") or []:
            validators.append({"action": action_id, **validator})
        if not result.get("passed"):
            errors.append(
                f"action {action_id!r} failed: "
                + "; ".join(result.get("errors") or [])
            )

    if workers == 1:
        stopped = False
        failure_reason = None
        for action in actions:
            action_id = action["id"]
            if stopped:
                summaries.append(
                    _action_summary(
                        action_id, note="not run: " + str(failure_reason)
                    )
                )
                continue
            result = run_action(
                manifest,
                action_id,
                project_root=project_root,
                state_dir=state_dir,
                timeout_scale=scale,
                cache=cache_obj,
                force=force,
            )
            summaries.append(_action_summary(action_id, result))
            _absorb(action_id, result)
            if not result["passed"]:
                stopped = True
                failure_reason = f"action {action_id!r} failed"
    else:

        def _run_action(index, action):
            try:
                return run_action(
                    manifest,
                    action["id"],
                    project_root=project_root,
                    state_dir=state_dir,
                    timeout_scale=scale,
                    cache=cache_obj,
                    force=force,
                )
            except Exception as exc:  # a crashed worker becomes deterministic state
                return {
                    "action": action["id"],
                    "passed": False,
                    "exit": None,
                    "seconds": 0.0,
                    "timedOut": False,
                    "artifacts": [],
                    "validators": [],
                    "errors": [f"{type(exc).__name__}: {exc}"],
                    "statePath": None,
                    "cache": None,
                }

        parallel = cache_spec.run_parallel(
            actions, _run_action, max_workers=workers, cancel_on_failure=True
        )
        parallel_cancelled = bool(parallel["cancelled"])
        results = parallel["results"]
        first_failed = None
        for index, action in enumerate(actions):
            action_id = action["id"]
            result = results[index]
            if result is None:
                cancelled_actions.append(action_id)
                note = "not run: cancelled"
                if first_failed:
                    note += f" after action {first_failed!r} failed"
                summaries.append(_action_summary(action_id, note=note))
                continue
            summaries.append(_action_summary(action_id, result))
            _absorb(action_id, result)
            if not result.get("passed") and first_failed is None:
                first_failed = action_id

    failed = any(summary["status"] == "failed" for summary in summaries)
    not_run = any(summary["status"] == "not-run" for summary in summaries)
    finished_moment = _utc_now()
    parallel_info = {
        "requestedWorkers": workers,
        "workers": workers,
        "cancelled": parallel_cancelled,
        "cancelledActions": cancelled_actions,
        "log": [f"{summary['action']}: {summary['status']}" for summary in summaries],
    }
    cache_summary = {
        "enabled": cache_obj.enabled,
        **cache_spec.counters_delta(cache_before, cache_obj.counters()),
    }
    document = {
        "schema": STATE_SCHEMA,
        "scope": "toolpack",
        "toolpack": toolpack_id,
        "toolpackName": manifest.get("name"),
        "runId": run_id,
        "manifestSha256": _manifest_sha256(manifest),
        "generated": _iso(finished_moment),
        "startedAt": _iso(started_moment),
        "finishedAt": _iso(finished_moment),
        "durationSeconds": round(time.time() - started_clock, 3),
        "passed": not failed and not not_run,
        "timeoutScale": scale,
        "actionOrder": [action["id"] for action in actions],
        "actions": summaries,
        "artifacts": artifacts,
        "validators": validators,
        "parallel": parallel_info,
        "cache": cache_summary,
        "license": manifest.get("license"),
        "tools": manifest.get("tools"),
        "errors": errors,
    }
    state_path = _toolpack_state_path(state_dir, toolpack_id, run_id)
    _atomic_write_json(state_path, document)
    result = dict(document)
    result["statePath"] = str(state_path)
    return result
