#!/usr/bin/env python3
"""Godot game adapter for the ProjectGypsy vertical slice.

Commands are intentionally thin: run the deterministic headless demo, export the Windows build,
and attempt a rendered capture. Evidence is written to workstream/state/ and printed as JSON by the CLI.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import time
from pathlib import Path

import gypsy

GAME_DIR = gypsy.REPO_ROOT / "game"
BUILD_DIR = gypsy.REPO_ROOT / "build"
CAPTURE_DIR = gypsy.REPO_ROOT / "artifacts" / "game"
DEFAULT_PRESET = "Windows Desktop"


def _godot_cli():
    record = gypsy.detect_godot()
    if not record.get("installed") or not record.get("usable"):
        raise gypsy.GypsyError("Godot is not installed/usable")
    return record


def _evidence(name: str, payload: dict):
    gypsy.STATE_DIR.mkdir(parents=True, exist_ok=True)
    path = gypsy.STATE_DIR / name
    import json

    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def _ffmpeg():
    """Resolve ffmpeg from PATH or the GameTools manifest (DSH sessions may have a stale PATH)."""
    found = shutil.which("ffmpeg")
    if found:
        return found
    local = Path(__import__("os").environ.get("LOCALAPPDATA", "")) / "Programs" / "GameTools" / "ffmpeg"
    for candidate in local.glob("*/bin/ffmpeg.exe"):
        return str(candidate)
    return None


def demo(game_dir: Path = GAME_DIR, timeout: int = 180) -> dict:
    game_dir = Path(game_dir)
    if not (game_dir / "project.godot").exists():
        raise gypsy.GypsyError("game/project.godot is missing")
    record = _godot_cli()
    started = time.time()
    result = gypsy.run([record["cli"], "--headless", "--path", str(game_dir), "--", "--demo"], timeout=timeout, cwd=gypsy.REPO_ROOT)
    text = result["stdout"] + "\n" + result["stderr"]
    match = re.search(r"GYPSY_DEMO_OK\s+collected=(\d+)\s+frames=(\d+)", text)
    evidence = {
        "schema": "gypsy.artifact/v1",
        "kind": "game.demo",
        "engine": "godot",
        "engineVersion": record.get("version"),
        "command": result["cmd"],
        "exit": result["exit"],
        "seconds": result["seconds"],
        "marker": match.group(0) if match else None,
        "collected": int(match.group(1)) if match else None,
        "frames": int(match.group(2)) if match else None,
        "stdout": result["stdout"][-4000:],
        "stderr": result["stderr"][-4000:],
        "passed": result["exit"] == 0 and match is not None and int(match.group(1)) == 3,
    }
    evidence["evidencePath"] = str(_evidence("game-demo.json", evidence))
    if not evidence["passed"]:
        raise gypsy.GypsyError("game demo failed: " + text[-2000:])
    return evidence


def build(game_dir: Path = GAME_DIR, preset: str = DEFAULT_PRESET, output: Path = None, timeout: int = 600) -> dict:
    game_dir = Path(game_dir)
    if not (game_dir / "project.godot").exists():
        raise gypsy.GypsyError("game/project.godot is missing")
    record = _godot_cli()
    templates = Path(__import__("os").environ.get("APPDATA", "")) / "Godot" / "export_templates"
    if not templates.is_dir() or not any(templates.iterdir()):
        raise gypsy.GypsyError("Godot export templates are not installed")
    output = Path(output) if output else BUILD_DIR / "ProjectGypsy.exe"
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()
    result = gypsy.run(
        [record["cli"], "--headless", "--path", str(game_dir), "--export-release", preset, str(output)],
        timeout=timeout,
        cwd=gypsy.REPO_ROOT,
    )
    evidence = {
        "schema": "gypsy.artifact/v1",
        "kind": "game.build",
        "engine": "godot",
        "engineVersion": record.get("version"),
        "preset": preset,
        "output": str(output),
        "command": result["cmd"],
        "exit": result["exit"],
        "seconds": result["seconds"],
        "bytes": output.stat().st_size if output.exists() else 0,
        "stdout": result["stdout"][-4000:],
        "stderr": result["stderr"][-4000:],
        "passed": result["exit"] == 0 and output.exists() and output.stat().st_size > 0,
    }
    runtime = None
    if evidence["passed"]:
        runtime = gypsy.run([str(output), "--headless", "--", "--demo"], timeout=120, cwd=gypsy.REPO_ROOT)
        runtime_text = runtime["stdout"] + "\n" + runtime["stderr"]
        runtime_match = re.search(r"GYPSY_DEMO_OK\s+collected=(\d+)\s+frames=(\d+)", runtime_text)
        evidence["runtime"] = {
            "command": runtime["cmd"],
            "exit": runtime["exit"],
            "seconds": runtime["seconds"],
            "marker": runtime_match.group(0) if runtime_match else None,
            "passed": runtime["exit"] == 0 and runtime_match is not None and int(runtime_match.group(1)) == 3,
            "stdout": runtime["stdout"][-2000:],
            "stderr": runtime["stderr"][-2000:],
        }
    evidence["evidencePath"] = str(_evidence("game-build.json", evidence))
    if not evidence["passed"]:
        raise gypsy.GypsyError("game build failed: " + (result["stdout"] + result["stderr"])[-2000:])
    return evidence


def capture(game_dir: Path = GAME_DIR, seconds: int = 30, timeout: int = 240) -> dict:
    """Windowed movie-maker capture. Headless has no renderer, so this intentionally omits --headless."""
    game_dir = Path(game_dir)
    record = _godot_cli()
    CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
    movie = CAPTURE_DIR / "demo.avi"
    if movie.exists():
        movie.unlink()
    result = gypsy.run(
        [record["cli"], "--path", str(game_dir), "--write-movie", str(movie), "--fixed-fps", "30", "--", "--demo"],
        timeout=timeout,
        cwd=gypsy.REPO_ROOT,
    )
    ffmpeg = _ffmpeg()
    mp4 = None
    frame = None
    if movie.exists() and ffmpeg:
        mp4 = CAPTURE_DIR / "demo.mp4"
        frame = CAPTURE_DIR / "frame.png"
        gypsy.run([ffmpeg, "-y", "-i", str(movie), "-pix_fmt", "yuv420p", str(mp4)], timeout=120)
        gypsy.run([ffmpeg, "-y", "-i", str(mp4), "-frames:v", "1", str(frame)], timeout=60)
    evidence = {
        "schema": "gypsy.artifact/v1",
        "kind": "game.capture",
        "engine": "godot",
        "mode": "windowed movie maker",
        "command": result["cmd"],
        "exit": result["exit"],
        "seconds": result["seconds"],
        "movie": str(movie) if movie.exists() else None,
        "mp4": str(mp4) if mp4 and mp4.exists() else None,
        "frame": str(frame) if frame and frame.exists() else None,
        "stdout": result["stdout"][-2000:],
        "stderr": result["stderr"][-2000:],
        "passed": result["exit"] == 0 and movie.exists() and movie.stat().st_size > 0,
    }
    evidence["evidencePath"] = str(_evidence("game-capture.json", evidence))
    if not evidence["passed"]:
        raise gypsy.GypsyError("game capture failed: " + (result["stdout"] + result["stderr"])[-2000:])
    return evidence


def verify(game_dir: Path = GAME_DIR) -> dict:
    demo_result = demo(game_dir)
    build_result = build(game_dir)
    capture_result = None
    capture_error = None
    try:
        capture_result = capture(game_dir)
    except gypsy.GypsyError as exc:
        capture_error = str(exc)
    result = {
        "schema": "gypsy.artifact/v1",
        "kind": "game.verify",
        "demo": {k: demo_result[k] for k in ("passed", "marker", "frames", "seconds")},
        "build": {k: build_result[k] for k in ("passed", "output", "bytes", "seconds")},
        "capture": ({k: capture_result[k] for k in ("passed", "movie", "mp4", "frame")} if capture_result else None),
        "captureError": capture_error,
        "passed": demo_result["passed"] and build_result["passed"],
        "capturePassed": bool(capture_result and capture_result["passed"]),
    }
    result["evidencePath"] = str(_evidence("game-verify.json", result))
    return result