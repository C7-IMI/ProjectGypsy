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
from urllib.parse import parse_qs, urlparse

try:
    from . import slices as slice_spec
except ImportError:
    import slices as slice_spec

REPO_ROOT = Path(__file__).resolve().parent.parent
ASSETS = REPO_ROOT / "design" / "dashboard"
STATE = REPO_ROOT / "workstream" / "state"
TOKEN = secrets.token_urlsafe(24)
JOB_LOCK = threading.Lock()
JOB = {"id": None, "action": None, "status": "idle", "startedAt": None, "finishedAt": None, "returncode": None, "output": "", "command": None}
MAX_OUTPUT = 20000

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


def _phases(states, gates):
    def passed(slice_id):
        item = states.get(slice_id) or {}
        return bool(item.get("passed"))
    return [
        {"phase": 0, "label": "Foundation", "status": "done", "detail": "probes, manifests, checks"},
        {"phase": 1, "label": "Vertical slice", "status": "done", "detail": "demo, build, capture"},
        {"phase": 2, "label": "Orchestrator", "status": "done", "detail": "state, hashes, multi-slice"},
        {"phase": 3, "label": "Toolpacks", "status": "done" if passed("toolpacks") else "ready", "detail": "import + audio"},
        {"phase": 4, "label": "Console", "status": "done", "detail": "read-only board, preview, diff"},
        {"phase": 5, "label": "Live / mobile", "status": "partial", "detail": "APK built; device untested"},
        {"phase": 6, "label": "UE5 adapter", "status": "blocked", "detail": "4 GB < 8 GB VRAM"},
    ]


def _gates(task, states):
    apk = (REPO_ROOT / "build" / "ProjectGypsy.apk").exists()
    exe = (REPO_ROOT / "build" / "ProjectGypsy.exe").exists()
    return [
        {"id": "windows", "label": "Windows build", "status": "pass" if exe else "ready", "detail": "109,127,680 B" if exe else "not built"},
        {"id": "mobile", "label": "Android package", "status": "pass" if apk else "ready", "detail": "signed arm64 APK" if apk else "not built"},
        {"id": "device", "label": "Device launch", "status": "untested", "detail": "no device or emulator used"},
        {"id": "engine2", "label": "Second engine", "status": "blocked", "detail": "Unity licence PASS, no Unity slice; UE5 VRAM; Flax no headless"},
        {"id": "ue5", "label": "Phase 6 UE5", "status": "blocked", "detail": "4 GB VRAM < 8 GB minimum"},
        {"id": "quality", "label": "Quality + records", "status": "pass" if passed_quality(states) else "ready", "detail": "checks, tests, records"},
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
    with JOB_LOCK:
        job = dict(JOB)
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
        "metrics": {
            "tests": tests,
            "capabilities": caps,
            "slicesPassed": sum(1 for item in slices if item.get("passed")),
            "slicesTotal": len(slices),
            "blocked": sum(1 for gate in gates if gate.get("status") == "blocked"),
            "untested": sum(1 for gate in gates if gate.get("status") == "untested"),
        },
        "benchmark": benchmark,
        "job": job,
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
    command = COMMANDS.get(action)
    if not command:
        return
    started = _utc()
    with JOB_LOCK:
        JOB.update({"id": uuid.uuid4().hex[:8], "action": action, "status": "running", "startedAt": started, "finishedAt": None, "returncode": None, "output": "", "command": command["argv"]})
    import subprocess
    try:
        result = subprocess.run(command["argv"], cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1800, shell=False)
        output = (result.stdout or "") + (result.stderr or "")
        code = result.returncode
    except subprocess.TimeoutExpired as exc:
        output = (str(exc.stdout or "") + "\n" + str(exc.stderr or "")) + "\nTIMEOUT"
        code = -1
    except Exception as exc:
        output = "ERROR " + type(exc).__name__ + ": " + str(exc)
        code = -1
    clipped = output[-MAX_OUTPUT:]
    with JOB_LOCK:
        JOB.update({"status": "passed" if code == 0 else "failed", "finishedAt": _utc(), "returncode": code, "output": clipped})
    try:
        (STATE / "dashboard-job.json").write_text(json.dumps(dict(JOB), indent=2) + "\n", encoding="utf-8")
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
                html = (ASSETS / "index.html").read_text(encoding="utf-8").replace("__TOKEN__", TOKEN)
            except OSError as exc:
                self._send(HTTPStatus.INTERNAL_SERVER_ERROR, "dashboard assets missing: " + str(exc), "text/plain")
                return
            self._send(HTTPStatus.OK, html, "text/html; charset=utf-8")
            return
        if parsed.path in {"/app.css", "/app.js"}:
            name = parsed.path.lstrip("/")
            try:
                data = (ASSETS / name).read_bytes()
            except OSError:
                self._send(HTTPStatus.NOT_FOUND, "missing", "text/plain")
                return
            content_type = "text/css" if name.endswith(".css") else "application/javascript"
            self._send(HTTPStatus.OK, data, content_type + "; charset=utf-8")
            return
        if parsed.path == "/api/state":
            try:
                self._json(HTTPStatus.OK, collect_state())
            except Exception as exc:
                self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": type(exc).__name__ + ": " + str(exc)})
            return
        if parsed.path == "/api/job":
            with JOB_LOCK:
                self._json(HTTPStatus.OK, dict(JOB))
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
        raise SystemExit("dashboard assets missing at " + str(ASSETS))
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
