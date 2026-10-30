#!/usr/bin/env python3
"""Phase-2 manifest-driven slice orchestrator (docs/ADR-010-slice-orchestrator.md).

The orchestrator turns a gypsy.slice/v1 manifest into executed steps: it validates the
manifest, resolves a stable topological order, calls an explicit handler per step, persists
durable per-step state atomically, hashes declared artifacts into a ledger and aggregates
multiple slices into one task report. There is no shell, no model call and no hidden retry.

Handlers are looked up in HANDLERS by step kind and have this contract:

    handler(step, context) -> dict | bool

* step is the manifest step object (id, kind, needs, required, timeout, args).
* context is a JSON-safe dict: project_root, project_dir, state_dir, slice_id, step_id,
  timeout (already scaled), run_id and manifest.
* a returned dict may carry passed (default true), output, exit and error; a bool is the
  passed flag. Raising is recorded as a failed step, never propagated out of run_slice.

The default handlers import workstream/game.py, gypsy.py and scripts/records_check.py lazily,
so this module is importable and testable without Godot or the network.

Public API:

    HANDLERS
    run_slice(manifest, *, project_root, state_dir, resume=False, force=False,
              handlers=None, timeout_scale=1.0, cache=None, cache_enabled=True) -> dict
    run_task(manifests, *, project_root, state_dir, resume=False, force=False,
             handlers=None, max_workers=1, cache=None, cache_enabled=True) -> dict

A step may opt into the local content-addressed action cache with a "cache" object
(see cache.py). Cache hits restore the declared artifacts and skip the handler; misses run
the handler and store only passing results. run_task(max_workers=N) uses the bounded
parallel scheduler for independent slices; result order stays deterministic.
"""
from __future__ import annotations

import hashlib
import importlib
import json
import os
import subprocess
import sys
import tempfile
import time
import uuid
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path

try:  # imported as workstream.orchestrator
    from . import cache as cache_spec
    from . import slices as slice_spec
except ImportError:  # imported with workstream/ on sys.path (the CLI does this)
    import cache as cache_spec
    import slices as slice_spec

WORKSTREAM_DIR = Path(__file__).resolve().parent
REPO_ROOT = WORKSTREAM_DIR.parent
STATE_SCHEMA = "gypsy.slice-state/v1"
TASK_SCHEMA = "gypsy.task-state/v1"
LEDGER_SCHEMA = "gypsy.artifact-ledger/v1"
OUTPUT_LIMIT = 4000


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


def _cache_step_argv(step: dict) -> list:
    """A stable argv-like identity token for a handler step's declared arguments."""
    try:
        args = json.dumps(
            step.get("args") or {},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
    except (TypeError, ValueError):
        args = repr(step.get("args"))
    return [str(step.get("kind")), args]


def _project_dir(project_root: Path, manifest: dict) -> Path:
    project = manifest.get("project")
    if isinstance(project, str) and project.strip() and project not in (".", "./"):
        return Path(project_root) / project
    return Path(project_root)


def _interpret(result):
    """Normalise a handler result into (passed, output, exit, error)."""
    if result is None:
        return True, "", None, None
    if isinstance(result, bool):
        return result, "", None, None
    if not isinstance(result, dict):
        return (
            False,
            "",
            None,
            f"handler returned unsupported type {type(result).__name__}",
        )
    passed = bool(result.get("passed", True))
    output = result.get("output")
    if output is None:
        parts = []
        if result.get("stdout"):
            parts.append(str(result["stdout"]))
        if result.get("stderr"):
            parts.append(str(result["stderr"]))
        output = "\n".join(parts)
    exit_code = result.get("exit")
    if isinstance(exit_code, bool) or not isinstance(exit_code, int):
        exit_code = None
    error = result.get("error")
    error = _clip(error) if error else None
    if not passed and not error and result.get("stderr"):
        error = _clip(result["stderr"])
    return passed, _clip(output), exit_code, error


def _hash_artifacts(manifest: dict, project_root: Path) -> list:
    entries = []
    for name in manifest.get("artifacts") or []:
        path = Path(project_root) / Path(name)
        entry = {"path": name, "exists": path.is_file(), "sha256": None, "bytes": None}
        if entry["exists"]:
            digest = hashlib.sha256()
            size = 0
            with open(path, "rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
                    size += len(chunk)
            entry["sha256"] = digest.hexdigest()
            entry["bytes"] = size
        entries.append(entry)
    return entries


def _write_artifact_ledger(
    state_dir: Path, slice_id: str, run_id: str, manifest_sha: str, artifacts: list, passed: bool
) -> Path:
    path = Path(state_dir) / "artifacts" / f"{slice_id}-{run_id}.json"
    document = {
        "schema": LEDGER_SCHEMA,
        "slice": slice_id,
        "runId": run_id,
        "manifestSha256": manifest_sha,
        "generated": _iso(_utc_now()),
        "passed": passed,
        "artifacts": artifacts,
    }
    _atomic_write_json(path, document)
    return path


def run_slice(
    manifest,
    *,
    project_root,
    state_dir,
    resume=False,
    force=False,
    handlers=None,
    timeout_scale=1.0,
    cache=None,
    cache_enabled=True,
) -> dict:
    """Execute one slice manifest and return a JSON-safe run result.

    The durable state is written to <state_dir>/slices/<slice_id>.json (atomically) and its
    path is returned as statePath. A required step that fails or is skipped fails the slice;
    its dependents are skipped. With resume=True a step that passed under the same manifest
    SHA-256 is not executed again; force=True ignores existing state entirely.

    A step may opt into the local action cache with a "cache" object declaring inputs and
    artifacts. A hit restores the declared artifacts and skips the handler; a miss executes
    and stores only a passing result. cache=ActionCache shares one cache across a parallel
    task; cache_enabled=False disables it for this run (the CLI --no-cache switch).

    Raises slice_spec.SliceError before doing anything when the manifest is invalid.
    """
    if not isinstance(manifest, dict):
        raise slice_spec.SliceError("manifest must be a JSON object")
    errors = slice_spec.validate_manifest(manifest)
    if not errors:
        for step in manifest.get("steps") or []:
            if isinstance(step, dict) and "cache" in step:
                errors.extend(
                    cache_spec.validate_config(
                        step["cache"], label=f"step {step.get('id')!r} cache"
                    )
                )
    if errors:
        raise slice_spec.SliceError("invalid slice manifest: " + "; ".join(errors))
    try:
        timeout_scale = float(timeout_scale)
    except (TypeError, ValueError):
        raise ValueError("timeout_scale must be a positive number") from None
    if timeout_scale <= 0:
        raise ValueError("timeout_scale must be a positive number")

    project_root = Path(project_root)
    state_dir = Path(state_dir)
    if cache is not None and not isinstance(cache, cache_spec.ActionCache):
        raise ValueError("cache must be a cache.ActionCache instance or None")
    cache_obj = cache if cache is not None else cache_spec.ActionCache(
        state_dir, enabled=bool(cache_enabled)
    )
    registry = dict(HANDLERS)
    if handlers:
        registry.update(handlers)

    slice_id = manifest["id"]
    order = slice_spec.resolve_order(manifest)
    steps_by_id = {step["id"]: step for step in manifest["steps"]}
    cache_configs = {}
    for step in manifest["steps"]:
        if "cache" not in step:
            continue
        try:
            cache_configs[step["id"]] = cache_spec.resolve_config(
                step["cache"],
                project_root=project_root,
                label=f"step {step['id']!r} cache",
            )
        except cache_spec.CacheError as exc:
            raise slice_spec.SliceError(str(exc)) from exc
    manifest_sha = _manifest_sha256(manifest)
    state_path = slice_spec.step_state_path(state_dir, slice_id)
    started_moment = _utc_now()
    started = time.time()
    run_id = _run_id(started_moment)

    previous = {}
    resumed = False
    resume_note = None
    if resume and not force and state_path.is_file():
        try:
            prior = json.loads(state_path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            prior = None
            resume_note = f"existing state unreadable: {exc}"
        if isinstance(prior, dict):
            if prior.get("manifestSha256") == manifest_sha:
                resumed = True
                previous = {
                    entry.get("id"): entry
                    for entry in prior.get("steps", [])
                    if isinstance(entry, dict) and isinstance(entry.get("id"), str)
                }
            else:
                resume_note = "manifest changed; previous state ignored"

    project_dir = _project_dir(project_root, manifest)
    step_results = []
    status_by_id = {}
    errors = []
    cache_hits = 0
    cache_misses = 0
    cache_stores = 0
    for step_id in order:
        step = steps_by_id[step_id]
        required = bool(step.get("required", True))
        needs = list(step.get("needs") or [])
        unmet = [need for need in needs if status_by_id.get(need) != "passed"]
        prior_step = previous.get(step_id)
        if resumed and prior_step and prior_step.get("status") == "passed":
            moment = _iso(_utc_now())
            step_results.append(
                {
                    "id": step_id,
                    "kind": step["kind"],
                    "status": "passed",
                    "required": required,
                    "attempted": False,
                    "cached": True,
                    "seconds": 0.0,
                    "startedAt": moment,
                    "finishedAt": moment,
                    "output": "not run: resume found this step passed under the unchanged manifest",
                    "error": None,
                    "exit": prior_step.get("exit"),
                }
            )
            status_by_id[step_id] = "passed"
            continue
        if unmet:
            moment = _iso(_utc_now())
            step_results.append(
                {
                    "id": step_id,
                    "kind": step["kind"],
                    "status": "skipped",
                    "required": required,
                    "attempted": False,
                    "cached": False,
                    "seconds": 0.0,
                    "startedAt": moment,
                    "finishedAt": moment,
                    "output": "",
                    "error": "dependencies not met: " + ", ".join(unmet),
                    "exit": None,
                }
            )
            status_by_id[step_id] = "skipped"
            errors.append(
                f"step {step_id!r} skipped: dependencies not met: {', '.join(unmet)}"
            )
            continue

        step_cache = cache_configs.get(step_id)
        cache_key = None
        cache_descriptor = None
        cache_restored = []
        cache_error = None
        cache_active = bool(step_cache and step_cache["enabled"] and cache_obj.enabled)
        if step_cache is not None and not cache_obj.enabled:
            cache_error = "cache disabled for this run"
        elif step_cache is not None and not step_cache["enabled"]:
            cache_error = "cache disabled by the step manifest"
        if cache_active:
            cache_inputs = cache_spec.input_hashes(project_root, step_cache["inputs"])
            cache_key, cache_descriptor = cache_spec.action_key(
                identity={
                    "kind": "slice-step",
                    "slice": slice_id,
                    "step": step_id,
                    "stepKind": step["kind"],
                    "manifestSha256": manifest_sha,
                },
                argv=_cache_step_argv(step),
                cwd=str(project_dir),
                inputs=cache_inputs,
                artifacts=step_cache["artifacts"],
                tool_versions=step_cache["toolVersions"],
            )
            if not force:
                cached_entry = cache_obj.lookup(cache_key)
                if cached_entry is not None:
                    restored_ok, restored_paths, restore_error = cache_obj.restore(
                        cached_entry, project_root
                    )
                    if restored_ok:
                        moment = _iso(_utc_now())
                        cache_hits += 1
                        step_results.append(
                            {
                                "id": step_id,
                                "kind": step["kind"],
                                "status": "passed",
                                "required": required,
                                "attempted": False,
                                "cached": False,
                                "seconds": 0.0,
                                "startedAt": moment,
                                "finishedAt": moment,
                                "output": "cache hit: restored "
                                + str(len(restored_paths))
                                + " artifact(s)",
                                "error": None,
                                "exit": 0,
                                "cache": {
                                    "key": cache_key,
                                    "hit": True,
                                    "stored": False,
                                    "restored": restored_paths,
                                    "error": None,
                                },
                            }
                        )
                        status_by_id[step_id] = "passed"
                        continue
                    cache_error = restore_error

        timeout = float(step.get("timeout") or slice_spec.DEFAULT_TIMEOUT) * timeout_scale
        context = {
            "project_root": project_root,
            "project_dir": project_dir,
            "state_dir": state_dir,
            "slice_id": slice_id,
            "step_id": step_id,
            "timeout": timeout,
            "run_id": run_id,
            "manifest": manifest,
        }
        step_started = _utc_now()
        clock = time.time()
        try:
            handler = registry.get(step["kind"])
            if handler is None:
                raise slice_spec.SliceError(
                    f"no handler registered for kind {step['kind']!r}"
                )
            passed, output, exit_code, error = _interpret(handler(step, context))
        except Exception as exc:  # noqa: BLE001 - a handler failure is state, not a crash
            passed = False
            output = ""
            exit_code = None
            error = _clip(f"{type(exc).__name__}: {exc}")
        seconds = round(time.time() - clock, 3)
        status = "passed" if passed else "failed"
        status_by_id[step_id] = status
        moment = _iso(_utc_now())
        cache_info = None
        if step_cache is not None:
            if cache_active:
                cache_misses += 1
            cache_stored = False
            if passed and cache_active and cache_key:
                stored_entry = cache_obj.store(
                    cache_key,
                    descriptor=cache_descriptor,
                    project_root=project_root,
                    artifacts=step_cache["artifacts"],
                    result={"exit": exit_code, "output": _clip(output)},
                )
                cache_stored = stored_entry is not None
                if cache_stored:
                    cache_stores += 1
            cache_info = {
                "key": cache_key,
                "hit": False,
                "stored": cache_stored,
                "restored": [],
                "error": cache_error,
            }
        step_record = {
            "id": step_id,
            "kind": step["kind"],
            "status": status,
            "required": required,
            "attempted": True,
            "cached": False,
            "seconds": seconds,
            "startedAt": _iso(step_started),
            "finishedAt": moment,
            "output": output,
            "error": error,
            "exit": exit_code,
        }
        if cache_info is not None:
            step_record["cache"] = cache_info
        step_results.append(step_record)
        if not passed:
            errors.append(f"step {step_id!r} failed: {error or 'handler reported failure'}")

    required_ok = all(
        status_by_id.get(step_id) == "passed"
        for step_id in order
        if bool(steps_by_id[step_id].get("required", True))
    )
    passed = required_ok
    artifacts = []
    ledger_path = None
    if passed:
        artifacts = _hash_artifacts(manifest, project_root)
        missing = [entry["path"] for entry in artifacts if not entry["exists"]]
        ledger_path = _write_artifact_ledger(
            state_dir, slice_id, run_id, manifest_sha, artifacts, passed=not missing
        )
        if missing:
            passed = False
            errors.append("missing declared artifact(s): " + ", ".join(missing))

    finished_moment = _utc_now()
    duration = round(time.time() - started, 3)
    cache_summary = {
        "enabled": cache_obj.enabled,
        "configuredSteps": len(cache_configs),
        "hits": cache_hits,
        "misses": cache_misses,
        "stores": cache_stores,
    }
    state_document = {
        "schema": STATE_SCHEMA,
        "slice": slice_id,
        "project": manifest.get("project"),
        "runId": run_id,
        "manifestSha256": manifest_sha,
        "startedAt": _iso(started_moment),
        "finishedAt": _iso(finished_moment),
        "durationSeconds": duration,
        "passed": passed,
        "timeoutScale": timeout_scale,
        "resumed": resumed,
        "resumeIgnored": resume_note,
        "stepOrder": order,
        "steps": step_results,
        "artifacts": artifacts,
        "ledgerPath": str(ledger_path) if ledger_path else None,
        "cache": cache_summary,
        "errors": errors,
    }
    _atomic_write_json(state_path, state_document)
    result = dict(state_document)
    result["statePath"] = str(state_path)
    return result


def _count_statuses(steps) -> dict:
    counts = {"total": len(steps), "passed": 0, "failed": 0, "skipped": 0}
    for step in steps:
        status = step.get("status")
        if status in counts:
            counts[status] += 1
    return counts


def _report_lines(task_name: str, passed: bool, slices: list, counts: dict, artifacts: list, duration: float) -> list:
    lines = [
        f"task {task_name}: {'PASS' if passed else 'FAIL'} "
        f"({counts['passed']}/{counts['total']} steps, {len(artifacts)} artifacts, {duration}s)"
    ]
    for summary in slices:
        if summary["status"] == "not-run":
            lines.append(f"  {summary['slice']}: not run - {summary.get('note', 'previous slice failed')}")
        else:
            step_counts = summary["steps"]
            lines.append(
                f"  {summary['slice']}: {summary['status'].upper()} "
                f"({step_counts['passed']}/{step_counts['total']} steps, "
                f"{summary['artifacts']} artifacts, {summary['durationSeconds']}s)"
            )
    for summary in slices:
        for error in summary.get("errors") or []:
            lines.append(f"  {summary['slice']}: {error}")
    return lines


def run_task(
    manifests,
    *,
    project_root,
    state_dir,
    resume=False,
    force=False,
    handlers=None,
    max_workers=1,
    cache=None,
    cache_enabled=True,
) -> dict:
    """Run several slice manifests, writing one aggregate task report.

    *manifests* may be a mapping (as returned by slices.load_all) or any iterable of
    manifests, iterated in that order. A failed slice stops later slices; their summaries are
    recorded as not-run (sequential) or cancelled after the first failure (parallel).
    max_workers=1 keeps the original sequential behaviour; 2..8 uses the bounded parallel
    scheduler for independent slices with deterministic result ordering and logs. The
    aggregate is written atomically to <state_dir>/slices/task-<UTC timestamp>.json and its
    path is returned as statePath. A shared ActionCache is passed to every slice.

    Raises slice_spec.SliceError before running anything if any manifest is invalid or two
    slices share an id.
    """
    if isinstance(manifests, Mapping):
        sequence = list(manifests.values())
    else:
        sequence = list(manifests)
    if not sequence:
        raise slice_spec.SliceError("no slice manifests to run")

    seen = set()
    for manifest in sequence:
        errors = slice_spec.validate_manifest(manifest)
        slice_id = manifest.get("id") if isinstance(manifest, dict) else None
        if errors:
            raise slice_spec.SliceError(
                f"invalid slice manifest {slice_id!r}: " + "; ".join(errors)
            )
        if slice_id in seen:
            raise slice_spec.SliceError(f"duplicate slice id {slice_id!r} in task")
        seen.add(slice_id)
    try:
        workers = cache_spec.worker_count(max_workers)
    except cache_spec.CacheError as exc:
        raise slice_spec.SliceError(str(exc)) from exc

    project_root = Path(project_root)
    state_dir = Path(state_dir)
    if cache is not None and not isinstance(cache, cache_spec.ActionCache):
        raise ValueError("cache must be a cache.ActionCache instance or None")
    cache_obj = cache if cache is not None else cache_spec.ActionCache(
        state_dir, enabled=bool(cache_enabled)
    )
    cache_before = cache_obj.counters()

    started_moment = _utc_now()
    started = time.time()
    stamp = started_moment.strftime("%Y%m%dT%H%M%SZ")
    state_path = Path(state_dir) / "slices" / f"task-{stamp}.json"
    suffix = 2
    while state_path.exists():
        state_path = Path(state_dir) / "slices" / f"task-{stamp}-{suffix}.json"
        suffix += 1
    task_name = state_path.stem

    counts = {"total": 0, "passed": 0, "failed": 0, "skipped": 0}
    artifacts = []
    slice_summaries = []
    cancelled_slices = []
    parallel_cancelled = False

    def _absorb(result: dict, slice_id: str) -> dict:
        step_counts = _count_statuses(result.get("steps") or [])
        for key in counts:
            counts[key] += step_counts[key]
        for artifact in result.get("artifacts") or []:
            artifacts.append({"slice": slice_id, **artifact})
        return {
            "slice": slice_id,
            "status": "passed" if result.get("passed") else "failed",
            "passed": result.get("passed"),
            "statePath": result.get("statePath"),
            "steps": step_counts,
            "artifacts": len(result.get("artifacts") or []),
            "durationSeconds": result.get("durationSeconds"),
            "errors": list(result.get("errors") or []),
            "cache": result.get("cache"),
        }

    def _not_run_summary(manifest: dict, note: str) -> dict:
        return {
            "slice": manifest["id"],
            "status": "not-run",
            "passed": None,
            "statePath": None,
            "steps": {"total": 0, "passed": 0, "failed": 0, "skipped": 0},
            "artifacts": 0,
            "durationSeconds": 0.0,
            "errors": [],
            "note": note,
            "cache": None,
        }

    if workers == 1:
        stopped = False
        failure_reason = None
        for manifest in sequence:
            slice_id = manifest["id"]
            if stopped:
                slice_summaries.append(
                    _not_run_summary(manifest, "not run: " + str(failure_reason))
                )
                continue
            result = run_slice(
                manifest,
                project_root=project_root,
                state_dir=state_dir,
                resume=resume,
                force=force,
                handlers=handlers,
                cache=cache_obj,
            )
            slice_summaries.append(_absorb(result, slice_id))
            if not result.get("passed"):
                stopped = True
                failure_reason = f"slice {slice_id!r} failed"
    else:

        def _run_slice(index, manifest):
            try:
                return run_slice(
                    manifest,
                    project_root=project_root,
                    state_dir=state_dir,
                    resume=resume,
                    force=force,
                    handlers=handlers,
                    cache=cache_obj,
                )
            except Exception as exc:  # a crashed worker becomes deterministic state
                return {
                    "slice": manifest.get("id"),
                    "passed": False,
                    "statePath": None,
                    "steps": [],
                    "artifacts": [],
                    "durationSeconds": 0.0,
                    "errors": [f"{type(exc).__name__}: {exc}"],
                    "cache": None,
                }

        parallel = cache_spec.run_parallel(
            sequence, _run_slice, max_workers=workers, cancel_on_failure=True
        )
        parallel_cancelled = bool(parallel["cancelled"])
        results = parallel["results"]
        first_failed = None
        for index, manifest in enumerate(sequence):
            result = results[index]
            if result is None:
                cancelled_slices.append(manifest["id"])
                note = "not run: cancelled"
                if first_failed:
                    note += f" after slice {first_failed!r} failed"
                slice_summaries.append(_not_run_summary(manifest, note))
                continue
            summary = _absorb(result, manifest["id"])
            slice_summaries.append(summary)
            if not result.get("passed") and first_failed is None:
                first_failed = manifest["id"]

    duration = round(time.time() - started, 3)
    failed = any(summary["status"] == "failed" for summary in slice_summaries)
    not_run = any(summary["status"] == "not-run" for summary in slice_summaries)
    passed = not failed and not not_run
    finished_moment = _utc_now()
    parallel_info = {
        "requestedWorkers": workers,
        "workers": workers,
        "cancelled": parallel_cancelled,
        "cancelledSlices": cancelled_slices,
        "log": [
            f"{summary['slice']}: {summary['status']}" for summary in slice_summaries
        ],
    }
    cache_summary = {
        "enabled": cache_obj.enabled,
        **cache_spec.counters_delta(cache_before, cache_obj.counters()),
    }
    report = _report_lines(task_name, passed, slice_summaries, counts, artifacts, duration)
    if workers > 1:
        report.insert(
            1,
            f"parallel: {workers} worker(s), cancelled={parallel_cancelled}"
            + (" (" + ", ".join(cancelled_slices) + ")" if cancelled_slices else ""),
        )
    document = {
        "schema": TASK_SCHEMA,
        "task": task_name,
        "startedAt": _iso(started_moment),
        "finishedAt": _iso(finished_moment),
        "durationSeconds": duration,
        "passed": passed,
        "sliceOrder": [manifest["id"] for manifest in sequence],
        "slices": slice_summaries,
        "steps": counts,
        "artifacts": artifacts,
        "parallel": parallel_info,
        "cache": cache_summary,
        "report": report,
    }
    _atomic_write_json(state_path, document)
    result = dict(document)
    result["statePath"] = str(state_path)
    return result


# -- default handlers -------------------------------------------------------


def _workstream_module(name: str):
    """Import a workstream module (game, gypsy) lazily, with workstream/ on sys.path."""
    workstream = str(WORKSTREAM_DIR)
    if workstream not in sys.path:
        sys.path.insert(0, workstream)
    return importlib.import_module(name)


def _combine(stdout, stderr) -> str:
    parts = [part for part in (stdout, stderr) if part]
    return "\n".join(parts).strip()


def _run_command(argv, cwd, timeout, label="command") -> dict:
    """Run an explicit argv list with shell=False and return a handler result."""
    started = time.time()
    if not isinstance(argv, (list, tuple)) or not argv:
        return {
            "passed": False,
            "error": f"{label}: argv must be a non-empty list of strings",
            "output": "",
        }
    if not all(isinstance(argument, str) for argument in argv):
        return {
            "passed": False,
            "error": f"{label}: argv must be a list of strings",
            "output": "",
        }
    try:
        completed = subprocess.run(
            list(argv),
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=float(timeout),
            shell=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "passed": False,
            "error": f"{label}: timeout after {float(timeout):g}s",
            "output": _clip(_combine(exc.stdout, exc.stderr)),
            "seconds": round(time.time() - started, 3),
        }
    except FileNotFoundError as exc:
        return {
            "passed": False,
            "error": f"{label}: not found: {exc}",
            "output": "",
            "seconds": round(time.time() - started, 3),
        }
    except OSError as exc:
        return {
            "passed": False,
            "error": f"{label}: could not run: {exc}",
            "output": "",
            "seconds": round(time.time() - started, 3),
        }
    return {
        "passed": completed.returncode == 0,
        "exit": completed.returncode,
        "output": _clip(_combine(completed.stdout, completed.stderr)),
        "seconds": round(time.time() - started, 3),
    }


def _game_handler(function_name: str):
    """Build a lazy handler for game.demo / game.build / game.capture."""

    def handler(step, context):
        game = _workstream_module("game")
        function = getattr(game, function_name)
        args = step.get("args") or {}
        project_dir = Path(context["project_dir"])
        kwargs = {
            "game_dir": Path(args["path"]) if args.get("path") else project_dir,
            "timeout": max(1, int(float(args.get("timeout", context["timeout"])))),
        }
        if function_name == "build":
            if args.get("preset"):
                kwargs["preset"] = str(args["preset"])
            output = args.get("out", args.get("output"))
            if output:
                output_path = Path(output)
                if not output_path.is_absolute():
                    output_path = Path(context["project_root"]) / output_path
                kwargs["output"] = output_path
        if function_name == "capture" and args.get("seconds") is not None:
            kwargs["seconds"] = int(args["seconds"])
        return function(**kwargs)

    handler.__name__ = "handle_" + function_name.replace(".", "_")
    return handler


def handle_check_all(step, context) -> dict:
    """Run the pack check list (scripts/check_all.py); no engine/GameTools dependency."""
    root = Path(context["project_root"])
    script = root / "scripts" / "check_all.py"
    return _run_command([sys.executable, str(script)], root, context["timeout"], label="check_all")


def handle_tests(step, context) -> dict:
    args = step.get("args") or {}
    start = str(args.get("start") or "workstream/tests")
    argv = [sys.executable, "-m", "unittest", "discover", "-s", start, "-v"]
    if args.get("pattern"):
        argv.extend(["-p", str(args["pattern"])])
    return _run_command(argv, context["project_root"], context["timeout"], label="tests")


def handle_records(step, context) -> dict:
    args = step.get("args") or {}
    root = Path(context["project_root"])
    script = Path(args["script"]) if args.get("script") else root / "scripts" / "records_check.py"
    if not script.is_absolute():
        script = root / script
    argv = [sys.executable, str(script), "--root", str(root)]
    return _run_command(argv, root, context["timeout"], label="records")


def handle_command(step, context) -> dict:
    args = step.get("args") or {}
    argv = args.get("argv", args.get("cmd", args.get("command")))
    if isinstance(argv, str):
        return {
            "passed": False,
            "error": "command: argv must be an explicit list of strings, not a shell string",
            "output": "",
        }
    if not isinstance(argv, list) or not argv or not all(isinstance(item, str) for item in argv):
        return {
            "passed": False,
            "error": "command: argv must be a non-empty list of strings",
            "output": "",
        }
    cwd = Path(args.get("cwd", "."))
    if not cwd.is_absolute():
        cwd = Path(context["project_root"]) / cwd
    return _run_command(argv, cwd, context["timeout"], label="command")


def handle_toolpack(step, context) -> dict:
    """Run a Phase-3 toolpack action or whole toolpack and return its validated result."""
    toolpacks = _workstream_module("toolpacks")
    args = step.get("args") or {}
    toolpack_id = args.get("toolpack")
    if not isinstance(toolpack_id, str) or not toolpack_id:
        return {"passed": False, "error": "toolpack: args.toolpack is required", "output": ""}
    root = Path(context["project_root"])
    path = Path(args["path"]) if args.get("path") else root / "toolpacks" / (toolpack_id + ".json")
    if not path.is_absolute():
        path = root / path
    try:
        manifest = toolpacks.load_manifest(path)
        errors = toolpacks.validate_manifest(manifest)
        if errors:
            return {"passed": False, "error": "; ".join(errors), "output": ""}
        action = args.get("action")
        if action:
            result = toolpacks.run_action(manifest, action, project_root=root, state_dir=Path(context["state_dir"]), timeout_scale=context["timeout"] / float(step.get("timeout") or 300))
        else:
            result = toolpacks.run_toolpack(manifest, project_root=root, state_dir=Path(context["state_dir"]), timeout_scale=context["timeout"] / float(step.get("timeout") or 300))
    except Exception as exc:  # noqa: BLE001 - a toolpack failure is state
        return {"passed": False, "error": f"toolpack: {type(exc).__name__}: {exc}", "output": ""}
    summary = {
        "toolpack": manifest.get("id"),
        "action": action,
        "passed": result.get("passed"),
        "artifacts": result.get("artifacts", []),
        "validators": result.get("validators", []),
        "statePath": result.get("statePath"),
        "errors": result.get("errors", []),
    }
    return {
        "passed": bool(result.get("passed")),
        "output": json.dumps(summary, indent=2)[:4000],
        "error": "; ".join(str(item) for item in result.get("errors", [])) or None,
        "statePath": result.get("statePath"),
    }


HANDLERS = {
    "game.demo": _game_handler("demo"),
    "game.build": _game_handler("build"),
    "game.capture": _game_handler("capture"),
    "check_all": handle_check_all,
    "tests": handle_tests,
    "records": handle_records,
    "command": handle_command,
    "toolpack": handle_toolpack,
}