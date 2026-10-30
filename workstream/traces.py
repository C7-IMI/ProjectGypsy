#!/usr/bin/env python3
"""Deterministic hierarchical traces over Gypsy run state (local, disk-derived).

Gypsy records each run as JSON state (gypsy.task-state/v1, gypsy.slice-state/v1 and
gypsy.toolpack-state/v1). This module turns that state into one trace per run:

    run (task)        -> slice summary spans
    run (slice)       -> step spans
    run (toolpack)    -> action spans
    run (action-only) -> one root span with the action detail

There is no live instrumentation and no collector: every trace is reconstructed from files
under workstream/state, the ids are deterministic hashes of the state, and nothing is sent over
the network. The export shape is OTEL-inspired so a real collector could one day consume it, but
it is explicitly labelled local and partial.

Trace model gypsy.trace/v1
--------------------------
Payload:
    schema, generated, source {stateDir, collector, live, note}, traces, counts, warnings, errors

Each trace: traceId, kind (task|slice|toolpack|toolpack-action|problem), name, runId, sourceFile,
startTime, endTime, durationSeconds, status, spans.

Each span: traceId, spanId, parentSpanId, name, kind (run|slice|step|action|problem), status
(ok|error|skipped|unset), startTime, endTime, durationSeconds, attributes.

Ids use the W3C Trace Context shape: traceId is 32 lowercase hex characters and spanId is 16
lowercase hex characters. They are derived as SHA-256 prefixes of the state file path and the
recorded run identity, so two collections of the same state produce the same ids; they are
deterministic ids, not random ones.

Honesty rules:
* A field the state does not record is null, not invented. A task's per-slice start/end times are
  not recorded, so those spans carry the recorded duration only and timingRecorded=false; step
  and root spans carry real times when the state has them.
* A task state records only slice summaries. Its slice spans therefore use the summary and do
  not import the latest state/slices/<slice>.json step list (that file may be from another run).
* A missing state directory, an unreadable file, invalid JSON, a JSON value that is not an
  object, or an unexpected schema becomes a problem trace (kind=problem, status=error). No run
  is fabricated for it.
* Toolpack action state files referenced by a toolpack run state are represented inside that
  run's trace; they are not emitted twice. Other action-only files become their own traces.
* The engine attribute is filled only when the slice state names a project with a readable
  project.gypsy.json; otherwise it is null with engineSource=null.
* Full command output is not copied into spans: outputBytes/stdoutTail are bounded attributes.

Canonical ordering: traces are sorted by (startTime or empty, traceId); within a trace spans are
in pre-order, and children are ordered by recorded order (sliceOrder/stepOrder/actionOrder) with
start time and name as tie-breaks. Every list of spans is therefore stable across runs.

OTEL export: to_otel(payload) returns an explicitly local resourceSpans document. It keeps the
deterministic ids, maps status to OTEL codes (0 unset, 1 ok, 2 error), uses INTERNAL span kind
and emits int64 values as decimal strings per the OTEL JSON protocol. Times are omitted when the
state did not record them. It is not a live exporter and never opens a socket.

Public API
----------
    SCHEMA, TASK_SCHEMA, SLICE_SCHEMA, TOOLPACK_SCHEMA, TRACE_KINDS, SPAN_KINDS, STATUSES,
    OTEL_NOTE, TraceError
    collect(state_dir=None) -> dict
    validate(payload) -> list[str]
    problems(payload) -> list[str]
    to_json(payload, indent=2) -> str
    to_otel(payload) -> dict
    render_summary(payload) -> str
    main(argv=None) -> int

Usage:
    python workstream/traces.py [--state-dir PATH] [--json]
    python workstream/traces.py --otel
    python workstream/traces.py --validate [--json]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import gypsy

SCHEMA = "gypsy.trace/v1"
TASK_SCHEMA = "gypsy.task-state/v1"
SLICE_SCHEMA = "gypsy.slice-state/v1"
TOOLPACK_SCHEMA = "gypsy.toolpack-state/v1"
TRACE_KINDS = ("task", "slice", "toolpack", "toolpack-action", "problem")
SPAN_KINDS = ("run", "slice", "step", "action", "problem")
STATUSES = ("ok", "error", "skipped", "unset")
OTEL_NOTE = (
    "Local, disk-derived trace. Not live instrumentation; nothing is sent to a collector."
)
HEX32 = re.compile(r"^[0-9a-f]{32}$")
HEX16 = re.compile(r"^[0-9a-f]{16}$")
PATH_SPLIT = re.compile(r"[\\/]")


class TraceError(ValueError):
    """A trace payload or state file is unreadable, invalid or not JSON-safe."""


def _digest(text: str, size: int) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:size]


def _posix(value: str) -> str:
    return value.replace("\\", "/")


def _label(path: Path) -> str:
    try:
        return path.resolve().relative_to(gypsy.REPO_ROOT).as_posix()
    except (OSError, ValueError):
        return _posix(str(path.resolve() if path.is_absolute() else path))


def _basename(value):
    if not isinstance(value, str) or not value.strip():
        return None
    parts = [part for part in PATH_SPLIT.split(value.strip()) if part]
    return parts[-1] if parts else None


def _parse_time(value):
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _iso(dt):
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _duration(seconds, start, end):
    if isinstance(seconds, (int, float)) and not isinstance(seconds, bool) and seconds >= 0:
        return round(float(seconds), 3)
    if start is not None and end is not None and end >= start:
        return round((end - start).total_seconds(), 3)
    return None


def _status(passed, recorded=None):
    if isinstance(recorded, str):
        mapped = {
            "passed": "ok",
            "ok": "ok",
            "failed": "error",
            "error": "error",
            "skipped": "skipped",
            "unset": "unset",
            "blocked": "error",
        }.get(recorded.strip().lower())
        if mapped:
            return mapped
    if isinstance(passed, bool):
        return "ok" if passed else "error"
    return "unset"


def _reject_constant(value):
    raise ValueError("non-finite number {!r} is not allowed in state".format(value))


def _read_state(path: Path):
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise TraceError("unreadable: {}".format(exc)) from exc
    try:
        data = json.loads(text, parse_constant=_reject_constant)
    except json.JSONDecodeError as exc:
        raise TraceError("invalid JSON: {}".format(exc)) from exc
    except ValueError as exc:
        raise TraceError("invalid state value: {}".format(exc)) from exc
    if not isinstance(data, dict):
        raise TraceError("state file must be a JSON object")
    return data


def _artifacts(items):
    result = []
    if not isinstance(items, list):
        return result
    for item in items:
        if not isinstance(item, dict):
            continue
        entry = {}
        for field in ("path", "slice", "action", "declaredAs"):
            value = item.get(field)
            if isinstance(value, str):
                entry[field] = value
        for field in ("bytes",):
            value = item.get(field)
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                entry[field] = value
        digest = item.get("sha256")
        if isinstance(digest, str):
            entry["sha256"] = digest
        if isinstance(item.get("exists"), bool):
            entry["exists"] = item["exists"]
        result.append(entry)
        if len(result) >= 200:
            break
    return result


def _errors(items):
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, str)][:50]


def _dict_or_none(value):
    return value if isinstance(value, dict) else None


def _text_bytes(value):
    if isinstance(value, str):
        return len(value.encode("utf-8", "replace"))
    return None


def _tail(value, limit=500):
    if not isinstance(value, str) or not value:
        return None
    return value[-limit:]


def _project_engine(project):
    if not isinstance(project, str) or not project.strip():
        return None, None, None
    relative = Path(project.strip())
    if relative.is_absolute() or ".." in relative.parts:
        return None, None, None
    manifest = gypsy.REPO_ROOT / relative / "project.gypsy.json"
    try:
        data = json.loads(manifest.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError, ValueError):
        return None, None, None
    engine = data.get("engine") if isinstance(data, dict) else None
    if not isinstance(engine, dict):
        return None, None, None
    engine_id = engine.get("id") if isinstance(engine.get("id"), str) else None
    version = engine.get("version") if isinstance(engine.get("version"), str) else None
    source = "project.gypsy.json" if engine_id else None
    return engine_id, version, source


def _span(trace_id, span_id, parent, name, kind, status, start, end, duration, attributes):
    return {
        "traceId": trace_id,
        "spanId": span_id,
        "parentSpanId": parent,
        "name": name,
        "kind": kind,
        "status": status,
        "startTime": start,
        "endTime": end,
        "durationSeconds": duration,
        "attributes": attributes,
    }


def _make_trace(kind, name, run_id, source_file, root_attributes, children):
    """Build one trace. children are dicts with key, name, kind, status, times, duration,
    attributes and an order index; they are sorted canonically before ids are assigned."""
    trace_id = _digest("gypsy.trace/v1|" + kind + "|" + source_file, 32)
    root_span_id = _digest(trace_id + "|root", 16)
    ordered = sorted(
        children,
        key=lambda child: (
            child.get("startTime") or "",
            child.get("order", 0),
            child.get("name", ""),
        ),
    )
    spans = [
        _span(
            trace_id,
            root_span_id,
            None,
            name,
            "problem" if kind == "problem" else "run",
            root_attributes.pop("_status", "unset"),
            root_attributes.pop("_start", None),
            root_attributes.pop("_end", None),
            root_attributes.pop("_duration", None),
            root_attributes,
        )
    ]
    for child in ordered:
        span_id = _digest(root_span_id + "|" + child["key"], 16)
        spans.append(
            _span(
                trace_id,
                span_id,
                root_span_id,
                child["name"],
                child["kind"],
                child["status"],
                child.get("startTime"),
                child.get("endTime"),
                child.get("durationSeconds"),
                child["attributes"],
            )
        )
    root = spans[0]
    return {
        "traceId": trace_id,
        "kind": kind,
        "name": name,
        "runId": run_id,
        "sourceFile": source_file,
        "startTime": root["startTime"],
        "endTime": root["endTime"],
        "durationSeconds": root["durationSeconds"],
        "status": root["status"],
        "spans": spans,
    }


def _problem_trace(source_file, message):
    return _make_trace(
        "problem",
        "problem: " + source_file,
        None,
        source_file,
        {
            "_status": "error",
            "path": source_file,
            "error": message,
        },
        [],
    )


def _task_trace(rel, data):
    start = _parse_time(data.get("startedAt"))
    end = _parse_time(data.get("finishedAt"))
    duration = _duration(data.get("durationSeconds"), start, end)
    status = _status(data.get("passed"))
    slices = data.get("slices") if isinstance(data.get("slices"), list) else []
    order = []
    if isinstance(data.get("sliceOrder"), list):
        order = [item for item in data["sliceOrder"] if isinstance(item, str)]
    index = {name: position for position, name in enumerate(order)}
    all_artifacts = data.get("artifacts") if isinstance(data.get("artifacts"), list) else []
    children = []
    for position, summary in enumerate(slices):
        if not isinstance(summary, dict):
            continue
        slice_name = summary.get("slice") if isinstance(summary.get("slice"), str) else "?"
        artifacts = [
            item
            for item in all_artifacts
            if isinstance(item, dict) and item.get("slice") == slice_name
        ]
        children.append(
            {
                "key": "slice:" + slice_name,
                "name": "slice " + slice_name,
                "kind": "slice",
                "status": _status(summary.get("passed"), summary.get("status")),
                "startTime": None,
                "endTime": None,
                "durationSeconds": _duration(summary.get("durationSeconds"), None, None),
                "order": index.get(slice_name, 1000 + position),
                "attributes": {
                    "slice": slice_name,
                    "recordedStatus": summary.get("status"),
                    "passed": summary.get("passed"),
                    "steps": summary.get("steps"),
                    "artifactCount": summary.get("artifacts"),
                    "artifacts": _artifacts(artifacts),
                    "errors": _errors(summary.get("errors")),
                    "cache": _dict_or_none(summary.get("cache")),
                    "stateFile": _basename(summary.get("statePath")),
                    "timingRecorded": False,
                    "timingNote": "per-slice start/end are not recorded in gypsy.task-state/v1",
                },
            }
        )
    attributes = {
        "stateFile": rel,
        "schema": TASK_SCHEMA,
        "task": data.get("task"),
        "passed": data.get("passed"),
        "steps": data.get("steps"),
        "sliceCount": len(slices),
        "artifactCount": len(all_artifacts),
        "artifacts": _artifacts(all_artifacts),
        "cache": _dict_or_none(data.get("cache")),
        "parallel": _dict_or_none(data.get("parallel")),
        "errors": _errors(data.get("errors")),
        "engine": None,
        "engineVersion": None,
        "engineSource": None,
    }
    return _make_trace(
        "task",
        "run " + str(data.get("task") or Path(rel).stem),
        data.get("task") if isinstance(data.get("task"), str) else None,
        rel,
        dict(attributes, _start=_iso(start), _end=_iso(end), _duration=duration, _status=status),
        children,
    )


def _slice_step_children(data):
    steps = data.get("steps") if isinstance(data.get("steps"), list) else []
    order = []
    if isinstance(data.get("stepOrder"), list):
        order = [item for item in data["stepOrder"] if isinstance(item, str)]
    index = {name: position for position, name in enumerate(order)}
    children = []
    for position, step in enumerate(steps):
        if not isinstance(step, dict):
            continue
        step_id = step.get("id") if isinstance(step.get("id"), str) else "?"
        start = _parse_time(step.get("startedAt"))
        end = _parse_time(step.get("finishedAt"))
        seconds = step.get("seconds")
        duration = _duration(seconds, start, end)
        output = step.get("output") if isinstance(step.get("output"), str) else None
        children.append(
            {
                "key": "step:" + step_id,
                "name": "step " + step_id,
                "kind": "step",
                "status": _status(None, step.get("status")),
                "startTime": _iso(start),
                "endTime": _iso(end),
                "durationSeconds": duration,
                "order": index.get(step_id, 1000 + position),
                "attributes": {
                    "step": step_id,
                    "stepKind": step.get("kind"),
                    "required": step.get("required"),
                    "attempted": step.get("attempted"),
                    "cached": step.get("cached"),
                    "cacheHit": bool(step.get("cached")) if isinstance(step.get("cached"), bool) else None,
                    "exit": step.get("exit"),
                    "error": step.get("error"),
                    "outputBytes": _text_bytes(output),
                    "outputTruncated": "[truncated]" in output if output else None,
                    "recordedStatus": step.get("status"),
                    "timingRecorded": bool(start is not None or isinstance(seconds, (int, float))),
                },
            }
        )
    return children


def _slice_trace(rel, data):
    start = _parse_time(data.get("startedAt"))
    end = _parse_time(data.get("finishedAt"))
    duration = _duration(data.get("durationSeconds"), start, end)
    status = _status(data.get("passed"))
    engine, engine_version, engine_source = _project_engine(data.get("project"))
    artifacts = data.get("artifacts") if isinstance(data.get("artifacts"), list) else []
    attributes = {
        "stateFile": rel,
        "schema": SLICE_SCHEMA,
        "slice": data.get("slice"),
        "project": data.get("project"),
        "runId": data.get("runId"),
        "manifestSha256": data.get("manifestSha256"),
        "passed": data.get("passed"),
        "timeoutScale": data.get("timeoutScale"),
        "resumed": data.get("resumed"),
        "stepCount": len(data.get("steps") or []),
        "artifactCount": len(artifacts),
        "artifacts": _artifacts(artifacts),
        "ledgerFile": _basename(data.get("ledgerPath")),
        "cache": _dict_or_none(data.get("cache")),
        "errors": _errors(data.get("errors")),
        "engine": engine,
        "engineVersion": engine_version,
        "engineSource": engine_source,
    }
    return _make_trace(
        "slice",
        "run " + str(data.get("slice") or Path(rel).stem),
        data.get("runId") if isinstance(data.get("runId"), str) else None,
        rel,
        dict(attributes, _start=_iso(start), _end=_iso(end), _duration=duration, _status=status),
        _slice_step_children(data),
    )


def _action_children(data):
    actions = data.get("actions") if isinstance(data.get("actions"), list) else []
    order = []
    if isinstance(data.get("actionOrder"), list):
        order = [item for item in data["actionOrder"] if isinstance(item, str)]
    index = {name: position for position, name in enumerate(order)}
    children = []
    for position, action in enumerate(actions):
        if not isinstance(action, dict):
            continue
        action_name = action.get("action") if isinstance(action.get("action"), str) else "?"
        children.append(
            {
                "key": "action:" + action_name,
                "name": "action " + action_name,
                "kind": "action",
                "status": _status(action.get("passed"), action.get("status")),
                "startTime": None,
                "endTime": None,
                "durationSeconds": _duration(action.get("seconds"), None, None),
                "order": index.get(action_name, 1000 + position),
                "attributes": {
                    "action": action_name,
                    "recordedStatus": action.get("status"),
                    "passed": action.get("passed"),
                    "exit": action.get("exit"),
                    "timedOut": action.get("timedOut"),
                    "artifactCount": action.get("artifacts"),
                    "validatorCount": action.get("validators"),
                    "errors": _errors(action.get("errors")),
                    "cache": _dict_or_none(action.get("cache")),
                    "stateFile": _basename(action.get("statePath")),
                    "timingRecorded": False,
                    "timingNote": "per-action start/end are not recorded in the run summary",
                },
            }
        )
    return children


def _toolpack_trace(rel, data):
    start = _parse_time(data.get("startedAt"))
    end = _parse_time(data.get("finishedAt"))
    duration = _duration(data.get("durationSeconds"), start, end)
    status = _status(data.get("passed"))
    artifacts = data.get("artifacts") if isinstance(data.get("artifacts"), list) else []
    validators = data.get("validators") if isinstance(data.get("validators"), list) else []
    attributes = {
        "stateFile": rel,
        "schema": TOOLPACK_SCHEMA,
        "scope": "toolpack",
        "toolpack": data.get("toolpack"),
        "toolpackName": data.get("toolpackName"),
        "runId": data.get("runId"),
        "manifestSha256": data.get("manifestSha256"),
        "passed": data.get("passed"),
        "actionCount": len(data.get("actions") or []),
        "artifactCount": len(artifacts),
        "artifacts": _artifacts(artifacts),
        "validatorCount": len(validators),
        "cache": _dict_or_none(data.get("cache")),
        "parallel": _dict_or_none(data.get("parallel")),
        "tools": [item for item in (data.get("tools") or []) if isinstance(item, str)],
        "license": data.get("license"),
        "errors": _errors(data.get("errors")),
        "engine": None,
        "engineVersion": None,
        "engineSource": None,
    }
    return _make_trace(
        "toolpack",
        "run " + str(data.get("toolpack") or Path(rel).stem),
        data.get("runId") if isinstance(data.get("runId"), str) else None,
        rel,
        dict(attributes, _start=_iso(start), _end=_iso(end), _duration=duration, _status=status),
        _action_children(data),
    )


def _action_only_trace(rel, data):
    start = _parse_time(data.get("startedAt"))
    end = _parse_time(data.get("finishedAt"))
    duration = _duration(data.get("durationSeconds"), start, end)
    status = _status(data.get("passed"))
    command = data.get("command") if isinstance(data.get("command"), dict) else {}
    artifacts = data.get("artifacts") if isinstance(data.get("artifacts"), list) else []
    validators = data.get("validators") if isinstance(data.get("validators"), list) else []
    attributes = {
        "stateFile": rel,
        "schema": TOOLPACK_SCHEMA,
        "scope": "action",
        "toolpack": data.get("toolpack"),
        "toolpackName": data.get("toolpackName"),
        "action": data.get("action"),
        "runId": data.get("runId"),
        "passed": data.get("passed"),
        "timedOut": data.get("timedOut"),
        "exit": data.get("exit"),
        "seconds": data.get("seconds"),
        "timeoutSeconds": data.get("timeoutSeconds"),
        "argv": [item for item in (command.get("argv") or []) if isinstance(item, str)],
        "cwd": command.get("cwd"),
        "stdoutBytes": _text_bytes(data.get("stdout")),
        "stderrBytes": _text_bytes(data.get("stderr")),
        "stdoutTail": _tail(data.get("stdout")),
        "stderrTail": _tail(data.get("stderr")),
        "artifactCount": len(artifacts),
        "artifacts": _artifacts(artifacts),
        "validatorCount": len(validators),
        "tools": [item for item in (data.get("tools") or []) if isinstance(item, str)],
        "license": data.get("license"),
        "errors": _errors(data.get("errors")),
        "engine": None,
        "engineVersion": None,
        "engineSource": None,
    }
    name = "action {}/{}".format(data.get("toolpack") or "?", data.get("action") or "?")
    return _make_trace(
        "toolpack-action",
        "run " + name,
        data.get("runId") if isinstance(data.get("runId"), str) else None,
        rel,
        dict(attributes, _start=_iso(start), _end=_iso(end), _duration=duration, _status=status),
        [],
    )


def _finish(payload, traces, warnings):
    traces = sorted(traces, key=lambda trace: (trace.get("startTime") or "", trace["traceId"]))
    spans = sum(len(trace["spans"]) for trace in traces)
    problem_traces = [trace for trace in traces if trace["kind"] == "problem"]
    counts = {
        "traces": len(traces),
        "spans": spans,
        "problemTraces": len(problem_traces),
        "problemSpans": sum(len(trace["spans"]) for trace in problem_traces),
        "okTraces": sum(1 for trace in traces if trace["status"] == "ok"),
        "errorTraces": sum(1 for trace in traces if trace["status"] == "error"),
        "unsetTraces": sum(1 for trace in traces if trace["status"] == "unset"),
        "byKind": {
            kind: sum(1 for trace in traces if trace["kind"] == kind) for kind in TRACE_KINDS
        },
    }
    payload["traces"] = traces
    payload["counts"] = counts
    payload["warnings"] = warnings
    return payload


def collect(state_dir=None) -> dict:
    """Collect deterministic local traces from the Gypsy state directory."""
    source = Path(state_dir).expanduser() if state_dir else gypsy.STATE_DIR
    payload = {
        "schema": SCHEMA,
        "generated": gypsy.now_iso(),
        "source": {
            "stateDir": _label(source),
            "collector": "disk-derived local trace",
            "live": False,
            "note": OTEL_NOTE,
        },
        "traces": [],
        "counts": {},
        "warnings": [],
        "errors": [],
    }
    traces = []
    warnings = []
    if not source.is_dir():
        traces.append(
            _problem_trace(
                "state",
                "state directory not found: " + _label(source),
            )
        )
        return _finish(payload, traces, warnings)

    task_files = []
    slice_files = []
    toolpack_runs = []
    toolpack_actions = []
    referenced_actions = set()
    for label, directory in (("slices", source / "slices"), ("toolpacks", source / "toolpacks")):
        if not directory.is_dir():
            warnings.append("no {} state directory: {}".format(label, _label(directory)))
            continue
        for path in sorted(directory.glob("*.json")):
            if not path.is_file():
                continue
            rel = label + "/" + path.name
            try:
                data = _read_state(path)
            except TraceError as exc:
                traces.append(_problem_trace(rel, str(exc)))
                continue
            schema = data.get("schema")
            if label == "slices":
                if schema == TASK_SCHEMA:
                    task_files.append((rel, data))
                elif schema == SLICE_SCHEMA:
                    slice_files.append((rel, data))
                else:
                    traces.append(
                        _problem_trace(
                            rel,
                            "unexpected slice state schema {!r}; expected {} or {}".format(
                                schema, TASK_SCHEMA, SLICE_SCHEMA
                            ),
                        )
                    )
                continue
            if schema != TOOLPACK_SCHEMA:
                traces.append(
                    _problem_trace(
                        rel,
                        "unexpected toolpack state schema {!r}; expected {}".format(
                            schema, TOOLPACK_SCHEMA
                        ),
                    )
                )
                continue
            scope = data.get("scope")
            if scope == "toolpack":
                toolpack_runs.append((rel, data))
                for action in data.get("actions") or []:
                    if isinstance(action, dict):
                        name = _basename(action.get("statePath"))
                        if name:
                            referenced_actions.add(name)
            elif scope == "action":
                toolpack_actions.append((rel, data))
            else:
                traces.append(
                    _problem_trace(
                        rel,
                        "toolpack state scope must be toolpack or action, found {!r}".format(
                            scope
                        ),
                    )
                )

    for rel, data in toolpack_runs:
        traces.append(_toolpack_trace(rel, data))
    for rel, data in toolpack_actions:
        if Path(rel).name in referenced_actions:
            continue
        traces.append(_action_only_trace(rel, data))
    for rel, data in slice_files:
        traces.append(_slice_trace(rel, data))
    for rel, data in task_files:
        traces.append(_task_trace(rel, data))
    return _finish(payload, traces, warnings)


def _valid_iso_or_none(value) -> bool:
    if value is None:
        return True
    if not isinstance(value, str):
        return False
    return _parse_time(value) is not None


def validate(payload) -> list:
    """Return shape and consistency errors for a trace payload; empty means valid."""
    if not isinstance(payload, dict):
        return ["payload must be a JSON object"]
    errors = []
    if payload.get("schema") != SCHEMA:
        errors.append("schema must be {!r}, found {!r}".format(SCHEMA, payload.get("schema")))
    if not isinstance(payload.get("generated"), str) or not payload["generated"].strip():
        errors.append("generated must be a non-empty string")
    source = payload.get("source")
    if not isinstance(source, dict):
        errors.append("source must be an object")
    else:
        if not isinstance(source.get("stateDir"), str) or not source["stateDir"].strip():
            errors.append("source.stateDir must be a non-empty string")
        if not isinstance(source.get("collector"), str) or not source["collector"].strip():
            errors.append("source.collector must be a non-empty string")
        if source.get("live") is not False:
            errors.append("source.live must be false: this is not live instrumentation")
        if not isinstance(source.get("note"), str) or not source["note"].strip():
            errors.append("source.note must be a non-empty string")

    traces = payload.get("traces")
    if not isinstance(traces, list):
        errors.append("traces must be a list")
        traces = []
    trace_ids = []
    span_count = 0
    for index, trace in enumerate(traces):
        label = "traces[{}]".format(index)
        if not isinstance(trace, dict):
            errors.append(label + " must be an object")
            continue
        trace_id = trace.get("traceId")
        if not isinstance(trace_id, str) or not HEX32.match(trace_id):
            errors.append(label + ": traceId must be 32 lowercase hex characters")
        else:
            trace_ids.append(trace_id)
        if trace.get("kind") not in TRACE_KINDS:
            errors.append(label + ": kind must be one of {}".format(list(TRACE_KINDS)))
        if not isinstance(trace.get("name"), str) or not trace["name"].strip():
            errors.append(label + ": name must be a non-empty string")
        run_id = trace.get("runId")
        if run_id is not None and not isinstance(run_id, str):
            errors.append(label + ": runId must be a string or null")
        if not isinstance(trace.get("sourceFile"), str) or not trace["sourceFile"].strip():
            errors.append(label + ": sourceFile must be a non-empty string")
        for field in ("startTime", "endTime"):
            if not _valid_iso_or_none(trace.get(field)):
                errors.append(label + ": {} must be an ISO time or null".format(field))
        duration = trace.get("durationSeconds")
        if duration is not None and (
            not isinstance(duration, (int, float))
            or isinstance(duration, bool)
            or duration < 0
        ):
            errors.append(label + ": durationSeconds must be a non-negative number or null")
        if trace.get("status") not in STATUSES:
            errors.append(label + ": status must be one of {}".format(list(STATUSES)))
        spans = trace.get("spans")
        if not isinstance(spans, list) or not spans:
            errors.append(label + ": spans must be a non-empty list")
            continue
        span_count += len(spans)
        seen = set()
        parent_positions = {}
        for position, span in enumerate(spans):
            span_label = label + ".spans[{}]".format(position)
            if not isinstance(span, dict):
                errors.append(span_label + " must be an object")
                continue
            if span.get("traceId") != trace_id:
                errors.append(span_label + ": traceId must match the trace")
            span_id = span.get("spanId")
            if not isinstance(span_id, str) or not HEX16.match(span_id):
                errors.append(span_label + ": spanId must be 16 lowercase hex characters")
            elif span_id in seen:
                errors.append(span_label + ": spanId is not unique within the trace")
            else:
                seen.add(span_id)
                parent_positions[span_id] = position
            parent = span.get("parentSpanId")
            if parent is not None and not (isinstance(parent, str) and HEX16.match(parent)):
                errors.append(span_label + ": parentSpanId must be 16 lowercase hex or null")
            if not isinstance(span.get("name"), str) or not span["name"].strip():
                errors.append(span_label + ": name must be a non-empty string")
            if span.get("kind") not in SPAN_KINDS:
                errors.append(span_label + ": kind must be one of {}".format(list(SPAN_KINDS)))
            if span.get("status") not in STATUSES:
                errors.append(span_label + ": status must be one of {}".format(list(STATUSES)))
            for field in ("startTime", "endTime"):
                if not _valid_iso_or_none(span.get(field)):
                    errors.append(
                        span_label + ": {} must be an ISO time or null".format(field)
                    )
            span_duration = span.get("durationSeconds")
            if span_duration is not None and (
                not isinstance(span_duration, (int, float))
                or isinstance(span_duration, bool)
                or span_duration < 0
            ):
                errors.append(
                    span_label + ": durationSeconds must be a non-negative number or null"
                )
            attributes = span.get("attributes")
            if not isinstance(attributes, dict):
                errors.append(span_label + ": attributes must be an object")
            else:
                try:
                    json.dumps(attributes)
                except (TypeError, ValueError):
                    errors.append(span_label + ": attributes must be JSON-safe")
        root = spans[0] if isinstance(spans[0], dict) else {}
        if root.get("parentSpanId") is not None:
            errors.append(label + ": the first span must be the root (parentSpanId null)")
        expected_kind = "problem" if trace.get("kind") == "problem" else "run"
        if root.get("kind") != expected_kind:
            errors.append(label + ": root span kind must be {!r}".format(expected_kind))
        for position, span in enumerate(spans[1:], 1):
            if not isinstance(span, dict):
                continue
            parent = span.get("parentSpanId")
            if parent not in parent_positions or parent_positions[parent] >= position:
                errors.append(
                    label + ".spans[{}]: parent span must appear before its child".format(position)
                )
    if len(set(trace_ids)) != len(trace_ids):
        errors.append("traceIds must be unique")
    if traces != sorted(traces, key=lambda trace: ((trace.get("startTime") or "") if isinstance(trace, dict) else "", trace.get("traceId", "") if isinstance(trace, dict) else "")):
        errors.append("traces must be sorted by (startTime, traceId)")

    counted = sum(
        len(trace.get("spans") or [])
        for trace in traces
        if isinstance(trace, dict)
    )
    counts = payload.get("counts")
    if not isinstance(counts, dict):
        errors.append("counts must be an object")
    else:
        expected = {
            "traces": len(traces),
            "spans": counted,
            "problemTraces": sum(1 for trace in traces if isinstance(trace, dict) and trace.get("kind") == "problem"),
            "problemSpans": sum(
                len(trace.get("spans") or [])
                for trace in traces
                if isinstance(trace, dict) and trace.get("kind") == "problem"
            ),
            "okTraces": sum(1 for trace in traces if isinstance(trace, dict) and trace.get("status") == "ok"),
            "errorTraces": sum(1 for trace in traces if isinstance(trace, dict) and trace.get("status") == "error"),
            "unsetTraces": sum(1 for trace in traces if isinstance(trace, dict) and trace.get("status") == "unset"),
            "byKind": {
                kind: sum(1 for trace in traces if isinstance(trace, dict) and trace.get("kind") == kind)
                for kind in TRACE_KINDS
            },
        }
        if counts != expected:
            errors.append("counts must match the traces")
    for field in ("warnings", "errors"):
        value = payload.get(field)
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            errors.append("{} must be a list of strings".format(field))
    return errors


def problems(payload) -> list:
    """Return the problems --validate should fail on: invalid payload, errors and problem traces."""
    result = list(validate(payload))
    result.extend(payload.get("errors") or [])
    for trace in payload.get("traces") or []:
        if not isinstance(trace, dict) or trace.get("kind") != "problem":
            continue
        root = (trace.get("spans") or [{}])[0]
        attributes = root.get("attributes") if isinstance(root, dict) else {}
        detail = attributes.get("error") if isinstance(attributes, dict) else None
        result.append(
            "problem trace {}: {}".format(
                trace.get("sourceFile"), detail or "unreadable state"
            )
        )
    return result


def to_json(payload, indent: int = 2) -> str:
    """Return the trace payload as JSON after validating it and proving it round-trips."""
    errors = validate(payload)
    if errors:
        raise TraceError("trace payload is not valid: " + "; ".join(errors))
    try:
        text = json.dumps(payload, indent=indent, ensure_ascii=False)
        if json.loads(text) != payload:
            raise TraceError("trace payload is not JSON-safe: it changed through JSON")
    except (TypeError, ValueError) as exc:
        raise TraceError("trace payload is not JSON-safe: {}".format(exc)) from exc
    return text + "\n"


def _otel_value(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return {"boolValue": value}
    if isinstance(value, int):
        return {"intValue": str(value)}
    if isinstance(value, float):
        return {"doubleValue": value}
    if isinstance(value, str):
        return {"stringValue": value}
    return {"stringValue": json.dumps(value, sort_keys=True, separators=(",", ":"))}


def to_otel(payload) -> dict:
    """Return an explicitly local OTEL-compatible document; no collector and no network."""
    errors = validate(payload)
    if errors:
        raise TraceError("trace payload is not valid: " + "; ".join(errors))
    otel_spans = []
    for trace in payload["traces"]:
        for span in trace["spans"]:
            attributes = []
            for key in sorted(span["attributes"]):
                encoded = _otel_value(span["attributes"][key])
                if encoded is not None:
                    attributes.append({"key": key, "value": encoded})
            code = {"ok": 1, "error": 2}.get(span["status"], 0)
            entry = {
                "traceId": span["traceId"],
                "spanId": span["spanId"],
                "name": span["name"],
                "kind": 1,
                "status": {"code": code},
                "attributes": attributes,
            }
            if span.get("parentSpanId"):
                entry["parentSpanId"] = span["parentSpanId"]
            start = _parse_time(span.get("startTime"))
            end = _parse_time(span.get("endTime"))
            if start is not None:
                entry["startTimeUnixNano"] = str(int(start.timestamp() * 1_000_000_000))
            if end is not None:
                entry["endTimeUnixNano"] = str(int(end.timestamp() * 1_000_000_000))
            otel_spans.append(entry)
    return {
        "_local": True,
        "_note": OTEL_NOTE,
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": "gypsy"}},
                        {"key": "gypsy.local_trace", "value": {"boolValue": True}},
                        {"key": "gypsy.trace.source", "value": {"stringValue": payload["source"]["stateDir"]}},
                    ]
                },
                "scopeSpans": [
                    {
                        "scope": {"name": "gypsy.traces", "version": "0.1.0"},
                        "spans": otel_spans,
                    }
                ],
            }
        ],
    }


def render_summary(payload) -> str:
    """Render a compact human-readable summary of the collected traces."""
    counts = payload.get("counts", {})
    lines = [
        "local trace: {} trace(s), {} span(s), {} problem trace(s)".format(
            counts.get("traces", 0),
            counts.get("spans", 0),
            counts.get("problemTraces", 0),
        ),
        "status: ok {} | error {} | unset {}".format(
            counts.get("okTraces", 0),
            counts.get("errorTraces", 0),
            counts.get("unsetTraces", 0),
        ),
        "source: {}".format(payload.get("source", {}).get("stateDir")),
        "note: " + OTEL_NOTE,
    ]
    traces = payload.get("traces") or []
    for trace in traces[:15]:
        lines.append(
            "  {}  status={} spans={} duration={}  {}".format(
                trace.get("name"),
                trace.get("status"),
                len(trace.get("spans") or []),
                trace.get("durationSeconds"),
                trace.get("sourceFile"),
            )
        )
    if len(traces) > 15:
        lines.append("  ... {} more trace(s)".format(len(traces) - 15))
    for trace in traces:
        if trace.get("kind") != "problem":
            continue
        root = (trace.get("spans") or [{}])[0]
        attributes = root.get("attributes") if isinstance(root, dict) else {}
        lines.append(
            "  problem: {} ({})".format(
                trace.get("sourceFile"),
                attributes.get("error") if isinstance(attributes, dict) else "unreadable",
            )
        )
    for warning in (payload.get("warnings") or [])[:10]:
        lines.append("  warning: " + warning)
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="traces",
        description=(
            "Local, disk-derived hierarchical traces over Gypsy run state. "
            "Not live instrumentation; nothing is sent to a collector."
        ),
    )
    parser.add_argument(
        "--state-dir",
        default=None,
        metavar="PATH",
        help="Gypsy state directory (default: workstream/state)",
    )
    parser.add_argument("--json", action="store_true", help="print the gypsy.trace/v1 payload")
    parser.add_argument(
        "--otel",
        action="store_true",
        help="print the explicitly local OTEL-compatible document (no collector, no network)",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="exit 1 when the payload is invalid or a problem trace exists",
    )
    args = parser.parse_args(argv)
    if args.json and args.otel:
        parser.error("choose --json or --otel, not both")
    try:
        payload = collect(args.state_dir)
        if args.otel:
            print(json.dumps(to_otel(payload), indent=2, ensure_ascii=False) + "\n", end="")
        elif args.json:
            print(to_json(payload), end="")
        else:
            print(render_summary(payload))
    except TraceError as exc:
        print("traces: FAIL - {}".format(exc), file=sys.stderr)
        return 2
    if args.validate:
        found = problems(payload)
        for issue in found:
            print("FAIL traces - {}".format(issue), file=sys.stderr)
        return 1 if found else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
