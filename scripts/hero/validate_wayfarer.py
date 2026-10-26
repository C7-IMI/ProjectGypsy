#!/usr/bin/env python3
"""Non-Blender, non-network validation for the exported Wayfarer hero asset.

Usage:
    python scripts/hero/validate_wayfarer.py [--repo <dir>] [--json <path>]

Parses the GLB container directly (JSON + BIN chunks), asserts the rig, skin weights,
actions, bounds, materials, embedded texture and file budgets, compares the Godot
mirror byte-for-byte, and checks the game integration files. It does not import
Blender, Godot, numpy or any network client. Exit code 0 on pass, 1 on failure.
Prints HERO_VALIDATE_OK / HERO_VALIDATE_FAIL for machine-readable evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
import sys
from pathlib import Path

REPO_DEFAULT = Path(__file__).resolve().parents[2]
GLB_REL = Path("assets") / "hero" / "wayfarer.glb"
FBX_REL = Path("assets") / "hero" / "wayfarer.fbx"
TEXTURE_REL = Path("assets") / "hero" / "textures" / "wayfarer_atlas.png"
BRIEF_REL = Path("assets") / "hero" / "ART-BRIEF.md"
GENERATOR_REL = Path("scripts") / "hero" / "generate_wayfarer.py"
GAME_GLB_REL = Path("game") / "assets" / "hero" / "wayfarer.glb"
PLAYER_SCENE_REL = Path("game") / "scenes" / "player.tscn"
HERO_SCRIPT_REL = Path("game") / "scripts" / "hero_visual.gd"
PLAYER_SCRIPT_REL = Path("game") / "scripts" / "player.gd"
MAIN_SCRIPT_REL = Path("game") / "scripts" / "main.gd"

COMPONENTS = {
    5120: ("b", 1, 127.0),
    5121: ("B", 1, 255.0),
    5122: ("h", 2, 32767.0),
    5123: ("H", 2, 65535.0),
    5125: ("I", 4, 4294967295.0),
    5126: ("f", 4, 1.0),
}
TYPE_COUNTS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT2": 4, "MAT3": 9, "MAT4": 16}


class Checker:
    def __init__(self) -> None:
        self.records = []
        self.failures = 0

    def check(self, name: str, ok: bool, detail: str = "") -> bool:
        self.records.append({"name": name, "status": "pass" if ok else "fail", "detail": detail})
        if not ok:
            self.failures += 1
        print(("PASS " if ok else "FAIL ") + name + (" - " + detail if detail else ""))
        return ok

    def warn(self, name: str, detail: str) -> None:
        self.records.append({"name": name, "status": "warn", "detail": detail})
        print("WARN " + name + " - " + detail)


class Glb:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.data = path.read_bytes()
        if len(self.data) < 20:
            raise ValueError("file is too small to be a GLB")
        magic, version, length = struct.unpack_from("<4sII", self.data, 0)
        if magic != b"glTF":
            raise ValueError("missing glTF magic")
        if version != 2:
            raise ValueError("not glTF 2.0 (version=" + str(version) + ")")
        self.declared_length = length
        self.json = None
        self.bin = b""
        offset = 12
        while offset + 8 <= len(self.data):
            chunk_length, chunk_type = struct.unpack_from("<I4s", self.data, offset)
            offset += 8
            chunk = self.data[offset:offset + chunk_length]
            offset += chunk_length
            if chunk_type == b"JSON":
                self.json = json.loads(chunk.decode("utf-8"))
            elif chunk_type == b"BIN\x00" and not self.bin:
                self.bin = chunk
        if self.json is None:
            raise ValueError("no JSON chunk")
        if not self.bin:
            raise ValueError("no BIN chunk")

    def accessor(self, index: int):
        accessor = self.json["accessors"][index]
        view = self.json["bufferViews"][accessor["bufferView"]]
        component = accessor["componentType"]
        if component not in COMPONENTS:
            raise ValueError("unsupported componentType " + str(component))
        fmt, size, normalizer = COMPONENTS[component]
        if accessor["type"] not in TYPE_COUNTS:
            raise ValueError("unsupported accessor type " + str(accessor["type"]))
        count = TYPE_COUNTS[accessor["type"]]
        stride = view.get("byteStride", size * count)
        start = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
        normalized = bool(accessor.get("normalized"))
        values = []
        for i in range(accessor["count"]):
            raw = struct.unpack_from("<" + fmt * count, self.bin, start + i * stride)
            if normalized:
                raw = tuple(float(value) / normalizer for value in raw)
            values.append(raw)
        return values

    def accessor_min_max(self, index: int):
        accessor = self.json["accessors"][index]
        return accessor.get("min"), accessor.get("max")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def png_size(path: Path):
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    width, height = struct.unpack_from(">II", data, 16)
    return width, height


def validate(repo: Path, checker: Checker) -> dict:
    facts = {}
    glb_path = repo / GLB_REL
    texture_path = repo / TEXTURE_REL
    fbx_path = repo / FBX_REL
    game_glb = repo / GAME_GLB_REL

    # ---- tracked files -------------------------------------------------------
    for label, path in (
        ("glb exists", glb_path),
        ("texture exists", texture_path),
        ("art brief exists", repo / BRIEF_REL),
        ("generator exists", repo / GENERATOR_REL),
        ("godot mirror exists", game_glb),
    ):
        checker.check(label, path.is_file(), str(path))
    if not glb_path.is_file():
        return facts
    if not texture_path.is_file():
        return facts

    # ---- budgets / mirror ----------------------------------------------------
    checker.check("glb size <= 2 MB", glb_path.stat().st_size <= 2 * 1024 * 1024,
                  str(glb_path.stat().st_size) + " bytes")
    checker.check("texture <= 512 KB", texture_path.stat().st_size <= 512 * 1024,
                  str(texture_path.stat().st_size) + " bytes")
    texture_size = png_size(texture_path)
    checker.check("texture is 256x256 PNG", texture_size == (256, 256), str(texture_size))
    if game_glb.is_file():
        checker.check("godot mirror is byte-identical", sha256(game_glb) == sha256(glb_path),
                      sha256(glb_path)[:16] + "…")
    fb_present = fbx_path.is_file()
    if fb_present:
        header = fbx_path.read_bytes()[:27]
        version = struct.unpack_from("<I", fbx_path.read_bytes(), 23)[0] if len(header) >= 27 else 0
        checker.check("fbx is binary FBX 7.4", header.startswith(b"Kaydara FBX Binary") and version == 7400,
                      "version=" + str(version) + " bytes=" + str(fbx_path.stat().st_size))
        checker.check("fbx size <= 4 MB", fbx_path.stat().st_size <= 4 * 1024 * 1024,
                      str(fbx_path.stat().st_size) + " bytes")
    else:
        checker.warn("fbx optional", "no FBX present (GLB is the runtime asset)")

    # ---- GLB container -------------------------------------------------------
    try:
        glb = Glb(glb_path)
    except (OSError, ValueError, struct.error) as exc:
        checker.check("glb parses", False, str(exc))
        return facts
    checker.check("glb parses", True,
                  "version " + str(glb.json.get("asset", {}).get("version")) + ", " + str(len(glb.data)) + " bytes")
    checker.check("glb has no external buffers", all("uri" not in item for item in glb.json.get("buffers", [])),
                  str(len(glb.json.get("buffers", []))) + " buffer(s)")
    checker.check("glb has no external images", all("uri" not in item for item in glb.json.get("images", [])),
                  str(len(glb.json.get("images", []))) + " image(s)")
    checker.check("glb has no cameras", not glb.json.get("cameras"), str(len(glb.json.get("cameras", []) or [])) + " camera(s)")
    checker.check("asset generator is Blender glTF I/O",
                  "Blender" in str(glb.json.get("asset", {}).get("generator", "")),
                  str(glb.json.get("asset", {}).get("generator")))

    # ---- mesh / geometry -----------------------------------------------------
    meshes = glb.json.get("meshes", [])
    checker.check("exactly one mesh", len(meshes) == 1, str(len(meshes)))
    if not meshes:
        return facts
    primitives = meshes[0].get("primitives", [])
    checker.check("mesh has 4 primitives (4 materials)", len(primitives) == 4, str(len(primitives)))
    required_attrs = ("POSITION", "NORMAL", "TEXCOORD_0", "JOINTS_0", "WEIGHTS_0")
    missing = [key for primitive in primitives for key in required_attrs if key not in primitive.get("attributes", {})]
    checker.check("all primitives are skinned and textured", not missing,
                  "missing=" + ",".join(sorted(set(missing))) if missing else "POSITION/NORMAL/UV/JOINTS/WEIGHTS present")

    vertex_records = 0
    triangles = 0
    bounds_min = [math.inf, math.inf, math.inf]
    bounds_max = [-math.inf, -math.inf, -math.inf]
    weight_sums = []
    multi_influence = 0
    unweighted = 0
    max_influences = 0
    positions_ok = True
    for primitive in primitives:
        attributes = primitive["attributes"]
        pos_index = attributes["POSITION"]
        vertex_records += glb.json["accessors"][pos_index]["count"]
        if "indices" in primitive:
            triangles += glb.json["accessors"][primitive["indices"]]["count"] // 3
        lo, hi = glb.accessor_min_max(pos_index)
        if lo and hi:
            for axis in range(3):
                bounds_min[axis] = min(bounds_min[axis], float(lo[axis]))
                bounds_max[axis] = max(bounds_max[axis], float(hi[axis]))
        else:
            positions_ok = False
        for weights in glb.accessor(attributes["WEIGHTS_0"]):
            total = sum(weights)
            weight_sums.append(total)
            influences = sum(1 for value in weights if value > 0.0005)
            max_influences = max(max_influences, influences)
            if influences == 0:
                unweighted += 1
            if influences >= 2:
                multi_influence += 1
    checker.check("positions carry bounds", positions_ok)
    height = bounds_max[1] - bounds_min[1]
    width = bounds_max[0] - bounds_min[0]
    depth = bounds_max[2] - bounds_min[2]
    facts["bounds"] = {"min": bounds_min, "max": bounds_max, "height": height, "width": width, "depth": depth}
    checker.check("hero height is 1.70-2.00 m", 1.70 <= height <= 2.00, "%.3f m" % height)
    checker.check("feet rest near y=0", abs(bounds_min[1]) <= 0.02, "min y=%.4f" % bounds_min[1])
    checker.check("hero is centred on x", abs(bounds_min[0] + bounds_max[0]) <= 0.03,
                  "x %.3f..%.3f" % (bounds_min[0], bounds_max[0]))
    checker.check("hero fits the capsule footprint", width <= 1.0 and depth <= 1.0,
                  "width=%.3f depth=%.3f" % (width, depth))
    checker.check("low-poly triangle budget", 500 <= triangles <= 12000, str(triangles) + " triangles")
    facts["vertexRecords"] = vertex_records
    facts["triangles"] = triangles

    # ---- skin / rig ----------------------------------------------------------
    skins = glb.json.get("skins", [])
    checker.check("exactly one skin", len(skins) == 1, str(len(skins)))
    if skins:
        skin = skins[0]
        joints = skin.get("joints", [])
        checker.check("skin has >= 15 joints", len(joints) >= 15, str(len(joints)) + " joints")
        ibm = skin.get("inverseBindMatrices")
        checker.check("inverse bind matrices match joints",
                      ibm is not None and glb.json["accessors"][ibm]["count"] == len(joints),
                      str(glb.json["accessors"][ibm]["count"]) if ibm is not None else "missing")
        nodes = glb.json.get("nodes", [])
        names = [nodes[index].get("name", "") for index in joints]
        facts["joints"] = names
        needed = ["hips", "spine", "chest", "head", "upper_arm.L", "upper_arm.R",
                  "forearm.L", "forearm.R", "hand.L", "hand.R", "thigh.L", "thigh.R",
                  "shin.L", "shin.R", "foot.L", "foot.R"]
        absent = [name for name in needed if name not in names]
        checker.check("humanoid joint set is present", not absent, "missing=" + ",".join(absent) if absent else "16 core joints")
        checker.check("weights are normalised", all(abs(value - 1.0) <= 0.002 for value in weight_sums),
                      "min=%.5f max=%.5f" % (min(weight_sums), max(weight_sums)))
        checker.check("every vertex is weighted", unweighted == 0, str(unweighted) + " unweighted")
        checker.check("max 4 influences per vertex", max_influences <= 4, str(max_influences))
        checker.check("weighting blends across joints", multi_influence > 0,
                      str(multi_influence) + " vertex records with >= 2 influences")
        facts["skinning"] = {
            "joints": len(joints),
            "weightMin": min(weight_sums),
            "weightMax": max(weight_sums),
            "unweighted": unweighted,
            "maxInfluences": max_influences,
            "multiInfluenceRecords": multi_influence,
        }

    # ---- actions -------------------------------------------------------------
    animations = glb.json.get("animations", [])
    checker.check("at least 3 animations", len(animations) >= 3, str(len(animations)))
    names = [str(animation.get("name", "")).lower() for animation in animations]
    facts["animations"] = []
    joint_set = set(skins[0].get("joints", [])) if skins else set()
    expected = {
        "idle": (2.8, 3.2),
        "run": (0.9, 1.1),
        "reach": (1.8, 2.2),
    }
    for wanted, (low, high) in expected.items():
        matching = [animation for animation, name in zip(animations, names) if name == wanted]
        if not matching:
            checker.check("animation " + wanted, False, "not present (found " + ",".join(names) + ")")
            continue
        animation = matching[0]
        duration = 0.0
        for sampler in animation.get("samplers", []):
            _lo, hi = glb.accessor_min_max(sampler["input"])
            if hi:
                duration = max(duration, float(hi[0]))
        channels = animation.get("channels", [])
        joint_channels = sum(1 for channel in channels if channel.get("target", {}).get("node") in joint_set)
        facts["animations"].append({"name": wanted, "duration": duration, "channels": len(channels)})
        checker.check("animation " + wanted + " duration", low <= duration <= high, "%.2f s" % duration)
        checker.check("animation " + wanted + " drives joints", joint_channels >= 10,
                      str(joint_channels) + "/" + str(len(channels)) + " joint channels")
    exact = set(names) == {"idle", "run", "reach"}
    checker.check("clip set is exactly idle/run/reach", exact, ",".join(sorted(names)))

    # ---- materials / texture -------------------------------------------------
    materials = glb.json.get("materials", [])
    material_names = [str(material.get("name", "")) for material in materials]
    checker.check("4 named materials", len(materials) == 4, ",".join(material_names))
    textured = [
        material for material in materials
        if (material.get("pbrMetallicRoughness") or {}).get("baseColorTexture")
    ]
    checker.check("at least 2 textured materials", len(textured) >= 2,
                  str(len(textured)) + " textured, " + ",".join(material_names))
    emissive = [
        material for material in materials
        if any(float(value) > 0.05 for value in (material.get("emissiveFactor") or [0.0, 0.0, 0.0]))
    ]
    checker.check("emissive accent material", len(emissive) >= 1,
                  ",".join(str(material.get("name")) for material in emissive))
    checker.check("double-sided cloth materials", all(bool(material.get("doubleSided")) for material in materials),
                  str(sum(1 for material in materials if material.get("doubleSided"))) + "/" + str(len(materials)))
    images = glb.json.get("images", [])
    checker.check("exactly one embedded image", len(images) == 1, str(len(images)))
    if images:
        image = images[0]
        checker.check("image is PNG", image.get("mimeType") == "image/png", str(image.get("mimeType")))
        view_index = image.get("bufferView")
        if view_index is not None:
            view = glb.json["bufferViews"][view_index]
            start = view.get("byteOffset", 0)
            data = glb.bin[start:start + view["byteLength"]]
            png_ok = data[:8] == b"\x89PNG\r\n\x1a\n"
            dims = struct.unpack_from(">II", data, 16) if png_ok else None
            checker.check("embedded image is a 256x256 PNG", png_ok and dims == (256, 256),
                          str(dims) + ", " + str(view["byteLength"]) + " bytes")
            facts["embeddedImage"] = {"mime": image.get("mimeType"), "dimensions": dims, "bytes": view["byteLength"]}

    # ---- integration (game files) -------------------------------------------
    player_scene = repo / PLAYER_SCENE_REL
    if player_scene.is_file():
        text = player_scene.read_text(encoding="utf-8")
        checker.check("player scene instances the hero GLB", "res://assets/hero/wayfarer.glb" in text)
        checker.check("hero is parented under Player", "[node name=\"Hero\"" in text)
        checker.check("hero is offset to the capsule bottom", "position = Vector3(0, -0.9, 0)" in text,
                      "expected local y=-0.9")
        checker.check("capsule collision is preserved", "CapsuleShape3D" in text)
        checker.check("placeholder capsule visual removed", "CapsuleMesh" not in text)
    else:
        checker.check("player scene exists", False, str(player_scene))
    hero_script = repo / HERO_SCRIPT_REL
    if hero_script.is_file():
        text = hero_script.read_text(encoding="utf-8")
        for wanted in ("idle", "run", "reach"):
            checker.check("hero visual maps " + wanted, wanted in text)
    else:
        checker.check("hero visual script exists", False, str(hero_script))
    player_script = repo / PLAYER_SCRIPT_REL
    if player_script.is_file():
        text = player_script.read_text(encoding="utf-8")
        checker.check("player script drives the hero visual", "hero" in text.lower() and "play_collect" in text)
    main_script = repo / MAIN_SCRIPT_REL
    if main_script.is_file():
        checker.check("demo marker contract intact", "GYPSY_DEMO_OK" in main_script.read_text(encoding="utf-8"))
    import_file = repo / "game" / "assets" / "hero" / "wayfarer.glb.import"
    if import_file.is_file():
        checker.check("godot import metadata exists", True, str(import_file))
        uid_text = import_file.read_text(encoding="utf-8")
        checker.check("godot import metadata references the GLB", "wayfarer.glb" in uid_text)
    else:
        checker.warn("godot import metadata", "wayfarer.glb.import is absent; run godot --headless --path game --import")

    facts["files"] = {
        "glbBytes": glb_path.stat().st_size,
        "glbSha256": sha256(glb_path),
        "textureBytes": texture_path.stat().st_size,
        "fbxBytes": fbx_path.stat().st_size if fb_present else 0,
        "materialNames": material_names,
    }
    return facts


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the exported Wayfarer hero without Blender")
    parser.add_argument("--repo", default=str(REPO_DEFAULT))
    parser.add_argument("--json", default=None, help="write a machine-readable report")
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    print("Wayfarer asset validation — repo " + str(repo))
    checker = Checker()
    try:
        facts = validate(repo, checker)
    except Exception as exc:  # keep the failure legible instead of a traceback-only run
        checker.check("validation ran without exceptions", False, type(exc).__name__ + ": " + str(exc))
        facts = {}
    report = {
        "schema": "gypsy.hero.validate/v1",
        "repo": str(repo),
        "facts": facts,
        "checks": checker.records,
        "passed": checker.failures == 0,
        "failures": [record for record in checker.records if record["status"] == "fail"],
    }
    if args.json:
        path = Path(args.json)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(report, indent=2) + "\n")
        print("report: " + str(path))
    if checker.failures:
        print("HERO_VALIDATE_FAIL " + str(checker.failures) + " check(s) failed")
        return 1
    print("HERO_VALIDATE_OK checks=" + str(len(checker.records)) +
          " bones=" + str(len(facts.get("joints", []))) +
          " actions=" + str(len(facts.get("animations", []))) +
          " tris=" + str(facts.get("triangles")) +
          " glb=" + str(facts.get("files", {}).get("glbBytes")) + "B")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
