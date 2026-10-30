#!/usr/bin/env python3
"""Deterministic, read-only asset registry for Gypsy Studio.

A scan walks the configured asset roots, fingerprints every non-ignored file and reports what
is there. It is read-only: it never renames, imports, moves or rewrites an asset. It is a
registry of what exists, not a build pipeline.

What a scan reports (schema gypsy.asset-registry/v1)
----------------------------------------------------
For every asset: path (repository-relative POSIX when the file is inside the checkout, an
absolute POSIX path otherwise), the configured root it came from, bytes, SHA-256, media kind
(image, model, audio, text or binary), modified time (UTC, seconds), a duplicate flag, the
provenance entry (if any) and per-asset warnings.

Determinism and ignore rules
----------------------------
Assets are sorted by path; duplicate groups, roots and warning lists are sorted or emitted in
a fixed order. Two scans of an unchanged tree differ only in the top-level "generated" value.
The scan prunes generated, imported and dependency directories (IGNORED_DIRS: Library, obj,
build, import/imports, Temp, Logs, node_modules, engine caches, plus every directory whose name
starts with "."), ignores generated engine metadata and temp files (IGNORED_FILE_SUFFIXES:
.meta, .import, .uid, .tmp, .bak, .swp, .log), ignores Windows/macOS metadata files
(IGNORED_FILE_NAMES) and hidden files. A configured root that does not exist is a warning, not
a crash; a root that exists but is not a directory is recorded as an error. The registry sidecar
file itself is never listed as an asset.

Media kind is decided by the file extension only, from a documented table (MEDIA_EXTENSIONS);
an unknown or missing extension is "binary". This is a classification, not content sniffing,
and it is stated rather than guessed.

Duplicate content
-----------------
Files are grouped by SHA-256. Every content group with more than one path is reported under
"duplicates" and every member is marked duplicate=true. Duplicates are reported, never merged
or deleted: the same bytes under assets/ and game/assets/ is exactly what a real import copy
looks like and the registry should show it.

Provenance and licence (optional sidecar)
-----------------------------------------
An optional sidecar registry, by default assets/registry/provenance.json, can record
provenance/licence per asset. Schema gypsy.asset-provenance/v1:

    {
      "schema": "gypsy.asset-provenance/v1",
      "assets": [
        {"path": "assets/hero/wayfarer.fbx", "license": "CC0-1.0",
         "source": "Blender-generated in this repository", "author": "Gypsy build",
         "approved": true, "notes": "..."}
      ]
    }

The sidecar is optional: when it is missing, malformed or has the wrong schema the scan still
runs and reports a warning; it never turns unknown provenance into a pass. When the sidecar
loads, an asset with no entry gets a per-asset warning, an entry without a license gets a
per-asset warning, and an entry for a path that is not in the scanned roots gets a registry
warning. The full ADR-002 D5 provenance record (tool id/version, generation parameters, source
hash, AI flag, approver and date) is NOT implemented here; this scan extracts what the sidecar
declares and says so. Do not read a reported license as a legal clearance.

Optional state
--------------
python workstream/assets.py --save-state writes the payload to workstream/state/assets.json
by default (same schema, atomic temp file + os.replace). It is a cache for comparing scans,
never a source of truth: the next scan re-reads the tree, and stale state must not be shown as
current. The state file is gitignored under workstream/state/. load_state validates the whole
payload and refuses anything it cannot trust.

Wiring: workstream/gypsy.py and the dashboard are not modified by this module (the Lead owns
that integration). The module is importable (import assets) and has a thin standalone entry
point.

Public API
----------
    SCHEMA, PROVENANCE_SCHEMA, MEDIA_KINDS, MEDIA_EXTENSIONS, IGNORED_DIRS,
    IGNORED_FILE_SUFFIXES, IGNORED_FILE_NAMES, DEFAULT_ROOTS, DEFAULT_REGISTRY,
    DEFAULT_STATE, AssetError
    media_kind(path_or_name) -> str
    sha256_file(path) -> str
    scan(roots=None, registry=None) -> dict
    validate_payload(payload) -> list[str]
    to_json(payload, indent=2) -> str
    save_state(payload, path=None) -> Path
    load_state(path=None) -> dict
    render_summary(payload) -> str
    main(argv=None) -> int

Usage:
    python workstream/assets.py [--root PATH ...] [--registry PATH] [--json]
    python workstream/assets.py --validate [--json]
    python workstream/assets.py --save-state [PATH]
    python workstream/assets.py --state PATH [--json]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import gypsy

SCHEMA = "gypsy.asset-registry/v1"
PROVENANCE_SCHEMA = "gypsy.asset-provenance/v1"
MEDIA_KINDS = ("image", "model", "audio", "text", "binary")

DEFAULT_ROOTS = (
    gypsy.REPO_ROOT / "assets",
    gypsy.REPO_ROOT / "game" / "assets",
    gypsy.REPO_ROOT / "unity" / "LeftBehind" / "Assets",
)
DEFAULT_REGISTRY = gypsy.REPO_ROOT / "assets" / "registry" / "provenance.json"
DEFAULT_STATE = gypsy.STATE_DIR / "assets.json"

HASH_CHUNK = 1024 * 1024

# Directories that are generated, imported or dependencies, compared casefolded.
IGNORED_DIRS = frozenset(
    {
        "library",
        "obj",
        "build",
        "import",
        "imports",
        "temp",
        "logs",
        "node_modules",
        "__pycache__",
        ".git",
        ".godot",
        ".cache",
        "hf-cache",
        "intermediate",
        "saved",
        "binaries",
        "deriveddatacache",
        "userpresettings",
    }
)

# Generated engine metadata and editor/temp files, compared casefolded.
IGNORED_FILE_SUFFIXES = (".meta", ".import", ".uid", ".tmp", ".bak", ".swp", ".log")
IGNORED_FILE_NAMES = frozenset({".ds_store", "thumbs.db", "desktop.ini"})

MEDIA_EXTENSIONS = {
    "image": frozenset(
        {
            ".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tga", ".tif", ".tiff",
            ".exr", ".hdr", ".dds", ".psd", ".svg", ".ico", ".ktx2",
        }
    ),
    "model": frozenset(
        {
            ".glb", ".gltf", ".fbx", ".obj", ".blend", ".dae", ".usd", ".usda", ".usdc",
            ".usdz", ".stl", ".ply", ".3ds", ".ma", ".mb", ".abc",
        }
    ),
    "audio": frozenset(
        {".wav", ".mp3", ".ogg", ".flac", ".aif", ".aiff", ".m4a", ".opus", ".wma", ".aac"}
    ),
    "text": frozenset(
        {
            ".md", ".txt", ".json", ".yaml", ".yml", ".csv", ".tsv", ".py", ".gd", ".cs",
            ".js", ".ts", ".shader", ".gdshader", ".hlsl", ".glsl", ".cginc", ".unity",
            ".tscn", ".tres", ".godot", ".cfg", ".ini", ".toml", ".xml", ".html", ".css",
            ".sh", ".ps1", ".bat", ".cmd", ".psm1", ".h", ".c", ".cc", ".cpp", ".hpp",
            ".rml",
        }
    ),
}

SHA256_LENGTH = 64


class AssetError(ValueError):
    """A scan input, payload or state file is unreadable, invalid or not JSON-safe."""


def _sha256_text_is_hex(value: str) -> bool:
    if not isinstance(value, str) or len(value) != SHA256_LENGTH:
        return False
    return all(character in "0123456789abcdef" for character in value)


def _utc_now() -> str:
    return gypsy.now_iso()


def _iso_utc(timestamp: float) -> str:
    return (
        datetime.fromtimestamp(timestamp, tz=timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _posix(value: str) -> str:
    return value.replace("\\", "/")


def _repo_relative(path: Path, repo_root: Path) -> str:
    """Return path relative to the repository when possible, POSIX, else absolute POSIX."""
    try:
        return path.resolve().relative_to(repo_root).as_posix()
    except (OSError, ValueError):
        return _posix(str(path.resolve() if path.is_absolute() else path))


def _label(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root).as_posix()
    except (OSError, ValueError):
        return _posix(str(path.resolve()))


def media_kind(path_or_name) -> str:
    """Classify by extension only; unknown or missing extensions are binary."""
    suffix = Path(str(path_or_name)).suffix.casefold()
    if suffix:
        for kind in ("image", "model", "audio", "text"):
            if suffix in MEDIA_EXTENSIONS[kind]:
                return kind
    return "binary"


def sha256_file(path) -> str:
    """Return the lowercase SHA-256 of a file, read in chunks (binary; no text decode)."""
    digest = hashlib.sha256()
    with open(Path(path), "rb") as handle:
        for chunk in iter(lambda: handle.read(HASH_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _ignored_dir(name: str) -> bool:
    lowered = name.casefold()
    return name.startswith(".") or lowered in IGNORED_DIRS


def _ignored_file(name: str) -> bool:
    lowered = name.casefold()
    if name.startswith(".") or name.endswith("~"):
        return True
    if lowered in IGNORED_FILE_NAMES:
        return True
    return any(lowered.endswith(suffix) for suffix in IGNORED_FILE_SUFFIXES)


def _normalise_registry_key(value: str) -> str:
    text = _posix(value.strip())
    while text.startswith("./"):
        text = text[2:]
    return text


def _reject_constant(value):
    raise ValueError("non-finite number {!r} is not allowed in the registry".format(value))


def _describe_roots(roots) -> list:
    """Resolve, sort and de-duplicate configured roots; return (paths, warnings)."""
    candidates = []
    for item in roots if roots else DEFAULT_ROOTS:
        path = Path(item).expanduser()
        try:
            resolved = path.resolve()
        except OSError as exc:
            raise AssetError("asset root cannot be resolved: {}: {}".format(item, exc)) from exc
        candidates.append(resolved)
    warnings = []
    unique = []
    seen = set()
    for resolved in sorted(candidates, key=lambda candidate: _posix(str(candidate))):
        key = _posix(str(resolved)).casefold()
        if key in seen:
            warnings.append("duplicate asset root ignored: {}".format(_posix(str(resolved))))
            continue
        seen.add(key)
        unique.append(resolved)
    for index, first in enumerate(unique):
        for second in unique[index + 1:]:
            if second == first or first in second.parents:
                warnings.append(
                    "overlapping asset roots: {} is inside {}; files are counted once".format(
                        _posix(str(second)), _posix(str(first))
                    )
                )
            elif second in first.parents:
                warnings.append(
                    "overlapping asset roots: {} is inside {}; files are counted once".format(
                        _posix(str(first)), _posix(str(second))
                    )
                )
    return unique, warnings


def _load_registry(path: Path):
    """Load the optional sidecar; return (entries, info). Never raises for bad files."""
    info = {
        "path": _repo_relative(path, gypsy.REPO_ROOT),
        "found": path.is_file(),
        "schema": None,
        "entries": 0,
        "loaded": False,
        "warnings": [],
    }
    entries = {}
    if not path.is_file():
        info["warnings"].append(
            "provenance registry not found; provenance is unknown for every asset"
        )
        return entries, info
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        info["warnings"].append("provenance registry is unreadable: {}".format(exc))
        return entries, info
    try:
        data = json.loads(text, parse_constant=_reject_constant)
    except json.JSONDecodeError as exc:
        info["warnings"].append("provenance registry is not valid JSON: {}".format(exc))
        return entries, info
    except ValueError as exc:
        info["warnings"].append("provenance registry is not valid: {}".format(exc))
        return entries, info
    if not isinstance(data, dict):
        info["warnings"].append("provenance registry must be a JSON object")
        return entries, info
    schema = data.get("schema")
    if schema != PROVENANCE_SCHEMA:
        info["warnings"].append(
            "provenance registry schema must be {!r}, found {!r}".format(
                PROVENANCE_SCHEMA, schema
            )
        )
        return entries, info
    info["schema"] = schema
    raw = data.get("assets")
    if not isinstance(raw, list):
        info["warnings"].append("provenance registry assets must be a list")
        return entries, info
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            info["warnings"].append("registry assets[{}] must be an object".format(index))
            continue
        declared = item.get("path")
        if not isinstance(declared, str) or not declared.strip():
            info["warnings"].append(
                "registry assets[{}] has no non-empty path".format(index)
            )
            continue
        key = _normalise_registry_key(declared)
        if key in entries:
            info["warnings"].append("registry repeats asset path {!r}".format(key))
            continue
        entries[key] = item
    info["entries"] = len(entries)
    info["loaded"] = True
    return entries, info


def _duplicate_groups(assets: list) -> dict:
    groups = {}
    for entry in assets:
        groups.setdefault(entry["sha256"], []).append(entry["path"])
    duplicates = {
        digest: sorted(paths) for digest, paths in groups.items() if len(paths) > 1
    }
    return {
        digest: duplicates[digest]
        for digest in sorted(duplicates)
    }


def scan(roots=None, registry=None) -> dict:
    """Scan asset roots read-only and return a validated-shape gypsy.asset-registry/v1 payload.

    roots: iterable of filesystem paths; defaults to DEFAULT_ROOTS.
    registry: optional provenance sidecar path; defaults to DEFAULT_REGISTRY.
    Raises AssetError only when the configuration itself cannot be resolved; a missing root,
    an unreadable file, a malformed sidecar or a broken individual file are recorded as
    warnings/errors in the payload instead.
    """
    root_paths, setup_warnings = _describe_roots(roots)
    registry_path = Path(registry).expanduser() if registry else DEFAULT_REGISTRY
    try:
        registry_resolved = registry_path.resolve()
    except OSError:
        registry_resolved = registry_path
    provenance_entries, registry_info = _load_registry(registry_path)
    global_warnings = list(setup_warnings)

    assets = []
    errors = []
    root_reports = []
    seen = set()

    def on_error(error):
        errors.append("scan error: {}".format(error))

    for root in root_paths:
        report = {
            "path": _label(root, gypsy.REPO_ROOT),
            "found": root.is_dir(),
            "assets": 0,
            "ignored": 0,
            "warnings": [],
        }
        if not root.exists():
            report["warnings"].append("asset root does not exist")
            global_warnings.append(
                "asset root does not exist: " + report["path"]
            )
        elif not root.is_dir():
            errors.append("asset root is not a directory: " + report["path"])
            report["warnings"].append("asset root is not a directory")
        else:
            for directory, dirnames, filenames in os.walk(
                str(root), topdown=True, followlinks=False, onerror=on_error
            ):
                dirnames[:] = sorted(name for name in dirnames if not _ignored_dir(name))
                for name in sorted(filenames):
                    if _ignored_file(name):
                        report["ignored"] += 1
                        continue
                    path = Path(directory) / name
                    try:
                        resolved = path.resolve()
                    except OSError as exc:
                        errors.append("cannot resolve {}: {}".format(_posix(str(path)), exc))
                        continue
                    if resolved == registry_resolved:
                        report["ignored"] += 1
                        continue
                    key = _posix(str(resolved)).casefold()
                    if key in seen:
                        continue
                    seen.add(key)
                    try:
                        stat = path.stat()
                        if not path.is_file():
                            continue
                        digest = sha256_file(path)
                    except OSError as exc:
                        errors.append("cannot read {}: {}".format(_posix(str(path)), exc))
                        continue
                    assets.append(
                        {
                            "path": _repo_relative(path, gypsy.REPO_ROOT),
                            "root": report["path"],
                            "bytes": int(stat.st_size),
                            "sha256": digest,
                            "media": media_kind(name),
                            "modified": _iso_utc(stat.st_mtime),
                            "duplicate": False,
                            "provenance": None,
                            "warnings": [],
                        }
                    )
                    report["assets"] += 1
        root_reports.append(report)

    assets.sort(key=lambda entry: entry["path"])
    duplicates = _duplicate_groups(assets)
    duplicate_paths = {
        path for paths in duplicates.values() for path in paths
    }
    for entry in assets:
        entry["duplicate"] = entry["path"] in duplicate_paths

    if provenance_entries:
        lookup = {}
        for key, item in provenance_entries.items():
            lookup.setdefault(key.casefold(), (key, item))
        used = set()
        for entry in assets:
            key = _normalise_registry_key(entry["path"])
            match = provenance_entries.get(key)
            if match is None:
                folded = lookup.get(key.casefold())
                if folded is not None:
                    key, match = folded
            if match is None:
                entry["warnings"].append("no provenance entry in the registry")
                continue
            used.add(key)
            entry["provenance"] = match
            declared = match.get("license")
            if not isinstance(declared, str) or not declared.strip():
                entry["warnings"].append("provenance entry has no license")
        for key in sorted(set(provenance_entries) - used):
            registry_info["warnings"].append(
                "registry entry is not an asset in the scanned roots: " + key
            )
    elif registry_info["loaded"]:
        global_warnings.append(
            "provenance registry is empty; provenance is unknown for every asset"
        )
    elif not registry_info["found"]:
        global_warnings.append(
            "no provenance registry at {}; provenance is unknown for {} assets".format(
                registry_info["path"], len(assets)
            )
        )
    else:
        global_warnings.append(
            "provenance registry could not be used ({} warning(s)); provenance is unknown "
            "for {} assets".format(len(registry_info["warnings"]), len(assets))
        )

    counts = {
        kind: sum(1 for entry in assets if entry["media"] == kind) for kind in MEDIA_KINDS
    }
    with_provenance = sum(1 for entry in assets if entry["provenance"] is not None)
    missing_license = sum(
        1
        for entry in assets
        if entry["provenance"] is not None
        and (
            not isinstance(entry["provenance"].get("license"), str)
            or not entry["provenance"].get("license", "").strip()
        )
    )
    payload = {
        "schema": SCHEMA,
        "generated": _utc_now(),
        "roots": root_reports,
        "assets": assets,
        "duplicates": duplicates,
        "count": len(assets),
        "totalBytes": sum(entry["bytes"] for entry in assets),
        "counts": counts,
        "registry": registry_info,
        "provenance": {
            "withProvenance": with_provenance,
            "missingProvenance": len(assets) - with_provenance,
            "missingLicense": missing_license,
        },
        "warnings": global_warnings,
        "errors": errors,
    }
    return payload


def validate_payload(payload) -> list:
    """Return errors for a registry payload or state file; empty means it can be trusted."""
    if not isinstance(payload, dict):
        return ["payload must be a JSON object"]
    errors = []
    if payload.get("schema") != SCHEMA:
        errors.append("schema must be {!r}, found {!r}".format(SCHEMA, payload.get("schema")))
    if not isinstance(payload.get("generated"), str) or not payload["generated"].strip():
        errors.append("generated must be a non-empty string")

    roots = payload.get("roots")
    if not isinstance(roots, list):
        errors.append("roots must be a list")
        roots = []
    root_labels = []
    for index, report in enumerate(roots):
        label = "roots[{}]".format(index)
        if not isinstance(report, dict):
            errors.append("{} must be an object".format(label))
            continue
        if not isinstance(report.get("path"), str) or not report["path"].strip():
            errors.append("{}: path must be a non-empty string".format(label))
        else:
            root_labels.append(report["path"])
        if not isinstance(report.get("found"), bool):
            errors.append("{}: found must be true or false".format(label))
        for field in ("assets", "ignored"):
            value = report.get(field)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                errors.append("{}: {} must be a non-negative integer".format(label, field))
        warnings = report.get("warnings")
        if not isinstance(warnings, list) or not all(isinstance(item, str) for item in warnings):
            errors.append("{}: warnings must be a list of strings".format(label))

    assets = payload.get("assets")
    if not isinstance(assets, list):
        errors.append("assets must be a list")
        assets = []
    paths = []
    digest_paths = {}
    duplicate_expected = set()
    for index, entry in enumerate(assets):
        label = "assets[{}]".format(index)
        if not isinstance(entry, dict):
            errors.append("{} must be an object".format(label))
            continue
        path = entry.get("path")
        if not isinstance(path, str) or not path.strip():
            errors.append("{}: path must be a non-empty string".format(label))
        else:
            paths.append(path)
        root = entry.get("root")
        if not isinstance(root, str) or not root.strip():
            errors.append("{}: root must be a non-empty string".format(label))
        size = entry.get("bytes")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            errors.append("{}: bytes must be a non-negative integer".format(label))
        digest = entry.get("sha256")
        if not _sha256_text_is_hex(digest):
            errors.append("{}: sha256 must be a 64-character lowercase hex string".format(label))
        else:
            digest_paths.setdefault(digest, []).append(path)
        if entry.get("media") not in MEDIA_KINDS:
            errors.append("{}: media must be one of {}".format(label, list(MEDIA_KINDS)))
        modified = entry.get("modified")
        if not isinstance(modified, str) or not modified.strip():
            errors.append("{}: modified must be a non-empty string".format(label))
        else:
            try:
                datetime.fromisoformat(modified.replace("Z", "+00:00"))
            except ValueError:
                errors.append("{}: modified must be ISO-8601".format(label))
        if not isinstance(entry.get("duplicate"), bool):
            errors.append("{}: duplicate must be true or false".format(label))
        provenance = entry.get("provenance")
        if provenance is not None and not isinstance(provenance, dict):
            errors.append("{}: provenance must be an object or null".format(label))
        warnings = entry.get("warnings")
        if not isinstance(warnings, list) or not all(isinstance(item, str) for item in warnings):
            errors.append("{}: warnings must be a list of strings".format(label))
    if paths != sorted(paths):
        errors.append("assets must be sorted by path")
    if len(set(paths)) != len(paths):
        errors.append("asset paths must be unique")

    duplicates = payload.get("duplicates")
    if not isinstance(duplicates, dict):
        errors.append("duplicates must be an object")
        duplicates = {}
    for digest, grouped in duplicates.items():
        if not _sha256_text_is_hex(digest):
            errors.append("duplicates: keys must be sha256 hex strings")
        if not isinstance(grouped, list) or len(grouped) < 2:
            errors.append("duplicates[{!r}] must be a list of at least two paths".format(digest))
            continue
        if not all(isinstance(path, str) and path.strip() for path in grouped):
            errors.append("duplicates[{!r}] must be a list of paths".format(digest))
            continue
        if grouped != sorted(grouped):
            errors.append("duplicates[{!r}] must be sorted".format(digest))
        for path in grouped:
            duplicate_expected.add(path)
    for entry in assets:
        if not isinstance(entry, dict):
            continue
        path = entry.get("path")
        digest = entry.get("sha256")
        expected = path in duplicate_expected
        if isinstance(entry.get("duplicate"), bool) and entry["duplicate"] != expected:
            errors.append(
                "{}: duplicate flag does not match the duplicates report".format(path)
            )
        if _sha256_text_is_hex(digest) and isinstance(path, str):
            same = digest_paths.get(digest) or []
            if len(same) > 1 and digest not in duplicates:
                errors.append("sha256 {} has {} paths but no duplicate group".format(digest, len(same)))

    count = payload.get("count")
    if not isinstance(count, int) or isinstance(count, bool) or count != len(assets):
        errors.append("count must be the number of assets")
    total = payload.get("totalBytes")
    if (
        not isinstance(total, int)
        or isinstance(total, bool)
        or total != sum(entry.get("bytes", 0) for entry in assets if isinstance(entry, dict))
    ):
        errors.append("totalBytes must add up to the asset bytes")
    counts = payload.get("counts")
    if not isinstance(counts, dict):
        errors.append("counts must be an object")
    else:
        expected_counts = {
            kind: sum(1 for entry in assets if isinstance(entry, dict) and entry.get("media") == kind)
            for kind in MEDIA_KINDS
        }
        if counts != expected_counts:
            errors.append("counts must match the asset media kinds")

    registry = payload.get("registry")
    if not isinstance(registry, dict):
        errors.append("registry must be an object")
    else:
        if not isinstance(registry.get("path"), str) or not registry["path"].strip():
            errors.append("registry.path must be a non-empty string")
        if not isinstance(registry.get("found"), bool):
            errors.append("registry.found must be true or false")
        if not isinstance(registry.get("loaded"), bool):
            errors.append("registry.loaded must be true or false")
        schema = registry.get("schema")
        if schema is not None and not isinstance(schema, str):
            errors.append("registry.schema must be a string or null")
        entries = registry.get("entries")
        if not isinstance(entries, int) or isinstance(entries, bool) or entries < 0:
            errors.append("registry.entries must be a non-negative integer")
        warnings = registry.get("warnings")
        if not isinstance(warnings, list) or not all(isinstance(item, str) for item in warnings):
            errors.append("registry.warnings must be a list of strings")

    provenance = payload.get("provenance")
    if not isinstance(provenance, dict):
        errors.append("provenance must be an object")
    else:
        with_provenance = sum(
            1
            for entry in assets
            if isinstance(entry, dict) and entry.get("provenance") is not None
        )
        missing_license = sum(
            1
            for entry in assets
            if isinstance(entry, dict)
            and entry.get("provenance") is not None
            and (
                not isinstance(entry["provenance"].get("license"), str)
                or not entry["provenance"].get("license", "").strip()
            )
        )
        expected = {
            "withProvenance": with_provenance,
            "missingProvenance": len(assets) - with_provenance,
            "missingLicense": missing_license,
        }
        if provenance != expected:
            errors.append("provenance counts must match the assets")

    for field in ("warnings", "errors"):
        value = payload.get(field)
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            errors.append("{} must be a list of strings".format(field))
    return errors


def to_json(payload, indent: int = 2) -> str:
    """Return the payload as JSON text after validating it and proving it round-trips."""
    errors = validate_payload(payload)
    if errors:
        raise AssetError("asset registry payload is not valid: " + "; ".join(errors))
    try:
        text = json.dumps(payload, indent=indent, ensure_ascii=False)
        if json.loads(text) != payload:
            raise AssetError("asset registry payload is not JSON-safe: it changed through JSON")
    except (TypeError, ValueError) as exc:
        raise AssetError("asset registry payload is not JSON-safe: {}".format(exc)) from exc
    return text + "\n"


def save_state(payload, path=None) -> Path:
    """Write a validated registry payload to the state file atomically; return the path."""
    target = Path(path) if path else DEFAULT_STATE
    text = to_json(payload)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".tmp")
    try:
        temporary.write_text(text, encoding="utf-8")
        os.replace(str(temporary), str(target))
    finally:
        if temporary.exists():
            try:
                temporary.unlink()
            except OSError:
                pass
    return target


def load_state(path=None) -> dict:
    """Read and validate a registry state file; raise AssetError when it cannot be trusted."""
    source = Path(path) if path else DEFAULT_STATE
    try:
        text = source.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise AssetError("asset registry state is unreadable: {}: {}".format(source, exc)) from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AssetError(
            "asset registry state is invalid JSON: {}: {}".format(source, exc)
        ) from exc
    if not isinstance(data, dict):
        raise AssetError("asset registry state must be a JSON object: {}".format(source))
    errors = validate_payload(data)
    if errors:
        raise AssetError("asset registry state is not trustworthy: " + "; ".join(errors))
    return data


def render_summary(payload) -> str:
    """Render a compact human-readable summary of a scan."""
    lines = [
        "asset registry: {} asset(s), {} byte(s) under {} root(s)".format(
            payload.get("count", 0), payload.get("totalBytes", 0), len(payload.get("roots", []))
        )
    ]
    counts = payload.get("counts", {})
    lines.append(
        "media: " + ", ".join("{} {}".format(kind, counts.get(kind, 0)) for kind in MEDIA_KINDS)
    )
    duplicates = payload.get("duplicates", {})
    lines.append(
        "duplicates: {} content group(s), {} file(s)".format(
            len(duplicates), sum(len(paths) for paths in duplicates.values())
        )
    )
    registry = payload.get("registry", {})
    provenance = payload.get("provenance", {})
    lines.append(
        "provenance: registry {} (found={} loaded={} entries={})".format(
            registry.get("path"),
            registry.get("found"),
            registry.get("loaded"),
            registry.get("entries"),
        )
    )
    lines.append(
        "provenance: with {withProvenance}, missing {missingProvenance}, "
        "missing licence {missingLicense}".format(**provenance)
    )
    for report in payload.get("roots", []):
        line = "root {}: {} asset(s), {} ignored".format(
            report.get("path"), report.get("assets"), report.get("ignored")
        )
        if not report.get("found"):
            line += " (missing)"
        lines.append(line)
    warnings = payload.get("warnings") or []
    registry_warnings = registry.get("warnings") or []
    errors = payload.get("errors") or []
    if errors:
        lines.append("errors: {}".format(len(errors)))
        for error in errors[:10]:
            lines.append("  error: " + error)
    if warnings:
        lines.append("warnings: {}".format(len(warnings)))
        for warning in warnings[:10]:
            lines.append("  warning: " + warning)
    if registry_warnings:
        lines.append("registry warnings: {}".format(len(registry_warnings)))
        for warning in registry_warnings[:10]:
            lines.append("  warning: " + warning)
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="assets",
        description="Read-only asset registry: scan asset roots, hash files and report provenance gaps.",
    )
    parser.add_argument(
        "--root",
        action="append",
        default=None,
        metavar="PATH",
        help="asset root to scan; repeatable (default: assets/, game/assets/, unity/LeftBehind/Assets/)",
    )
    parser.add_argument(
        "--registry",
        default=None,
        metavar="PATH",
        help="optional provenance sidecar (default: assets/registry/provenance.json)",
    )
    parser.add_argument("--json", action="store_true", help="print the payload as JSON")
    parser.add_argument(
        "--validate",
        action="store_true",
        help="exit 1 when the scan recorded an error or the payload fails validation",
    )
    parser.add_argument(
        "--save-state",
        nargs="?",
        const=str(DEFAULT_STATE),
        default=None,
        metavar="PATH",
        help="write the scan to a state file (default: workstream/state/assets.json)",
    )
    parser.add_argument(
        "--state",
        metavar="PATH",
        help="print a previously saved registry state instead of scanning (validated first)",
    )
    args = parser.parse_args(argv)

    try:
        if args.state:
            payload = load_state(args.state)
        else:
            payload = scan(args.root, args.registry)
        saved = save_state(payload, args.save_state) if args.save_state else None
    except AssetError as exc:
        print("assets: FAIL - {}".format(exc), file=sys.stderr)
        return 2

    if args.json:
        print(to_json(payload), end="")
    else:
        print(render_summary(payload))
        if saved:
            print("state written: {}".format(saved))

    problems = list(payload.get("errors") or [])
    problems.extend(validate_payload(payload))
    if args.validate:
        for problem in problems:
            print("FAIL assets - {}".format(problem), file=sys.stderr)
        return 1 if problems else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
