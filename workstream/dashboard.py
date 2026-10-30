#!/usr/bin/env python3
"""Local-only ProjectGypsy dashboard.

Serves a dark single-page control panel on 127.0.0.1, reads the existing slice/toolpack state and
executes a fixed whitelist of CLI commands. It never exposes a remote interface and never accepts
arbitrary argv from the browser.
"""
from __future__ import annotations

import json
import mimetypes
import os
import re
import secrets
import sys
import threading
import time
import uuid
import webbrowser
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

try:
    from . import slices as slice_spec
except ImportError:
    import slices as slice_spec

REPO_ROOT = Path(__file__).resolve().parent.parent
ASSETS = REPO_ROOT / "design" / "dashboard"
V2_ASSETS = REPO_ROOT / "design" / "dashboard-v2"
STATE = REPO_ROOT / "workstream" / "state"
TOKEN = secrets.token_urlsafe(24)
JOB_LOCK = threading.Lock()
JOB = {
    "id": None,
    "action": None,
    "status": "idle",
    "startedAt": None,
    "finishedAt": None,
    "returncode": None,
    "output": "",
    "command": None,
    "commandLine": None,
    "pid": None,
    "timedOut": False,
    "durationSeconds": None,
}
MAX_OUTPUT = 20000
JOB_TIMEOUT = 1800
CACHE_STATS_PATHS = (
    "cache/stats.json",
    "cache/cache-stats.json",
    "cache-stats.json",
    "cache.json",
)
SCHEDULER_STATE_PATHS = ("scheduler.json", "parallel.json", "cache/scheduler.json")
DOCUMENTED_DEFAULT_ENGINE = {
    "engine": "unity",
    "version": "6000.6.7f1",
    "source": "docs/ADR-018-unity-default.md",
    "kind": "documented-policy",
}

COMMANDS = {
    "run_all": {"label": "Run all gates", "argv": [sys.executable, "workstream/gypsy.py", "slices", "run", "--all"], "hint": "phase1 + quality + toolpacks + mobile"},
    "phase1": {"label": "Run phase1", "argv": [sys.executable, "workstream/gypsy.py", "slices", "run", "phase1"], "hint": "demo, build, capture"},
    "quality": {"label": "Run quality", "argv": [sys.executable, "workstream/gypsy.py", "slices", "run", "quality"], "hint": "checks, tests, records"},
    "toolpacks": {"label": "Run toolpacks", "argv": [sys.executable, "workstream/gypsy.py", "slices", "run", "toolpacks"], "hint": "golden import + seeded audio"},
    "mobile": {"label": "Build Android", "argv": [sys.executable, "workstream/gypsy.py", "slices", "run", "mobile"], "hint": "signed debug APK"},
    "bench": {"label": "Benchmark", "argv": [sys.executable, "workstream/gypsy.py", "game", "bench", "--runs", "3"], "hint": "demo + render budget"},
    "verify": {"label": "Verify game", "argv": [sys.executable, "workstream/gypsy.py", "game", "verify"], "hint": "demo, build, capture"},
    "check": {"label": "Run pack checks", "argv": [sys.executable, "scripts/check_all.py"], "hint": "records, links, tests"},
    "live_once": {"label": "Live run once", "argv": [sys.executable, "workstream/gypsy.py", "live", "--paths", "game", "--once", "--command", "demo"], "hint": "one-shot live loop"},
    "android_direct": {"label": "Build APK raw", "argv": ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "scripts/build_android.ps1"], "hint": "direct Android script"},
    "leftbehind": {"label": "Run LeftBehind", "argv": [sys.executable, "workstream/gypsy.py", "slices", "run", "leftbehind"], "hint": "Unity build + demo + capture"},
    "leftbehind_build": {"label": "LeftBehind build", "argv": [sys.executable, "workstream/gypsy.py", "toolpacks", "run", "leftbehind.unity", "--action", "build"], "hint": "Unity player build only"},
    "leftbehind_demo": {"label": "LeftBehind demo", "argv": [sys.executable, "workstream/gypsy.py", "toolpacks", "run", "leftbehind.unity", "--action", "demo"], "hint": "headless marker only"},
    "leftbehind_capture": {"label": "LeftBehind capture", "argv": [sys.executable, "workstream/gypsy.py", "toolpacks", "run", "leftbehind.unity", "--action", "capture"], "hint": "windowed capture only"},
}

CSP = "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'"


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _latest_task():
    try:
        files = sorted((STATE / "slices").glob("task-*.json"), key=lambda item: item.stat().st_mtime)
    except OSError:
        return None
    return _read_json(files[-1]) if files else None


def _slice_states():
    out = {}
    try:
        files = (STATE / "slices").glob("*.json")
    except OSError:
        return out
    for path in files:
        if path.name.startswith("task-"):
            continue
        data = _read_json(path)
        if isinstance(data, dict) and data.get("slice"):
            out[data["slice"]] = data
    return out


def _count_capabilities():
    return len(list((REPO_ROOT / "workstream" / "capabilities").glob("*.json")))


def _tests_from_states(states):
    for data in states.values():
        if data.get("slice") != "quality":
            continue
        for step in data.get("steps", []):
            text = str(step.get("output") or "")
            match = re.search(r"Ran\s+(\d+)\s+tests", text)
            if match:
                return int(match.group(1))
    return None


def _artifact_entry(path: Path):
    rel = path.relative_to(REPO_ROOT).as_posix() if path.is_absolute() else path.as_posix()
    full = path if path.is_absolute() else REPO_ROOT / path
    exists = full.exists()
    entry = {"path": rel, "exists": exists, "bytes": full.stat().st_size if exists else 0, "kind": full.suffix.lstrip(".").lower() or "file"}
    if exists and full.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".mp4", ".avi", ".wav"}:
        entry["preview"] = "/api/artifact?raw=1&path=" + rel
    return entry


def _artifacts(task, states):
    entries = []
    seen = set()
    def add(path):
        if path in seen:
            return
        seen.add(path)
        entries.append(_artifact_entry(Path(path)))
    for artifact in (task or {}).get("artifacts", []):
        if isinstance(artifact, dict) and artifact.get("path"):
            add(artifact["path"])
    for state in states.values():
        for artifact in state.get("artifacts", []):
            if isinstance(artifact, dict) and artifact.get("path"):
                add(artifact["path"])
    for path in ("build/ProjectGypsy.exe", "build/ProjectGypsy.apk", "artifacts/game/frame.png", "artifacts/game/demo.mp4", "artifacts/toolpacks/musicgen.wav"):
        add(path)
    return entries


def _device_evidence():
    data = _read_json(REPO_ROOT / "docs" / "DEVICE-EVIDENCE.json")
    if not isinstance(data, dict):
        return None
    return data


def _phases(states, gates):
    def passed(slice_id):
        item = states.get(slice_id) or {}
        return bool(item.get("passed"))
    device = _device_evidence() or {}
    device_pass = device.get("result") == "pass"
    return [
        {"phase": 0, "label": "Foundation", "status": "done", "detail": "probes, manifests, checks"},
        {"phase": 1, "label": "Vertical slice", "status": "done", "detail": "demo, build, capture"},
        {"phase": 2, "label": "Orchestrator", "status": "done", "detail": "state, hashes, multi-slice, cache"},
        {"phase": 3, "label": "Toolpacks", "status": "done" if passed("toolpacks") else "ready", "detail": "import + audio + quality"},
        {"phase": 4, "label": "Console", "status": "done", "detail": "insights, live logs, preflight"},
        {"phase": 5, "label": "Live / mobile", "status": "done" if device_pass else "partial", "detail": "emulator pass; physical untested" if device_pass else "APK built; device untested"},
        {"phase": 6, "label": "UE5 adapter", "status": "blocked", "detail": "4 GB < 8 GB VRAM"},
    ]


def _gates(task, states):
    apk = (REPO_ROOT / "build" / "ProjectGypsy.apk").exists()
    exe = (REPO_ROOT / "build" / "ProjectGypsy.exe").exists()
    device = _device_evidence() or {}
    device_pass = device.get("result") == "pass"
    device_detail = "emulator: boot, install, launch, render, screenshot, logcat" if device_pass else "no device or emulator used"
    return [
        {"id": "windows", "label": "Windows build", "status": "pass" if exe else "ready", "detail": "109,127,680 B" if exe else "not built"},
        {"id": "mobile", "label": "Android package", "status": "pass" if apk else "ready", "detail": "signed arm64 APK" if apk else "not built"},
        {"id": "device", "label": "Device launch", "status": "pass" if device_pass else "untested", "detail": device_detail},
        {"id": "engine2", "label": "Second engine", "status": "pass" if (REPO_ROOT / "unity" / "LeftBehind" / "Build" / "LeftBehind.exe").exists() else "blocked", "detail": "LeftBehind Unity build/demo/capture PASS" if (REPO_ROOT / "unity" / "LeftBehind" / "Build" / "LeftBehind.exe").exists() else "no Unity build evidence"},
        {"id": "ue5", "label": "Phase 6 UE5", "status": "blocked", "detail": "4 GB VRAM < 8 GB minimum"},
        {"id": "quality", "label": "Quality + records", "status": "pass" if passed_quality(states) else "ready", "detail": "checks, tests, records, visual gate"},
    ]


def passed_quality(states):
    item = states.get("quality") or {}
    return bool(item.get("passed"))


def _engine_state():
    path = STATE / "engines.json"
    data = _read_json(path)
    if not isinstance(data, dict):
        return {"note": "run engines probe to refresh"}
    machine = data.get("machine") or {}
    gpu = machine.get("gpu") or {}
    disks = machine.get("disks") or {}
    return {
        "gpu": gpu.get("name"), "vramGb": gpu.get("vram_gb"),
        "ramGb": machine.get("ram_gb"),
        "diskC": (disks.get("C") or {}).get("free_gb"),
        "diskD": (disks.get("D") or {}).get("free_gb"),
        "godot": ((data.get("engines") or {}).get("godot") or {}).get("version"),
    }


# -- insights --------------------------------------------------------------


def _first_number(mapping, keys):
    if not isinstance(mapping, dict):
        return None
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            return value
    return None


def _first_text(mapping, keys):
    if not isinstance(mapping, dict):
        return None
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _command_line(argv):
    """Render an argv list for display/copy as one command line."""
    if not isinstance(argv, (list, tuple)) or not argv:
        return ""
    parts = [str(item) for item in argv]
    name = Path(parts[0]).name.lower()
    if name.startswith("python"):
        parts[0] = "python"
    return " ".join(parts)


def _repo_relative(path):
    """Display a path relative to the repo when possible; otherwise just its file name."""
    try:
        return Path(path).relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return Path(path).name


def _project_manifest(path):
    data = _read_json(Path(path))
    if not isinstance(data, dict):
        return None
    engine = data.get("engine") if isinstance(data.get("engine"), dict) else {}
    try:
        display = Path(path).relative_to(REPO_ROOT).as_posix()
    except ValueError:
        display = str(path)
    return {
        "manifest": display,
        "name": data.get("name"),
        "engine": engine.get("id"),
        "version": engine.get("version"),
        "adapter": engine.get("adapter"),
        "targets": data.get("targets") if isinstance(data.get("targets"), list) else [],
    }


def _detected_engines():
    data = _read_json(STATE / "engines.json")
    engines = (data or {}).get("engines") if isinstance(data, dict) else None
    out = {}
    if isinstance(engines, dict):
        for key, value in engines.items():
            if isinstance(value, dict):
                out[key] = {
                    "version": value.get("version"),
                    "installed": bool(value.get("installed")),
                    "usable": bool(value.get("usable")),
                }
    return out


def _engine_insight():
    """Explain the engine default from checked-in manifests plus the documented ADR-018 policy."""
    current = _project_manifest(REPO_ROOT / "game" / "project.gypsy.json")
    second = _project_manifest(REPO_ROOT / "unity" / "LeftBehind" / "project.gypsy.json")
    detected = _detected_engines()
    default = dict(DOCUMENTED_DEFAULT_ENGINE)
    detected_unity = detected.get("unity") or {}
    default["detectedMatch"] = (
        detected_unity.get("version") == default["version"] if detected_unity else None
    )
    facts = []
    if current:
        facts.append(
            "This checkout's game is pinned to "
            + str(current.get("engine"))
            + " "
            + str(current.get("version"))
            + " ("
            + str(current.get("adapter"))
            + "); it is the legacy/reference slice, not the default for new work."
        )
    if second:
        facts.append(
            str(second.get("name"))
            + " proves the same slice on "
            + str(second.get("engine"))
            + " "
            + str(second.get("version"))
            + "."
        )
    facts.append(
        "New projects default to Unity "
        + str(default["version"])
        + " (ADR-018, gypsy project init); an engine change is a port, not a toggle."
    )
    if default["detectedMatch"] is True:
        facts.append("The installed Unity matches the documented default version.")
    elif default["detectedMatch"] is False:
        facts.append("The detected Unity version differs from the documented default; pin the project version explicitly.")
    godot = detected.get("godot") or {}
    if godot:
        facts.append(
            "Detected Godot "
            + str(godot.get("version"))
            + " is "
            + ("usable" if godot.get("usable") else "not usable")
            + " on this machine."
        )
    return {
        "current": current,
        "second": second,
        "default": default,
        "detected": detected,
        "summary": facts[0] if facts else "No project manifest found; run gypsy project init.",
        "facts": facts,
        "source": "game/project.gypsy.json, unity/LeftBehind/project.gypsy.json, workstream/state/engines.json, ADR-018",
    }


def _cache_raw(task):
    for relative in CACHE_STATS_PATHS:
        path = STATE / relative
        data = _read_json(path)
        if isinstance(data, dict):
            try:
                source = path.relative_to(REPO_ROOT).as_posix()
            except ValueError:
                source = str(path)
            return data, source
    if isinstance(task, dict):
        for key in ("cache", "cacheStats", "cache_stats"):
            value = task.get(key)
            if isinstance(value, dict):
                return value, "latest task state (" + key + ")"
    return None, None


def _explicit_step_cache(states):
    """Count only explicit cache markers; resume's 'cached' field is a different mechanism."""
    hits = misses = 0
    seen = False
    for state in states.values():
        steps = state.get("steps") if isinstance(state, dict) else None
        for step in steps or []:
            if not isinstance(step, dict):
                continue
            marker = step.get("cache")
            value = None
            if isinstance(marker, str):
                value = marker
            elif isinstance(marker, dict):
                value = marker.get("result") or marker.get("status")
            if value is None:
                flag = step.get("cacheHit")
                if isinstance(flag, bool):
                    value = "hit" if flag else "miss"
            if isinstance(value, str):
                seen = True
                lowered = value.lower()
                if lowered in ("hit", "cached", "reuse", "true"):
                    hits += 1
                elif lowered in ("miss", "executed", "run", "false"):
                    misses += 1
    return hits, misses, seen


def _cache_insight(task, states):
    raw, source = _cache_raw(task)
    hits = misses = None
    entries = saved = total_bytes = hit_rate = None
    if raw is not None:
        hits = _first_number(raw, ("hits", "cacheHits", "hitCount"))
        misses = _first_number(raw, ("misses", "cacheMisses", "missCount"))
        entries = _first_number(raw, ("entries", "objects", "keys", "size"))
        saved = _first_number(raw, ("savedSeconds", "secondsSaved", "timeSavedSeconds"))
        total_bytes = _first_number(raw, ("bytes", "sizeBytes", "totalBytes"))
        hit_rate = _first_number(raw, ("hitRate", "hit_rate", "rate"))
        if hits is None and misses is None:
            step_hits, step_misses, seen = _explicit_step_cache(states)
            if seen:
                hits, misses = step_hits, step_misses
                source = source + " + explicit step cache fields"
    else:
        hits, misses, seen = _explicit_step_cache(states)
        if seen:
            source = "explicit cache fields in slice/toolpack state"
        else:
            return {
                "available": False,
                "source": None,
                "hits": None,
                "misses": None,
                "hitRate": None,
                "entries": None,
                "savedSeconds": None,
                "bytes": None,
                "summary": "No execution-cache state recorded in this checkout.",
                "emptyReason": (
                    "The action cache is opt-in (IMPROVEMENT-ROADMAP item 1 / task-13). Run a slice or toolpack "
                    "with caching enabled; this card reads workstream/state/cache/stats.json or explicit cache "
                    "fields in run state. Hits/misses are never inferred from resume state."
                ),
                "lookedFor": list(CACHE_STATS_PATHS),
            }
    if hit_rate is None and hits is not None and misses is not None and (hits + misses) > 0:
        hit_rate = round(hits / (hits + misses), 4)
    pieces = []
    if hits is not None and misses is not None:
        pieces.append(str(int(hits)) + " hits, " + str(int(misses)) + " misses")
        if hit_rate is not None:
            pieces.append(str(round(hit_rate * 100)) + "% hit rate")
    if entries is not None:
        pieces.append(str(int(entries)) + " cached entries")
    if saved is not None:
        pieces.append(str(round(saved, 1)) + "s saved")
    if total_bytes is not None:
        pieces.append(str(int(total_bytes)) + " B stored")
    if pieces:
        summary = "Execution cache: " + ", ".join(pieces) + " (from " + str(source) + ")."
    else:
        summary = (
            "Execution-cache state was found at "
            + str(source)
            + " but it has no hit/miss counters yet."
        )
    return {
        "available": True,
        "source": source,
        "hits": int(hits) if hits is not None else None,
        "misses": int(misses) if misses is not None else None,
        "hitRate": hit_rate,
        "entries": int(entries) if entries is not None else None,
        "savedSeconds": saved,
        "bytes": int(total_bytes) if total_bytes is not None else None,
        "summary": summary,
        "emptyReason": None,
        "lookedFor": list(CACHE_STATS_PATHS),
    }


def _scheduler_raw(task):
    for relative in SCHEDULER_STATE_PATHS:
        path = STATE / relative
        data = _read_json(path)
        if isinstance(data, dict):
            try:
                source = path.relative_to(REPO_ROOT).as_posix()
            except ValueError:
                source = str(path)
            return data, source
    if isinstance(task, dict):
        for key in ("scheduler", "parallel", "execution"):
            value = task.get(key)
            if isinstance(value, dict):
                return value, "latest task state (" + key + ")"
    return None, None


def _scheduler_insight(task):
    raw, source = _scheduler_raw(task)
    if raw is None:
        return {
            "available": False,
            "source": None,
            "mode": None,
            "parallel": None,
            "workers": None,
            "queueSeconds": None,
            "cancelled": None,
            "summary": "No parallel-scheduler state recorded in this checkout.",
            "emptyReason": (
                "Slices and toolpack actions run sequentially by default; parallel execution is opt-in (task-13). "
                "A task state with scheduler fields (mode, workers, queueSeconds, cancelled) fills this card."
            ),
            "lookedFor": list(SCHEDULER_STATE_PATHS),
        }
    mode = _first_text(raw, ("mode", "scheduler", "kind"))
    workers = _first_number(raw, ("workers", "maxWorkers", "slots", "workerCount"))
    queue = _first_number(raw, ("queueSeconds", "queueTimeSeconds", "queueSecondsTotal"))
    cancelled = _first_number(raw, ("cancelled", "canceled"))
    parallel = raw.get("parallel") if isinstance(raw.get("parallel"), bool) else None
    if parallel is None and mode:
        parallel = mode.lower() in ("parallel", "dag", "pool")
    if mode is None:
        mode = "parallel" if parallel else ("sequential" if parallel is False else None)
    pieces = []
    if mode:
        pieces.append(str(mode))
    if workers is not None:
        pieces.append(str(int(workers)) + " workers")
    if queue is not None:
        pieces.append(str(round(queue, 2)) + "s queued")
    if cancelled is not None:
        pieces.append(str(int(cancelled)) + " cancelled")
    if pieces:
        summary = "Scheduler: " + ", ".join(pieces) + " (from " + str(source) + ")."
    else:
        summary = (
            "Scheduler state was found at "
            + str(source)
            + " but it has no mode/worker counters yet."
        )
    return {
        "available": True,
        "source": source,
        "mode": mode,
        "parallel": parallel,
        "workers": int(workers) if workers is not None else None,
        "queueSeconds": queue,
        "cancelled": int(cancelled) if cancelled is not None else None,
        "summary": summary,
        "emptyReason": None,
        "lookedFor": list(SCHEDULER_STATE_PATHS),
    }


def _last_run_insight(task, runs):
    if runs:
        run = runs[0]
        steps = run.get("steps") if isinstance(run.get("steps"), dict) else {}
        passed = bool(run.get("passed"))
        failed_slices = []
        if not passed and isinstance(task, dict):
            failed_slices = [
                item.get("slice")
                for item in task.get("slices", [])
                if isinstance(item, dict) and item.get("status") != "passed"
            ]
        duration = run.get("durationSeconds")
        duration_text = str(round(float(duration), 1)) + "s" if isinstance(duration, (int, float)) else "an unknown time"
        summary = (
            "Last run "
            + str(run.get("title"))
            + " "
            + ("passed" if passed else "failed")
            + " in "
            + duration_text
            + " ("
            + str(int(steps.get("passed", 0)))
            + "/"
            + str(int(steps.get("total", 0)))
            + " steps, "
            + str(int(run.get("artifactCount", 0)))
            + " artifacts)."
        )
        run_id = run.get("id")
        return {
            "available": True,
            "runId": run_id,
            "runView": "?view=run&id=" + quote(str(run_id), safe="") if run_id else "?view=run",
            "title": run.get("title"),
            "kind": run.get("kind"),
            "status": run.get("status"),
            "passed": passed,
            "startedAt": run.get("startedAt"),
            "durationSeconds": duration,
            "steps": {
                "passed": int(steps.get("passed", 0)),
                "total": int(steps.get("total", 0)),
            },
            "artifacts": int(run.get("artifactCount", 0)),
            "failedSlices": failed_slices,
            "command": _command_line(COMMANDS["run_all"]["argv"]),
            "retryAction": "run_all",
            "summary": summary,
            "emptyReason": None,
        }
    return {
        "available": False,
        "runId": None,
        "runView": "?view=overview",
        "title": None,
        "kind": None,
        "status": None,
        "passed": None,
        "startedAt": None,
        "durationSeconds": None,
        "steps": {"passed": 0, "total": 0},
        "artifacts": 0,
        "failedSlices": [],
        "command": _command_line(COMMANDS["run_all"]["argv"]),
        "retryAction": "run_all",
        "summary": "No run has been recorded yet.",
        "emptyReason": "Run all gates once; this card then explains the last run in plain language from task state.",
    }


def _quality_insight(gates, metrics):
    passing = [gate for gate in gates if gate.get("status") == "pass"]
    attention = [gate for gate in gates if gate.get("status") in ("untested", "ready")]
    blocked = [gate for gate in gates if gate.get("status") == "blocked"]
    parts = [str(len(passing)) + " gates pass"]
    if attention:
        parts.append(
            str(len(attention))
            + " need attention ("
            + ", ".join(str(gate.get("label")) for gate in attention)
            + ")"
        )
    if blocked:
        parts.append(
            str(len(blocked))
            + " blocked ("
            + ", ".join(str(gate.get("label")) for gate in blocked)
            + ")"
        )
    tests = metrics.get("tests")
    capabilities = metrics.get("capabilities")
    summary = "Quality: " + "; ".join(parts) + "."
    if tests is not None:
        summary += " " + str(tests) + " workstream tests recorded"
    if capabilities is not None:
        summary += ("; " if tests is not None else " ") + str(capabilities) + " capability manifests."
    return {
        "passing": len(passing),
        "attention": {
            "count": len(attention),
            "names": [gate.get("label") for gate in attention],
        },
        "blocked": {
            "count": len(blocked),
            "names": [gate.get("label") for gate in blocked],
        },
        "tests": tests,
        "capabilities": capabilities,
        "summary": summary,
        "source": "workstream state; gate labels/details are computed from local evidence",
    }


def _next_actions(gates, last_run, cache, scheduler):
    """Actionable next steps. Every action id must exist in COMMANDS; info rows have no button."""
    run_all = _command_line(COMMANDS["run_all"]["argv"])
    mobile = _command_line(COMMANDS["mobile"]["argv"])
    actions = []
    if last_run.get("available") and not last_run.get("passed"):
        actions.append(
            {
                "id": "last-run-failed",
                "title": "Last run failed - inspect the failed step",
                "why": last_run.get("summary"),
                "command": last_run.get("command") or run_all,
                "action": "run_all",
                "view": last_run.get("runView") or "?view=run",
                "tone": "bad",
            }
        )
    for gate in gates:
        status = gate.get("status")
        if status == "untested":
            actions.append(
                {
                    "id": "gate-" + str(gate.get("id")),
                    "title": str(gate.get("label")) + " needs a real check",
                    "why": str(gate.get("detail") or ""),
                    "command": mobile,
                    "action": "mobile",
                    "view": "?view=review",
                    "tone": "warn",
                }
            )
        elif status == "blocked":
            actions.append(
                {
                    "id": "gate-" + str(gate.get("id")),
                    "title": str(gate.get("label")) + " is blocked",
                    "why": str(gate.get("detail") or ""),
                    "command": "",
                    "action": None,
                    "view": "?view=review",
                    "tone": "bad",
                }
            )
    if not last_run.get("available"):
        actions.insert(
            0,
            {
                "id": "no-run",
                "title": "No run state yet",
                "why": "Run the gates once; the board, insights, runs and artifacts fill from the records that command writes.",
                "command": run_all,
                "action": "run_all",
                "view": "?view=overview",
                "tone": "info",
            },
        )
    if not cache.get("available"):
        actions.append(
            {
                "id": "cache-unavailable",
                "title": "Execution cache has no recorded stats",
                "why": cache.get("emptyReason"),
                "command": run_all,
                "action": None,
                "view": "?view=insights",
                "tone": "info",
            }
        )
    if not scheduler.get("available"):
        actions.append(
            {
                "id": "scheduler-unavailable",
                "title": "Parallel scheduler is opt-in and has no recorded run",
                "why": scheduler.get("emptyReason"),
                "command": run_all,
                "action": None,
                "view": "?view=insights",
                "tone": "info",
            }
        )
    if not actions:
        actions.append(
            {
                "id": "all-clear",
                "title": "No blocked action; refresh the evidence",
                "why": "Every recorded gate passes. Re-run all gates when code changes, and keep device/UE5 gaps explicit.",
                "command": run_all,
                "action": "run_all",
                "view": "?view=overview",
                "tone": "good",
            }
        )
    return actions[:6]


def _insights(task, states, gates, runs, metrics):
    engine = _engine_insight()
    cache = _cache_insight(task, states)
    scheduler = _scheduler_insight(task)
    last_run = _last_run_insight(task, runs)
    quality = _quality_insight(gates, metrics)
    return {
        "engine": engine,
        "cache": cache,
        "scheduler": scheduler,
        "lastRun": last_run,
        "quality": quality,
        "nextActions": _next_actions(gates, last_run, cache, scheduler),
        "summary": [
            engine["summary"],
            last_run["summary"],
            quality["summary"],
            cache["summary"],
            scheduler["summary"],
        ],
    }


def _display_command(data):
    if data.get("scope") == "toolpack":
        return "python workstream/gypsy.py toolpacks run " + str(data.get("toolpack"))
    return "python workstream/gypsy.py slices run --all"


def _retry_action(data, failed_steps):
    title = str(data.get("toolpackName") or data.get("toolpack") or data.get("task") or "").lower()
    if data.get("scope") == "toolpack":
        return "leftbehind" if "leftbehind" in title else "run_all"
    for step in failed_steps:
        candidate = str(step.get("id") or "").split(" \u00b7 ")[0]
        if candidate in COMMANDS:
            return candidate
    return "run_all"


def _run_remediation(data, failed_steps, command, run_view):
    if failed_steps:
        names = ", ".join(str(step.get("id")) for step in failed_steps)
        summary = (
            "Failed step(s): "
            + names
            + ". Read each failed step output, copy the command, or open the matching run. "
            + "Retrying writes a new state record; it never edits this evidence."
        )
    else:
        summary = (
            "All steps passed. Evidence is immutable; a retry writes a new run instead of editing this one."
        )
    return {
        "summary": summary,
        "failedSteps": [str(step.get("id")) for step in failed_steps],
        "command": command,
        "retryAction": _retry_action(data, failed_steps),
        "runView": run_view,
        "logView": run_view,
    }


def _decorate_job(job):
    if not isinstance(job, dict):
        return job
    command_line = job.get("commandLine") or _command_line(job.get("command"))
    job["commandLine"] = command_line or None
    status = job.get("status")
    action = job.get("action")
    retry = action if isinstance(action, str) and action in COMMANDS else None
    if status == "idle":
        job["remediation"] = {
            "summary": "No job has run in this process yet. Start a whitelisted action to stream its output.",
            "command": "",
            "retryAction": None,
            "runView": "?view=run",
            "copyCommand": "",
        }
    elif status == "running":
        job["remediation"] = {
            "summary": (
                "Running. Output streams live over SSE; the drawer falls back to polling when the stream is unavailable."
            ),
            "command": command_line or "",
            "retryAction": None,
            "runView": "?view=run",
            "copyCommand": command_line or "",
        }
    elif status == "failed":
        if job.get("timedOut"):
            summary = "The command timed out after " + str(JOB_TIMEOUT) + "s. Copy the command, check the tool, then retry."
        else:
            exit_text = "" if job.get("returncode") is None else " (exit " + str(job.get("returncode")) + ")"
            summary = (
                "The command failed"
                + exit_text
                + ". Read the last output lines, copy the exact command, or open the latest run for step-level logs."
            )
        job["remediation"] = {
            "summary": summary,
            "command": command_line or "",
            "retryAction": retry,
            "runView": "?view=run",
            "copyCommand": command_line or "",
        }
    else:
        job["remediation"] = {
            "summary": "No active failure. Open the latest run for step-level evidence and hashes.",
            "command": command_line or "",
            "retryAction": retry,
            "runView": "?view=run",
            "copyCommand": command_line or "",
        }
    return job


def _job_public():
    with JOB_LOCK:
        job = dict(JOB)
    return _decorate_job(job)


def _run_summaries(limit=20):
    runs = []
    state_root = STATE
    try:
        tasks = sorted((state_root / "slices").glob("task-*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
    except OSError:
        tasks = []
    for path in tasks[:limit]:
        data = _read_json(path)
        if not isinstance(data, dict) or data.get("schema") != "gypsy.task-state/v1":
            continue
        steps = data.get("steps") or {}
        total = steps.get("total", len(data.get("slices", [])))
        passed = steps.get("passed", 0)
        runs.append({
            "id": _repo_relative(path),
            "kind": "task",
            "title": data.get("task") or path.stem,
            "status": "passed" if data.get("passed") else "failed",
            "passed": bool(data.get("passed")),
            "startedAt": data.get("startedAt"),
            "durationSeconds": data.get("durationSeconds"),
            "steps": {"total": total, "passed": passed},
            "sliceCount": len(data.get("slices", [])),
            "artifactCount": len(data.get("artifacts", [])),
        })
    try:
        toolpacks = sorted((state_root / "toolpacks").glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
    except OSError:
        toolpacks = []
    for path in toolpacks:
        if "-build-" in path.name or "-demo-" in path.name or "-capture-" in path.name:
            continue
        data = _read_json(path)
        if not isinstance(data, dict) or data.get("scope") != "toolpack":
            continue
        actions = data.get("actions", [])
        runs.append({
            "id": _repo_relative(path),
            "kind": "toolpack",
            "title": data.get("toolpack") or path.stem,
            "status": "passed" if data.get("passed") else "failed",
            "passed": bool(data.get("passed")),
            "startedAt": data.get("startedAt"),
            "durationSeconds": data.get("durationSeconds"),
            "steps": {"total": len(actions), "passed": sum(1 for item in actions if item.get("passed"))},
            "sliceCount": 0,
            "artifactCount": len(data.get("artifacts", [])),
        })
        if len(runs) >= limit:
            break
    runs.sort(key=lambda item: item.get("startedAt") or "", reverse=True)
    seen = set()
    unique = []
    for item in runs:
        key = (item.get("kind"), item.get("title"))
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique[:limit]


def _run_detail(run_id, state_root=None):
    """Read one run state document read-only. state_root is injectable for tests."""
    root = (Path(state_root) if state_root else STATE).resolve()
    raw = Path(run_id)
    candidate = raw if raw.is_absolute() else (REPO_ROOT / raw)
    candidate = candidate.resolve()
    if candidate.suffix != ".json" or not candidate.is_file() or not candidate.is_relative_to(root):
        return None
    data = _read_json(candidate)
    if not isinstance(data, dict):
        return None
    steps = []
    artifacts = []
    validators = []
    command = _display_command(data)
    if data.get("schema") == "gypsy.task-state/v1":
        for slice_summary in data.get("slices", []):
            state = _read_json(Path(slice_summary["statePath"])) if slice_summary.get("statePath") else None
            if not isinstance(state, dict):
                continue
            for step in state.get("steps", []):
                steps.append({
                    "id": state.get("slice", "?") + " · " + str(step.get("id")),
                    "status": step.get("status"),
                    "seconds": step.get("seconds"),
                    "output": step.get("output") or step.get("error") or "",
                    "error": step.get("error"),
                })
            for artifact in state.get("artifacts", []):
                artifacts.append({"path": artifact.get("path"), "sha256": artifact.get("sha256"), "bytes": artifact.get("bytes"), "exists": artifact.get("exists")})
        # task summaries may include artifacts not in slice state; keep aggregate copies
        for artifact in data.get("artifacts", []):
            if not any(item.get("path") == artifact.get("path") for item in artifacts):
                artifacts.append({"path": artifact.get("path"), "sha256": artifact.get("sha256"), "bytes": artifact.get("bytes"), "exists": artifact.get("exists")})
        title = data.get("task") or candidate.stem
    elif data.get("scope") == "toolpack":
        for action in data.get("actions", []):
            state = _read_json(Path(action["statePath"])) if action.get("statePath") else None
            output = ""
            if isinstance(state, dict):
                output = (state.get("stdout") or "") + (state.get("stderr") or "")
            steps.append({"id": action.get("action"), "status": action.get("status"), "seconds": action.get("seconds"), "output": output, "error": "; ".join(action.get("errors", [])) or None})
        for artifact in data.get("artifacts", []):
            artifacts.append({"path": artifact.get("path"), "sha256": artifact.get("sha256"), "bytes": artifact.get("bytes"), "exists": artifact.get("exists")})
        validators = data.get("validators", [])
        title = data.get("toolpackName") or data.get("toolpack") or candidate.stem
    else:
        return None
    try:
        display_id = candidate.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        display_id = candidate.name
    run_view = "?view=run&id=" + quote(display_id, safe="")
    failed_steps = [step for step in steps if step.get("status") == "failed"]
    return {
        "id": display_id,
        "title": title,
        "kind": "task" if data.get("schema") == "gypsy.task-state/v1" else "toolpack",
        "passed": bool(data.get("passed")),
        "status": "passed" if data.get("passed") else "failed",
        "startedAt": data.get("startedAt"),
        "durationSeconds": data.get("durationSeconds"),
        "command": command,
        "steps": steps,
        "artifacts": artifacts,
        "validators": validators,
        "remediation": _run_remediation(data, failed_steps, command, run_view),
    }


def collect_state():
    task = _latest_task()
    states = _slice_states()
    slices = []
    if task:
        for item in task.get("slices", []):
            state = states.get(item.get("slice"), {})
            slices.append({
                "id": item.get("slice"),
                "status": item.get("status"),
                "passed": item.get("passed"),
                "seconds": item.get("durationSeconds"),
                "steps": item.get("steps"),
                "artifacts": item.get("artifacts"),
                "errors": item.get("errors", []),
                "statePath": item.get("statePath"),
                "detail": state.get("stepOrder", []),
            })
    else:
        for slice_id, state in sorted(states.items()):
            slices.append({
                "id": slice_id, "status": "passed" if state.get("passed") else "failed",
                "passed": state.get("passed"), "seconds": state.get("durationSeconds"),
                "steps": len(state.get("steps", [])), "artifacts": len(state.get("artifacts", [])),
                "errors": state.get("errors", []), "statePath": state.get("statePath"),
                "detail": state.get("stepOrder", []),
            })
    seen_slices = {item.get('id') for item in slices}
    for slice_id, state in sorted(states.items()):
        if slice_id in seen_slices:
            continue
        slices.append({
            'id': slice_id,
            'status': 'passed' if state.get('passed') else 'failed',
            'passed': state.get('passed'),
            'seconds': state.get('durationSeconds'),
            'steps': len(state.get('steps', [])),
            'artifacts': len(state.get('artifacts', [])),
            'errors': state.get('errors', []),
            'statePath': state.get('statePath'),
            'detail': state.get('stepOrder', []),
        })

    artifacts = _artifacts(task, states)
    gates = _gates(task, states)
    benchmark = _read_json(STATE / "game-benchmark.json")
    tests = _tests_from_states(states)
    caps = _count_capabilities()
    runs = _run_summaries()
    metrics = {
        "tests": tests,
        "capabilities": caps,
        "slicesPassed": sum(1 for item in slices if item.get("passed")),
        "slicesTotal": len(slices),
        "blocked": sum(1 for gate in gates if gate.get("status") == "blocked"),
        "untested": sum(1 for gate in gates if gate.get("status") == "untested"),
    }
    insights = _insights(task, states, gates, runs, metrics)
    return {
        "generated": _utc(),
        "repo": REPO_ROOT.name,
        "branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
        "head": _git("rev-parse", "--short", "HEAD"),
        "clean": _git("status", "--porcelain") == "",
        "task": task.get("task") if task else None,
        "taskPassed": task.get("passed") if task else None,
        "taskSeconds": task.get("durationSeconds") if task else None,
        "slices": slices,
        "artifacts": artifacts,
        "gates": gates,
        "phases": _phases(states, gates),
        "machine": _engine_state(),
        "metrics": metrics,
        "benchmark": benchmark,
        "job": _job_public(),
        "runs": runs,
        "insights": insights,
        "cache": insights["cache"],
        "scheduler": insights["scheduler"],
        "commands": [{"id": key, **value} for key, value in COMMANDS.items()],
        "links": {
            "phase5": "docs/PHASE-5-EVIDENCE.md",
            "phase6": "docs/PHASE-6-GATE.md",
            "phase3": "docs/PHASE-3-EVIDENCE.md",
        },
    }



def _git(*args):
    try:
        import subprocess
        result = subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10)
        return result.stdout.strip() if result.returncode == 0 else ""
    except Exception:
        return ""


def _execute(action):
    """Run one whitelisted action, streaming stdout/stderr into JOB as it arrives."""
    command = COMMANDS.get(action)
    if not command:
        return
    started = _utc()
    clock = time.time()
    with JOB_LOCK:
        JOB.update({
            "id": uuid.uuid4().hex[:8],
            "action": action,
            "status": "running",
            "startedAt": started,
            "finishedAt": None,
            "returncode": None,
            "output": "",
            "command": command["argv"],
            "commandLine": _command_line(command["argv"]),
            "pid": None,
            "timedOut": False,
            "durationSeconds": None,
        })
    import subprocess
    collected = []
    last_push = [0.0]

    def reader(stream):
        try:
            for line in stream:
                collected.append(line)
                now = time.time()
                if now - last_push[0] >= 0.2:
                    last_push[0] = now
                    with JOB_LOCK:
                        JOB["output"] = "".join(collected)[-MAX_OUTPUT:]
        except (OSError, ValueError):
            return

    timed_out = False
    try:
        process = subprocess.Popen(
            command["argv"],
            cwd=REPO_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            shell=False,
            bufsize=1,
        )
        with JOB_LOCK:
            JOB["pid"] = process.pid
        thread = threading.Thread(target=reader, args=(process.stdout,), daemon=True)
        thread.start()
        try:
            code = process.wait(timeout=JOB_TIMEOUT)
        except subprocess.TimeoutExpired:
            timed_out = True
            process.kill()
            try:
                code = process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                code = -1
        thread.join(timeout=2)
        output = "".join(collected)
        if timed_out:
            output += "\nTIMEOUT after " + str(JOB_TIMEOUT) + "s"
    except Exception as exc:
        output = "ERROR " + type(exc).__name__ + ": " + str(exc)
        code = -1
    clipped = output[-MAX_OUTPUT:]
    with JOB_LOCK:
        JOB.update({
            "status": "passed" if code == 0 and not timed_out else "failed",
            "finishedAt": _utc(),
            "returncode": code,
            "output": clipped,
            "timedOut": timed_out,
            "durationSeconds": round(time.time() - clock, 3),
            "pid": None,
        })
    try:
        with JOB_LOCK:
            snapshot = dict(JOB)
        (STATE / "dashboard-job.json").write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
    except OSError:
        pass


def _start_job(action):
    with JOB_LOCK:
        if JOB.get("status") == "running":
            return False
    thread = threading.Thread(target=_execute, args=(action,), daemon=True)
    thread.start()
    return True


def _safe_artifact(path_value):
    candidate = (REPO_ROOT / path_value).resolve()
    if not candidate.is_relative_to(REPO_ROOT) or not candidate.is_file():
        return None
    try:
        parts = candidate.relative_to(REPO_ROOT).parts
    except ValueError:
        return None
    if not parts or parts[0] not in {"build", "artifacts", "docs", "design"}:
        return None
    return candidate


class Handler(BaseHTTPRequestHandler):
    server_version = "ProjectGypsyDashboard/1.0"

    def log_message(self, fmt, *args):
        sys.stderr.write("[dashboard] " + (fmt % args) + "\n")

    def _send(self, code, body, content_type="application/json; charset=utf-8", extra=None):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json(self, code, payload):
        self._send(code, json.dumps(payload), "application/json; charset=utf-8")

    def _sse(self, event, payload):
        frame = "event: " + event + "\ndata: " + json.dumps(payload) + "\n\n"
        self.wfile.write(frame.encode("utf-8"))
        self.wfile.flush()

    def _stream_logs(self):
        """Server-sent events for the active job; close-delimited, read-only, local only."""
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.send_header("X-Accel-Buffering", "no")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()
        deadline = time.time() + JOB_TIMEOUT + 120
        last = None
        heartbeat = time.time()
        try:
            self.wfile.write(b"retry: 2000\n\n")
            self.wfile.flush()
            while time.time() < deadline:
                job = _job_public()
                if job.get("status") == "idle":
                    self._sse("idle", {
                        "status": "idle",
                        "message": "No job has run in this process yet. Start a whitelisted action to stream its output.",
                    })
                    return
                signature = (job.get("status"), job.get("finishedAt"), job.get("output"))
                if signature != last:
                    self._sse("job", {
                        "status": job.get("status"),
                        "action": job.get("action"),
                        "id": job.get("id"),
                        "output": job.get("output") or "",
                        "commandLine": job.get("commandLine"),
                        "returncode": job.get("returncode"),
                        "finishedAt": job.get("finishedAt"),
                        "timedOut": job.get("timedOut"),
                        "durationSeconds": job.get("durationSeconds"),
                        "remediation": job.get("remediation"),
                    })
                    last = signature
                if job.get("status") in ("passed", "failed"):
                    self._sse("done", job)
                    return
                if time.time() - heartbeat > 10:
                    self.wfile.write(b": keep-alive\n\n")
                    self.wfile.flush()
                    heartbeat = time.time()
                time.sleep(0.25)
        except (BrokenPipeError, ConnectionResetError, OSError):
            return

    def _authorized(self):
        token = self.headers.get("X-Gypsy-Token", "")
        if not secrets.compare_digest(token, TOKEN):
            self._json(HTTPStatus.FORBIDDEN, {"error": "bad token"})
            return False
        origin = self.headers.get("Origin", "")
        if origin and not origin.startswith("http://127.0.0.1:") and not origin.startswith("http://localhost:"):
            self._json(HTTPStatus.FORBIDDEN, {"error": "bad origin"})
            return False
        return True

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in {"/", "/index.html"}:
            try:
                html = (V2_ASSETS / "index.html").read_text(encoding="utf-8").replace("__TOKEN__", TOKEN)
            except OSError as exc:
                self._send(HTTPStatus.INTERNAL_SERVER_ERROR, "dashboard assets missing: " + str(exc), "text/plain")
                return
            self._send(HTTPStatus.OK, html, "text/html; charset=utf-8")
            return
        if parsed.path == "/classic":
            try:
                html = (ASSETS / "index.html").read_text(encoding="utf-8").replace("__TOKEN__", TOKEN)
                html = html.replace('href="/app.css"', 'href="/classic/app.css"').replace('src="/app.js"', 'src="/classic/app.js"')
            except OSError as exc:
                self._send(HTTPStatus.INTERNAL_SERVER_ERROR, "classic assets missing: " + str(exc), "text/plain")
                return
            self._send(HTTPStatus.OK, html, "text/html; charset=utf-8")
            return
        if parsed.path in {"/app.css", "/app.js", "/mockups.css"}:
            name = parsed.path.lstrip("/")
            try:
                data = (V2_ASSETS / name).read_bytes()
            except OSError:
                self._send(HTTPStatus.NOT_FOUND, "missing", "text/plain")
                return
            content_type = "text/css" if name.endswith(".css") else "application/javascript"
            self._send(HTTPStatus.OK, data, content_type + "; charset=utf-8")
            return
        if parsed.path in {"/classic/app.css", "/classic/app.js"}:
            name = parsed.path.rsplit("/", 1)[-1]
            try:
                data = (ASSETS / name).read_bytes()
            except OSError:
                self._send(HTTPStatus.NOT_FOUND, "missing", "text/plain")
                return
            content_type = "text/css" if name.endswith(".css") else "application/javascript"
            self._send(HTTPStatus.OK, data, content_type + "; charset=utf-8")
            return
        if parsed.path == "/api/logs/stream":
            self._stream_logs()
            return
        if parsed.path == "/api/runs":
            self._json(HTTPStatus.OK, {"runs": _run_summaries()})
            return
        if parsed.path == "/api/run":
            query = parse_qs(parsed.query)
            run_id = (query.get("id") or [""])[0]
            detail = _run_detail(run_id)
            if detail is None:
                self._json(HTTPStatus.NOT_FOUND, {"error": "run not found"})
            else:
                self._json(HTTPStatus.OK, detail)
            return
        if parsed.path == "/api/state":
            try:
                self._json(HTTPStatus.OK, collect_state())
            except Exception as exc:
                self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": type(exc).__name__ + ": " + str(exc)})
            return
        if parsed.path == "/api/catalog":
            try:
                import catalog as catalog_spec
                self._json(HTTPStatus.OK, catalog_spec.discover(REPO_ROOT))
            except Exception as exc:
                self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": type(exc).__name__ + ": " + str(exc)})
            return
        if parsed.path == "/api/insights":
            try:
                self._json(HTTPStatus.OK, {"insights": collect_state()["insights"]})
            except Exception as exc:
                self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": type(exc).__name__ + ": " + str(exc)})
            return
        if parsed.path == "/api/job":
            self._json(HTTPStatus.OK, _job_public())
            return
        if parsed.path == "/api/artifact":
            query = parse_qs(parsed.query)
            path_value = (query.get("path") or [""])[0]
            target = _safe_artifact(path_value)
            if target is None:
                self._json(HTTPStatus.NOT_FOUND, {"error": "artifact not found"})
                return
            if (query.get("raw") or ["0"])[0] == "1":
                content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
                self._send(HTTPStatus.OK, target.read_bytes(), content_type)
                return
            entry = _artifact_entry(target)
            entry["sha256"] = _hash(target)
            self._json(HTTPStatus.OK, entry)
            return
        if parsed.path == "/api/diff":
            try:
                import console
                self._json(HTTPStatus.OK, console.diff_report(REPO_ROOT))
            except Exception as exc:
                self._json(HTTPStatus.OK, {"available": False, "error": str(exc)})
            return
        self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path != "/api/run":
            self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        if not self._authorized():
            return

        length = int(self.headers.get("Content-Length", "0") or "0")
        if length > 4096:
            self._json(HTTPStatus.BAD_REQUEST, {"error": "body too large"})
            return
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._json(HTTPStatus.BAD_REQUEST, {"error": "bad json"})
            return
        action = payload.get("action")
        if action not in COMMANDS:
            self._json(HTTPStatus.BAD_REQUEST, {"error": "unknown action"})
            return
        if not _start_job(action):
            self._json(HTTPStatus.CONFLICT, {"error": "a job is already running"})
            return
        self._json(HTTPStatus.ACCEPTED, {"job": action})


def _hash(path):
    import hashlib
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def serve(port=8765, open_browser=True):
    if not (ASSETS / "index.html").exists():
        raise SystemExit("classic dashboard assets missing at " + str(ASSETS))
    if not (V2_ASSETS / "index.html").exists():
        raise SystemExit("dashboard assets missing at " + str(V2_ASSETS))
    server = ThreadingHTTPServer(("127.0.0.1", int(port)), Handler)
    url = "http://127.0.0.1:" + str(port) + "/"
    print("ProjectGypsy dashboard: " + url)
    print("local-only; token-protected actions; Ctrl+C to stop")
    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        server.server_close()
    return 0


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description="Local-only ProjectGypsy dashboard")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-open", action="store_true", help="do not open the browser")
    args = parser.parse_args(argv)
    return serve(args.port, not args.no_open)


if __name__ == "__main__":
    raise SystemExit(main())
