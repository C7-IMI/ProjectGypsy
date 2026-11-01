#!/usr/bin/env python3
"""MocapAnything toolkit plugin: video-to-motion capture integration.

The repository is an external MIT-licensed research implementation. Gypsy integrates its
already-installed environment by running fixed inference/validation commands and reporting
the real environment; it does not install PyTorch/model weights and does not claim inference
works unless the configured command exits successfully and expected outputs exist.

Commands:
  status   inspect repo, Python, torch, CUDA, checkpoint and demo-data readiness
  infer    run inference/video2pose2rot.py with a repository-local YAML config
  validate parse a BVH header and motion frame count
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import toolkit as toolkit_core

TOOLKIT_ID = "mocapanything"
NAME = "MocapAnything"
SUMMARY = "Video-to-motion capture for arbitrary skeletons via an external MoCapAnything V2 environment."
LICENSE = "MIT code/weights; demo data research-use; RMBG-1.4 and Truebones data have separate terms"
STATUS = "experimental"
KIND = "animation-mocap"
CAPABILITY = "toolkit.mocapanything"
HOME = "https://github.com/phongdaot/MocapAnything"
DOCS = "docs/ADR-027-mocapanything.md"

DEFAULT_HOME = r"C:\GameTools\MocapAnything"
HOME_ENV = "MOCAPANYTHING_HOME"
PYTHON_ENV = "MOCAPANYTHING_PYTHON"
DEFAULT_TIMEOUT = 900.0
MAX_TIMEOUT = 3600.0
CONFIG_SUFFIXES = {".yaml", ".yml"}
META = set(";\r\n$" + chr(96) + "\"")


class MocapAnythingError(toolkit_core.ToolkitError):
    """The environment, config or output is unavailable or unsafe."""


def _home():
    return Path(os.environ.get(HOME_ENV) or DEFAULT_HOME).expanduser()


def _python():
    return Path(os.environ.get(PYTHON_ENV) or (_home() / ".venv" / "Scripts" / "python.exe")).expanduser()


def _python_command():
    path = _python()
    if path.suffix.lower() == ".py":
        return [sys.executable, str(path)]
    return [str(path)]


def _run(argv, cwd, timeout, env=None):
    try:
        return subprocess.run(list(argv), cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=min(float(timeout), MAX_TIMEOUT), shell=False, env=env)
    except (OSError, subprocess.SubprocessError):
        return None


def _python_probe():
    if not _python().is_file():
        return {"ok": False, "version": None, "torch": None, "cuda": None, "error": "Python executable missing"}
    code = "import sys, json; out={'version':sys.version.split()[0]};\ntry:\n import torch; out['torch']=torch.__version__; out['cuda']=bool(torch.cuda.is_available()); out['device']=torch.cuda.get_device_name(0) if torch.cuda.is_available() else None\nexcept Exception as exc: out['torch']=None; out['cuda']=None; out['error']=type(exc).__name__+': '+str(exc)\nprint(json.dumps(out))"
    completed = _run([*_python_command(), "-c", code], _home(), 30.0)
    if completed is None:
        return {"ok": False, "version": None, "torch": None, "cuda": None, "error": "python probe timed out"}
    try:
        data = json.loads(completed.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError):
        return {"ok": False, "version": None, "torch": None, "cuda": None, "error": (completed.stderr or completed.stdout)[-300:]}
    data["ok"] = completed.returncode == 0 and data.get("torch") is not None
    return data


def probe():
    home = _home()
    python_info = _python_probe()
    checkpoint = home / "checkpoints" / "video2pos2rot_epoch60.pt"
    data = home / "demo" / "data"
    configs = home / "demo" / "configs"
    evidence = None
    try:
        evidence_path = Path(__file__).resolve().parents[2] / "docs" / "evidence" / "mocapanything-trial.json"
        candidate = json.loads(evidence_path.read_text(encoding="utf-8"))
        if isinstance(candidate, dict) and candidate.get("schema") == "gypsy.mocapanything-evidence/v1":
            evidence = candidate
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        evidence = None
    return {
        "toolkit": TOOLKIT_ID,
        "repo": str(home),
        "repoExists": home.is_dir(),
        "python": str(_python()),
        "pythonExists": _python().is_file(),
        "pythonInfo": python_info,
        "checkpoint": str(checkpoint),
        "checkpointExists": checkpoint.is_file(),
        "checkpointBytes": checkpoint.stat().st_size if checkpoint.is_file() else 0,
        "demoData": str(data),
        "demoDataExists": data.is_dir(),
        "configs": str(configs),
        "configsExist": configs.is_dir(),
        "ready": bool(home.is_dir() and python_info.get("ok") and checkpoint.is_file()),
        "inferenceVerified": bool(evidence and evidence.get("result") == "pass"),
        "evidence": evidence,
        "checkedAt": toolkit_core.utc_now_iso(),
        "notes": [
            "ready means the repo, Python/torch and checkpoint are present; it does not mean inference was run.",
            "A 4 GB GPU is not validated for this model; CPU inference is possible but slow.",
            "External repo and weights remain separately licensed; Gypsy does not redistribute them.",
        ],
    }


def _safe_config(value):
    home = _home().resolve()
    if not isinstance(value, str) or not value.strip() or any(ch in META for ch in value):
        raise MocapAnythingError("config path is unsafe or empty")
    candidate = Path(value)
    if candidate.is_absolute():
        try:
            candidate = candidate.resolve().relative_to(home)
        except ValueError:
            raise MocapAnythingError("config resolves outside the MocapAnything home") from None
    if ".." in candidate.parts or candidate.suffix.lower() not in CONFIG_SUFFIXES:
        raise MocapAnythingError("config must be a repository-local YAML file")
    target = (home / candidate).resolve()
    if not target.is_file():
        raise MocapAnythingError("config not found: " + value)
    return target.relative_to(home).as_posix()


def infer(config, expect=None, timeout=DEFAULT_TIMEOUT):
    home = _home()
    if not _python().is_file():
        raise MocapAnythingError("MocapAnything Python environment is missing: " + str(_python()))
    config_rel = _safe_config(config)
    expected = None
    before_mtime = None
    started_ns = time.time_ns()
    if expect:
        raw_expect = Path(expect)
        if any(ch in META for ch in str(expect)) or ".." in raw_expect.parts:
            raise MocapAnythingError("expect path is unsafe")
        if raw_expect.is_absolute():
            try:
                raw_expect = raw_expect.resolve().relative_to(home.resolve())
            except ValueError:
                raise MocapAnythingError("expect path resolves outside the MocapAnything home") from None
        expected = (home / raw_expect).resolve()
        if not expected.is_relative_to(home.resolve()):
            raise MocapAnythingError("expect path resolves outside the MocapAnything home")
        before_mtime = expected.stat().st_mtime_ns if expected.is_file() else None
    argv = [*_python_command(), "inference/video2pose2rot.py", "--config", config_rel]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(home) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    completed = _run(argv, home, timeout, env)
    if completed is None:
        raise MocapAnythingError("inference did not start or timed out")
    artifacts = []
    verified_artifact = False
    if expected is not None:
        after_mtime = expected.stat().st_mtime_ns if expected.is_file() else None
        produced = after_mtime is not None and after_mtime >= started_ns and (before_mtime is None or after_mtime > before_mtime)
        if produced:
            artifacts.append({"path": str(expected), "bytes": expected.stat().st_size, "sha256": toolkit_core.sha256_file(expected)})
            verified_artifact = True
    combined = (completed.stdout or "") + "\n" + (completed.stderr or "")
    failed = [
        r"All\s+\d+\s+frames failed",
        r"All frames failed",
        r"failed preprocessing",
        r"\u6210\u529f 0",
        "Torch not compiled with CUDA",
        "CUDA error",
        "out of memory",
        "OutOfMemoryError",
    ]
    output_failure = any(re.search(pattern, combined) if pattern.startswith("All ") or "\\d" in pattern else pattern in combined for pattern in failed)
    errors = []
    if completed.returncode != 0:
        errors.append("inference exited " + str(completed.returncode))
    if output_failure:
        errors.append("inference output reports failed frames or CUDA/torch failure")
    if expected is None:
        errors.append("no expected artifact supplied; exit 0 alone is not a pass")
    elif not verified_artifact:
        errors.append("expected artifact was not produced by this run: " + expected.as_posix())
    passed = completed.returncode == 0 and not output_failure and verified_artifact
    return {
        "toolkit": TOOLKIT_ID,
        "action": "infer",
        "passed": passed,
        "config": config_rel,
        "expect": expect,
        "returncode": completed.returncode,
        "stdout": completed.stdout[-4000:],
        "stderr": completed.stderr[-4000:],
        "artifacts": artifacts,
        "errors": errors,
        "checkedAt": toolkit_core.utc_now_iso(),
        "notes": ["Only a newly produced expected artifact plus clean output counts as a pass."],
    }

def validate_bvh(path):
    target = Path(path).expanduser().resolve()
    if not target.is_file():
        raise MocapAnythingError("BVH not found: " + str(target))
    if target.suffix.lower() != ".bvh":
        raise MocapAnythingError("expected a .bvh file")
    with target.open("r", encoding="utf-8", errors="replace") as handle:
        text = handle.read(4 * 1024 * 1024)
    joints = len(re.findall(r"^\s*JOINT\s+", text, re.MULTILINE))
    frames = re.search(r"^Frames:\s*(\d+)", text, re.MULTILINE)
    frame_match = re.search(r"^Frame Time:\s*([0-9.]+)", text, re.MULTILINE)
    channels = len(re.findall(r"^\s*CHANNELS\s+", text, re.MULTILINE))
    passed = text.startswith("HIERARCHY") and "MOTION" in text and joints > 0 and frames is not None
    return {
        "toolkit": TOOLKIT_ID,
        "action": "validate-bvh",
        "passed": passed,
        "path": str(target),
        "bytes": target.stat().st_size,
        "sha256": toolkit_core.sha256_file(target),
        "joints": joints,
        "channels": channels,
        "frames": int(frames.group(1)) if frames else None,
        "frameTime": float(frame_match.group(1)) if frame_match else None,
        "errors": [] if passed else ["not a valid HIERARCHY/MOTION BVH"],
        "checkedAt": toolkit_core.utc_now_iso(),
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
        "repo": str(_home()),
        "commands": [
            "status",
            "infer --config demo/configs/demo_zoo.yaml [--expect PATH] [--timeout 900]",
            "validate --path PATH.bvh",
        ],
        "limits": [
            "External repo and model weights are not bundled; inference requires their environment.",
            "ready/probe presence is not an inference pass; only a zero exit and expected artifact count as a run.",
            "No automatic retargeting into Godot/Unity; BVH must be retargeted in Blender.",
            "GPU memory is not validated; 4 GB T600 may be insufficient.",
        ],
    }


def _configure_status(parser):
    return None


def _run_status(args):
    return 0, probe()


def _render_status(result):
    return "\n".join([
        "mocapanything: " + ("READY" if result.get("ready") else "NOT READY"),
        "repo: " + str(result.get("repo")),
        "python: " + str(result.get("pythonInfo")),
        "checkpoint: " + (str(result.get("checkpointBytes")) + " bytes" if result.get("checkpointExists") else "missing"),
        "demo data: " + ("present" if result.get("demoDataExists") else "missing"),
        "inference verified: " + str(result.get("inferenceVerified")),
    ])


def _configure_infer(parser):
    parser.add_argument("--config", required=True, help="repository-local YAML config")
    parser.add_argument("--expect", default=None, help="optional expected output file")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)


def _run_infer(args):
    return 0, infer(args.config, expect=args.expect, timeout=args.timeout)


def _render_infer(result):
    lines = ["mocapanything infer: " + ("PASS" if result.get("passed") else "FAIL"), "config: " + str(result.get("config")), "returncode: " + str(result.get("returncode"))]
    for artifact in result.get("artifacts", []):
        lines.append("artifact: " + artifact["path"] + " " + str(artifact["bytes"]) + " B")
    for error in result.get("errors", []):
        lines.append("ERROR " + str(error))
    return "\n".join(lines)


def _configure_validate(parser):
    parser.add_argument("--path", required=True, help="BVH file")


def _run_validate(args):
    return 0, validate_bvh(args.path)


def _render_validate(result):
    lines = ["mocapanything BVH: " + ("PASS" if result.get("passed") else "FAIL"), "path: " + str(result.get("path")), "joints: " + str(result.get("joints")) + " channels: " + str(result.get("channels")) + " frames: " + str(result.get("frames")), "sha256: " + str(result.get("sha256"))]
    for error in result.get("errors", []):
        lines.append("ERROR " + str(error))
    return "\n".join(lines)


COMMANDS = {
    "status": {"summary": "inspect the external MoCapAnything environment", "configure": _configure_status, "run": _run_status, "render": _render_status},
    "infer": {"summary": "run a repository-local inference config", "configure": _configure_infer, "run": _run_infer, "render": _render_infer},
    "validate": {"summary": "validate a BVH header and frame count", "configure": _configure_validate, "run": _run_validate, "render": _render_validate},
}
