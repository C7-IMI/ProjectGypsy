#!/usr/bin/env python3
"""SculptForge toolkit plugin: headless sculpt/LOD/convert and Blender bridge handoff.

The CLI is invoked with fixed command templates and project-confined paths. The bridge is a
file-exchange folder owned by SculptForge; live GUI automation is not claimed. SculptForge is
GPL-3.0-or-later and is not redistributed here.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import toolkit as toolkit_core

TOOLKIT_ID = "sculptforge"
NAME = "SculptForge"
SUMMARY = "Headless SculptForge LOD/convert commands and the Blender bridge handoff."
LICENSE = "SculptForge GPL-3.0-or-later; plugin original; application not redistributed"
STATUS = "partial"
KIND = "design-sculpting"
CAPABILITY = "toolkit.sculptforge"
HOME = "https://sculptforge.app/"
DOCS = "docs/ADR-026-sculptforge.md"

DEFAULT_CLI = r"C:\Program Files\SculptForge\bin\sculptforge-cli.exe"
CLI_ENV = "SCULPTFORGE_CLI"
BRIDGE_ENV = "SCULPTFORGE_BLENDER_EXCHANGE"
ADDON_ID = "sculptforge_bridge"
DEFAULT_TIMEOUT = 180.0
MAX_TIMEOUT = 600.0
MAX_LEVELS = 6
MIN_LEVELS = 1
FORMATS = {"glb": "export_glb", "fbx": "export_fbx", "usd": "export_usd"}
INPUT_SUFFIXES = {".obj", ".fbx", ".glb", ".gltf", ".ply", ".stl", ".usd", ".usda", ".usdz", ".goz"}
META = set(";\r\n$" + chr(96) + "\"")


class SculptForgeError(toolkit_core.ToolkitError):
    """SculptForge is missing, the command is unsafe, or the CLI failed."""


def _utc():
    return toolkit_core.utc_now_iso()


def _cli_path():
    return Path(os.environ.get(CLI_ENV) or DEFAULT_CLI).expanduser()


def _cli_command():
    path = _cli_path()
    if path.suffix.lower() == ".py":
        return [sys.executable, str(path)]
    return [str(path)]


def _bridge_exchange():
    override = os.environ.get(BRIDGE_ENV)
    if override:
        return Path(override).expanduser()
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "SculptForge" / "SculptForge" / "blender"
    return Path.home() / "AppData" / "Roaming" / "SculptForge" / "SculptForge" / "blender"


def _addon_paths():
    appdata = os.environ.get("APPDATA")
    roots = []
    if appdata:
        roots.append(Path(appdata) / "Blender Foundation" / "Blender")
    roots.append(Path.home() / "AppData" / "Roaming" / "Blender Foundation" / "Blender")
    found = []
    seen = set()
    for root in roots:
        if not root.is_dir():
            continue
        for version in sorted(root.iterdir(), reverse=True):
            candidate = version / "extensions" / "user_default" / ADDON_ID
            key = str(candidate.resolve()) if candidate.exists() else str(candidate)
            if candidate.is_dir() and key not in seen:
                seen.add(key)
                found.append(candidate)
    return found


def _read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def _heartbeat(exchange):
    data = _read_json(exchange / "alive.json")
    if not isinstance(data, dict):
        return None
    return {"pid": data.get("pid"), "time": data.get("time"), "ageSeconds": _age(data.get("time"))}


def _age(value):
    if not isinstance(value, str):
        return None
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        return round((datetime.now(timezone.utc) - moment.astimezone(timezone.utc)).total_seconds(), 1)
    except (TypeError, ValueError):
        return None


def _app_path():
    data = _read_json(_bridge_exchange() / "app.json")
    return data.get("path") if isinstance(data, dict) and isinstance(data.get("path"), str) else None


def _version():
    data = _read_json(_bridge_exchange() / "app.json")
    if isinstance(data, dict) and isinstance(data.get("version"), str):
        return data["version"]
    return None


def _run(argv, cwd, timeout):
    try:
        return subprocess.run(list(argv), cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=min(float(timeout), MAX_TIMEOUT), shell=False)
    except (OSError, subprocess.SubprocessError):
        return None


def probe():
    cli = _cli_path()
    installed = cli.is_file()
    help_ok = False
    help_error = None
    if installed:
        completed = _run([*_cli_command(), "--help"], Path.cwd(), 8.0)
        if completed is None:
            help_error = "CLI probe timed out"
        else:
            help_ok = completed.returncode == 0
            if not help_ok:
                help_error = "CLI --help exited " + str(completed.returncode)
    exchange = _bridge_exchange()
    addons = _addon_paths()
    return {
        "toolkit": TOOLKIT_ID,
        "installed": installed,
        "cli": str(cli),
        "version": _version(),
        "helpOk": help_ok,
        "helpError": help_error,
        "bridgeAddonInstalled": bool(addons),
        "bridgeAddonPaths": [str(path) for path in addons],
        "exchange": str(exchange),
        "exchangeExists": exchange.is_dir(),
        "heartbeat": _heartbeat(exchange),
        "appPath": _app_path(),
        "checkedAt": _utc(),
        "notes": [
            "Bridge is file-exchange based; alive.json is rewritten by SculptForge while it runs.",
            "The CLI runs headless; bridge-send/receive use the SculptForge exchange folder.",
            "No live GUI automation or arbitrary remote command execution.",
        ],
    }


def _project_root(value):
    root = Path(value or ".").expanduser().resolve()
    if not root.is_dir():
        raise SculptForgeError("project root is not a directory: " + str(root))
    return root


def _safe_relpath(value, root, label):
    if not isinstance(value, str) or not value.strip():
        raise SculptForgeError(label + " is required")
    if any(ch in META for ch in value):
        raise SculptForgeError(label + " contains a script metacharacter")
    candidate = Path(value)
    if candidate.is_absolute():
        try:
            candidate = candidate.resolve().relative_to(root)
        except ValueError:
            raise SculptForgeError(label + " resolves outside the project") from None
    if ".." in candidate.parts:
        raise SculptForgeError(label + " must not contain '..'")
    return toolkit_core.resolve_within(root, candidate.as_posix(), label=label)


def _safe_value(value, label):
    if not isinstance(value, str) or any(ch in META for ch in value):
        raise SculptForgeError(label + " contains a script metacharacter")
    return value


def _validate_input(value, root):
    path = _safe_relpath(value, root, "input")
    if not path.is_file():
        raise SculptForgeError("input not found: " + str(path))
    if path.suffix.lower() not in INPUT_SUFFIXES:
        raise SculptForgeError("unsupported SculptForge input extension: " + path.suffix)
    return path.relative_to(root).as_posix()


def _validate_output(value, root):
    path = _safe_relpath(value, root, "output")
    if path.suffix.lower() not in {".glb", ".fbx", ".usd", ".usda", ".usdz"}:
        raise SculptForgeError("unsupported output extension: " + path.suffix)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path, path.relative_to(root).as_posix()


def _run_cli(root, sets, script, timeout):
    argv = [*_cli_command()]
    for name, value in sets.items():
        argv.extend(["--set", name + "=" + _safe_value(str(value), "CLI value")])
    argv.extend(["-c", script])
    completed = _run(argv, root, timeout)
    if completed is None:
        raise SculptForgeError("SculptForge CLI did not start or timed out")
    return {"returncode": completed.returncode, "stdout": completed.stdout[-4000:], "stderr": completed.stderr[-4000:], "script": script}


def _artifact(path, root):
    return {"path": path.relative_to(root).as_posix(), "bytes": path.stat().st_size, "sha256": toolkit_core.sha256_file(path)}


def lods(project, input, output, levels=3, ratio=0.5, force=False, timeout=DEFAULT_TIMEOUT):
    root = _project_root(project)
    input_rel = _validate_input(input, root)
    output_path, output_rel = _validate_output(output, root)
    try:
        levels = int(levels)
        ratio = float(ratio)
    except (TypeError, ValueError) as exc:
        raise SculptForgeError("levels/ratio must be numeric") from exc
    if not MIN_LEVELS <= levels <= MAX_LEVELS:
        raise SculptForgeError("levels must be 1-6")
    if not 0.05 <= ratio <= 0.95:
        raise SculptForgeError("ratio must be between 0.05 and 0.95")
    expected = [output_path.with_name(output_path.stem + "_LOD" + str(index) + ".glb") for index in range(levels + 1)]
    existing = [path for path in expected if path.exists()]
    if existing and not force:
        raise SculptForgeError("LOD output exists; use --force: " + ", ".join(path.name for path in existing))
    result = _run_cli(root, {"INPUT": input_rel, "OUT": output_rel, "LEVELS": levels, "RATIO": ratio}, "open path=$INPUT; export_lods path=$OUT levels=$LEVELS ratio=$RATIO", timeout)
    missing = [path.relative_to(root).as_posix() for path in expected if not path.is_file()]
    errors = []
    if result["returncode"] != 0:
        errors.append("SculptForge CLI exited " + str(result["returncode"]))
    if missing:
        errors.append("missing LOD outputs: " + ", ".join(missing))
    return {
        "toolkit": TOOLKIT_ID,
        "action": "lods",
        "passed": result["returncode"] == 0 and not missing,
        "project": str(root),
        "input": input_rel,
        "output": output_rel,
        "levels": levels,
        "ratio": ratio,
        "artifacts": [_artifact(path, root) for path in expected if path.is_file()],
        "command": result,
        "errors": errors,
        "checkedAt": _utc(),
    }


def convert(project, input, output, format="glb", force=False, timeout=DEFAULT_TIMEOUT):
    root = _project_root(project)
    input_rel = _validate_input(input, root)
    output_path, output_rel = _validate_output(output, root)
    format = str(format).lower()
    if format not in FORMATS:
        raise SculptForgeError("format must be glb, fbx or usd")
    if output_path.exists() and not force:
        raise SculptForgeError("output exists; use --force: " + output_rel)
    result = _run_cli(root, {"INPUT": input_rel, "OUT": output_rel}, "open path=$INPUT; " + FORMATS[format] + " path=$OUT", timeout)
    errors = []
    if result["returncode"] != 0:
        errors.append("SculptForge CLI exited " + str(result["returncode"]))
    if not output_path.is_file():
        errors.append("output missing: " + output_rel)
    return {
        "toolkit": TOOLKIT_ID,
        "action": "convert",
        "passed": result["returncode"] == 0 and output_path.is_file(),
        "project": str(root),
        "input": input_rel,
        "output": output_rel,
        "format": format,
        "artifacts": [_artifact(output_path, root)] if output_path.is_file() else [],
        "command": result,
        "errors": errors,
        "checkedAt": _utc(),
    }


def bridge_send(project, input, timeout=DEFAULT_TIMEOUT):
    root = _project_root(project)
    input_rel = _validate_input(input, root)
    exchange = _bridge_exchange()
    manifest = exchange / "to_blender" / "manifest.json"
    before = manifest.stat().st_mtime_ns if manifest.is_file() else None
    result = _run_cli(root, {"INPUT": input_rel}, "open path=$INPUT; blender_send", timeout)
    after = manifest.stat().st_mtime_ns if manifest.is_file() else None
    errors = []
    if result["returncode"] != 0:
        errors.append("SculptForge CLI exited " + str(result["returncode"]))
    if not manifest.is_file():
        errors.append("bridge manifest not created at " + str(manifest))
    elif before == after:
        errors.append("bridge manifest did not change; the send may not have been consumed")
    return {
        "toolkit": TOOLKIT_ID,
        "action": "bridge-send",
        "passed": result["returncode"] == 0 and manifest.is_file() and before != after,
        "project": str(root),
        "input": input_rel,
        "exchange": str(exchange),
        "manifest": str(manifest),
        "manifestChanged": before != after,
        "bridge": probe(),
        "command": result,
        "errors": errors,
        "checkedAt": _utc(),
    }


def bridge_receive(project, output, force=False, timeout=DEFAULT_TIMEOUT):
    root = _project_root(project)
    output_path, output_rel = _validate_output(output, root)
    if output_path.exists() and not force:
        raise SculptForgeError("output exists; use --force: " + output_rel)
    result = _run_cli(root, {"OUT": output_rel}, "blender_receive; export_glb path=$OUT", timeout)
    errors = []
    if result["returncode"] != 0:
        errors.append("SculptForge CLI exited " + str(result["returncode"]))
    if not output_path.is_file():
        errors.append("output missing: " + output_rel)
    return {
        "toolkit": TOOLKIT_ID,
        "action": "bridge-receive",
        "passed": result["returncode"] == 0 and output_path.is_file(),
        "project": str(root),
        "output": output_rel,
        "exchange": str(_bridge_exchange()),
        "artifacts": [_artifact(output_path, root)] if output_path.is_file() else [],
        "command": result,
        "errors": errors,
        "checkedAt": _utc(),
    }


def describe():
    return {
        "id": TOOLKIT_ID,
        "name": NAME,
        "summary": SUMMARY,
        "license": LICENSE,
        "status": STATUS,
        "kind": KIND,
        "capability": CAPABILITY,
        "home": HOME,
        "docs": DOCS,
        "cli": str(_cli_path()),
        "bridgeExchange": str(_bridge_exchange()),
        "bridgeAddonId": ADDON_ID,
        "commands": [
            "status",
            "lods --project DIR --input FILE --output FILE [--levels 3] [--ratio 0.5] [--force]",
            "convert --project DIR --input FILE --output FILE --format glb|fbx|usd [--force]",
            "bridge-send --project DIR --input FILE",
            "bridge-receive --project DIR --output FILE [--force]",
        ],
        "limits": [
            "Bridge commands require SculptForge and the Blender add-on/exchange folder; no GUI automation.",
            "Only fixed templates and project-local paths are passed; no arbitrary argv or shell.",
            "SculptForge is GPL-3.0-or-later and is not redistributed.",
            "A missing heartbeat is reported, not treated as success.",
        ],
    }


def _configure_status(parser):
    return None


def _run_status(args):
    return 0, probe()


def _render_status(payload):
    lines = [
        "sculptforge: " + ("INSTALLED" if payload.get("installed") else "NOT INSTALLED"),
        "version: " + str(payload.get("version") or "unknown"),
        "cli: " + str(payload.get("cli")),
        "bridge add-on: " + ("FOUND" if payload.get("bridgeAddonInstalled") else "NOT FOUND"),
        "exchange: " + str(payload.get("exchange")) + (" (exists)" if payload.get("exchangeExists") else " (missing)"),
        "heartbeat: " + ("present" if payload.get("heartbeat") else "not running/no heartbeat"),
        "app: " + str(payload.get("appPath") or "not recorded"),
    ]
    return "\n".join(lines)


def _configure_lods(parser):
    parser.add_argument("--project", default=".")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--levels", type=int, default=3)
    parser.add_argument("--ratio", type=float, default=0.5)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)


def _run_lods(args):
    return 0, lods(args.project, args.input, args.output, levels=args.levels, ratio=args.ratio, force=args.force, timeout=args.timeout)


def _configure_convert(parser):
    parser.add_argument("--project", default=".")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--format", default="glb", choices=sorted(FORMATS))
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)


def _run_convert(args):
    return 0, convert(args.project, args.input, args.output, format=args.format, force=args.force, timeout=args.timeout)


def _configure_bridge_send(parser):
    parser.add_argument("--project", default=".")
    parser.add_argument("--input", required=True)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)


def _run_bridge_send(args):
    return 0, bridge_send(args.project, args.input, timeout=args.timeout)


def _configure_bridge_receive(parser):
    parser.add_argument("--project", default=".")
    parser.add_argument("--output", required=True)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)


def _run_bridge_receive(args):
    return 0, bridge_receive(args.project, args.output, force=args.force, timeout=args.timeout)


def _render_action(payload):
    lines = ["sculptforge " + str(payload.get("action") or "status") + ": " + ("PASS" if payload.get("passed") else "FAIL")]
    if payload.get("input"):
        lines.append("input: " + str(payload["input"]))
    if payload.get("output"):
        lines.append("output: " + str(payload["output"]))
    for artifact in payload.get("artifacts", []):
        lines.append("artifact: " + artifact["path"] + " " + str(artifact["bytes"]) + " B " + artifact["sha256"][:16] + "...")
    for error in payload.get("errors", []):
        lines.append("ERROR " + str(error))
    return "\n".join(lines)


COMMANDS = {
    "status": {"summary": "locate SculptForge, the Blender bridge and its heartbeat", "configure": _configure_status, "run": _run_status, "render": _render_status},
    "lods": {"summary": "headless LOD chain export", "configure": _configure_lods, "run": _run_lods, "render": _render_action},
    "convert": {"summary": "headless convert to GLB/FBX/USD", "configure": _configure_convert, "run": _run_convert, "render": _render_action},
    "bridge-send": {"summary": "send a model to Blender via SculptForge bridge", "configure": _configure_bridge_send, "run": _run_bridge_send, "render": _render_action},
    "bridge-receive": {"summary": "receive the Blender result into a GLB", "configure": _configure_bridge_receive, "run": _run_bridge_receive, "render": _render_action},
}
