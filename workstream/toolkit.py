#!/usr/bin/env python3
"""Reusable toolkit registry for Gypsy Studio (docs/ADR-015-actionforge-toolkit.md).

A toolkit is a first-class tool integration that belongs to Gypsy Studio, not to one game
project. Each plugin lives in workstream/toolkits/<id>.py, declares a small standard
interface and may add its own verbs under "gypsy toolkit <id> ...". The registry discovers
and validates plugins, exposes list/show/probe/capabilities, and provides the shared
filesystem helpers the plugins use (project-root confinement and atomic writes).

Plugin contract (module-level attributes):

    TOOLKIT_ID   lowercase id, letters/digits/'_'/'-', not a reserved command
    NAME         human-readable name
    SUMMARY      one-line description
    LICENSE      licence summary (must include attribution/provenance requirements)
    STATUS       one of stable, partial, experimental, planned
    KIND         short category such as asset-library or generator
    CAPABILITY   capability manifest id under workstream/capabilities/
    HOME         source/home URL
    COMMANDS     dict: verb -> {summary, configure, run, render}
    describe()   -> JSON-safe dict with the toolkit details/catalog
    probe(opener=None, timeout=...) -> dict with a truthful reachable/error result

Because the registry is deliberately small, a future tool is added by writing one plugin,
one capability manifest and one test file addition; nothing in workstream/gypsy.py knows
the tool by name.

This module is standard library only and does not open a network connection. Plugins may,
but only inside explicit commands (probe/fetch); list/show/capabilities stay offline.

Usage:
    python workstream/gypsy.py toolkit list [--json]
    python workstream/gypsy.py toolkit show actionforge [--json]
    python workstream/gypsy.py toolkit probe actionforge [--json]
    python workstream/gypsy.py toolkit capabilities [--json]
    python workstream/gypsy.py toolkit actionforge catalog [--json]
    python workstream/gypsy.py toolkit actionforge fetch --project DIR --clips IDS [--rig]
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

WS_DIR = Path(__file__).resolve().parent
REPO_ROOT = WS_DIR.parent
TOOLKITS_DIR = WS_DIR / "toolkits"
CAP_DIR = WS_DIR / "capabilities"

CAPABILITY_SCHEMA = "gypsy.capability/v1"
ID_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
STATUSES = ("stable", "partial", "experimental", "planned")
MATURITY = frozenset({"stable", "partial", "experimental", "planned", "blocked"})
RESERVED_IDS = frozenset({"list", "show", "probe", "capabilities"})
REQUIRED_ATTRS = (
    "TOOLKIT_ID",
    "NAME",
    "SUMMARY",
    "LICENSE",
    "STATUS",
    "KIND",
    "CAPABILITY",
    "HOME",
    "COMMANDS",
)
REQUIRED_CALLABLES = ("describe", "probe")
COMMAND_KEYS = frozenset({"summary", "configure", "run", "render"})


class ToolkitError(ValueError):
    """A toolkit plugin is missing, invalid, or asked to act outside its project."""


class Toolkit:
    """A validated plugin: its metadata, command table and module object."""

    def __init__(self, module, path: Path):
        self.module = module
        self.path = Path(path)
        self.id = module.TOOLKIT_ID
        self.name = module.NAME
        self.summary = module.SUMMARY
        self.license = module.LICENSE
        self.status = module.STATUS
        self.kind = module.KIND
        self.capability = module.CAPABILITY
        self.home = module.HOME
        self.commands = module.COMMANDS

    def info(self) -> dict:
        """The JSON-safe registry row used by `toolkit list`."""
        return {
            "id": self.id,
            "name": self.name,
            "summary": self.summary,
            "license": self.license,
            "status": self.status,
            "kind": self.kind,
            "capability": self.capability,
            "home": self.home,
            "commands": sorted(self.commands),
            "plugin": display_path(self.path),
        }


def display_path(path) -> str:
    """Render a path relative to the Gypsy checkout when possible, POSIX-style."""
    path = Path(path)
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except (OSError, ValueError):
        return str(path)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_write(path: Path, data: bytes) -> None:
    """Write bytes atomically via a temp file in the destination directory."""
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


def atomic_write_bytes(path, data: bytes) -> None:
    """Atomic write of raw bytes (no shell, no newline translation)."""
    _atomic_write(Path(path), bytes(data))


def atomic_write_text(path, text: str) -> None:
    """Atomic UTF-8 write with LF line endings and no BOM."""
    text = str(text)
    if text and not text.endswith("\n"):
        text += "\n"
    _atomic_write(Path(path), text.encode("utf-8"))


def resolve_within(root, relative, *, label: str = "path") -> Path:
    """Resolve a project-relative path and refuse anything that escapes *root*.

    Absolute paths, drive/UNC anchors, '..' segments and symlink escapes are rejected.
    The path does not have to exist yet.
    """
    root = Path(root).expanduser().resolve()
    if not isinstance(relative, (str, os.PathLike)):
        raise ToolkitError(f"{label} must be a relative path")
    if not str(relative).strip():
        raise ToolkitError(f"{label} must be a non-empty relative path")
    try:
        rel = Path(relative)
    except (TypeError, ValueError) as exc:
        raise ToolkitError(f"{label} is not a usable path: {exc}") from exc
    if rel.is_absolute() or rel.drive or rel.root:
        raise ToolkitError(f"{label} must be relative to the project root")
    if ".." in rel.parts:
        raise ToolkitError(f"{label} must not escape the project root with '..'")
    target = (root / rel).resolve()
    if target != root and not target.is_relative_to(root):
        raise ToolkitError(f"{label} resolves outside the project root: {relative!r}")
    return target


def _load_module(path: Path):
    module_name = "gypsy_toolkit_" + re.sub(r"[^A-Za-z0-9_]", "_", path.stem)
    spec = importlib.util.spec_from_file_location(module_name, str(path))
    if spec is None or spec.loader is None:
        raise ToolkitError(f"{path.name}: could not load toolkit plugin")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:  # import-time failure is a plugin defect, not a CLI traceback
        raise ToolkitError(
            f"{path.name}: toolkit plugin failed to import: {type(exc).__name__}: {exc}"
        ) from exc
    return module


def validate_plugin(module, path=None) -> list:
    """Return schema errors for a loaded plugin; empty means valid."""
    label = Path(path).name if path else getattr(module, "__name__", "plugin")
    errors = []
    for attr in REQUIRED_ATTRS:
        if not hasattr(module, attr):
            errors.append(f"{label}: missing required attribute {attr}")
    if errors:
        return errors
    toolkit_id = module.TOOLKIT_ID
    if not isinstance(toolkit_id, str) or not ID_RE.match(toolkit_id):
        errors.append(
            f"{label}: TOOLKIT_ID must be a lowercase id of letters, digits, '_' or '-'"
        )
    elif toolkit_id in RESERVED_IDS:
        errors.append(f"{label}: TOOLKIT_ID {toolkit_id!r} is a reserved command name")
    for attr in ("NAME", "SUMMARY", "LICENSE", "KIND", "HOME", "CAPABILITY"):
        value = getattr(module, attr)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{label}: {attr} must be a non-empty string")
    if module.STATUS not in STATUSES:
        errors.append(
            f"{label}: STATUS {module.STATUS!r} must be one of {', '.join(STATUSES)}"
        )
    for attr in REQUIRED_CALLABLES:
        if not callable(getattr(module, attr, None)):
            errors.append(f"{label}: {attr}() must be callable")
    commands = module.COMMANDS
    if not isinstance(commands, dict):
        errors.append(f"{label}: COMMANDS must be a dict of verb -> command spec")
        return errors
    for verb, spec in commands.items():
        if not isinstance(verb, str) or not ID_RE.match(verb):
            errors.append(f"{label}: command verb {verb!r} is not a valid id")
            continue
        if not isinstance(spec, dict):
            errors.append(f"{label}: command {verb!r} must be a dict")
            continue
        missing = sorted(COMMAND_KEYS - set(spec))
        if missing:
            errors.append(f"{label}: command {verb!r} is missing {', '.join(missing)}")
        unknown = sorted(set(spec) - COMMAND_KEYS)
        if unknown:
            errors.append(
                f"{label}: command {verb!r} has unknown key(s) {', '.join(unknown)}"
            )
        if not isinstance(spec.get("summary"), str) or not spec.get("summary", "").strip():
            errors.append(f"{label}: command {verb!r} summary must be a non-empty string")
        for key in ("configure", "run", "render"):
            if not callable(spec.get(key)):
                errors.append(f"{label}: command {verb!r} {key} must be callable")
    return errors


def discover(directory=None) -> dict:
    """Load and validate every toolkit plugin in *directory*; return id -> Toolkit.

    Raises ToolkitError listing every invalid plugin. An empty directory returns an empty
    dict; registry_errors() reports that as a problem for this repository.
    """
    directory = Path(directory) if directory else TOOLKITS_DIR
    if not directory.is_dir():
        raise ToolkitError(f"toolkit directory does not exist: {directory}")
    toolkits = {}
    errors = []
    for path in sorted(directory.glob("*.py")):
        if path.name.startswith("_"):
            continue
        try:
            module = _load_module(path)
        except ToolkitError as exc:
            errors.append(str(exc))
            continue
        problems = validate_plugin(module, path)
        if problems:
            errors.extend(problems)
            continue
        toolkit = Toolkit(module, path)
        if toolkit.id in toolkits:
            errors.append(f"{path.name}: duplicate toolkit id {toolkit.id!r}")
            continue
        toolkits[toolkit.id] = toolkit
    if errors:
        raise ToolkitError("; ".join(errors))
    return toolkits


def describe_toolkit(toolkit: Toolkit) -> dict:
    """Merge the plugin's describe() details with the registry's authoritative fields."""
    details = toolkit.module.describe()
    if not isinstance(details, dict):
        raise ToolkitError(f"{toolkit.path.name}: describe() must return a dict")
    data = dict(details)
    data.update(
        {
            "id": toolkit.id,
            "name": toolkit.name,
            "summary": toolkit.summary,
            "license": toolkit.license,
            "status": toolkit.status,
            "kind": toolkit.kind,
            "capability": toolkit.capability,
            "home": toolkit.home,
            "commands": sorted(toolkit.commands),
        }
    )
    data.setdefault("catalog", [])
    return data


def capability_rows(toolkits=None, cap_dir=None) -> list:
    """Return one row per toolkit describing its capability manifest."""
    toolkits = toolkits if toolkits is not None else discover()
    cap_dir = Path(cap_dir) if cap_dir else CAP_DIR
    rows = []
    for toolkit in sorted(toolkits.values(), key=lambda item: item.id):
        path = cap_dir / f"{toolkit.capability}.json"
        row = {
            "toolkit": toolkit.id,
            "capability": toolkit.capability,
            "manifest": display_path(path),
            "exists": path.is_file(),
            "schema": None,
            "id": None,
            "maturity": None,
            "error": None,
            "data": None,
        }
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8-sig"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                row["error"] = f"unreadable capability manifest: {exc}"
            else:
                if not isinstance(data, dict):
                    row["error"] = "capability manifest must be a JSON object"
                else:
                    row["data"] = data
                    row["schema"] = data.get("schema")
                    row["id"] = data.get("id")
                    row["maturity"] = data.get("maturity")
        rows.append(row)
    return rows


def registry_errors(directory=None, cap_dir=None) -> list:
    """Validate every plugin and its capability link; return human-readable errors."""
    try:
        toolkits = discover(directory)
    except ToolkitError as exc:
        return [str(exc)]
    errors = []
    if not toolkits:
        errors.append("no toolkit plugins are registered")
    seen_capabilities = {}
    for row in capability_rows(toolkits, cap_dir=cap_dir):
        if not row["exists"]:
            errors.append(
                f"{row['toolkit']}: capability manifest {row['capability']!r} is missing ({row['manifest']})"
            )
            continue
        if row["error"]:
            errors.append(f"{row['toolkit']}: {row['error']}")
            continue
        if row["schema"] != CAPABILITY_SCHEMA:
            errors.append(
                f"{row['toolkit']}: capability schema must be {CAPABILITY_SCHEMA!r}, found {row['schema']!r}"
            )
        if row["id"] != row["capability"]:
            errors.append(
                f"{row['toolkit']}: capability id {row['id']!r} does not match {row['capability']!r}"
            )
        if row["maturity"] not in MATURITY:
            errors.append(
                f"{row['toolkit']}: capability maturity {row['maturity']!r} is not one of {sorted(MATURITY)}"
            )
        if row["capability"] in seen_capabilities:
            errors.append(
                f"{row['toolkit']}: capability {row['capability']!r} is also claimed by "
                f"{seen_capabilities[row['capability']]}"
            )
        else:
            seen_capabilities[row["capability"]] = row["toolkit"]
    return errors
