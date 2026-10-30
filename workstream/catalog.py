#!/usr/bin/env python3
"""Project catalog for Gypsy Studio (docs/IMPROVEMENT-ROADMAP.md section 5, item 1).

A catalog is a read-only index of every project manifest (project.gypsy.json, schema
gypsy.project/v1) under a root. It is generated from the manifests, not maintained by hand:
manifests stay the single source of truth and every scan re-reads them.

What a scan reports
-------------------
For each manifest: name, engine id, version, adapter, targets, the project path (relative to
the scanned root, POSIX separators), the manifest path, and a health value with the
errors/warnings behind it.

    health = "ok"       the manifest validates and has no warnings
           = "warning"  the manifest validates but has warnings (a duplicate project name,
                        a missing optional field such as "created")
           = "invalid"  unreadable, not JSON, not a JSON object, or schema-invalid

Health is manifest health only. It is not engine readiness, licence state, build health or
game health: those need gypsy check, gypsy engines probe and real engine runs, which this
module deliberately does not perform so that a catalog scan stays deterministic, offline and
quick. A catalog entry is a claim about a file, not about a working build.

Rules
-----
* No fake projects: only a file named exactly project.gypsy.json is a project. Template
  manifests use another name (templates/*/project.gypsy.template.json) and are ignored, so a
  template is never listed as a project.
* No writes during a scan. Writing a state file is an explicit, separate call.
* Hidden and heavy/generated directories are pruned (EXCLUDED_DIRS plus every directory whose
  name starts with "."), so a checkout with .git, a Unity Library/, build outputs or
  artifacts/ is scanned quickly. A project whose directory is inside a pruned tree is not
  discovered; point --root at it instead.
* The payload is JSON-safe by construction (str, int, bool, None, list and dict only) and
  to_json checks the serialised form round-trips before returning it.
* Duplicate detection compares casefolded names, so Demo and demo collide.

Optional catalog state (design)
-------------------------------
python workstream/catalog.py --save-state writes the last scan to workstream/state/catalog.json
by default (schema gypsy.catalog/v1, the same payload; written to a temporary file and moved
with os.replace so a reader never sees a partial file). The state file exists to compare a new
scan with the last one, never to answer for the manifests: it is a cache, discovery wins on
every run, and stale state must never be presented as current project health. It is gitignored
under workstream/state/ and machine-specific because "root" is absolute. load_state validates
the whole payload and refuses anything it cannot trust. load_state and save_state are the only
functions here that touch disk for writing, and only when called.

Wiring: workstream/gypsy.py is not modified by this module (the Lead owns that integration).
The module is importable (import catalog) and has its own thin, read-only entry point so the
catalog can be used before the CLI wiring exists.

Public API
----------
    SCHEMA, PROJECT_SCHEMA, MANIFEST_NAME, EXCLUDED_DIRS, HEALTH_STATES, CatalogError
    discover(root=None) -> dict
    load_manifest(path) -> dict
    validate_manifest(manifest) -> list[str]
    manifest_warnings(manifest) -> list[str]
    validate_catalog(catalog) -> list[str]
    health_problems(catalog) -> list[str]
    to_json(catalog, indent=2) -> str
    save_state(catalog, path=None) -> Path
    load_state(path=None) -> dict
    render_catalog(catalog) -> str
    main(argv=None) -> int

Usage:
    python workstream/catalog.py [--root DIR] [--json]
    python workstream/catalog.py --validate [--root DIR] [--json]
    python workstream/catalog.py --save-state [PATH]
    python workstream/catalog.py --state PATH [--json]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import gypsy

SCHEMA = "gypsy.catalog/v1"
PROJECT_SCHEMA = "gypsy.project/v1"
MANIFEST_NAME = "project.gypsy.json"
HEALTH_STATES = ("ok", "warning", "invalid")
DEFAULT_STATE = gypsy.STATE_DIR / "catalog.json"

# Heavy, generated or dependency directories that never hold a project root worth cataloguing.
# The scan prunes these by exact name, and every name starting with "." as well.
EXCLUDED_DIRS = frozenset(
    {
        "node_modules",
        "__pycache__",
        ".venv",
        "venv",
        "env",
        "Library",
        "Temp",
        "Logs",
        "obj",
        "bin",
        "build",
        "artifacts",
        "dist",
        "target",
        "coverage",
        "hf-cache",
        "GameTools",
        "intermediate",
        "Saved",
        "DerivedDataCache",
    }
)

REQUIRED_ENTRY_FIELDS = (
    "name",
    "engine",
    "version",
    "adapter",
    "targets",
    "path",
    "manifest",
    "health",
    "duplicate",
    "errors",
    "warnings",
)


class CatalogError(ValueError):
    """A manifest, catalog payload or state file is unreadable, invalid or not JSON-safe."""


def _as_relative(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def _pruned(name: str) -> bool:
    return name.startswith(".") or name in EXCLUDED_DIRS


def load_manifest(path) -> dict:
    """Load one project manifest and return it as a dict.

    Raises CatalogError when the file is missing/unreadable, not JSON, or not a JSON object.
    This does not validate the schema; call validate_manifest for that.
    """
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise CatalogError("{}: unreadable: {}".format(path, exc)) from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise CatalogError("{}: invalid JSON: {}".format(path, exc)) from exc
    if not isinstance(data, dict):
        raise CatalogError("{}: manifest must be a JSON object".format(path))
    return data


def validate_manifest(manifest) -> list:
    """Return a list of schema errors for one gypsy.project/v1 manifest; empty means valid."""
    if not isinstance(manifest, dict):
        return ["manifest must be a JSON object"]
    errors = []

    if manifest.get("schema") != PROJECT_SCHEMA:
        errors.append(
            "schema must be {!r}, found {!r}".format(PROJECT_SCHEMA, manifest.get("schema"))
        )

    name = manifest.get("name")
    if not isinstance(name, str) or not name.strip():
        errors.append("name must be a non-empty string")

    engine = manifest.get("engine")
    if not isinstance(engine, dict):
        errors.append("engine must be an object with id, version and adapter")
    else:
        engine_id = engine.get("id")
        if not isinstance(engine_id, str) or not engine_id.strip():
            errors.append("engine.id must be a non-empty string")
        elif engine_id not in gypsy.ENGINE_NAMES:
            errors.append(
                "engine.id {!r} is not a known engine; choose one of {}".format(
                    engine_id, sorted(gypsy.ENGINE_NAMES)
                )
            )
        version = engine.get("version")
        if not isinstance(version, str) or not version.strip():
            errors.append("engine.version must be a non-empty string")
        adapter = engine.get("adapter")
        if not isinstance(adapter, str) or not adapter.strip():
            errors.append("engine.adapter must be a non-empty string")

    targets = manifest.get("targets")
    if not isinstance(targets, list) or not targets:
        errors.append("targets must be a non-empty list of strings")
    else:
        for index, target in enumerate(targets):
            if not isinstance(target, str) or not target.strip():
                errors.append("targets[{}] must be a non-empty string".format(index))

    paths = manifest.get("paths")
    if not isinstance(paths, dict):
        errors.append("paths must be an object of relative path strings")
    else:
        for key, value in sorted(paths.items()):
            if not isinstance(key, str) or not isinstance(value, str) or not value.strip():
                errors.append("paths.{!r} must be a non-empty string".format(key))

    return errors


def manifest_warnings(manifest) -> list:
    """Return non-fatal warnings for a manifest that already parsed as an object."""
    warnings = []
    if not isinstance(manifest, dict):
        return warnings
    paths = manifest.get("paths")
    if isinstance(paths, dict):
        for required in ("game", "artifacts"):
            if required not in paths:
                warnings.append(
                    "paths.{} is missing (the schema expects game and artifacts)".format(required)
                )
    created = manifest.get("created")
    if not isinstance(created, str) or not created.strip():
        warnings.append("created is missing or not a string")
    if "decisions" in manifest and not isinstance(manifest.get("decisions"), list):
        warnings.append("decisions must be a list when present")
    return warnings


def _entry(manifest_path: Path, root: Path) -> dict:
    entry = {
        "name": manifest_path.parent.name,
        "engine": None,
        "version": None,
        "adapter": None,
        "targets": [],
        "path": _as_relative(manifest_path.parent, root),
        "manifest": _as_relative(manifest_path, root),
        "health": "invalid",
        "duplicate": False,
        "errors": [],
        "warnings": [],
    }
    try:
        manifest = load_manifest(manifest_path)
    except CatalogError as exc:
        entry["errors"] = [str(exc)]
        return entry

    entry["errors"] = validate_manifest(manifest)
    entry["warnings"] = manifest_warnings(manifest)
    name = manifest.get("name")
    if isinstance(name, str) and name.strip():
        entry["name"] = name.strip()
    engine = manifest.get("engine")
    if isinstance(engine, dict):
        if isinstance(engine.get("id"), str):
            entry["engine"] = engine["id"]
        if isinstance(engine.get("version"), str):
            entry["version"] = engine["version"]
        if isinstance(engine.get("adapter"), str):
            entry["adapter"] = engine["adapter"]
    targets = manifest.get("targets")
    if isinstance(targets, list):
        entry["targets"] = [target for target in targets if isinstance(target, str)]
    if entry["errors"]:
        entry["health"] = "invalid"
    elif entry["warnings"]:
        entry["health"] = "warning"
    else:
        entry["health"] = "ok"
    return entry


def _group_duplicates(entries):
    groups = {}
    for entry in entries:
        groups.setdefault(entry["name"].casefold(), []).append(entry)
    duplicates = {}
    paths_by_name = {}
    for folded, group in groups.items():
        if len(group) > 1:
            duplicates[group[0]["name"]] = sorted(item["path"] for item in group)
            paths_by_name[folded] = duplicates[group[0]["name"]]
    ordered = {
        name: paths
        for name, paths in sorted(duplicates.items(), key=lambda pair: pair[0].casefold())
    }
    return ordered, paths_by_name


def discover(root=None) -> dict:
    """Scan root (default: the Gypsy checkout) for project.gypsy.json manifests.

    Returns a gypsy.catalog/v1 payload. The scan is read-only, deterministic (projects sorted
    by path, duplicate names sorted) and JSON-safe. Raises CatalogError only for a root that
    cannot be scanned; an individual broken manifest is reported in its entry instead.
    """
    root_path = Path(root).expanduser() if root else gypsy.REPO_ROOT
    try:
        root_path = root_path.resolve()
    except OSError as exc:
        raise CatalogError("catalog root cannot be resolved: {}".format(exc)) from exc
    if not root_path.is_dir():
        raise CatalogError("catalog root is not a directory: {}".format(root_path))

    scan_errors = []

    def on_error(error):
        scan_errors.append("scan error: {}".format(error))

    entries = []
    for directory, dirnames, filenames in os.walk(
        str(root_path), topdown=True, followlinks=False, onerror=on_error
    ):
        dirnames[:] = sorted(name for name in dirnames if not _pruned(name))
        if MANIFEST_NAME in filenames:
            entries.append(_entry(Path(directory) / MANIFEST_NAME, root_path))
    entries.sort(key=lambda item: item["path"])

    duplicates, paths_by_name = _group_duplicates(entries)
    for entry in entries:
        folded = entry["name"].casefold()
        if folded not in paths_by_name:
            continue
        entry["duplicate"] = True
        others = [path for path in paths_by_name[folded] if path != entry["path"]]
        entry["warnings"].append(
            "duplicate project name; also declared in " + ", ".join(others)
        )
        if entry["health"] == "ok":
            entry["health"] = "warning"

    counts = {
        state: sum(1 for entry in entries if entry["health"] == state)
        for state in HEALTH_STATES
    }
    return {
        "schema": SCHEMA,
        "generated": gypsy.now_iso(),
        "root": str(root_path),
        "projects": entries,
        "duplicates": duplicates,
        "count": len(entries),
        "counts": counts,
        "errors": scan_errors,
    }


def validate_catalog(catalog) -> list:
    """Return errors for a catalog payload or state file; empty means it can be trusted."""
    if not isinstance(catalog, dict):
        return ["catalog must be a JSON object"]
    errors = []
    if catalog.get("schema") != SCHEMA:
        errors.append("schema must be {!r}, found {!r}".format(SCHEMA, catalog.get("schema")))
    generated = catalog.get("generated")
    if not isinstance(generated, str) or not generated.strip():
        errors.append("generated must be a non-empty string")
    root = catalog.get("root")
    if not isinstance(root, str) or not root.strip():
        errors.append("root must be a non-empty string")

    projects = catalog.get("projects")
    if not isinstance(projects, list):
        errors.append("projects must be a list")
        projects = []
    paths_seen = set()
    for index, entry in enumerate(projects):
        label = "projects[{}]".format(index)
        if not isinstance(entry, dict):
            errors.append("{} must be an object".format(label))
            continue
        for field in REQUIRED_ENTRY_FIELDS:
            if field not in entry:
                errors.append("{}: missing field {!r}".format(label, field))
        name = entry.get("name")
        if not isinstance(name, str) or not name.strip():
            errors.append("{}: name must be a non-empty string".format(label))
        for field in ("engine", "version", "adapter"):
            value = entry.get(field)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                errors.append("{}: {} must be null or a non-empty string".format(label, field))
        targets = entry.get("targets")
        if not isinstance(targets, list) or not all(
            isinstance(target, str) for target in targets
        ):
            errors.append("{}: targets must be a list of strings".format(label))
        path = entry.get("path")
        if not isinstance(path, str) or not path.strip():
            errors.append("{}: path must be a non-empty string".format(label))
        elif path in paths_seen:
            errors.append("{}: path {!r} appears twice".format(label, path))
        else:
            paths_seen.add(path)
        manifest = entry.get("manifest")
        if not isinstance(manifest, str) or not manifest.strip():
            errors.append("{}: manifest must be a non-empty string".format(label))
        if entry.get("health") not in HEALTH_STATES:
            errors.append("{}: health must be one of {}".format(label, list(HEALTH_STATES)))
        if not isinstance(entry.get("duplicate"), bool):
            errors.append("{}: duplicate must be true or false".format(label))
        for field in ("errors", "warnings"):
            value = entry.get(field)
            if not isinstance(value, list) or not all(
                isinstance(item, str) for item in value
            ):
                errors.append("{}: {} must be a list of strings".format(label, field))

    duplicates = catalog.get("duplicates")
    if not isinstance(duplicates, dict):
        errors.append("duplicates must be an object of name -> paths")
    else:
        for name, paths in duplicates.items():
            if not isinstance(name, str) or not name.strip():
                errors.append("duplicates: keys must be non-empty strings")
            if not isinstance(paths, list) or not all(
                isinstance(item, str) and item.strip() for item in paths
            ):
                errors.append("duplicates[{!r}] must be a list of paths".format(name))

    count = catalog.get("count")
    if not isinstance(count, int) or isinstance(count, bool) or count != len(projects):
        errors.append("count must be the number of projects")
    counts = catalog.get("counts")
    if not isinstance(counts, dict):
        errors.append("counts must be an object")
    else:
        total = 0
        for state in HEALTH_STATES:
            value = counts.get(state)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                errors.append("counts.{} must be a non-negative integer".format(state))
            else:
                total += value
        if total != len(projects):
            errors.append("counts must add up to count")
    scan_errors = catalog.get("errors")
    if not isinstance(scan_errors, list) or not all(
        isinstance(item, str) for item in scan_errors
    ):
        errors.append("errors must be a list of strings")
    return errors


def health_problems(catalog) -> list:
    """Return the problems a --validate run should fail on: invalid manifests and duplicates."""
    problems = []
    for entry in catalog.get("projects", []):
        if entry.get("health") == "invalid":
            detail = "; ".join(entry.get("errors") or []) or "invalid manifest"
            problems.append("{}: {}".format(entry.get("path"), detail))
    for name, paths in sorted((catalog.get("duplicates") or {}).items()):
        problems.append("duplicate project name {!r}: {}".format(name, ", ".join(paths)))
    for error in catalog.get("errors") or []:
        problems.append(error)
    return problems


def to_json(catalog, indent: int = 2) -> str:
    """Return the catalog as JSON text, after validating it and proving it round-trips."""
    errors = validate_catalog(catalog)
    if errors:
        raise CatalogError("catalog is not valid: " + "; ".join(errors))
    try:
        text = json.dumps(catalog, indent=indent, ensure_ascii=False)
        if json.loads(text) != catalog:
            raise CatalogError("catalog is not JSON-safe: the payload changed through JSON")
    except (TypeError, ValueError) as exc:
        raise CatalogError("catalog is not JSON-safe: {}".format(exc)) from exc
    return text + "\n"


def save_state(catalog, path=None) -> Path:
    """Write a validated catalog payload to the state file atomically; return the path."""
    target = Path(path) if path else DEFAULT_STATE
    text = to_json(catalog)
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
    """Read and validate a catalog state file; raise CatalogError when it cannot be trusted."""
    source = Path(path) if path else DEFAULT_STATE
    try:
        text = source.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise CatalogError("catalog state is unreadable: {}: {}".format(source, exc)) from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise CatalogError("catalog state is invalid JSON: {}: {}".format(source, exc)) from exc
    if not isinstance(data, dict):
        raise CatalogError("catalog state must be a JSON object: {}".format(source))
    errors = validate_catalog(data)
    if errors:
        raise CatalogError("catalog state is not trustworthy: " + "; ".join(errors))
    return data


def render_catalog(catalog) -> str:
    """Render the catalog as a small human-readable table."""
    projects = catalog.get("projects", [])
    lines = [
        "project catalog: {} project(s) under {}".format(
            catalog.get("count", 0), catalog.get("root")
        )
    ]
    counts = catalog.get("counts", {})
    lines.append(
        "health: " + ", ".join("{} {}".format(state, counts.get(state, 0)) for state in HEALTH_STATES)
    )
    if not projects:
        lines.append("no project.gypsy.json found")
    else:
        name_width = max([len("NAME")] + [len(entry["name"]) for entry in projects])
        engine_width = max([len("ENGINE")] + [len(entry["engine"] or "-") for entry in projects])
        targets_width = max(
            [len("TARGETS")] + [len(",".join(entry["targets"]) or "-") for entry in projects]
        )
        header = "{:<{nw}}  {:<{ew}}  {:<{tw}}  {:<7}  {}".format(
            "NAME",
            "ENGINE",
            "TARGETS",
            "HEALTH",
            "PATH",
            nw=name_width,
            ew=engine_width,
            tw=targets_width,
        )
        lines.append("")
        lines.append(header)
        for entry in projects:
            lines.append(
                "{:<{nw}}  {:<{ew}}  {:<{tw}}  {:<7}  {}".format(
                    entry["name"],
                    entry["engine"] or "-",
                    ",".join(entry["targets"]) or "-",
                    entry["health"],
                    entry["path"],
                    nw=name_width,
                    ew=engine_width,
                    tw=targets_width,
                )
            )
            for warning in entry.get("warnings", []):
                lines.append("    warning: " + warning)
            for error in entry.get("errors", []):
                lines.append("    error: " + error)
    for name, paths in sorted((catalog.get("duplicates") or {}).items()):
        lines.append("duplicate name {!r}: {}".format(name, ", ".join(paths)))
    for error in catalog.get("errors") or []:
        lines.append(error)
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="catalog",
        description="Read-only project catalog: discover project.gypsy.json manifests and their health.",
    )
    parser.add_argument("--root", help="directory to scan (default: the Gypsy checkout root)")
    parser.add_argument("--json", action="store_true", help="print the catalog payload as JSON")
    parser.add_argument(
        "--validate",
        action="store_true",
        help="exit 1 when a manifest is invalid, a project name is duplicated, or the scan failed",
    )
    parser.add_argument(
        "--save-state",
        nargs="?",
        const=str(DEFAULT_STATE),
        default=None,
        metavar="PATH",
        help="write the scan to a state file (default: workstream/state/catalog.json)",
    )
    parser.add_argument(
        "--state",
        metavar="PATH",
        help="print a previously saved catalog state instead of scanning (validated first)",
    )
    args = parser.parse_args(argv)

    try:
        if args.state:
            catalog = load_state(args.state)
        else:
            catalog = discover(args.root)
        saved = save_state(catalog, args.save_state) if args.save_state else None
    except CatalogError as exc:
        print("catalog: FAIL - {}".format(exc), file=sys.stderr)
        return 2

    if args.json:
        print(to_json(catalog), end="")
    else:
        print(render_catalog(catalog))
        if saved:
            print("state written: {}".format(saved))

    problems = health_problems(catalog)
    if args.validate:
        for problem in problems:
            print("FAIL catalog - {}".format(problem), file=sys.stderr)
        return 1 if problems else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
