#!/usr/bin/env python3
"""Slice manifests for the Phase-2 orchestrator (docs/ADR-010-slice-orchestrator.md).

A slice is a JSON manifest: an ordered list of steps with explicit needs, timeouts and the
artifacts a run must leave behind. This module only loads, validates and orders manifests;
orchestrator executes them. Standard library only.

Schema gypsy.slice/v1:

    {
      "schema": "gypsy.slice/v1",
      "id": "phase1",
      "project": "game",
      "artifacts": ["build/ProjectGypsy.exe"],
      "steps": [
        {"id": "demo", "kind": "game.demo", "needs": [], "required": true,
         "timeout": 240, "args": {}}
      ]
    }

Step rules:

* id - unique within the slice, letters/digits/dot/underscore/dash, at most 64 characters.
* kind - one of STEP_KINDS, matching a handler in orchestrator.HANDLERS.
* needs - ids of steps that must pass first; missing ids and cycles are errors.
* required - defaults to true. A failed or skipped required step fails the slice.
* timeout - seconds, positive, defaults to DEFAULT_TIMEOUT.
* args - handler-specific object.

Artifact paths are repo-relative (relative to the project root the run is given) and must not
escape it with '..' or an absolute path.

Public API:

    SCHEMA, STEP_KINDS, DEFAULT_TIMEOUT, SliceError
    load_manifest(path) -> dict
    load_all(directory) -> dict[str, dict]
    validate_manifest(manifest) -> list[str]
    resolve_order(manifest) -> list[str]
    step_state_path(state_dir, slice_id) -> Path
"""
from __future__ import annotations

import json
import re
from pathlib import Path

SCHEMA = "gypsy.slice/v1"
STEP_KINDS = frozenset(
    {
        "game.demo",
        "game.build",
        "game.capture",
        "check_all",
        "tests",
        "records",
        "command",
        "toolpack",
    }
)
DEFAULT_TIMEOUT = 300.0
ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class SliceError(ValueError):
    """A manifest is unreadable, invalid, or cannot be resolved into an order."""


def load_manifest(path) -> dict:
    """Load one JSON manifest.

    Raises SliceError when the file is unreadable, not JSON, or not a JSON object.
    This does not validate the schema; call validate_manifest for that.
    """
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise SliceError(f"{path}: unreadable: {exc}") from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SliceError(f"{path}: invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise SliceError(f"{path}: manifest must be a JSON object")
    return data


def load_all(directory) -> dict:
    """Load every JSON manifest in *directory*, keyed by manifest id.

    Files are read in sorted file-name order so the returned dict has a deterministic order
    (slices/phase1.json before slices/quality.json). Raises SliceError on unreadable files,
    invalid JSON, a missing id or a duplicate id.
    """
    directory = Path(directory)
    if not directory.is_dir():
        raise SliceError(f"{directory}: slice directory does not exist")
    manifests: dict = {}
    for path in sorted(directory.glob("*.json")):
        manifest = load_manifest(path)
        slice_id = manifest.get("id")
        if not isinstance(slice_id, str) or not slice_id:
            raise SliceError(f"{path.name}: manifest has no string id")
        if slice_id in manifests:
            raise SliceError(f"{path.name}: duplicate slice id {slice_id!r}")
        manifests[slice_id] = manifest
    return manifests


def _topological(manifest):
    """Return (order, missing_errors, cycle_error) without raising."""
    steps = manifest.get("steps") if isinstance(manifest, dict) else None
    if not isinstance(steps, list):
        return [], ["steps must be a list"], None
    declared = []
    needs = {}
    for step in steps:
        if not isinstance(step, dict):
            continue
        step_id = step.get("id")
        if not isinstance(step_id, str) or not ID_PATTERN.match(step_id):
            continue
        if step_id in needs:
            continue
        raw_needs = step.get("needs", [])
        if raw_needs is None:
            raw_needs = []
        if not isinstance(raw_needs, list):
            return [], [f"step {step_id!r}: needs must be a list"], None
        declared.append(step_id)
        needs[step_id] = [need for need in raw_needs if isinstance(need, str)]
    missing = []
    for step_id in declared:
        for need in needs[step_id]:
            if need not in needs:
                message = f"step {step_id!r} needs unknown step {need!r}"
                if message not in missing:
                    missing.append(message)
    if missing:
        return [], missing, None
    remaining = list(declared)
    resolved = set()
    order = []
    while remaining:
        picked = None
        for step_id in remaining:
            if all(need in resolved for need in needs[step_id]):
                picked = step_id
                break
        if picked is None:
            return [], [], "cycle detected among steps: " + ", ".join(remaining)
        remaining.remove(picked)
        resolved.add(picked)
        order.append(picked)
    return order, [], None


def resolve_order(manifest) -> list:
    """Return a stable topological order of step ids (declaration order breaks ties).

    Raises SliceError for missing needs or a dependency cycle.
    """
    order, missing, cycle = _topological(manifest)
    if missing:
        raise SliceError("; ".join(missing))
    if cycle:
        raise SliceError(cycle)
    return order


def _valid_relative_path(value: str) -> bool:
    try:
        path = Path(value)
    except (TypeError, ValueError):
        return False
    return not path.is_absolute() and ".." not in path.parts


def validate_manifest(manifest) -> list:
    """Return a list of human-readable schema errors; empty means valid."""
    if not isinstance(manifest, dict):
        return ["manifest must be a JSON object"]
    errors = []
    if manifest.get("schema") != SCHEMA:
        errors.append(f"schema must be {SCHEMA!r}, found {manifest.get('schema')!r}")

    slice_id = manifest.get("id")
    if not isinstance(slice_id, str) or not ID_PATTERN.match(slice_id):
        errors.append(
            "id must be a 1-64 character string of letters, digits, '.', '_' or '-'"
        )

    project = manifest.get("project")
    if not isinstance(project, str) or not project.strip():
        errors.append("project must be a non-empty repo-relative path string")
    elif not _valid_relative_path(project):
        errors.append("project must be a repo-relative path without '..'")

    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        errors.append("artifacts must be a list of repo-relative paths")
    else:
        for index, artifact in enumerate(artifacts):
            label = f"artifacts[{index}]"
            if not isinstance(artifact, str) or not artifact.strip():
                errors.append(f"{label} must be a non-empty string")
            elif not _valid_relative_path(artifact):
                errors.append(f"{label} must be a repo-relative path without '..'")

    steps = manifest.get("steps")
    if not isinstance(steps, list) or not steps:
        errors.append("steps must be a non-empty list")
        steps = steps if isinstance(steps, list) else []

    seen = set()
    for index, step in enumerate(steps):
        label = f"steps[{index}]"
        if not isinstance(step, dict):
            errors.append(f"{label} must be an object")
            continue
        step_id = step.get("id")
        if not isinstance(step_id, str) or not ID_PATTERN.match(step_id):
            errors.append(
                f"{label}: id must be a 1-64 character string of letters, digits, '.', '_' or '-'"
            )
        elif step_id in seen:
            errors.append(f"{label}: duplicate step id {step_id!r}")
        else:
            seen.add(step_id)
        kind = step.get("kind")
        if kind not in STEP_KINDS:
            errors.append(f"{label}: unknown kind {kind!r}; choose one of {sorted(STEP_KINDS)}")
        required = step.get("required", True)
        if not isinstance(required, bool):
            errors.append(f"{label}: required must be true or false")
        needs = step.get("needs", [])
        if needs is None:
            needs = []
        if not isinstance(needs, list):
            errors.append(f"{label}: needs must be a list of step ids")
        elif not all(isinstance(need, str) for need in needs):
            errors.append(f"{label}: needs must be a list of step ids")
        elif len(set(needs)) != len(needs):
            errors.append(f"{label}: needs contains duplicate step ids")
        timeout = step.get("timeout")
        if timeout is not None and (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or timeout <= 0
        ):
            errors.append(f"{label}: timeout must be a positive number of seconds")
        args = step.get("args", {})
        if not isinstance(args, dict):
            errors.append(f"{label}: args must be an object")

    _order, missing, cycle = _topological(manifest)
    errors.extend(missing)
    if cycle:
        errors.append(cycle)
    return errors


def step_state_path(state_dir, slice_id) -> Path:
    """Return the durable state file for a slice run: <state_dir>/slices/<slice_id>.json."""
    if not isinstance(slice_id, str) or not ID_PATTERN.match(slice_id):
        raise SliceError(f"invalid slice id for a state path: {slice_id!r}")
    return Path(state_dir) / "slices" / f"{slice_id}.json"