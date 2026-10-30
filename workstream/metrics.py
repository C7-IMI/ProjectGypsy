#!/usr/bin/env python3
"""Deterministic, state-derived metrics for Gypsy Studio (schema gypsy.metrics/v1).

This module is a read-only observability layer over the local state directory used by the
slice orchestrator, the toolpack runner, the action cache and the quality gate. It aggregates:

* task state (workstream/state/slices/task-*.json, gypsy.task-state/v1),
* per-slice state (workstream/state/slices/<slice>.json, gypsy.slice-state/v1),
* toolpack action state and aggregate runs (workstream/state/toolpacks/*.json,
  gypsy.toolpack-state/v1, scope action or toolpack),
* cache counters (workstream/state/cache/stats.json, gypsy.cache-stats/v1, including the
  remote hits/stores/errors counters) and cache entry/blob counts,
* the latest visual/performance quality gate result (workstream/state/quality/gate.json,
  gypsy.quality-gate/v1).

The result has a stable, JSON-safe shape: run counts, pass/fail, median/p95/min/max
durations, per-slice and per-toolpack breakdowns, latest timestamps and one latest record per
category. Missing state is treated as empty state. Unreadable files, wrong schemas and missing
required fields are skipped and listed under problems; they never abort collection and they
are never replaced with invented values. There is no network access, no wall-clock input and
no random value, so two runs over the same state directory produce the same document; the
"generated" timestamp is deliberately absent.

CLI (writes nothing unless --write is given):

    python workstream/metrics.py
    python workstream/metrics.py --state-dir workstream/state
    python workstream/metrics.py --write workstream/state/metrics/metrics.json

Public API:

    SCHEMA = "gypsy.metrics/v1"
    collect(state_dir="workstream/state") -> dict
    percentile(values, fraction) -> float | None
    duration_stats(values) -> dict
    write_metrics(path, metrics) -> Path
    main(argv=None) -> int
"""
from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = "gypsy.metrics/v1"
TASK_STATE_SCHEMA = "gypsy.task-state/v1"
SLICE_STATE_SCHEMA = "gypsy.slice-state/v1"
TOOLPACK_STATE_SCHEMA = "gypsy.toolpack-state/v1"
CACHE_STATS_SCHEMA = "gypsy.cache-stats/v1"
QUALITY_SCHEMA = "gypsy.quality-gate/v1"
DEFAULT_STATE_DIR = "workstream/state"
DURATION_KEYS = ("durationSeconds", "seconds")
TIMESTAMP_KEYS = ("finishedAt", "generated", "startedAt", "lastUpdated")
CACHE_COUNTER_KEYS = ("hits", "misses", "stores", "restores", "bytesStored")
REMOTE_COUNTER_KEYS = (
    ("remoteHits", "hits"),
    ("remoteStores", "stores"),
    ("remoteErrors", "errors"),
)


# -- small helpers -----------------------------------------------------------


def _number(value) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _parse_iso(value):
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment


def _timestamp(document, keys=TIMESTAMP_KEYS):
    for key in keys:
        value = document.get(key)
        if _parse_iso(value) is not None:
            return value
    return None


def _iso_or_none(value):
    return value if isinstance(value, str) and value else None


def percentile(values, fraction):
    """Nearest-rank percentile (ceil(fraction * n) - 1); None for an empty sequence."""
    if isinstance(fraction, bool) or not isinstance(fraction, (int, float)):
        raise ValueError("fraction must be a number greater than 0 and at most 1")
    if not math.isfinite(fraction) or fraction <= 0 or fraction > 1:
        raise ValueError("fraction must be a number greater than 0 and at most 1")
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return None
    index = max(0, math.ceil(fraction * len(ordered)) - 1)
    return ordered[index]


def duration_stats(values):
    """Return count/median/p95/min/max for finite non-negative durations, rounded to 3 dp."""
    numbers = []
    for value in values:
        if _number(value) and value >= 0:
            numbers.append(float(value))
    if not numbers:
        return {
            "count": 0,
            "medianSeconds": None,
            "p95Seconds": None,
            "minSeconds": None,
            "maxSeconds": None,
        }
    return {
        "count": len(numbers),
        "medianSeconds": round(statistics.median(numbers), 3),
        "p95Seconds": round(percentile(numbers, 0.95), 3),
        "minSeconds": round(min(numbers), 3),
        "maxSeconds": round(max(numbers), 3),
    }


def _new_accumulator():
    return {
        "runs": 0,
        "passed": 0,
        "failed": 0,
        "durations": [],
        "records": [],
    }


def _add(accumulator, passed, duration, record):
    accumulator["runs"] += 1
    if passed:
        accumulator["passed"] += 1
    else:
        accumulator["failed"] += 1
    if duration is not None:
        accumulator["durations"].append(duration)
    if record is not None:
        accumulator["records"].append(record)


def _pick_latest(records):
    valid = [
        record
        for record in records
        if isinstance(record, dict) and _parse_iso(record.get("at")) is not None
    ]
    if not valid:
        return None
    return max(
        valid,
        key=lambda record: (
            _parse_iso(record.get("at")),
            str(record.get("path") or ""),
        ),
    )


def _latest_at(records):
    latest = _pick_latest(records)
    return latest.get("at") if latest else None


def _max_iso(values):
    valid = [value for value in values if _parse_iso(value) is not None]
    if not valid:
        return None
    return max(valid, key=lambda value: (_parse_iso(value), value))


def _finish(accumulator):
    return {
        "runs": accumulator["runs"],
        "passed": accumulator["passed"],
        "failed": accumulator["failed"],
        "durations": duration_stats(accumulator["durations"]),
        "latest": _pick_latest(accumulator["records"]),
    }


def _finish_mapping(mapping):
    return {key: _finish(mapping[key]) for key in sorted(mapping)}


# -- state reading -----------------------------------------------------------


def _relative(path, state_dir):
    try:
        return path.relative_to(state_dir).as_posix()
    except ValueError:
        return path.as_posix()


def _json_files(directory):
    if not directory.is_dir():
        return []
    return sorted(
        (path for path in directory.glob("*.json") if path.is_file()),
        key=lambda path: path.name,
    )


def _read_json_object(path, relative, problems):
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        problems.append({"path": relative, "error": f"unreadable: {exc}"})
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        problems.append({"path": relative, "error": f"invalid JSON: {exc}"})
        return None
    if not isinstance(data, dict):
        problems.append({"path": relative, "error": "not a JSON object"})
        return None
    return data


def _duration(document, relative, problems):
    for key in DURATION_KEYS:
        if key not in document:
            continue
        value = document[key]
        if _number(value) and value >= 0:
            return round(float(value), 3)
        problems.append({"path": relative, "error": f"invalid {key}"})
        return None
    return None


def _require_id(document, key, relative, problems):
    value = document.get(key)
    if not isinstance(value, str) or not value:
        problems.append({"path": relative, "error": f"missing string {key}"})
        return None
    return value


def _record_state(document, relative, problems, expected_schema):
    """Common validation shared by task, slice and toolpack state documents."""
    if document.get("schema") != expected_schema:
        problems.append(
            {
                "path": relative,
                "error": f"unexpected schema {document.get('schema')!r}, expected {expected_schema!r}",
            }
        )
        return None
    passed = document.get("passed")
    if not isinstance(passed, bool):
        problems.append({"path": relative, "error": "missing boolean passed"})
        return None
    return passed


def _record_tasks(state_dir, problems):
    accumulator = _new_accumulator()
    for path in _json_files(state_dir / "slices"):
        relative = _relative(path, state_dir)
        data = _read_json_object(path, relative, problems)
        if data is None:
            continue
        schema = data.get("schema")
        if schema == SLICE_STATE_SCHEMA:
            continue  # handled by _record_slices
        if schema != TASK_STATE_SCHEMA:
            problems.append(
                {"path": relative, "error": f"unexpected schema {schema!r}"}
            )
            continue
        passed = _record_state(data, relative, problems, TASK_STATE_SCHEMA)
        if passed is None:
            continue
        duration = _duration(data, relative, problems)
        at = _timestamp(data, ("finishedAt", "startedAt"))
        task_id = data.get("task")
        if not isinstance(task_id, str) or not task_id:
            task_id = Path(relative).stem
        _add(
            accumulator,
            passed,
            duration,
            {
                "task": task_id,
                "passed": passed,
                "at": at,
                "finishedAt": _iso_or_none(data.get("finishedAt")),
                "durationSeconds": duration,
                "path": relative,
            },
        )
    return accumulator


def _record_slices(state_dir, problems):
    accumulator = _new_accumulator()
    by_slice = {}
    for path in _json_files(state_dir / "slices"):
        relative = _relative(path, state_dir)
        data = _read_json_object(path, relative, problems)
        if data is None:
            continue
        if data.get("schema") != SLICE_STATE_SCHEMA:
            continue  # task state or an unexpected schema, reported elsewhere
        passed = _record_state(data, relative, problems, SLICE_STATE_SCHEMA)
        if passed is None:
            continue
        slice_id = _require_id(data, "slice", relative, problems)
        if slice_id is None:
            continue
        duration = _duration(data, relative, problems)
        at = _timestamp(data, ("finishedAt", "startedAt"))
        record = {
            "slice": slice_id,
            "runId": _iso_or_none(data.get("runId")),
            "passed": passed,
            "at": at,
            "finishedAt": _iso_or_none(data.get("finishedAt")),
            "durationSeconds": duration,
            "path": relative,
        }
        _add(accumulator, passed, duration, record)
        _add(by_slice.setdefault(slice_id, _new_accumulator()), passed, duration, record)
    return accumulator, by_slice


def _record_toolpacks(state_dir, problems):
    actions = _new_accumulator()
    runs = _new_accumulator()
    by_action_toolpack = {}
    by_run_toolpack = {}
    for path in _json_files(state_dir / "toolpacks"):
        relative = _relative(path, state_dir)
        data = _read_json_object(path, relative, problems)
        if data is None:
            continue
        passed = _record_state(data, relative, problems, TOOLPACK_STATE_SCHEMA)
        if passed is None:
            continue
        scope = data.get("scope")
        if scope not in ("action", "toolpack"):
            problems.append(
                {"path": relative, "error": f"unknown toolpack state scope {scope!r}"}
            )
            continue
        toolpack_id = _require_id(data, "toolpack", relative, problems)
        if toolpack_id is None:
            continue
        duration = _duration(data, relative, problems)
        at = _timestamp(data, ("finishedAt", "startedAt"))
        if scope == "action":
            action_id = _require_id(data, "action", relative, problems)
            if action_id is None:
                continue
            record = {
                "toolpack": toolpack_id,
                "action": action_id,
                "runId": _iso_or_none(data.get("runId")),
                "passed": passed,
                "at": at,
                "finishedAt": _iso_or_none(data.get("finishedAt")),
                "durationSeconds": duration,
                "path": relative,
            }
            _add(actions, passed, duration, record)
            _add(
                by_action_toolpack.setdefault(toolpack_id, _new_accumulator()),
                passed,
                duration,
                record,
            )
        else:
            record = {
                "toolpack": toolpack_id,
                "runId": _iso_or_none(data.get("runId")),
                "passed": passed,
                "at": at,
                "finishedAt": _iso_or_none(data.get("finishedAt")),
                "durationSeconds": duration,
                "path": relative,
            }
            _add(runs, passed, duration, record)
            _add(
                by_run_toolpack.setdefault(toolpack_id, _new_accumulator()),
                passed,
                duration,
                record,
            )
    return actions, runs, by_action_toolpack, by_run_toolpack


def _record_quality(state_dir, problems):
    empty = {"gates": 0, "passed": 0, "failed": 0, "latest": None}
    path = state_dir / "quality" / "gate.json"
    if not path.is_file():
        return empty
    relative = _relative(path, state_dir)
    data = _read_json_object(path, relative, problems)
    if data is None:
        return empty
    if data.get("schema") != QUALITY_SCHEMA:
        problems.append(
            {
                "path": relative,
                "error": f"unexpected schema {data.get('schema')!r}, expected {QUALITY_SCHEMA!r}",
            }
        )
        return empty
    passed = data.get("passed")
    if not isinstance(passed, bool):
        problems.append({"path": relative, "error": "missing boolean passed"})
        return empty
    visual = data.get("visual") if isinstance(data.get("visual"), dict) else {}
    performance = data.get("performance") if isinstance(data.get("performance"), dict) else {}
    metrics = performance.get("metrics") if isinstance(performance.get("metrics"), dict) else {}
    latest = {
        "path": relative,
        "at": data.get("generated"),
        "passed": passed,
        "visualPassed": visual.get("passed"),
        "performancePassed": performance.get("passed"),
        "changedRatio": visual.get("changedRatio"),
        "medianSeconds": metrics.get("medianSeconds"),
        "captureGpuMsPerFrame": metrics.get("captureGpuMsPerFrame"),
    }
    return {
        "gates": 1,
        "passed": 1 if passed else 0,
        "failed": 0 if passed else 1,
        "latest": latest,
    }


def _count_files(directory, pattern="*"):
    if not directory.is_dir():
        return 0
    return sum(1 for path in directory.glob(pattern) if path.is_file())


def _counter(document, key, relative, problems):
    value = document.get(key, 0)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        if key in document:
            problems.append({"path": relative, "error": f"invalid counter {key}"})
        return 0
    return value


def _record_cache(state_dir, problems):
    cache_dir = state_dir / "cache"
    stats_path = cache_dir / "stats.json"
    counters = {key: 0 for key in CACHE_COUNTER_KEYS}
    remote = {target: 0 for _, target in REMOTE_COUNTER_KEYS}
    last_updated = None
    stats_relative = None
    if stats_path.is_file():
        stats_relative = _relative(stats_path, state_dir)
        data = _read_json_object(stats_path, stats_relative, problems)
        if data is not None:
            if data.get("schema") != CACHE_STATS_SCHEMA:
                problems.append(
                    {
                        "path": stats_relative,
                        "error": f"unexpected schema {data.get('schema')!r}, expected {CACHE_STATS_SCHEMA!r}",
                    }
                )
            else:
                for key in CACHE_COUNTER_KEYS:
                    counters[key] = _counter(data, key, stats_relative, problems)
                for source, target in REMOTE_COUNTER_KEYS:
                    remote[target] = _counter(data, source, stats_relative, problems)
                last_updated = _iso_or_none(data.get("lastUpdated"))
    lookups = counters["hits"] + counters["misses"]
    return {
        "statsPath": stats_relative,
        "counters": counters,
        "remote": remote,
        "hitRate": round(counters["hits"] / lookups, 6) if lookups else None,
        "entries": _count_files(cache_dir / "entries", "*.json"),
        "blobs": _count_files(cache_dir / "blobs"),
        "lastUpdated": last_updated,
    }


# -- public API --------------------------------------------------------------


def collect(state_dir=DEFAULT_STATE_DIR) -> dict:
    """Collect the metrics document for one state directory; never raises on bad state."""
    state = Path(state_dir)
    problems = []
    if state.exists() and not state.is_dir():
        problems.append(
            {"path": state.as_posix(), "error": "state path is not a directory"}
        )
    task_accumulator = _record_tasks(state, problems)
    slice_accumulator, by_slice = _record_slices(state, problems)
    (
        action_accumulator,
        run_accumulator,
        by_action_toolpack,
        by_run_toolpack,
    ) = _record_toolpacks(state, problems)
    quality = _record_quality(state, problems)
    cache = _record_cache(state, problems)

    tasks = _finish(task_accumulator)
    slice_metrics = _finish(slice_accumulator)
    slice_metrics["bySlice"] = _finish_mapping(by_slice)
    action_metrics = _finish(action_accumulator)
    action_metrics["byToolpack"] = _finish_mapping(by_action_toolpack)
    run_metrics = _finish(run_accumulator)
    run_metrics["byToolpack"] = _finish_mapping(by_run_toolpack)

    quality_at = quality["latest"]["at"] if quality["latest"] else None
    latest = {
        "task": tasks["latest"]["at"] if tasks["latest"] else None,
        "slice": slice_metrics["latest"]["at"] if slice_metrics["latest"] else None,
        "toolpack": _max_iso(
            [
                _latest_at(action_accumulator["records"]),
                _latest_at(run_accumulator["records"]),
            ]
        ),
        "quality": quality_at,
        "cache": cache["lastUpdated"],
    }
    unique_problems = []
    seen = set()
    for problem in sorted(
        problems, key=lambda item: (str(item.get("path")), str(item.get("error")))
    ):
        key = (problem.get("path"), problem.get("error"))
        if key not in seen:
            seen.add(key)
            unique_problems.append(problem)
    return {
        "schema": SCHEMA,
        "stateDir": state.as_posix(),
        "asOf": _max_iso(list(latest.values())),
        "tasks": tasks,
        "slices": slice_metrics,
        "toolpacks": {"actions": action_metrics, "runs": run_metrics},
        "cache": cache,
        "quality": quality,
        "latest": latest,
        "problems": unique_problems,
    }


def write_metrics(path, metrics) -> Path:
    """Write the metrics document atomically (temp file in the same directory plus replace)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(metrics, indent=2, ensure_ascii=False) + "\n"
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
    return path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Deterministic state-derived metrics for Gypsy Studio"
    )
    parser.add_argument(
        "--state-dir",
        default=DEFAULT_STATE_DIR,
        help="state directory to read (default: %(default)s)",
    )
    parser.add_argument(
        "--write",
        default=None,
        metavar="PATH",
        help="optionally write the same JSON document to PATH atomically",
    )
    args = parser.parse_args(argv)
    metrics = collect(args.state_dir)
    text = json.dumps(metrics, indent=2, ensure_ascii=False) + "\n"
    sys.stdout.write(text)
    if args.write:
        try:
            written = write_metrics(args.write, metrics)
        except OSError as exc:
            print(f"ERROR: could not write metrics to {args.write}: {exc}", file=sys.stderr)
            return 1
        sys.stderr.write(f"metrics written: {written}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
