#!/usr/bin/env python3
"""Generate the golden import-test asset kit and verify Blender round-trips.

Run with:
    blender --background --factory-startup --python assets/test/golden/generate_golden.py -- --out <dir>

Creates four sources (.blend) and glTF/GLB + FBX exports:
  static_cube       - mesh + material
  rigged_character  - skinned mesh, 3 bone armature, 3 NLA actions
  morph_face        - mesh with a shape key
  lod_set           - three named LOD meshes + a collision mesh

Then re-imports each export into a fresh Blender scene and records counts.
Writes golden-report.json into the output directory. This is a round-trip test,
not an engine import test: engine importers are exercised by scripts/import_matrix.py.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from pathlib import Path

import bpy
import math
from mathutils import Vector


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def ensure_dir(path: Path):
    path.mkdir(parents=True, exist_ok=True)


def save_blend(path: Path):
    bpy.ops.wm.save_as_mainfile(filepath=str(path))


def material(name, color=(0.2, 0.45, 0.8, 1.0), roughness=0.45):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = color
        bsdf.inputs["Roughness"].default_value = roughness
        bsdf.inputs["Metallic"].default_value = 0.0
    return mat


def export_glb(path: Path):
    try:
        bpy.ops.export_scene.gltf(
            filepath=str(path),
            export_format="GLB",
            export_apply=True,
            export_yup=True,
            export_animations=True,
            export_morph=True,
            export_skins=True,
            export_materials="EXPORT",
            export_nla_strips=True,
            export_force_sampling=True,
        )
        return None
    except Exception as exc:
        return f"glTF export failed: {exc}"


def export_fbx(path: Path):
    try:
        bpy.ops.export_scene.fbx(
            filepath=str(path),
            object_types={"ARMATURE", "MESH"},
            use_mesh_modifiers=True,
            add_leaf_bones=False,
            bake_anim=True,
            bake_anim_use_all_actions=False,
            bake_anim_use_nla_strips=True,
            bake_anim_force_startend_keying=True,
            bake_anim_step=1.0,
            bake_anim_simplify_factor=0.0,
            path_mode="COPY",
            embed_textures=False,
            axis_forward="-Z",
            axis_up="Y",
            apply_scale_options="FBX_SCALE_ALL",
            use_selection=False,
        )
        return None
    except Exception as exc:
        return f"FBX export failed: {exc}"


def count_scene():
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    armatures = [o for o in bpy.context.scene.objects if o.type == "ARMATURE"]
    shape_keys = 0
    for obj in meshes:
        data = getattr(obj, "data", None)
        if data is not None and getattr(data, "shape_keys", None):
            shape_keys += len(data.shape_keys.key_blocks)
    return {
        "objects": len(bpy.context.scene.objects),
        "meshes": len(meshes),
        "armatures": len(armatures),
        "actions": len(bpy.data.actions),
        "shapeKeys": shape_keys,
        "materials": len(bpy.data.materials),
    }


def roundtrip(path: Path, kind: str):
    """Import an export into an empty scene and return what Blender sees."""
    reset()
    try:
        if kind == "glb":
            bpy.ops.import_scene.gltf(filepath=str(path))
        else:
            bpy.ops.import_scene.fbx(filepath=str(path), automatic_bone_orientation=False)
        counts = count_scene()
        counts["status"] = "pass"
        counts["path"] = str(path)
        counts["format"] = kind
        return counts
    except Exception as exc:
        return {"status": "fail", "error": str(exc), "path": str(path), "format": kind}


def make_static(out: Path):
    reset()
    bpy.ops.mesh.primitive_cube_add(size=2.0, location=(0, 0, 1))
    obj = bpy.context.active_object
    obj.name = "static_cube"
    obj.data.materials.append(material("M_static", (0.25, 0.5, 0.85, 1.0), 0.4))
    bpy.ops.object.shade_smooth()
    save_blend(out / "static_cube.blend")
    errors = {}
    glb, fbx = out / "static_cube.glb", out / "static_cube.fbx"
    e = export_glb(glb); errors["glb"] = e
    e = export_fbx(fbx); errors["fbx"] = e
    return {
        "name": "static_cube",
        "source": str(out / "static_cube.blend"),
        "exports": {"glb": str(glb), "fbx": str(fbx)},
        "exportErrors": {k: v for k, v in errors.items() if v},
        "roundtrip": {"glb": roundtrip(glb, "glb"), "fbx": roundtrip(fbx, "fbx")},
    }


def make_rigged(out: Path):
    reset()
    bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=0.45, depth=2.4, location=(0, 0, 1.2))
    mesh_obj = bpy.context.active_object
    mesh_obj.name = "character_body"
    mesh_obj.data.materials.append(material("M_character", (0.8, 0.35, 0.25, 1.0), 0.5))

    arm_data = bpy.data.armatures.new("character_rig")
    arm_obj = bpy.data.objects.new("character_rig", arm_data)
    bpy.context.collection.objects.link(arm_obj)
    bpy.context.view_layer.objects.active = arm_obj
    arm_obj.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    root = arm_data.edit_bones.new("root")
    root.head = (0, 0, 0)
    root.tail = (0, 0, 0.8)
    spine = arm_data.edit_bones.new("spine")
    spine.head = (0, 0, 0.8)
    spine.tail = (0, 0, 1.8)
    spine.parent = root
    hand = arm_data.edit_bones.new("hand")
    hand.head = (0, 0, 1.8)
    hand.tail = (0, 0, 2.5)
    hand.parent = spine
    bpy.ops.object.mode_set(mode="OBJECT")

    for bone_name in ("root", "spine", "hand"):
        mesh_obj.vertex_groups.new(name=bone_name)
    for vertex in mesh_obj.data.vertices:
        z = vertex.co.z
        if z < 0.8:
            mesh_obj.vertex_groups["root"].add([vertex.index], 1.0, "REPLACE")
        elif z < 1.8:
            mesh_obj.vertex_groups["spine"].add([vertex.index], 1.0, "REPLACE")
        else:
            mesh_obj.vertex_groups["hand"].add([vertex.index], 1.0, "REPLACE")
    modifier = mesh_obj.modifiers.new("Armature", "ARMATURE")
    modifier.object = arm_obj
    mesh_obj.parent = arm_obj

    arm_obj.animation_data_create()
    for index, (action_name, angle) in enumerate((("Idle", 0.02), ("Wave", 0.6), ("Turn", -0.4))):
        action = bpy.data.actions.new(action_name)
        arm_obj.animation_data.action = action
        for frame, factor in ((1, 0.0), (12, 1.0), (24, 0.0)):
            bpy.context.scene.frame_set(frame)
            pose = arm_obj.pose.bones["hand"]
            pose.rotation_mode = "XYZ"
            pose.rotation_euler = (angle * factor, 0.0, 0.0)
            pose.keyframe_insert(data_path="rotation_euler", frame=frame)
        action.use_fake_user = True
        track = arm_obj.animation_data.nla_tracks.new()
        track.name = action_name
        strip = track.strips.new(action_name, 1, action)
        strip.action_frame_start = 1
        strip.action_frame_end = 24
        arm_obj.animation_data.action = None
    bpy.context.scene.frame_start = 1
    bpy.context.scene.frame_end = 24
    save_blend(out / "rigged_character.blend")
    errors = {}
    glb, fbx = out / "rigged_character.glb", out / "rigged_character.fbx"
    e = export_glb(glb); errors["glb"] = e
    e = export_fbx(fbx); errors["fbx"] = e
    return {
        "name": "rigged_character",
        "source": str(out / "rigged_character.blend"),
        "exports": {"glb": str(glb), "fbx": str(fbx)},
        "exportErrors": {k: v for k, v in errors.items() if v},
        "roundtrip": {"glb": roundtrip(glb, "glb"), "fbx": roundtrip(fbx, "fbx")},
    }


def make_morph(out: Path):
    reset()
    bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=12, radius=0.7, location=(0, 0, 1.5))
    obj = bpy.context.active_object
    obj.name = "morph_face"
    obj.data.materials.append(material("M_face", (0.85, 0.65, 0.5, 1.0), 0.6))
    obj.shape_key_add(name="Basis", from_mix=False)
    smile = obj.shape_key_add(name="Smile", from_mix=False)
    for point in smile.data:
        if point.co.y > 0.0 and abs(point.co.x) < 0.35:
            point.co.z += 0.08
    bpy.ops.object.shade_smooth()
    save_blend(out / "morph_face.blend")
    errors = {}
    glb, fbx = out / "morph_face.glb", out / "morph_face.fbx"
    e = export_glb(glb); errors["glb"] = e
    e = export_fbx(fbx); errors["fbx"] = e
    return {
        "name": "morph_face",
        "source": str(out / "morph_face.blend"),
        "exports": {"glb": str(glb), "fbx": str(fbx)},
        "exportErrors": {k: v for k, v in errors.items() if v},
        "roundtrip": {"glb": roundtrip(glb, "glb"), "fbx": roundtrip(fbx, "fbx")},
    }


def make_lod(out: Path):
    reset()
    for index, size in enumerate((1.0, 0.9, 0.8)):
        bpy.ops.mesh.primitive_cube_add(size=size * 1.6, location=(index * 2.0, 0, 1.0))
        obj = bpy.context.active_object
        obj.name = f"character_LOD{index}"
        obj.data.materials.append(material(f"M_lod{index}", (0.3 + index * 0.1, 0.4, 0.8, 1.0), 0.5))
    bpy.ops.mesh.primitive_cube_add(size=1.4, location=(0, 3.0, 1.0))
    collision = bpy.context.active_object
    collision.name = "character_COLLISION"
    collision.data.materials.append(material("M_collision", (0.5, 0.5, 0.5, 1.0), 0.9))
    save_blend(out / "lod_set.blend")
    errors = {}
    glb, fbx = out / "lod_set.glb", out / "lod_set.fbx"
    e = export_glb(glb); errors["glb"] = e
    e = export_fbx(fbx); errors["fbx"] = e
    return {
        "name": "lod_set",
        "source": str(out / "lod_set.blend"),
        "exports": {"glb": str(glb), "fbx": str(fbx)},
        "exportErrors": {k: v for k, v in errors.items() if v},
        "roundtrip": {"glb": roundtrip(glb, "glb"), "fbx": roundtrip(fbx, "fbx")},
    }


def main():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=os.environ.get("GYPSY_GOLDEN_OUT", "artifacts/golden"))
    args = parser.parse_args(argv)
    out = Path(args.out).resolve()
    ensure_dir(out)
    report = {"blender": bpy.app.version_string, "out": str(out), "assets": []}
    for maker in (make_static, make_rigged, make_morph, make_lod):
        try:
            report["assets"].append(maker(out))
        except Exception as exc:
            print("GOLDEN ERROR", maker.__name__, exc, file=sys.stderr)
            traceback.print_exc()
            report["assets"].append({"name": maker.__name__, "status": "error", "error": str(exc)})
    report_path = out / "golden-report.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    failed = [a for a in report["assets"] if a.get("status") == "error" or a.get("exportErrors") or any(r.get("status") != "pass" for r in a.get("roundtrip", {}).values())]
    print(f"GOLDEN_REPORT {report_path}")
    print(f"GOLDEN_ASSETS {len(report['assets'])} failed={len(failed)}")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
