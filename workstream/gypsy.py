#!/usr/bin/env python3
"""Gypsy Studio workstream CLI.

Phase 0 of docs/ADR-003-workstream-architecture.md: engine registry, tool discovery, capability
manifests, project manifests and the checks that keep them honest. It runs real binaries, records
what it finds, and never invents a capability.

Usage:
    python workstream/gypsy.py engines probe [--json] [--save]
    python workstream/gypsy.py engines smoke godot|unity [--json] [--keep]
    python workstream/gypsy.py tools probe [--json]
    python workstream/gypsy.py capabilities list|check [--json]
    python workstream/gypsy.py toolkit list|show|probe|capabilities [--json]
    python workstream/gypsy.py toolkit actionforge catalog|fetch [--json]
    python workstream/gypsy.py project init --path DIR --engine ID --version VER [--targets pc,mobile] [--force]
    python workstream/gypsy.py project show [--path DIR] [--json]
    python workstream/gypsy.py check [--project DIR] [--json]
"""
from __future__ import annotations

import argparse
import ctypes
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import toolkit as toolkit_spec

REPO_ROOT = Path(__file__).resolve().parents[1]
WS_DIR = Path(__file__).resolve().parent
CAP_DIR = WS_DIR / "capabilities"
STATE_DIR = WS_DIR / "state"
TOOLS_MANIFEST = Path(
    os.environ.get("GYPSY_TOOLS_MANIFEST")
    or (Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "GameTools" / "tools.json")
)

ADR_ENGINES = "docs/ADR-001-engines.md"
ADR_WORKSTREAM = "docs/ADR-003-workstream-architecture.md"

ENGINE_NAMES = {"godot": "Godot", "unity": "Unity", "ue5": "Unreal Engine 5", "flax": "Flax"}
ADAPTERS = {
    "godot": "godot-4",
    "unity": "unity-6",
    "ue5": "ue5-5.8",
    "flax": "flax-1.13",
}
REQUIREMENTS = {
    "godot": {"min_vram_gb": 0, "min_free_gb": 5, "disk": "C"},
    "unity": {"min_vram_gb": 2, "min_free_gb": 10, "disk": "C"},
    "ue5": {"min_vram_gb": 8, "min_free_gb": 60, "disk": "D"},
    "flax": {"min_vram_gb": 2, "min_free_gb": 5, "disk": "C"},
}
CAP_MATURITY = {"stable", "partial", "experimental", "planned", "blocked"}
CAP_REQUIRED = {
    "id", "layer", "kind", "maturity", "description",
    "requires", "inputs", "outputs", "checks", "provenance",
}


class GypsyError(RuntimeError):
    """A user-facing failure. The CLI prints it and exits non-zero."""


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def run(cmd, timeout: int = 30, cwd=None) -> dict:
    started = time.time()
    try:
        proc = subprocess.run(
            [str(c) for c in cmd],
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        return {
            "cmd": [str(c) for c in cmd],
            "exit": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "seconds": round(time.time() - started, 3),
        }
    except subprocess.TimeoutExpired:
        return {
            "cmd": [str(c) for c in cmd],
            "exit": None,
            "stdout": "",
            "stderr": "timeout",
            "seconds": round(time.time() - started, 3),
            "timeout": True,
        }
    except FileNotFoundError as exc:
        return {
            "cmd": [str(c) for c in cmd],
            "exit": None,
            "stdout": "",
            "stderr": f"not found: {exc}",
            "seconds": round(time.time() - started, 3),
            "missing": True,
        }


def first_version(text: str):
    match = re.search(r"(\d+\.\d+(?:\.\d+)?(?:[a-z]\d*)?)", text or "")
    return match.group(1) if match else None


def unique_paths(paths):
    seen = set()
    out = []
    for path in paths:
        if not path:
            continue
        resolved = Path(path)
        key = str(resolved).casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(resolved)
    return out


def _memory_gb():
    if platform.system() != "Windows":
        return None
    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]
    status = MEMORYSTATUSEX()
    status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
    try:
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
        return round(status.ullTotalPhys / (1024 ** 3), 1)
    except Exception:
        return None


def probe_hardware() -> dict:
    gpu = None
    nvidia = shutil.which("nvidia-smi")
    if not nvidia:
        candidate = Path("C:/Program Files/NVIDIA Corporation/NVSMI/nvidia-smi.exe")
        nvidia = str(candidate) if candidate.exists() else None
    if nvidia:
        result = run(
            [nvidia, "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader,nounits"],
            timeout=20,
        )
        if result["exit"] == 0 and result["stdout"].strip():
            parts = [p.strip() for p in result["stdout"].strip().splitlines()[0].split(",")]
            if len(parts) >= 3:
                gpu = {"name": parts[0], "vram_gb": round(float(parts[1]) / 1024, 1), "driver": parts[2]}
    disks = {}
    for drive in ("C", "D"):
        root = Path(f"{drive}:/")
        if not root.exists():
            continue
        try:
            usage = shutil.disk_usage(root)
            disks[drive] = {
                "free_gb": round(usage.free / (1024 ** 3), 1),
                "total_gb": round(usage.total / (1024 ** 3), 1),
            }
        except OSError:
            pass
    return {"os": platform.system(), "arch": platform.machine(), "ram_gb": _memory_gb(), "gpu": gpu, "disks": disks}


def hardware_gate(engine_id: str, hardware: dict) -> dict:
    req = REQUIREMENTS.get(engine_id, {})
    reasons = []
    vram = ((hardware.get("gpu") or {}).get("vram_gb"))
    if req.get("min_vram_gb") and (vram is None or vram < req["min_vram_gb"]):
        reasons.append(f"GPU VRAM {vram} GB is below the {req['min_vram_gb']} GB declared minimum")
    disk = req.get("disk", "C")
    free = (hardware.get("disks", {}).get(disk) or {}).get("free_gb")
    if req.get("min_free_gb") and (free is None or free < req["min_free_gb"]):
        reasons.append(f"{disk}: free space {free} GB is below the {req['min_free_gb']} GB declared minimum")
    return {"ok": not reasons, "reasons": reasons, "requirements": req}


def detect_godot():
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    candidates = []
    for name in ("godot", "godot4"):
        found = shutil.which(name)
        if found:
            candidates.append(Path(found))
    link = local / "Microsoft" / "WinGet" / "Links" / "godot.exe"
    if link.exists():
        candidates.append(link)
    for package in (local / "Microsoft" / "WinGet" / "Packages").glob("GodotEngine*"):
        for exe in package.glob("Godot_v*_win64.exe"):
            if "_console" not in exe.name:
                candidates.append(exe)
    candidates = unique_paths(candidates)
    if not candidates:
        return {"id": "godot", "name": "Godot", "installed": False, "usable": False, "notes": ["no Godot binary found"]}
    editor = candidates[0]
    console = editor.with_name(editor.stem + "_console.exe")
    cli = console if console.exists() else editor
    version_result = run([editor, "--version"], timeout=20)
    raw = (version_result["stdout"] or version_result["stderr"]).strip().splitlines()
    raw = raw[0] if raw else ""
    version = first_version(raw)
    templates_root = Path(os.environ.get("APPDATA", "")) / "Godot" / "export_templates"
    templates = sorted(p.name for p in templates_root.iterdir()) if templates_root.is_dir() else []
    return {
        "id": "godot",
        "name": "Godot",
        "installed": True,
        "usable": bool(version) and version_result["exit"] == 0,
        "version": version,
        "raw_version": raw,
        "editor": str(editor),
        "cli": str(cli),
        "export_templates": templates,
        "notes": [] if version_result["exit"] == 0 else ["--version failed: " + version_result["stderr"][:200]],
    }


def detect_unity():
    roots = [
        Path("C:/Program Files"),
        Path("C:/Program Files (x86)"),
        Path("D:/Program Files"),
        Path("D:/Unity"),
        Path("D:/Unity/Hub/Editor"),
    ]
    candidates = []
    for root in roots:
        if not root.exists():
            continue
        candidates.extend(root.glob("Unity*/Editor/Unity.exe"))
        candidates.extend(root.glob("Unity/Hub/Editor/*/Editor/Unity.exe"))
    candidates = unique_paths(candidates)
    if not candidates:
        return {"id": "unity", "name": "Unity", "installed": False, "usable": False, "notes": ["no Unity editor found"]}
    editor = candidates[0]
    folder = editor.parents[1]
    version = first_version(folder.name)
    license_files = [
        Path(os.environ.get("PROGRAMDATA", "C:/ProgramData")) / "Unity" / "Unity_lic.ulf",
        Path(os.environ.get("PROGRAMDATA", "C:/ProgramData")) / "Unity" / "Unity_lic.ulf",
    ]
    licensed = any(p.exists() for p in set(license_files))
    licence_note = "batchmode still needs activation; prove it before claiming builds"
    try:
        evidence = json.loads((STATE_DIR / "smoke-unity.json").read_text(encoding="utf-8"))
        if evidence.get("passed"):
            licensed = True
            licence_note = "batchmode smoke evidence: passed " + str(evidence.get("checkedAt", "?"))
    except (OSError, json.JSONDecodeError):
        pass
    return {
        "id": "unity",
        "name": "Unity",
        "installed": True,
        "usable": True,
        "version": version,
        "folder": str(folder),
        "editor": str(editor),
        "cli": str(editor),
        "licence": {"proven": licensed, "note": licence_note},
        "notes": [] if licensed else ["no licence file found; batchmode may refuse to run"],
    }


def detect_ue5():
    roots = [Path("D:/UnrealEngine"), Path("C:/Program Files/Epic Games"), Path("D:/Epic Games"), Path("E:/UnrealEngine")]
    candidates = []
    for root in roots:
        if not root.exists():
            continue
        for engine_dir in root.glob("UE_*"):
            exe = engine_dir / "Engine" / "Binaries" / "Win64" / "UnrealEditor-Cmd.exe"
            if exe.exists():
                candidates.append(exe)
    candidates = unique_paths(candidates)
    if not candidates:
        return {"id": "ue5", "name": "Unreal Engine 5", "installed": False, "usable": False, "notes": ["no editor binary found"]}
    cli = candidates[0]
    engine_dir = cli.parents[3]
    version_file = engine_dir / "Engine" / "Build" / "Build.version"
    version = None
    raw = None
    if version_file.exists():
        try:
            data = json.loads(version_file.read_text(encoding="utf-8-sig"))
            version = f"{data.get('MajorVersion')}.{data.get('MinorVersion')}.{data.get('PatchVersion')}"
            raw = f"CL-{data.get('Changelist')} {data.get('BranchName')}"
        except (OSError, json.JSONDecodeError, TypeError):
            pass
    if not version:
        version = first_version(engine_dir.name.replace("UE_", ""))
    return {
        "id": "ue5",
        "name": "Unreal Engine 5",
        "installed": True,
        "usable": bool(version),
        "version": version,
        "raw_version": raw,
        "editor": str(engine_dir / "Engine" / "Binaries" / "Win64" / "UnrealEditor.exe"),
        "cli": str(cli),
        "notes": [],
    }


def detect_flax():
    roots = [Path("C:/Program Files (x86)/Flax"), Path("C:/Program Files/Flax"), Path("D:/Flax")]
    candidates = []
    for root in roots:
        if root.exists():
            candidates.extend(root.glob("Flax_*/Binaries/Editor/Win64/Release/FlaxEditor.exe"))
    candidates = unique_paths(candidates)
    if not candidates:
        return {"id": "flax", "name": "Flax", "installed": False, "usable": False, "notes": ["no editor found"]}
    editor = candidates[0]
    version = first_version(editor.parents[4].name.replace("Flax_", "")) if len(editor.parents) > 4 else None
    build_tool = editor.parents[4] / "Binaries" / "Tools" / "Flax.Build.exe" if len(editor.parents) > 4 else None
    return {
        "id": "flax",
        "name": "Flax",
        "installed": True,
        "usable": bool(version),
        "version": version,
        "editor": str(editor),
        "cli": str(build_tool) if build_tool and build_tool.exists() else str(editor),
        "notes": ["experimental adapter; no headless build/run demonstrated"],
    }


def probe_engines() -> dict:
    hardware = probe_hardware()
    engines = {
        "godot": detect_godot(),
        "unity": detect_unity(),
        "ue5": detect_ue5(),
        "flax": detect_flax(),
    }
    for engine_id, record in engines.items():
        record["gate"] = hardware_gate(engine_id, hardware)
        record["requirements"] = REQUIREMENTS.get(engine_id, {})
        if not record["gate"]["ok"]:
            record["notes"].append("hardware gate: " + "; ".join(record["gate"]["reasons"]))
    stale = []
    try:
        import winreg

        key_path = r"SOFTWARE\EpicGames\Unreal Engine"
        for hive in (winreg.HKEY_LOCAL_MACHINE,):
            try:
                with winreg.OpenKey(hive, key_path) as key:
                    index = 0
                    while True:
                        try:
                            name = winreg.EnumKey(key, index)
                        except OSError:
                            break
                        index += 1
                        with winreg.OpenKey(key, name) as sub:
                            try:
                                install_dir = winreg.QueryValueEx(sub, "InstalledDirectory")[0]
                            except OSError:
                                install_dir = ""
                        if install_dir and not Path(install_dir).exists():
                            stale.append({"source": f"HKLM/{key_path}/{name}", "path": install_dir, "reason": "directory missing"})
            except OSError:
                pass
    except ImportError:
        pass
    return {"generated": now_iso(), "machine": hardware, "engines": engines, "staleRegistry": stale}


def load_tools() -> dict:
    if not TOOLS_MANIFEST.exists():
        return {"manifest": str(TOOLS_MANIFEST), "exists": False, "tools": [], "missing": [], "errors": ["tools manifest not found"]}
    try:
        data = json.loads(TOOLS_MANIFEST.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"manifest": str(TOOLS_MANIFEST), "exists": True, "tools": [], "missing": [], "errors": [f"unreadable: {exc}"]}
    tools = data if isinstance(data, list) else data.get("tools", [])
    missing = []
    for tool in tools:
        path = tool.get("path")
        if not path or not Path(path).exists():
            missing.append({"name": tool.get("name"), "path": path})
    return {"manifest": str(TOOLS_MANIFEST), "exists": True, "tools": tools, "missing": missing, "errors": []}


def load_capabilities() -> list:
    capabilities = []
    if not CAP_DIR.is_dir():
        return capabilities
    for path in sorted(CAP_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            raise GypsyError(f"capability {path.name} is not valid JSON: {exc}") from exc
        data["_file"] = path.name
        capabilities.append(data)
    return capabilities


def validate_capabilities(capabilities=None) -> list:
    errors = []
    capabilities = capabilities if capabilities is not None else load_capabilities()
    seen = set()
    for cap in capabilities:
        name = cap.get("_file", cap.get("id", "?"))
        missing = CAP_REQUIRED - set(cap)
        if missing:
            errors.append(f"{name}: missing fields {sorted(missing)}")
        if cap.get("id") in seen:
            errors.append(f"{name}: duplicate id {cap.get('id')}")
        seen.add(cap.get("id"))
        if cap.get("maturity") not in CAP_MATURITY:
            errors.append(f"{name}: maturity {cap.get('maturity')!r} not in {sorted(CAP_MATURITY)}")
        if cap.get("layer") == "engine" and cap.get("engine") not in ENGINE_NAMES:
            errors.append(f"{name}: unknown engine {cap.get('engine')!r}")
        for field in ("requires", "inputs", "outputs", "checks"):
            if not isinstance(cap.get(field), (list, dict)):
                errors.append(f"{name}: {field} must be a list or object")
    return errors


def adapter_for(engine_id: str) -> str:
    if engine_id not in ADAPTERS:
        raise GypsyError(f"unknown engine {engine_id!r}; choose one of {sorted(ADAPTERS)}")
    return ADAPTERS[engine_id]


def version_matches(requested: str, detected: str) -> bool:
    if not requested or not detected:
        return False
    requested = requested.strip()
    detected = detected.strip()
    if requested == detected:
        return True
    return requested.startswith(detected) or detected.startswith(requested)


def init_project(path: Path, engine_id: str, version: str, targets, force: bool = False) -> dict:
    adapter = adapter_for(engine_id)
    probe = probe_engines()
    record = probe["engines"][engine_id]
    if not record.get("installed"):
        raise GypsyError(f"{engine_id} is not installed")
    if not record.get("usable"):
        raise GypsyError(f"{engine_id} is installed but not usable: {'; '.join(record.get('notes', []))}")
    if engine_id == "unity" and not (record.get("licence") or {}).get("proven") and not force:
        raise GypsyError("Unity licence is not proven; activate Unity before creating a Unity project (or pass --force)")
    if not version_matches(version, record.get("version")):
        raise GypsyError(f"{engine_id} version {record.get('version')} is installed, not {version}")
    gate = record.get("gate") or {"ok": True, "reasons": []}
    if not gate["ok"] and not force:
        raise GypsyError("hardware gate failed: " + "; ".join(gate["reasons"]) + " (pass --force to override)")
    target_dir = Path(path).expanduser().resolve()
    manifest_path = target_dir / "project.gypsy.json"
    if target_dir.exists() and any(target_dir.iterdir()) and not force:
        raise GypsyError(f"{target_dir} is not empty; choose an empty directory or pass --force")
    target_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema": "gypsy.project/v1",
        "name": target_dir.name,
        "engine": {"id": engine_id, "version": record.get("version"), "adapter": adapter},
        "targets": targets,
        "paths": {"game": "game", "artifacts": "artifacts"},
        "created": now_iso(),
        "hardware": probe["machine"],
        "hardwareGate": gate,
        "decisions": [
            {
                "date": now_iso(),
                "decision": f"engine {engine_id} {record.get('version')} ({adapter})",
                "reason": "operator selected the engine when creating the project",
            }
        ],
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return {"manifest": str(manifest_path), "project": manifest}


def show_project(path: Path) -> dict:
    manifest_path = Path(path).expanduser().resolve() / "project.gypsy.json"
    if not manifest_path.exists():
        raise GypsyError(f"no project.gypsy.json in {manifest_path.parent}")
    return json.loads(manifest_path.read_text(encoding="utf-8-sig"))


def smoke_godot(keep: bool = False) -> dict:
    record = detect_godot()
    if not record.get("installed") or not record.get("usable"):
        raise GypsyError("Godot is not installed/usable")
    temp = Path(tempfile.mkdtemp(prefix="gypsy-godot-smoke-"))
    try:
        (temp / "project.godot").write_text(
            'config_version=5\n\n[application]\n\nconfig/name="Gypsy Smoke"\nrun/main_scene="res://main.tscn"\n\n'
            '[rendering]\n\nrenderer/rendering_method="gl_compatibility"\n',
            encoding="utf-8",
        )
        (temp / "main.tscn").write_text(
            '[gd_scene load_steps=2 format=3]\n\n[ext_resource type="Script" path="res://main.gd" id="1"]\n\n'
            '[node name="Main" type="Node"]\nscript = ExtResource("1")\n',
            encoding="utf-8",
        )
        (temp / "main.gd").write_text(
            'extends Node\n\n'
            'func _ready() -> void:\n'
            '\tprint("GYPSY_SMOKE_OK engine=godot version=" + str(Engine.get_version_info().get("string", "?")))\n'
            '\tawait get_tree().process_frame\n'
            '\tget_tree().quit(0)\n',
            encoding="utf-8",
        )
        result = run([record["cli"], "--headless", "--path", str(temp)], timeout=90, cwd=temp)
        marker = "GYPSY_SMOKE_OK" in (result["stdout"] + result["stderr"])
        passed = result["exit"] == 0 and marker
        evidence = {
            "engine": "godot",
            "version": record.get("version"),
            "exit": result["exit"],
            "seconds": result["seconds"],
            "marker": marker,
            "stdout": result["stdout"][-2000:],
            "stderr": result["stderr"][-2000:],
            "exportTemplates": record.get("export_templates", []),
            "tempDir": str(temp) if keep else None,
            "passed": passed,
        }
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        (STATE_DIR / "smoke-godot.json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
        if not passed:
            raise GypsyError("Godot smoke failed: " + json.dumps(evidence, indent=2)[:2000])
        return evidence
    finally:
        if not keep:
            shutil.rmtree(temp, ignore_errors=True)


def smoke_unity(keep: bool = False) -> dict:
    record = detect_unity()
    if not record.get("installed"):
        raise GypsyError("Unity is not installed")
    temp = Path(tempfile.mkdtemp(prefix="gypsy-unity-smoke-"))
    try:
        (temp / "Assets" / "Editor").mkdir(parents=True)
        (temp / "ProjectSettings").mkdir(parents=True)
        (temp / "ProjectSettings" / "ProjectVersion.txt").write_text(
            "m_EditorVersion: " + str(record.get("version")) + "\n", encoding="utf-8"
        )
        (temp / "Assets" / "Editor" / "GypsySmoke.cs").write_text(
            "using UnityEditor;\nusing UnityEngine;\n\npublic static class GypsySmoke\n{\n"
            "    public static void Run()\n    {\n"
            "        Debug.Log(\"GYPSY_UNITY_SMOKE_OK version=\" + Application.unityVersion);\n"
            "        EditorApplication.Exit(0);\n    }\n}\n",
            encoding="utf-8",
        )
        log_path = temp / "unity.log"
        result = run(
            [record["cli"], "-batchmode", "-quit", "-nographics", "-projectPath", str(temp),
             "-executeMethod", "GypsySmoke.Run", "-logFile", str(log_path)],
            timeout=300,
            cwd=temp,
        )
        log_text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
        combined = result["stdout"] + "\n" + result["stderr"] + "\n" + log_text
        marker = "GYPSY_UNITY_SMOKE_OK" in combined
        licensed = "Exiting batchmode successfully" in combined or result["exit"] == 0
        evidence = {
            "engine": "unity",
            "version": record.get("version"),
            "checkedAt": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            "exit": result["exit"],
            "seconds": result["seconds"],
            "marker": marker,
            "licence": licensed,
            "stdout": result["stdout"][-3000:],
            "stderr": result["stderr"][-3000:],
            "logTail": log_text[-5000:],
            "tempDir": str(temp) if keep else None,
            "passed": result["exit"] == 0 and marker,
        }
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        (STATE_DIR / "smoke-unity.json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
        if not evidence["passed"]:
            raise GypsyError("Unity smoke failed: " + json.dumps(evidence, indent=2)[:2500])
        return evidence
    finally:
        if not keep:
            shutil.rmtree(temp, ignore_errors=True)


def check_all(project_path=None) -> dict:
    errors = []
    warnings = []
    capabilities = load_capabilities()
    errors.extend(validate_capabilities(capabilities))
    errors.extend(toolkit_spec.registry_errors())
    engines = probe_engines()
    if not engines["engines"]["godot"].get("usable"):
        errors.append("Godot is not usable; the reference adapter cannot run")
    for engine_id, record in engines["engines"].items():
        if not record.get("installed"):
            warnings.append(f"{engine_id}: not installed")
        elif not record.get("usable"):
            warnings.append(f"{engine_id}: installed but not usable")
        if record.get("installed") and not record.get("gate", {}).get("ok"):
            warnings.append(f"{engine_id}: hardware gate failed: {'; '.join(record['gate']['reasons'])}")
    tools = load_tools()
    errors.extend(tools.get("errors", []))
    for missing in tools.get("missing", []):
        errors.append(f"tool missing: {missing.get('name')} -> {missing.get('path')}")
    if engines.get("staleRegistry"):
        warnings.append(f"{len(engines['staleRegistry'])} stale engine registry entries ignored")
    project = None
    candidate = Path(project_path) if project_path else REPO_ROOT
    manifest_path = Path(candidate).expanduser().resolve() / "project.gypsy.json"
    if manifest_path.exists():
        try:
            project = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"project manifest unreadable: {exc}")
    if project:
        engine_id = (project.get("engine") or {}).get("id")
        if engine_id not in ENGINE_NAMES:
            errors.append(f"project engine {engine_id!r} is unknown")
        else:
            record = engines["engines"][engine_id]
            if not version_matches((project.get("engine") or {}).get("version"), record.get("version")):
                errors.append(f"project pins {project['engine'].get('version')} but {record.get('version')} is installed")
            if not (project.get("targets") or []):
                errors.append("project has no targets")
    return {
        "generated": now_iso(),
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "capabilities": len(capabilities),
        "engines": {k: {"installed": v.get("installed"), "usable": v.get("usable"), "version": v.get("version")} for k, v in engines["engines"].items()},
        "tools": {"manifest": tools.get("manifest"), "count": len(tools.get("tools", [])), "missing": len(tools.get("missing", []))},
        "project": project.get("name") if project else None,
    }


def print_human_toolkits(rows):
    print(f"toolkits: {len(rows)}")
    for row in rows:
        print(f"{row['id']:16} {row['status']:12} {row['kind']:16} {row['license']}")
        print(f"  {row['summary']}")
        print(f"  capability: {row['capability']} | home: {row['home']} | plugin: {row['plugin']}")


def print_human_toolkit(data):
    print(f"{data.get('id')} - {data.get('name')}")
    print(f"status: {data.get('status')} | licence: {data.get('license')}")
    print(f"kind: {data.get('kind')} | capability: {data.get('capability')}")
    print(f"home: {data.get('home')}")
    if data.get("docs"):
        print(f"docs: {data['docs']}")
    print(f"summary: {data.get('summary')}")
    if data.get("source"):
        for name, value in data["source"].items():
            print(f"source.{name}: {value}")
    if data.get("commands"):
        print("commands: " + ", ".join(data["commands"]))
    clips = data.get("catalog") or []
    if clips:
        print(f"catalog: {len(clips)} curated clips")
        for clip in clips:
            print(f"  {clip.get('id', '?'):24} {clip.get('category', ''):16} {clip.get('description', '')}")
    for note in data.get("notes") or []:
        print(f"note: {note}")


def print_human_toolkit_caps(rows):
    print(f"toolkit capabilities: {len(rows)}")
    for row in rows:
        print(f"{row['toolkit']:16} {row['capability']:28} {str(row['maturity'] or '-'):12} {row['manifest']}")
        if row.get("error"):
            print(f"  ERROR {row['error']}")


def print_human_engines(probe: dict):
    print(f"machine: {probe['machine'].get('os')} {probe['machine'].get('arch')} | RAM {probe['machine'].get('ram_gb')} GB")
    gpu = probe["machine"].get("gpu")
    if gpu:
        print(f"gpu: {gpu['name']} | {gpu['vram_gb']} GB VRAM | driver {gpu['driver']}")
    for drive, info in probe["machine"].get("disks", {}).items():
        print(f"disk {drive}: {info['free_gb']} GB free of {info['total_gb']} GB")
    print()
    for engine_id, record in probe["engines"].items():
        state = "usable" if record.get("usable") else ("installed, NOT usable" if record.get("installed") else "not installed")
        gate = "gate ok" if record.get("gate", {}).get("ok") else "GATE FAILED: " + "; ".join(record["gate"]["reasons"])
        print(f"{record.get('name','?'):18} {record.get('version') or '-':12} {state:22} {gate}")
        for key in ("editor", "cli"):
            if record.get(key):
                print(f"  {key}: {record[key]}")
        for note in record.get("notes", []):
            print(f"  note: {note}")
    if probe.get("staleRegistry"):
        print("\nstale registry entries ignored:")
        for item in probe["staleRegistry"]:
            print(f"  {item['source']} -> {item['path']} ({item['reason']})")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="gypsy", description="Gypsy Studio workstream CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    engines = sub.add_parser("engines", help="engine registry")
    engines_sub = engines.add_subparsers(dest="engines_command", required=True)
    probe_parser = engines_sub.add_parser("probe", help="detect installed engines")
    probe_parser.add_argument("--json", action="store_true")
    probe_parser.add_argument("--save", action="store_true")
    smoke_parser = engines_sub.add_parser("smoke", help="run an engine smoke test")
    smoke_parser.add_argument("engine", choices=["godot", "unity"])
    smoke_parser.add_argument("--json", action="store_true")
    smoke_parser.add_argument("--keep", action="store_true")

    tools_parser = sub.add_parser("tools", help="installed tool discovery")
    tools_sub = tools_parser.add_subparsers(dest="tools_command", required=True)
    tools_probe = tools_sub.add_parser("probe")
    tools_probe.add_argument("--json", action="store_true")

    cap_parser = sub.add_parser("capabilities", help="capability manifests")
    cap_sub = cap_parser.add_subparsers(dest="cap_command", required=True)
    cap_list = cap_sub.add_parser("list")
    cap_list.add_argument("--json", action="store_true")
    cap_check = cap_sub.add_parser("check")
    cap_check.add_argument("--json", action="store_true")

    toolkit_parser = sub.add_parser("toolkit", help="registered reusable toolkit plugins")
    toolkit_sub = toolkit_parser.add_subparsers(dest="toolkit_command", required=True)
    toolkit_list = toolkit_sub.add_parser("list", help="list registered toolkits")
    toolkit_list.add_argument("--json", action="store_true")
    toolkit_show = toolkit_sub.add_parser("show", help="show one toolkit and its catalog")
    toolkit_show.add_argument("toolkit_id")
    toolkit_show.add_argument("--json", action="store_true")
    toolkit_probe = toolkit_sub.add_parser("probe", help="probe a toolkit's source honestly")
    toolkit_probe.add_argument("toolkit_id")
    toolkit_probe.add_argument("--timeout", type=float, default=10.0)
    toolkit_probe.add_argument("--json", action="store_true")
    toolkit_caps = toolkit_sub.add_parser("capabilities", help="list toolkit capability manifests")
    toolkit_caps.add_argument("--json", action="store_true")
    toolkit_registry_error = None
    try:
        registered_toolkits = toolkit_spec.discover()
    except toolkit_spec.ToolkitError as exc:
        toolkit_registry_error = str(exc)
        registered_toolkits = {}
    for toolkit_id, registered in sorted(registered_toolkits.items()):
        plugin_parser = toolkit_sub.add_parser(toolkit_id, help=registered.summary)
        plugin_sub = plugin_parser.add_subparsers(dest="toolkit_action", required=True)
        for verb, command in sorted(registered.commands.items()):
            command_parser = plugin_sub.add_parser(verb, help=command["summary"])
            command["configure"](command_parser)
            command_parser.add_argument("--json", action="store_true")

    project = sub.add_parser("project", help="project manifest")
    project_sub = project.add_subparsers(dest="project_command", required=True)
    project_init = project_sub.add_parser("init")
    project_init.add_argument("--path", required=True)
    project_init.add_argument("--engine", required=True, choices=sorted(ENGINE_NAMES))
    project_init.add_argument("--version", required=True)
    project_init.add_argument("--targets", default="pc", help="comma list, e.g. pc,mobile")
    project_init.add_argument("--force", action="store_true")
    project_init.add_argument("--json", action="store_true")
    project_show = project_sub.add_parser("show")
    project_show.add_argument("--path", default=".")
    project_show.add_argument("--json", action="store_true")

    game_parser = sub.add_parser("game", help="vertical-slice adapter")
    game_sub = game_parser.add_subparsers(dest="game_command", required=True)
    for name in ("demo", "build", "capture", "verify", "bench"):
        game_cmd = game_sub.add_parser(name)
        game_cmd.add_argument("--path", default=str(REPO_ROOT / "game"))
        game_cmd.add_argument("--json", action="store_true")
        if name == "build":
            game_cmd.add_argument("--preset", default="Windows Desktop")
            game_cmd.add_argument("--out", default=None)
        if name == "bench":
            game_cmd.add_argument("--runs", type=int, default=3)
    slices_parser = sub.add_parser("slices", help="manifest-driven Phase-2 orchestrator")
    slices_sub = slices_parser.add_subparsers(dest="slices_command", required=True)
    for name in ("list", "plan", "run", "status"):
        slices_cmd = slices_sub.add_parser(name)
        slices_cmd.add_argument("--dir", default="slices", help="slice manifest directory")
        slices_cmd.add_argument("--state-dir", default=None)
        slices_cmd.add_argument("--json", action="store_true")
        if name == "plan":
            slices_cmd.add_argument("slice_id")
        if name == "run":
            slices_cmd.add_argument("slice_ids", nargs="*")
            slices_cmd.add_argument("--all", action="store_true")
            slices_cmd.add_argument("--resume", action="store_true")
            slices_cmd.add_argument("--force", action="store_true")
        if name == "status":
            slices_cmd.add_argument("slice_id", nargs="?")

    toolpacks_parser = sub.add_parser("toolpacks", help="Phase-3 toolpack manifests")
    toolpacks_sub = toolpacks_parser.add_subparsers(dest="toolpacks_command", required=True)
    for name in ("list", "check", "run"):
        toolpack_cmd = toolpacks_sub.add_parser(name)
        toolpack_cmd.add_argument("--dir", default="toolpacks")
        toolpack_cmd.add_argument("--state-dir", default=None)
        toolpack_cmd.add_argument("--json", action="store_true")
        if name == "run":
            toolpack_cmd.add_argument("toolpack_id")
            toolpack_cmd.add_argument("--action", default=None)

    console_parser = sub.add_parser("console", help="read-only Phase-4 terminal console")
    console_sub = console_parser.add_subparsers(dest="console_command", required=True)
    console_board = console_sub.add_parser("board")
    console_board.add_argument("--state-dir", default=None)
    console_board.add_argument("--json", action="store_true")
    console_preview = console_sub.add_parser("preview")
    console_preview.add_argument("path")
    console_preview.add_argument("--json", action="store_true")
    console_diff = console_sub.add_parser("diff")
    console_diff.add_argument("--staged", action="store_true")
    console_diff.add_argument("--commit", default=None)
    console_diff.add_argument("--json", action="store_true")

    live_parser = sub.add_parser("live", help="Phase-5 live-iteration watcher")
    live_parser.add_argument("--paths", action="append", default=None)
    live_parser.add_argument("--interval", type=float, default=0.5)
    live_parser.add_argument("--debounce", type=float, default=0.0)
    live_parser.add_argument("--iterations", type=int, default=None)
    live_parser.add_argument("--once", action="store_true")
    live_parser.add_argument("--command", dest="live_command", choices=["demo", "verify"], default="demo")
    live_parser.add_argument("--json", action="store_true")

    dashboard_parser = sub.add_parser("dashboard", help="local-only Phase-4 GUI control panel")
    dashboard_parser.add_argument("--port", type=int, default=8765)
    dashboard_parser.add_argument("--no-open", action="store_true")

    check_parser = sub.add_parser("check", help="run the Phase-0 checks")
    check_parser.add_argument("--project")
    check_parser.add_argument("--json", action="store_true")
    sub.add_parser("version", help="print version")

    args = parser.parse_args(argv)
    try:
        if args.command == "engines":
            if args.engines_command == "probe":
                probe = probe_engines()
                if args.save:
                    STATE_DIR.mkdir(parents=True, exist_ok=True)
                    (STATE_DIR / "engines.json").write_text(json.dumps(probe, indent=2) + "\n", encoding="utf-8")
                if args.json:
                    print(json.dumps(probe, indent=2))
                else:
                    print_human_engines(probe)
                return 0 if probe["engines"]["godot"].get("usable") else 1
            if args.engines_command == "smoke":
                if args.engine == "unity":
                    evidence = smoke_unity(keep=args.keep)
                    if args.json:
                        print(json.dumps(evidence, indent=2))
                    else:
                        print(f"PASS unity smoke | exit {evidence['exit']} | {evidence['seconds']}s | marker={evidence['marker']}")
                        print(f"licence: {'proven' if evidence.get('licence') else 'not proven'}")
                    return 0
                evidence = smoke_godot(keep=args.keep)
                if args.json:
                    print(json.dumps(evidence, indent=2))
                else:
                    print(f"PASS godot smoke | exit {evidence['exit']} | {evidence['seconds']}s | marker={evidence['marker']}")
                    print(f"export templates: {evidence['exportTemplates'] or 'none installed'}")
                return 0
        if args.command == "tools":
            data = load_tools()
            if args.json:
                print(json.dumps(data, indent=2))
            else:
                print(f"manifest: {data['manifest']} (exists={data['exists']})")
                for tool in data["tools"]:
                    print(f"  {tool.get('name','?'):16} {str(tool.get('version','-')):10} {tool.get('path','')}")
                for missing in data.get("missing", []):
                    print(f"  MISSING {missing.get('name')} -> {missing.get('path')}")
            return 0 if data["exists"] and not data.get("missing") else 1
        if args.command == "capabilities":
            capabilities = load_capabilities()
            if args.cap_command == "list":
                if args.json:
                    print(json.dumps(capabilities, indent=2))
                else:
                    for cap in capabilities:
                        print(f"{cap.get('id','?'):34} {cap.get('layer','?'):12} {cap.get('maturity','?'):12} {cap.get('kind','?'):10}")
            else:
                errors = validate_capabilities(capabilities)
                if args.json:
                    print(json.dumps({"passed": not errors, "errors": errors, "count": len(capabilities)}, indent=2))
                else:
                    for error in errors:
                        print("ERROR", error)
                    print(f"capabilities: {len(capabilities)} | errors: {len(errors)}")
                return 0 if not errors else 1
            return 0
        if args.command == "toolkit":
            if toolkit_registry_error:
                raise GypsyError("toolkit registry is invalid: " + toolkit_registry_error)
            if args.toolkit_command == "list":
                rows = [
                    registered.info()
                    for registered in sorted(registered_toolkits.values(), key=lambda item: item.id)
                ]
                if args.json:
                    print(json.dumps(rows, indent=2))
                else:
                    print_human_toolkits(rows)
                return 0
            if args.toolkit_command == "capabilities":
                rows = toolkit_spec.capability_rows(registered_toolkits)
                visible = [{key: value for key, value in row.items() if key != "data"} for row in rows]
                if args.json:
                    print(json.dumps(visible, indent=2))
                else:
                    print_human_toolkit_caps(visible)
                return 0
            if args.toolkit_command in ("show", "probe"):
                toolkit_id = args.toolkit_id
                if toolkit_id not in registered_toolkits:
                    raise GypsyError(
                        f"unknown toolkit {toolkit_id!r}; have: {', '.join(sorted(registered_toolkits))}"
                    )
                registered = registered_toolkits[toolkit_id]
                if args.toolkit_command == "show":
                    data = toolkit_spec.describe_toolkit(registered)
                    if args.json:
                        print(json.dumps(data, indent=2))
                    else:
                        print_human_toolkit(data)
                    return 0
                payload = dict(registered.module.probe(timeout=args.timeout))
                payload.setdefault("toolkit", toolkit_id)
                if args.json:
                    print(json.dumps(payload, indent=2))
                else:
                    state = "reachable" if payload.get("reachable") else "UNREACHABLE"
                    print(f"{toolkit_id} probe: {state}")
                    print(f"url: {payload.get('url')}")
                    print(f"method: {payload.get('method')} | status: {payload.get('status')}")
                    print(f"checked: {payload.get('checkedAt')}")
                    if payload.get("error"):
                        print(f"error: {payload['error']}")
                    for note in payload.get("notes") or []:
                        print(f"note: {note}")
                return 0 if payload.get("reachable") else 1
            registered = registered_toolkits[args.toolkit_command]
            command = registered.commands[args.toolkit_action]
            exit_code, payload = command["run"](args)
            print(json.dumps(payload, indent=2) if args.json else command["render"](payload))
            return exit_code
        if args.command == "project":
            if args.project_command == "init":
                targets = [t.strip() for t in args.targets.split(",") if t.strip()]
                result = init_project(Path(args.path), args.engine, args.version, targets, force=args.force)
                if args.json:
                    print(json.dumps(result, indent=2))
                else:
                    print(f"project manifest written: {result['manifest']}")
                    print(f"engine: {result['project']['engine']['id']} {result['project']['engine']['version']} ({result['project']['engine']['adapter']})")
                    print(f"targets: {', '.join(result['project']['targets'])}")
                return 0
            if args.project_command == "show":
                project = show_project(Path(args.path))
                if args.json:
                    print(json.dumps(project, indent=2))
                else:
                    engine = project.get("engine", {})
                    print(f"{project.get('name')} | {engine.get('id')} {engine.get('version')} ({engine.get('adapter')})")
                    print(f"targets: {', '.join(project.get('targets', []))}")
                    print(f"created: {project.get('created')}")
                return 0
        if args.command == "game":
            from game import benchmark as game_benchmark, build as game_build, capture as game_capture, demo as game_demo, verify as game_verify

            if args.game_command == "demo":
                evidence = game_demo(Path(args.path))
                print(json.dumps(evidence, indent=2) if args.json else f"PASS game demo | {evidence['marker']} | {evidence['seconds']}s")
                return 0
            if args.game_command == "build":
                evidence = game_build(Path(args.path), preset=args.preset, output=Path(args.out) if args.out else None)
                print(json.dumps(evidence, indent=2) if args.json else f"PASS game build | {evidence['output']} | {evidence['bytes']} bytes")
                return 0
            if args.game_command == "capture":
                evidence = game_capture(Path(args.path))
                print(json.dumps(evidence, indent=2) if args.json else f"PASS game capture | {evidence['movie']}")
                return 0
            if args.game_command == "verify":
                evidence = game_verify(Path(args.path))
                print(json.dumps(evidence, indent=2) if args.json else f"game verify | demo={evidence['demo']['passed']} build={evidence['build']['passed']} capture={evidence['capturePassed']}")
                return 0 if evidence["passed"] else 1
            if args.game_command == "bench":
                evidence = game_benchmark(args.runs, Path(args.path))
                print(json.dumps(evidence, indent=2) if args.json else f"game bench | median={evidence['medianSeconds']}s p95={evidence['p95Seconds']}s gpu={evidence['captureGpuMsPerFrame']}ms | passed={evidence['passed']}")
                return 0 if evidence["passed"] else 1
        if args.command == "live":
            import live as live_mod
            from game import demo as game_demo, verify as game_verify

            runner = (lambda: game_verify(Path("game"))) if args.live_command == "verify" else (lambda: game_demo(Path("game")))
            if args.once:
                result = runner()
                print(json.dumps(result, indent=2) if args.json else f"live run once: ok ({result.get('seconds', '?')}s)")
                return 0 if result.get("passed") else 1
            summary = live_mod.watch(args.paths or ["game"], runner=runner, iterations=args.iterations, interval=args.interval, debounce=args.debounce)
            print(json.dumps(summary, indent=2) if args.json else f"live: {summary['iterations']} change(s), {summary['runs']} run(s), {len(summary['errors'])} error(s)")
            return 0 if not summary["errors"] else 1

        if args.command == "dashboard":
            from dashboard import serve
            return serve(args.port, not args.no_open)

        if args.command == "console":
            import console as console_mod
            from pathlib import Path as _Path

            if args.console_command == "board":
                state_dir = _Path(args.state_dir) if args.state_dir else STATE_DIR
                data = console_mod.collect_board(state_dir, REPO_ROOT)
                print(json.dumps(data, indent=2) if args.json else console_mod.render_board(data))
                return 0 if data.get("slices") else 1
            if args.console_command == "preview":
                data = console_mod.preview_artifact(_Path(args.path), REPO_ROOT)
                print(json.dumps(data, indent=2) if args.json else console_mod.render_preview(data))
                return 0 if data.get("exists") else 1
            if args.console_command == "diff":
                data = console_mod.diff_report(REPO_ROOT, staged=args.staged, commit=args.commit)
                print(json.dumps(data, indent=2) if args.json else console_mod.render_diff(data))
                return 0 if data.get("available") else 1

        if args.command == "toolpacks":
            import toolpacks as toolpack_spec
            from pathlib import Path as _Path

            manifests = toolpack_spec.load_all(_Path(args.dir))
            state_dir = _Path(args.state_dir) if args.state_dir else STATE_DIR
            if args.toolpacks_command == "list":
                data = {
                    toolpack_id: {
                        "name": manifest.get("name"),
                        "actions": [action["id"] for action in manifest.get("actions", [])],
                        "validators": [validator["id"] for validator in manifest.get("validators", [])],
                        "tools": manifest.get("tools", []),
                    }
                    for toolpack_id, manifest in manifests.items()
                }
                if args.json:
                    print(json.dumps(data, indent=2))
                else:
                    for toolpack_id, info in data.items():
                        print(f"{toolpack_id}: {info['name']} (actions: {', '.join(info['actions'])})")
                return 0
            if args.toolpacks_command == "check":
                problems = {}
                for toolpack_id, manifest in manifests.items():
                    errors = toolpack_spec.validate_manifest(manifest)
                    if errors:
                        problems[toolpack_id] = errors
                payload = {"toolpacks": len(manifests), "errors": problems}
                if args.json:
                    print(json.dumps(payload, indent=2))
                else:
                    if problems:
                        for toolpack_id, errors in problems.items():
                            print(f"FAIL {toolpack_id}: " + "; ".join(errors))
                    else:
                        print(f"toolpacks: {len(manifests)} valid")
                return 1 if problems else 0
            if args.toolpacks_command == "run":
                if args.toolpack_id not in manifests:
                    raise GypsyError(f"unknown toolpack {args.toolpack_id!r}; have: {', '.join(manifests)}")
                manifest = manifests[args.toolpack_id]
                if args.action:
                    result = toolpack_spec.run_action(manifest, args.action, project_root=REPO_ROOT, state_dir=state_dir)
                else:
                    result = toolpack_spec.run_toolpack(manifest, project_root=REPO_ROOT, state_dir=state_dir)
                if args.json:
                    print(json.dumps(result, indent=2))
                else:
                    print(f"toolpack {result.get('toolpack')}: passed={result.get('passed')} artifacts={len(result.get('artifacts', []))} state={result.get('statePath')}")
                    for error in result.get("errors", []):
                        print(f"  ERROR {error}")
                return 0 if result.get("passed") else 1

        if args.command == "slices":
            from pathlib import Path as _Path

            import slices as slice_spec
            from orchestrator import run_slice, run_task

            manifest_dir = _Path(args.dir)
            state_dir = _Path(args.state_dir) if args.state_dir else STATE_DIR
            manifests = slice_spec.load_all(manifest_dir)
            if args.slices_command == "list":
                data = {
                    slice_id: {
                        "description": manifest.get("description", ""),
                        "project": manifest.get("project", "."),
                        "steps": [step["id"] for step in manifest.get("steps", [])],
                        "artifacts": manifest.get("artifacts", []),
                    }
                    for slice_id, manifest in manifests.items()
                }
                if args.json:
                    print(json.dumps(data, indent=2))
                else:
                    for slice_id, info in data.items():
                        print(f"{slice_id}: {info['description']} (steps: {', '.join(info['steps'])})")
                return 0
            if args.slices_command == "plan":
                if args.slice_id not in manifests:
                    raise GypsyError(f"unknown slice {args.slice_id!r}; have: {', '.join(manifests)}")
                manifest = manifests[args.slice_id]
                errors = slice_spec.validate_manifest(manifest)
                if errors:
                    raise GypsyError("; ".join(errors))
                order = slice_spec.resolve_order(manifest)
                data = {"slice": args.slice_id, "order": order, "manifest": manifest}
                if args.json:
                    print(json.dumps(data, indent=2))
                else:
                    print(f"{args.slice_id}: " + " -> ".join(order))
                    print(f"artifacts: {', '.join(manifest.get('artifacts', [])) or 'none'}")
                return 0
            if args.slices_command == "run":
                ids = list(manifests) if args.all else list(args.slice_ids)
                if not ids:
                    raise GypsyError("pass one or more slice ids, or --all")
                missing = [slice_id for slice_id in ids if slice_id not in manifests]
                if missing:
                    raise GypsyError(f"unknown slice(s): {', '.join(missing)}")
                if len(ids) == 1 and (args.force or manifests[ids[0]].get("project")):
                    # run_slice supports force; a task does not need it (default is a clean rerun).
                    result = run_slice(manifests[ids[0]], project_root=REPO_ROOT, state_dir=state_dir, resume=args.resume, force=args.force if len(ids) == 1 else False)
                else:
                    result = run_task([manifests[slice_id] for slice_id in ids], project_root=REPO_ROOT, state_dir=state_dir, resume=args.resume, force=args.force)
                if args.json:
                    print(json.dumps(result, indent=2))
                else:
                    if result.get("schema", "").endswith("task-state/v1"):
                        print(f"task {result.get('task')}: passed={result.get('passed')} slices={len(result.get('slices', []))} artifacts={len(result.get('artifacts', []))}")
                        for summary in result.get("slices", []):
                            print(f"  {summary['slice']}: {summary['status']}")
                    else:
                        print(f"slice {result.get('slice')}: passed={result.get('passed')} steps={len(result.get('steps', []))} artifacts={len(result.get('artifacts', []))}")
                    if result.get("errors"):
                        for error in result["errors"]:
                            print(f"  ERROR {error}")
                return 0 if result.get("passed") else 1
            if args.slices_command == "status":
                import os as _os
                state_root = state_dir / "slices"
                if args.slice_id:
                    path = state_root / f"{args.slice_id}.json"
                    if not path.exists():
                        raise GypsyError(f"no state for slice {args.slice_id!r} at {path}")
                    data = json.loads(path.read_text(encoding="utf-8"))
                else:
                    tasks = sorted(state_root.glob("task-*.json"), key=lambda item: item.stat().st_mtime)
                    if not tasks:
                        raise GypsyError(f"no task state under {state_root}")
                    data = json.loads(tasks[-1].read_text(encoding="utf-8"))
                if args.json:
                    print(json.dumps(data, indent=2))
                else:
                    print(f"{data.get('schema')} {data.get('task') or data.get('slice')}: passed={data.get('passed')} state={data.get('statePath') or data.get('task')}")
                    for summary in data.get("slices", []):
                        print(f"  {summary['slice']}: {summary['status']}")
                    if isinstance(data.get("steps"), list):
                        for step in data["steps"]:
                            print(f"  {step['id']}: {step['status']} {step.get('seconds', '')}s")
                return 0
        if args.command == "check":
            result = check_all(args.project)
            if args.json:
                print(json.dumps(result, indent=2))
            else:
                for error in result["errors"]:
                    print("FAIL", error)
                for warning in result["warnings"]:
                    print("WARN", warning)
                print(f"checks: {'PASS' if result['passed'] else 'FAIL'} | capabilities {result['capabilities']} | tools {result['tools']['count']} | project {result['project'] or '-'}")
            return 0 if result["passed"] else 1
        if args.command == "version":
            print("Gypsy Studio 0.1.0")
            return 0
    except (GypsyError, toolkit_spec.ToolkitError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())