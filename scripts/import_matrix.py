#!/usr/bin/env python3
"""Generate the golden kit, round-trip it in Blender, validate glTF, and run the engine import matrix.

Phase-0 evidence for ADR-006. Unity/UE5/Flax imports are recorded as blocked/gated here rather than faked.

Usage:
    python scripts/import_matrix.py [--skip-generate] [--json PATH] [--report PATH]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import struct
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
GOLDEN_DIR = REPO / "artifacts" / "golden"
GODOT_DIR = REPO / "artifacts" / "godot-import"
DEFAULT_BLENDER = r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"
GLTF_TRANSFORM = Path(os.environ.get("APPDATA", "")) / "npm" / "gltf-transform.cmd"
SYS_PYTHON = sys.executable


def run(cmd, timeout=180, cwd=REPO):
    started = time.time()
    try:
        proc = subprocess.run(
            [str(c) for c in cmd],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout,
            shell=False,
        )
        return {"cmd": [str(c) for c in cmd], "exit": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr, "seconds": round(time.time() - started, 2)}
    except subprocess.TimeoutExpired:
        return {"cmd": [str(c) for c in cmd], "exit": None, "stdout": "", "stderr": "timeout", "seconds": timeout, "timeout": True}
    except OSError as exc:
        return {"cmd": [str(c) for c in cmd], "exit": None, "stdout": "", "stderr": str(exc), "seconds": round(time.time() - started, 2)}


def probe_engines():
    result = run([SYS_PYTHON, REPO / "workstream" / "gypsy.py", "engines", "probe", "--json"], timeout=60)
    if result["exit"] != 0:
        return {"error": result["stderr"][-1000:]}
    try:
        return json.loads(result["stdout"])
    except json.JSONDecodeError as exc:
        return {"error": str(exc), "raw": result["stdout"][-1000:]}


def generate_golden(blender: str):
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    script = REPO / "assets" / "test" / "golden" / "generate_golden.py"
    result = run([blender, "--background", "--factory-startup", "--python", script, "--", "--out", GOLDEN_DIR], timeout=240)
    return result


def read_golden_report():
    path = GOLDEN_DIR / "golden-report.json"
    if not path.exists():
        return {"error": "golden-report.json missing"}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def validate_gltf(path: Path):
    if not GLTF_TRANSFORM.exists():
        return {"file": path.name, "status": "skip", "error": "gltf-transform not found"}
    result = run(["cmd", "/c", str(GLTF_TRANSFORM), "validate", str(path)], timeout=120)
    text = result["stdout"] + "\n" + result["stderr"]
    clean = re.sub(r"\x1b\[[0-9;]*m", "", text)
    no_errors = "No errors found" in clean
    warnings = sorted(set(re.findall(r"\b((?:NODE|ACCESSOR|ANIMATION|MATERIAL|MESH|TEXTURE|BUFFER|SCENE|SKIN)_[A-Z0-9_]+)\b", clean)))
    return {"file": path.name, "status": "pass" if no_errors else "fail", "warnings": warnings, "raw": clean[-2000:]}


def write_godot_project():
    if GODOT_DIR.exists():
        shutil.rmtree(GODOT_DIR, ignore_errors=True)
    GODOT_DIR.mkdir(parents=True, exist_ok=True)
    (GODOT_DIR / "project.godot").write_text(
        'config_version=5\n\n[application]\n\nconfig/name="Gypsy Golden Import"\n',
        encoding="ascii",
    )
    for glb in GOLDEN_DIR.glob("*.glb"):
        shutil.copy2(glb, GODOT_DIR / glb.name)
    check = """extends SceneTree
func _count_meshes(node: Node) -> int:
    var n: int = 0
    if node is MeshInstance3D:
        n += 1
    for child in node.get_children():
        n += _count_meshes(child)
    return n
func _init() -> void:
    var results: Dictionary = {}
    for name in ["static_cube", "rigged_character", "morph_face", "lod_set"]:
        var path: String = "res://" + str(name) + ".glb"
        var packed: PackedScene = load(path)
        if packed == null:
            results[name] = {"loaded": false}
            continue
        var inst: Node = packed.instantiate()
        var meshes: int = _count_meshes(inst)
        var anim = inst.find_child("AnimationPlayer", true, false)
        var clips: int = 0
        if anim != null and anim is AnimationPlayer:
            clips = anim.get_animation_list().size()
        results[name] = {"loaded": true, "meshes": meshes, "animations": clips}
        inst.free()
    print("GODOT_IMPORT_RESULTS ", JSON.stringify(results))
    quit(0)
"""
    (GODOT_DIR / "check.gd").write_text(check, encoding="ascii")


def godot_import(godot: str):
    write_godot_project()
    imported = run([godot, "--headless", "--path", GODOT_DIR, "--import"], timeout=180)
    checked = run([godot, "--headless", "--path", GODOT_DIR, "--script", "res://check.gd"], timeout=180)
    text = re.sub(r"\x1b\[[0-9;]*m", "", checked["stdout"] + "\n" + checked["stderr"])
    match = re.search(r"GODOT_IMPORT_RESULTS (\{.*\})", text)
    results = json.loads(match.group(1)) if match else None
    expected = {"static_cube": {"meshes": 1, "animations": 0}, "rigged_character": {"minMeshes": 1, "minAnimations": 3}, "morph_face": {"minMeshes": 1}, "lod_set": {"meshes": 4}}
    failures = []
    if not results:
        failures.append("no GODOT_IMPORT_RESULTS line")
    else:
        for name, expectation in expected.items():
            got = results.get(name) or {}
            if not got.get("loaded"):
                failures.append(name + ": not loaded")
                continue
            for key, value in expectation.items():
                actual_key = key[3:].lower() if key.startswith("min") else key
                actual = got.get(actual_key)
                if key.startswith("min"):
                    if actual is None or actual < value:
                        failures.append(name + ": " + key + " expected >= " + str(value) + ", got " + str(actual))
                elif actual != value:
                    failures.append(name + ": " + key + " expected " + str(value) + ", got " + str(actual))
    return {
        "status": "pass" if imported["exit"] == 0 and checked["exit"] == 0 and not failures else "fail",
        "importExit": imported["exit"],
        "checkExit": checked["exit"],
        "results": results,
        "failures": failures,
        "output": text[-2000:],
    }


def engine_matrix(probe: dict):
    engines = probe.get("engines", {}) if isinstance(probe, dict) else {}
    matrix = []
    for engine_id, record in engines.items():
        status = "not installed"
        reason = "; ".join(record.get("notes", []))
        if record.get("installed"):
            status = "not run"
            if engine_id == "unity":
                if not (record.get("licence") or {}).get("proven"):
                    status = "blocked: no licence"
                    reason = "batchmode exited 198: No valid Unity Editor license found (docs/ENGINE-SMOKE.md)"
            if engine_id == "ue5":
                gate = record.get("gate") or {}
                if not gate.get("ok"):
                    status = "blocked: hardware gate"
                    reason = "; ".join(gate.get("reasons", []))
            if engine_id == "flax":
                status = "experimental: not tested"
            if engine_id == "godot":
                status = "not run"
        matrix.append({"engine": engine_id, "version": record.get("version"), "status": status, "reason": reason})
    return matrix


def glb_metadata(path: Path):
    """Read the JSON chunk of a GLB and return the asset generator/version."""
    try:
        data = path.read_bytes()
        if data[:4] != b"glTF":
            return {"error": "not a GLB"}
        chunk_length = int.from_bytes(data[12:16], "little")
        chunk_type = data[16:20]
        if chunk_type != b"JSON":
            return {"error": "first chunk is not JSON"}
        document = json.loads(data[20:20 + chunk_length].decode("utf-8"))
        asset = document.get("asset") or {}
        return {"generator": asset.get("generator"), "version": asset.get("version"), "extensionsUsed": document.get("extensionsUsed") or []}
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {"error": str(exc)}


def fbx_metadata(path: Path):
    """Read the FBX binary header version (e.g. 7400 = FBX 7.4)."""
    try:
        data = path.read_bytes()
        if not data.startswith(b"Kaydara FBX Binary"):
            return {"error": "not a binary FBX"}
        version = struct.unpack("<I", data[23:27])[0]
        return {"version": version, "label": str(version // 1000) + "." + str((version % 1000) // 100)}
    except (OSError, struct.error) as exc:
        return {"error": str(exc)}


def markdown(report: dict) -> str:
    lines = []
    lines.append("# IMPORT-MATRIX.md — Blender 5.2 golden-asset import matrix")
    lines.append("")
    lines.append("Generated " + report["generated"] + " by " + report["script"] + ". This is Phase-0 evidence for")
    lines.append("[ADR-006](ADR-006-blender-import-matrix.md); it is not an art-quality claim.")
    lines.append("")
    lines.append("## Result")
    lines.append("")
    lines.append("| Engine | Version | glTF/GLB | FBX | Status | Evidence / reason |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for item in report["engines"]:
        if item["engine"] == "godot":
            gltf = report["godot"]["status"].upper()
            fbx = "not supported natively"
            status = "PASS" if report["godot"]["status"] == "pass" else "FAIL"
            evidence = "headless --import + scene assertions: " + json.dumps(report["godot"].get("results"))
        elif item["engine"] == "unity":
            gltf = "blocked"
            fbx = "blocked"
            status = item["status"]
            evidence = item["reason"]
        elif item["engine"] == "ue5":
            gltf = "blocked"
            fbx = "blocked"
            status = item["status"]
            evidence = item["reason"]
        elif item["engine"] == "flax":
            gltf = "not tested"
            fbx = "not tested"
            status = item["status"]
            evidence = item["reason"]
        else:
            gltf = "not run"
            fbx = "not run"
            status = item["status"]
            evidence = item["reason"]
        labels = {"godot": "Godot", "unity": "Unity", "ue5": "UE5", "flax": "Flax"}
        lines.append("| " + labels.get(item["engine"], item["engine"]) + " | " + str(item.get("version") or "-") + " | " + gltf + " | " + fbx + " | " + status + " | " + evidence.replace("\n", " ") + " |")
    lines.append("")
    lines.append("## Blender round-trip")
    lines.append("")
    lines.append("Blender " + report["blender"] + " exports each source to GLB and FBX, then re-imports each export into an empty scene.")
    lines.append("Counts below are what Blender itself read back; the engine is what the engine read.")
    lines.append("")
    lines.append("| Asset | Format | Objects | Meshes | Armatures | Actions | Shape keys | Materials | Status |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for asset in report["golden"].get("assets", []):
        for fmt in ("glb", "fbx"):
            r = asset.get("roundtrip", {}).get(fmt, {})
            lines.append("| " + asset["name"] + " | " + fmt + " | " + str(r.get("objects")) + " | " + str(r.get("meshes")) + " | " + str(r.get("armatures")) + " | " + str(r.get("actions")) + " | " + str(r.get("shapeKeys")) + " | " + str(r.get("materials")) + " | " + str(r.get("status")) + " |")
    lines.append("")
    lines.append("## glTF validation (Khronos validator via gltf-transform)")
    lines.append("")
    lines.append("| File | Status | Warning codes |")
    lines.append("| --- | --- | --- |")
    for item in report["gltf"]:
        lines.append("| " + item["file"] + " | " + item["status"] + " | " + (", ".join(item.get("warnings", [])) or "-") + " |")
    lines.append("")
    lines.append("A warning is recorded, not hidden: NODE_SKINNED_MESH_NON_ROOT is expected with Blender's armature export and is")
    lines.append("checked by the engine import test rather than treated as a pass by itself.")
    lines.append("")
    lines.append("## Export metadata (recorded per run)")
    lines.append("")
    lines.append("| Asset | glTF generator | glTF version | FBX header |")
    lines.append("| --- | --- | --- | --- |")
    for item in report.get("exports", []):
        glb = item.get("glb", {})
        fbx = item.get("fbx", {})
        fbx_text = "-" if "version" not in fbx else str(fbx.get("version")) + " (" + str(fbx.get("label")) + ")"
        lines.append("| " + item["asset"] + " | " + str(glb.get("generator") or glb.get("error") or "-") + " | " + str(glb.get("version") or "-") + " | " + fbx_text + " |")
    lines.append("")
    lines.append("## Pinned baseline")
    lines.append("")
    lines.append("| Item | Value |")
    lines.append("| --- | --- |")
    lines.append("| Blender | " + report["blender"] + " |")
    lines.append("| glTF export | GLB, apply modifiers, Y-up, animations, morphs, skins, NLA strips, force sampling |")
    lines.append("| FBX export | FBX 7400, -Z forward / Y up, apply scale all, no leaf bones, bake animation via NLA strips |")
    lines.append("| Godot | 4.7.2, headless import + scripted scene assertions |")
    lines.append("| Unity | installed, no licence -> blocked |")
    lines.append("| Unreal | 5.8.4, hardware gate fails (4 GB VRAM / free disk) -> blocked |")
    lines.append("| Flax | 1.13, experimental -> not tested |")
    lines.append("")
    lines.append("## Not tested / next")
    lines.append("")
    lines.append("- Unity and UE5 FBX/glTF import on this machine: blocked by licence/hardware; re-run on an activated/higher-spec machine.")
    lines.append("- Flax import: no demonstrated headless path.")
    lines.append("- Add-on smoke tests (Rigify, retopo/UV add-ons): not yet automated; ADR-006 records the policy.")
    lines.append("- Material/texture channel round-trip: the golden assets use simple Principled materials; a texture-embedded case is next.")
    lines.append("- Rendered capture after import: capture capability is still planned.")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Blender golden kit + engine import matrix")
    parser.add_argument("--skip-generate", action="store_true")
    parser.add_argument("--blender", default=os.environ.get("GYPSY_BLENDER", DEFAULT_BLENDER))
    parser.add_argument("--json", default=str(REPO / "workstream" / "state" / "import-matrix.json"))
    parser.add_argument("--report", default=str(REPO / "docs" / "IMPORT-MATRIX.md"))
    args = parser.parse_args()

    report = {"generated": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"), "script": "scripts/import_matrix.py"}
    if not args.skip_generate:
        gen = generate_golden(args.blender)
        report["generate"] = {"exit": gen["exit"], "seconds": gen["seconds"], "stderrTail": gen["stderr"][-1000:]}
        if gen["exit"] != 0:
            print("golden generation failed", file=sys.stderr)
            print(gen["stdout"][-1600:], file=sys.stderr)
            print(gen["stderr"][-1600:], file=sys.stderr)
            return 1
    golden = read_golden_report()
    if "error" in golden:
        print(golden["error"], file=sys.stderr)
        return 1
    report["blender"] = golden.get("blender", "?")
    report["golden"] = golden
    report["gltf"] = [validate_gltf(path) for path in sorted(GOLDEN_DIR.glob("*.glb"))]
    report["exports"] = []
    for asset in golden.get("assets", []):
        glb = Path((asset.get("exports") or {}).get("glb", ""))
        fbx = Path((asset.get("exports") or {}).get("fbx", ""))
        report["exports"].append({
            "asset": asset.get("name"),
            "glb": glb_metadata(glb) if glb.exists() else {"error": "missing"},
            "fbx": fbx_metadata(fbx) if fbx.exists() else {"error": "missing"},
        })
    probe = probe_engines()
    report["probe"] = {k: v for k, v in probe.items() if k in ("generated", "staleRegistry")} if isinstance(probe, dict) else probe
    report["engines"] = engine_matrix(probe)
    godot_cli = (((probe.get("engines") or {}).get("godot") or {}).get("cli")) if isinstance(probe, dict) else None
    if godot_cli and Path(godot_cli).exists():
        report["godot"] = godot_import(godot_cli)
    else:
        report["godot"] = {"status": "fail", "error": "Godot CLI not found", "failures": ["godot missing"]}
    for item in report["engines"]:
        if item["engine"] == "godot":
            item["status"] = "pass: glTF import" if report["godot"].get("status") == "pass" else "fail: glTF import"
            item["reason"] = "headless --import + scene assertions; FBX not native"
    json_path = Path(args.json)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    with open(json_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(report, indent=2) + "\n")
    report_path = Path(args.report)
    with open(report_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(markdown(report))
    failures = []
    if not all(asset.get("roundtrip", {}).get("glb", {}).get("status") == "pass" and asset.get("roundtrip", {}).get("fbx", {}).get("status") == "pass" for asset in golden.get("assets", [])):
        failures.append("Blender round-trip failed")
    if any(item["status"] != "pass" for item in report["gltf"]):
        failures.append("glTF validation failed")
    if report["godot"].get("status") != "pass":
        failures.append("Godot import failed: " + "; ".join(report["godot"].get("failures", []) or [report["godot"].get("error", "?")]))
    print("IMPORT_MATRIX " + ("PASS" if not failures else "FAIL") + " godot=" + str(report["godot"].get("status")))
    print("report: " + str(report_path))
    for failure in failures:
        print("FAIL " + failure, file=sys.stderr)
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
