#!/usr/bin/env python3
"""Phase-4 thin, read-only console (docs/ADR-003-workstream-architecture.md, Phase-4 gate).

The console is a presentation layer over state that already exists. It reads the
orchestrator's durable slice state (workstream/state/slices/*.json), the artifact
hashes/sizes recorded in it, artifact files themselves, and the git working tree. It never
writes, never runs a build, never calls the network and never creates state. Every value it
shows is derivable from what the CLI already wrote:

    python workstream/gypsy.py slices status ...
    workstream/state/slices/<slice>.json      (gypsy.slice-state/v1)
    workstream/state/slices/task-*.json       (gypsy.task-state/v1)
    git diff

There is no approval workflow in this repository and this module does not invent one: the
automated gates are the approval. collect_board reports that fact explicitly.

Public API:

    collect_board(state_dir, project_root) -> dict
    render_board(data) -> str
    preview_artifact(path, project_root) -> dict
    render_preview(data) -> str
    diff_report(project_root, staged=False, commit=None) -> dict
    render_diff(data) -> str
    main(argv=None) -> int

Preview is metadata-only and uses no external tools: PNG signature/IHDR dimensions, WAV
duration/channels/rate via the standard 'wave' module, JSON top-level type/keys, binary
glTF header magic/version, and RIFF/AVI or ISO-BMFF/MP4 size. Anything else is reported as
text or binary with its byte count.

The single subprocess is 'git diff --stat' / 'git diff --name-status': read-only, no
writes, cwd = project root, no pager, no colour, no external diff and
GIT_OPTIONAL_LOCKS=0. A missing git, a non-repository directory or a bad revision is
returned as an error value, never raised.

main is a thin manual entry point (board, preview PATH, diff); it only prints and therefore
keeps the no-write contract. The CLI wiring itself belongs to workstream/gypsy.py, which
this phase does not modify.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
import subprocess
import wave
from pathlib import Path

TASK_SCHEMA = "gypsy.task-state/v1"
SLICE_SCHEMA = "gypsy.slice-state/v1"
BOARD_SCHEMA = "gypsy.console-board/v1"
PREVIEW_SCHEMA = "gypsy.console-preview/v1"
DIFF_SCHEMA = "gypsy.console-diff/v1"
NO_STATE_MESSAGE = "no state yet - run slices run --all"
APPROVAL_NOTE = "no approval workflow; gates are automated"
DIFF_TIMEOUT = 30
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
GLB_MAGIC = b"glTF"
DEFAULT_STATE_DIR = Path(__file__).resolve().parent / "state"
DEFAULT_PROJECT_ROOT = Path(__file__).resolve().parent.parent


# -- shared helpers ---------------------------------------------------------


def _display(path, project_root) -> str:
    """Render path relative to project_root with forward slashes for stable output."""
    try:
        text = os.path.relpath(str(path), str(project_root))
    except (OSError, ValueError):
        text = str(path)
    return text.replace("\\", "/")


def _read_state_json(path):
    """Read one state document; return (dict, None) or (None, human readable error)."""
    try:
        text = Path(path).read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        return None, f"unreadable: {type(exc).__name__}: {exc}"
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON: {exc}"
    if not isinstance(data, dict):
        return None, "not a JSON object"
    return data, None


def _number(value):
    """Return a JSON number or None; booleans are not numbers."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def _int(value) -> int:
    value = _number(value)
    if value is None:
        return 0
    return int(value)


def _format_seconds(value) -> str:
    value = _number(value)
    if value is None:
        return "?"
    return f"{float(value):g}"


def _empty_counts() -> dict:
    return {"total": 0, "passed": 0, "failed": 0, "skipped": 0}


def _normalise_counts(value) -> dict:
    """Normalise a task-state count object or a slice-state step list into counts."""
    counts = _empty_counts()
    if isinstance(value, dict):
        for key in counts:
            counts[key] = _int(value.get(key))
    elif isinstance(value, list):
        for entry in value:
            if not isinstance(entry, dict):
                continue
            counts["total"] += 1
            status = entry.get("status")
            if status in ("passed", "failed", "skipped"):
                counts[status] += 1
    return counts


def _empty_artifacts() -> dict:
    return {"total": 0, "present": 0, "missing": 0, "bytes": 0, "missingPaths": []}


def _artifacts(entries) -> dict:
    """Count recorded artifacts; presence is the 'exists' field the run wrote."""
    summary = _empty_artifacts()
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        summary["total"] += 1
        if entry.get("exists"):
            summary["present"] += 1
            summary["bytes"] += _int(entry.get("bytes"))
        else:
            summary["missing"] += 1
            path = entry.get("path")
            if isinstance(path, str):
                summary["missingPaths"].append(path)
    return summary


def _status_text(status, passed) -> str:
    if isinstance(status, str) and status:
        return status
    return "passed" if passed else "failed"


def _status_label(status) -> str:
    if status in ("passed", "PASS"):
        return "PASS"
    if status in ("failed", "FAIL"):
        return "FAIL"
    if status == "not-run":
        return "NOT RUN"
    return str(status).upper() if status else "UNKNOWN"


def _pass_label(value) -> str:
    if value is True:
        return "PASS"
    if value is False:
        return "FAIL"
    return "UNKNOWN"


def _approvals() -> dict:
    return {"pending": [], "note": APPROVAL_NOTE}


# -- board ------------------------------------------------------------------


def _latest_task(slices_dir: Path, project_root):
    """Return (path, task document, errors) for the newest readable task state, if any."""
    candidates = [path for path in slices_dir.glob("task-*.json") if path.is_file()]
    if not candidates:
        return None, None, []

    def order_key(path):
        try:
            return (path.stat().st_mtime_ns, path.name)
        except OSError:
            return (0, path.name)

    errors = []
    for path in sorted(candidates, key=order_key, reverse=True):
        data, error = _read_state_json(path)
        if error is not None:
            errors.append(f"{_display(path, project_root)}: {error}")
            continue
        schema = data.get("schema")
        if isinstance(schema, str) and schema != TASK_SCHEMA:
            errors.append(f"{_display(path, project_root)}: not a {TASK_SCHEMA} document")
            continue
        return path, data, errors
    return None, None, errors


def _slice_row(state, path, project_root):
    """Build one board slice row plus the artifact entries it declares."""
    entries = [entry for entry in state.get("artifacts") or [] if isinstance(entry, dict)]
    slice_id = state.get("slice")
    row = {
        "slice": slice_id if isinstance(slice_id, str) else path.stem,
        "status": _status_text(None, state.get("passed")),
        "passed": bool(state.get("passed")),
        "steps": _normalise_counts(state.get("steps")),
        "artifacts": len(entries),
        "durationSeconds": _number(state.get("durationSeconds")),
        "errors": [str(item) for item in state.get("errors") or []],
        "statePath": _display(path, project_root),
        "startedAt": state.get("startedAt"),
        "finishedAt": state.get("finishedAt"),
    }
    return row, entries


def _board_from_task(task, path, state_dir, project_root, errors) -> dict:
    rows = []
    problems = list(errors)
    for summary in task.get("slices") or []:
        if not isinstance(summary, dict):
            continue
        slice_id = summary.get("slice")
        state_path = summary.get("statePath")
        row = {
            "slice": slice_id,
            "status": _status_text(summary.get("status"), summary.get("passed")),
            "passed": bool(summary.get("passed")),
            "steps": _normalise_counts(summary.get("steps")),
            "artifacts": _int(summary.get("artifacts")),
            "durationSeconds": _number(summary.get("durationSeconds")),
            "errors": [str(item) for item in summary.get("errors") or []],
            "statePath": _display(state_path, project_root) if isinstance(state_path, str) else None,
        }
        rows.append(row)
        for item in row["errors"]:
            problems.append(f"{slice_id}: {item}")
    entries = [entry for entry in task.get("artifacts") or [] if isinstance(entry, dict)]
    return {
        "schema": BOARD_SCHEMA,
        "stateKind": "task",
        "hasState": True,
        "projectRoot": _display(project_root, project_root),
        "stateDir": _display(state_dir, project_root),
        "statePath": _display(path, project_root),
        "task": task.get("task") if isinstance(task.get("task"), str) else path.stem,
        "startedAt": task.get("startedAt"),
        "finishedAt": task.get("finishedAt"),
        "durationSeconds": _number(task.get("durationSeconds")),
        "passed": bool(task.get("passed")),
        "slices": rows,
        "steps": _normalise_counts(task.get("steps")),
        "artifacts": _artifacts(entries),
        "errors": problems,
        "approvals": _approvals(),
        "message": None,
    }


def collect_board(state_dir, project_root) -> dict:
    """Read-only task board from the latest task state, else the per-slice states.

    The preferred source is the newest readable <state_dir>/slices/task-*.json. When no
    task state exists, each <state_dir>/slices/<slice>.json document is read instead. A
    missing state directory is not an error: the board says there is no state yet.

    The returned dict is JSON-safe and records the source (stateKind = task/slices/none),
    the slice rows (status, passed, step counts, artifact count, duration, errors), aggregate
    step counts, aggregate artifact counts (declared/present/missing/bytes), any state-read
    errors, and approvals: no pending approvals, because there is no approval workflow.
    """
    state_dir = Path(state_dir)
    project_root = Path(project_root)
    slices_dir = state_dir / "slices"
    board = {
        "schema": BOARD_SCHEMA,
        "stateKind": "none",
        "hasState": False,
        "projectRoot": _display(project_root, project_root),
        "stateDir": _display(state_dir, project_root),
        "statePath": None,
        "task": None,
        "startedAt": None,
        "finishedAt": None,
        "durationSeconds": None,
        "passed": None,
        "slices": [],
        "steps": _empty_counts(),
        "artifacts": _empty_artifacts(),
        "errors": [],
        "approvals": _approvals(),
        "message": NO_STATE_MESSAGE,
    }
    if not slices_dir.is_dir():
        return board

    task_path, task, errors = _latest_task(slices_dir, project_root)
    if task is not None:
        return _board_from_task(task, task_path, state_dir, project_root, errors)

    state_files = [
        path
        for path in sorted(slices_dir.glob("*.json"))
        if path.is_file() and not path.name.startswith("task-")
    ]
    rows = []
    entries = []
    for path in state_files:
        data, error = _read_state_json(path)
        if error is not None:
            errors.append(f"{_display(path, project_root)}: {error}")
            continue
        schema = data.get("schema")
        if isinstance(schema, str) and schema != SLICE_SCHEMA:
            errors.append(f"{_display(path, project_root)}: not a {SLICE_SCHEMA} document")
            continue
        row, row_entries = _slice_row(data, path, project_root)
        rows.append(row)
        entries.extend(row_entries)
        for item in row["errors"]:
            errors.append(f"{row['slice']}: {item}")
    if not rows and not errors:
        return board

    counts = _empty_counts()
    for row in rows:
        for key in counts:
            counts[key] += row["steps"][key]
    return {
        "schema": BOARD_SCHEMA,
        "stateKind": "slices",
        "hasState": True,
        "projectRoot": _display(project_root, project_root),
        "stateDir": _display(state_dir, project_root),
        "statePath": None,
        "task": None,
        "startedAt": None,
        "finishedAt": None,
        "durationSeconds": None,
        "passed": bool(rows) and all(row["passed"] for row in rows) and not errors,
        "slices": rows,
        "steps": counts,
        "artifacts": _artifacts(entries),
        "errors": errors,
        "approvals": _approvals(),
        "message": None,
    }


def render_board(data) -> str:
    """Render collect_board data as a compact plain-text board."""
    if not isinstance(data, dict):
        raise TypeError("board data must be a dict")
    if not data.get("hasState"):
        return NO_STATE_MESSAGE
    steps = _normalise_counts(data.get("steps"))
    artifacts = data.get("artifacts") or _empty_artifacts()
    lines = []
    if data.get("stateKind") == "task":
        lines.append(
            f"task {data.get('task') or '?'}: {_pass_label(data.get('passed'))} "
            f"({steps['passed']}/{steps['total']} steps, {artifacts.get('total', 0)} artifacts, "
            f"{_format_seconds(data.get('durationSeconds'))}s)"
        )
    else:
        lines.append(
            f"slices: {_pass_label(data.get('passed'))} "
            f"({len(data.get('slices') or [])} slices, {steps['passed']}/{steps['total']} steps, "
            f"{artifacts.get('total', 0)} artifacts)"
        )
    for row in data.get("slices") or []:
        if not isinstance(row, dict):
            continue
        row_steps = _normalise_counts(row.get("steps"))
        lines.append(
            f"  {row.get('slice')}: {_status_label(row.get('status'))} "
            f"({row_steps['passed']}/{row_steps['total']} steps, "
            f"{_int(row.get('artifacts'))} artifacts, "
            f"{_format_seconds(row.get('durationSeconds'))}s)"
        )
    lines.append(
        f"artifacts: {artifacts.get('total', 0)} declared, {artifacts.get('present', 0)} present, "
        f"{artifacts.get('missing', 0)} missing ({artifacts.get('bytes', 0)} bytes)"
    )
    for path in artifacts.get("missingPaths") or []:
        lines.append(f"  MISSING {path}")
    approvals = data.get("approvals") or {}
    lines.append(
        f"approvals: {len(approvals.get('pending') or [])} pending - "
        f"{approvals.get('note') or APPROVAL_NOTE}"
    )
    errors = [str(item) for item in data.get("errors") or []]
    if errors:
        lines.append("errors:")
        for item in errors:
            lines.append(f"  {item}")
    if data.get("statePath"):
        lines.append(f"state: {data['statePath']}")
    return "\n".join(lines)


# -- artifact preview -------------------------------------------------------


def _read_head(path, count: int) -> bytes:
    try:
        with open(path, "rb") as handle:
            return handle.read(count)
    except OSError:
        return b""


def _sha256(path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _preview_png(result, target) -> None:
    header = _read_head(target, 24)
    if len(header) < 24:
        result["error"] = "truncated PNG header"
        return
    if header[12:16] != b"IHDR":
        result["error"] = "PNG has no IHDR chunk"
        return
    width, height = struct.unpack(">II", header[16:24])
    result["width"] = width
    result["height"] = height


def _preview_wav(result, target) -> None:
    try:
        with wave.open(str(target), "rb") as handle:
            channels = handle.getnchannels()
            rate = handle.getframerate()
            frames = handle.getnframes()
    except (wave.Error, EOFError, OSError) as exc:
        result["error"] = f"unreadable WAV: {exc}"
        return
    result["channels"] = channels
    result["sampleRate"] = rate
    result["frames"] = frames
    if rate:
        result["durationSeconds"] = round(frames / rate, 3)


def _preview_json(result, target) -> None:
    try:
        text = target.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        result["error"] = f"unreadable JSON: {type(exc).__name__}: {exc}"
        return
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        result["error"] = f"invalid JSON: {exc}"
        return
    if isinstance(data, dict):
        result["jsonType"] = "object"
        result["topLevelKeys"] = sorted(str(key) for key in data)
    elif isinstance(data, list):
        result["jsonType"] = "array"
    else:
        result["jsonType"] = type(data).__name__


def _preview_glb(result, target) -> None:
    header = _read_head(target, 12)
    if len(header) < 12:
        result["error"] = "truncated GLB header"
        return
    result["glbMagic"] = header[:4].decode("ascii", "replace")
    version, length = struct.unpack("<II", header[4:12])
    result["glbVersion"] = version
    result["glbLength"] = length
    if version != 2:
        result["error"] = f"unsupported GLB version {version} (expected 2)"


def _looks_text(target) -> bool:
    sample = _read_head(target, 512)
    if not sample:
        return True
    if b"\x00" in sample:
        return False
    try:
        sample.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def _describe_artifact(result, target) -> None:
    header = _read_head(target, 16)
    extension = result["extension"]
    if header.startswith(PNG_SIGNATURE):
        result["kind"] = "png"
        _preview_png(result, target)
    elif header[:4] == b"RIFF" and header[8:12] == b"WAVE":
        result["kind"] = "wav"
        _preview_wav(result, target)
    elif header[:4] == GLB_MAGIC:
        result["kind"] = "glb"
        _preview_glb(result, target)
    elif header[:4] == b"RIFF" and header[8:12] == b"AVI ":
        result["kind"] = "video"
        result["videoFormat"] = "avi"
    elif len(header) >= 8 and header[4:8] == b"ftyp":
        result["kind"] = "video"
        result["videoFormat"] = "mp4"
    elif extension == ".json":
        result["kind"] = "json"
        _preview_json(result, target)
    else:
        fallback = {
            ".png": "png",
            ".wav": "wav",
            ".glb": "glb",
            ".json": "json",
            ".mp4": "video",
            ".m4v": "video",
            ".mov": "video",
            ".avi": "video",
        }
        kind = fallback.get(extension)
        if kind is not None:
            result["kind"] = kind
            if kind == "video":
                result["videoFormat"] = "avi" if extension == ".avi" else "mp4"
            elif kind == "glb":
                result["error"] = "not a GLB file (missing glTF magic)"
            else:
                result["error"] = f"not a {kind} file (signature did not match)"
        else:
            result["kind"] = "text" if _looks_text(target) else "binary"


def preview_artifact(path, project_root) -> dict:
    """Describe one artifact read-only, without external tools.

    Returns a JSON-safe dict with the project-relative path, existence, byte count, SHA-256
    and kind, plus kind-specific metadata:

    * png - width, height (from IHDR)
    * wav - durationSeconds, channels, sampleRate, frames
    * json - jsonType (object/array/scalar) and topLevelKeys for an object
    * glb - glbMagic, glbVersion, glbLength
    * video (avi/mp4) - videoFormat (the byte count is the size)

    Other files are text or binary. A missing file has kind missing; an unreadable or
    malformed file carries an error value instead of raising.
    """
    project_root = Path(project_root)
    target = Path(path)
    if not target.is_absolute():
        target = project_root / target
    result = {
        "schema": PREVIEW_SCHEMA,
        "path": _display(target, project_root),
        "absolute": str(target),
        "exists": False,
        "bytes": None,
        "sha256": None,
        "kind": "missing",
        "extension": target.suffix.lower(),
        "width": None,
        "height": None,
        "durationSeconds": None,
        "channels": None,
        "sampleRate": None,
        "frames": None,
        "topLevelKeys": None,
        "jsonType": None,
        "glbMagic": None,
        "glbVersion": None,
        "glbLength": None,
        "videoFormat": None,
        "error": None,
    }
    try:
        if not target.is_file():
            result["error"] = f"no such file: {result['path']}"
            return result
        result["exists"] = True
        result["bytes"] = target.stat().st_size
        result["sha256"] = _sha256(target)
        _describe_artifact(result, target)
    except OSError as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


def render_preview(data) -> str:
    """Render preview_artifact data as plain text."""
    if not isinstance(data, dict):
        raise TypeError("preview data must be a dict")
    path = data.get("path") or "?"
    if not data.get("exists"):
        lines = [f"MISSING {path}"]
        if data.get("error"):
            lines.append(f"  {data['error']}")
        return "\n".join(lines)
    lines = [
        f"{path}  kind={data.get('kind')}  {data.get('bytes')} bytes  "
        f"sha256={data.get('sha256')}"
    ]
    kind = data.get("kind")
    if kind == "png" and data.get("width") is not None:
        lines.append(f"  PNG {data['width']}x{data['height']}")
    elif kind == "wav" and data.get("sampleRate"):
        lines.append(
            f"  WAV {_format_seconds(data.get('durationSeconds'))}s "
            f"{data.get('channels')}ch {data.get('sampleRate')}Hz"
        )
    elif kind == "json":
        if data.get("jsonType") == "object":
            keys = data.get("topLevelKeys") or []
            lines.append(f"  JSON object keys: {', '.join(keys) if keys else '(none)'}")
        else:
            lines.append(f"  JSON {data.get('jsonType') or 'unknown'}")
    elif kind == "glb":
        lines.append(
            f"  GLB {data.get('glbMagic')} v{data.get('glbVersion')} "
            f"declared={data.get('glbLength')} bytes"
        )
    elif kind == "video":
        lines.append(f"  video {data.get('videoFormat') or '?'} {data.get('bytes')} bytes")
    elif kind == "text":
        lines.append(f"  text {data.get('bytes')} bytes")
    elif kind == "binary":
        lines.append(f"  binary {data.get('bytes')} bytes")
    if data.get("error"):
        lines.append(f"  ERROR {data['error']}")
    return "\n".join(lines)


# -- diff -------------------------------------------------------------------


def _git_environment() -> dict:
    environment = dict(os.environ)
    # No optional index lock/refresh: the console is read-only.
    environment["GIT_OPTIONAL_LOCKS"] = "0"
    return environment


def _run_git(argv, cwd):
    """Run one read-only git command; return (stdout, error)."""
    try:
        completed = subprocess.run(
            list(argv),
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=DIFF_TIMEOUT,
            shell=False,
            env=_git_environment(),
        )
    except FileNotFoundError:
        return None, "git unavailable: the git executable was not found on PATH"
    except subprocess.TimeoutExpired:
        return None, f"git unavailable: timed out after {DIFF_TIMEOUT}s"
    except OSError as exc:
        return None, f"git unavailable: {type(exc).__name__}: {exc}"
    if completed.returncode != 0:
        message = (completed.stderr or completed.stdout or "").strip()
        return None, f"git diff failed: {message or f'git exited {completed.returncode}'}"
    return completed.stdout, None


def _git_argv(base, options, commit):
    argv = list(base)
    argv.extend(options)
    if commit:
        argv.append(commit)
    argv.append("--")
    return argv


def _parse_name_status(text) -> list:
    files = []
    for line in (text or "").splitlines():
        if not line.strip():
            continue
        fields = line.split("\t")
        if len(fields) < 2:
            continue
        status = fields[0]
        entry = {
            "status": status,
            "change": status[:1] if status else "?",
            "path": fields[-1],
        }
        if len(fields) >= 3:
            entry["from"] = fields[1]
        files.append(entry)
    return files


def diff_report(project_root, staged=False, commit=None) -> dict:
    """Read-only git diff summary: --stat text plus parsed --name-status files.

    staged=True uses 'git diff --cached'; commit compares that revision with the
    index/working tree ('git diff <commit>'). The only subprocess is git diff itself, with
    pager, colour and external diff disabled and optional index locks off. A missing git, a
    directory that is not a repository, or a bad revision yields available=False and an
    error string instead of raising.
    """
    root = Path(project_root)
    commit_value = commit if isinstance(commit, str) else None
    result = {
        "schema": DIFF_SCHEMA,
        "available": False,
        "root": str(root),
        "staged": bool(staged),
        "commit": commit_value,
        "target": "staged" if staged else (commit_value or "worktree"),
        "stat": "",
        "nameStatus": "",
        "text": "",
        "files": [],
        "error": None,
    }
    if commit is not None:
        if not isinstance(commit, str) or not commit.strip():
            result["error"] = "invalid commit: expected a non-empty revision string"
            return result
        if commit.startswith("-") or any(
            character in commit for character in ("\n", "\r", "\x00")
        ):
            result["error"] = (
                f"invalid commit {commit!r}: a revision must not look like a git option "
                "or contain a newline"
            )
            return result

    base = ["git", "--no-pager", "diff", "--no-color", "--no-ext-diff"]
    if result["staged"]:
        base.append("--cached")
    stdout, error = _run_git(_git_argv(base, ["--stat"], commit_value), root)
    if error is not None:
        result["error"] = error
        return result
    status_stdout, error = _run_git(_git_argv(base, ["--name-status"], commit_value), root)
    if error is not None:
        result["error"] = error
        return result
    result["available"] = True
    result["stat"] = stdout.strip()
    result["text"] = stdout.strip()
    result["nameStatus"] = status_stdout.strip()
    result["files"] = _parse_name_status(status_stdout)
    return result


def render_diff(data) -> str:
    """Render diff_report data as plain text."""
    if not isinstance(data, dict):
        raise TypeError("diff data must be a dict")
    if not data.get("available"):
        return data.get("error") or "git unavailable: unknown error"
    if data.get("staged"):
        label = "staged changes"
    elif data.get("commit"):
        label = f"changes vs {data['commit']}"
    else:
        label = "working tree changes"
    lines = [f"diff {label}"]
    text = (data.get("text") or "").strip()
    if text:
        lines.append(text)
    files = data.get("files") or []
    if files:
        lines.append(f"files: {len(files)}")
        for entry in files:
            if not isinstance(entry, dict):
                continue
            if entry.get("from"):
                lines.append(f"  {entry.get('status')} {entry['from']} -> {entry.get('path')}")
            else:
                lines.append(f"  {entry.get('status')} {entry.get('path')}")
    elif not text:
        lines.append("no changes")
    else:
        lines.append("files: 0")
    return "\n".join(lines)


# -- manual entry point -----------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="console.py",
        description="read-only ProjectGypsy console (board, artifact preview, git diff)",
    )
    parser.add_argument("--state-dir", default=str(DEFAULT_STATE_DIR))
    parser.add_argument("--project-root", default=str(DEFAULT_PROJECT_ROOT))
    parser.add_argument("--json", action="store_true")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("board", help="show the latest task/slice state")
    preview = subparsers.add_parser("preview", help="describe an artifact without external tools")
    preview.add_argument("path")
    diff = subparsers.add_parser("diff", help="show read-only git changes")
    diff.add_argument("--staged", action="store_true")
    diff.add_argument("--commit", default=None)
    return parser


def main(argv=None) -> int:
    """Manual console entry point. Prints only; never writes. Returns a shell status."""
    args = _build_parser().parse_args(argv)
    if args.command == "board":
        data = collect_board(args.state_dir, args.project_root)
        print(json.dumps(data, indent=2) if args.json else render_board(data))
        return 0 if data.get("hasState") and data.get("passed") else 1
    if args.command == "preview":
        data = preview_artifact(args.path, args.project_root)
        print(json.dumps(data, indent=2) if args.json else render_preview(data))
        return 0 if data.get("exists") else 1
    data = diff_report(args.project_root, staged=args.staged, commit=args.commit)
    print(json.dumps(data, indent=2) if args.json else render_diff(data))
    return 0 if data.get("available") else 1


if __name__ == "__main__":
    raise SystemExit(main())
