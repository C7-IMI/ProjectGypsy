#!/usr/bin/env python3
r"""Generate the ProjectGypsy "Wayfarer" hero: low-poly mesh, atlas texture, rig, 3 actions, GLB/FBX.

Run (Blender 5.2.3, headless):
    "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe" --background --factory-startup \
        --python scripts/hero/generate_wayfarer.py -- --repo <repo-root>

Outputs (all reproducible):
    assets/hero/wayfarer.glb                      tracked runtime asset (embedded texture)
    assets/hero/wayfarer.fbx                      tracked FBX, only when the round-trip is clean
    assets/hero/textures/wayfarer_atlas.png       tracked source texture
    game/assets/hero/wayfarer.glb                 byte-identical mirror for res://
    artifacts/hero/wayfarer.blend                 source scene (ignored)
    artifacts/hero/renders/*.png                  preview renders (ignored)
    artifacts/hero/generation-report.json         machine-readable report (ignored)

No third-party assets, no network, no generative image model. Geometry, texture, rig and animation
are authored in this script. Prints WAYFARER_GEN_OK / WAYFARER_GEN_FAIL and exits 0/1.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import bpy
import numpy as np
from mathutils import Quaternion, Vector

# --------------------------------------------------------------------------------------------------
# constants
# --------------------------------------------------------------------------------------------------

ABSOLUTE_DEFAULT_REPO = Path(__file__).resolve().parents[2]
ASSET_SUBDIR = Path("assets") / "hero"
GAME_SUBDIR = Path("game") / "assets" / "hero"
ART_SUBDIR = Path("artifacts") / "hero"
FPS = 24
TEXTURE_SIZE = 512
TEXTURE_BANDS = 4
BAND_HEIGHT = TEXTURE_SIZE // TEXTURE_BANDS
MAX_INFLUENCES = 4
# production pass: explicit LOD chain, cape bones, atlas companions and a morph target
LOD_SPECS = (("lod1", 0.55), ("lod2", 0.28))
CAPE_BONES = ("cape_a", "cape_b", "cape_c")
TEXTURE_ATLAS_NAME = "wayfarer_atlas"
TEXTURE_NORMAL_NAME = "wayfarer_normal"
TEXTURE_ROUGHMETAL_NAME = "wayfarer_roughmetal"

CLOTH = 0
LEATHER = 1
SKIN = 2
ACCENT = 3
MATERIAL_NAMES = ["Wayfarer_Cloth", "Wayfarer_Leather", "Wayfarer_Skin", "Wayfarer_Accent"]

# (name, parent, head, tail, deform)
BONES = [
    ("root", None, (0.0, 0.0, 0.0), (0.0, 0.0, 0.16), False),
    ("hips", "root", (0.0, 0.0, 0.92), (0.0, 0.0, 1.02), True),
    ("spine", "hips", (0.0, 0.0, 1.02), (0.0, 0.0, 1.20), True),
    ("chest", "spine", (0.0, 0.0, 1.20), (0.0, 0.0, 1.42), True),
    ("neck", "chest", (0.0, 0.0, 1.42), (0.0, 0.0, 1.53), True),
    ("head", "neck", (0.0, 0.0, 1.53), (0.0, 0.0, 1.79), True),
    ("shoulder.R", "chest", (0.03, 0.0, 1.38), (0.16, 0.0, 1.39), True),
    ("upper_arm.R", "shoulder.R", (0.16, 0.0, 1.39), (0.215, 0.0, 1.14), True),
    ("forearm.R", "upper_arm.R", (0.215, 0.0, 1.14), (0.24, 0.0, 0.91), True),
    ("hand.R", "forearm.R", (0.24, 0.0, 0.91), (0.248, 0.0, 0.81), True),
    ("shoulder.L", "chest", (-0.03, 0.0, 1.38), (-0.16, 0.0, 1.39), True),
    ("upper_arm.L", "shoulder.L", (-0.16, 0.0, 1.39), (-0.215, 0.0, 1.14), True),
    ("forearm.L", "upper_arm.L", (-0.215, 0.0, 1.14), (-0.24, 0.0, 0.91), True),
    ("hand.L", "forearm.L", (-0.24, 0.0, 0.91), (-0.248, 0.0, 0.81), True),
    ("thigh.R", "hips", (0.095, 0.0, 0.94), (0.10, 0.0, 0.55), True),
    ("shin.R", "thigh.R", (0.10, 0.0, 0.55), (0.105, 0.0, 0.16), True),
    ("foot.R", "shin.R", (0.105, 0.0, 0.16), (0.105, 0.18, 0.045), True),
    ("thigh.L", "hips", (-0.095, 0.0, 0.94), (-0.10, 0.0, 0.55), True),
    ("shin.L", "thigh.L", (-0.10, 0.0, 0.55), (-0.105, 0.0, 0.16), True),
    ("foot.L", "shin.L", (-0.105, 0.0, 0.16), (-0.105, 0.18, 0.045), True),
    # production pass: a three-bone cape chain hanging behind the torso
    ("cape_a", "chest", (0.0, -0.105, 1.40), (0.0, -0.185, 1.12), True),
    ("cape_b", "cape_a", (0.0, -0.185, 1.12), (0.0, -0.245, 0.84), True),
    ("cape_c", "cape_b", (0.0, -0.245, 0.84), (0.0, -0.29, 0.55), True),
]
BONE_BY_NAME = {name: (Vector(head), Vector(tail)) for name, _parent, head, tail, _deform in BONES}
CONNECTED = {"spine", "chest", "neck", "head", "upper_arm.R", "forearm.R", "hand.R",
             "upper_arm.L", "forearm.L", "hand.L", "shin.R", "foot.R", "shin.L", "foot.L",
             "cape_b", "cape_c"}

ANIM_BONES = [
    "hips", "spine", "chest", "neck", "head",
    "shoulder.L", "upper_arm.L", "forearm.L", "hand.L",
    "shoulder.R", "upper_arm.R", "forearm.R", "hand.R",
    "thigh.L", "shin.L", "foot.L", "thigh.R", "shin.R", "foot.R",
    "cape_a", "cape_b", "cape_c",
]

# rest stance offsets (radians); applied as the neutral pose for every clip
BASE_POSE = {
    "chest": (-0.02, 0.0, 0.0),
    "neck": (0.01, 0.0, 0.0),
    "head": (0.02, 0.0, 0.0),
    "upper_arm.R": (0.02, -0.06, 0.0),
    "forearm.R": (0.16, 0.0, 0.0),
    "hand.R": (0.04, 0.0, 0.0),
    "upper_arm.L": (0.02, 0.06, 0.0),
    "forearm.L": (0.16, 0.0, 0.0),
    "hand.L": (0.04, 0.0, 0.0),
    "thigh.R": (-0.02, 0.0, 0.0),
    "shin.R": (-0.05, 0.0, 0.0),
    "foot.R": (0.07, 0.0, 0.0),
    "thigh.L": (-0.02, 0.0, 0.0),
    "shin.L": (-0.05, 0.0, 0.0),
    "foot.L": (0.07, 0.0, 0.0),
}


def log(message: str) -> None:
    print("[wayfarer] " + message, flush=True)


def iso_now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def srgb_to_linear(value: float) -> float:
    return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4


def rgb(hex_value: str) -> tuple[float, float, float]:
    raw = hex_value.lstrip("#")
    return tuple(srgb_to_linear(int(raw[i:i + 2], 16) / 255.0) for i in (0, 2, 4))


# --------------------------------------------------------------------------------------------------
# texture atlas
# --------------------------------------------------------------------------------------------------

ATLAS_BANDS = [
    # band 0 - weathered ochre cloak
    {"base": "#c99a68", "shadow": "#9a6c45", "pattern": "weave", "noise": 0.022, "roughness": 0.80},
    # band 1 - deep teal tunic / trousers
    {"base": "#4a7f8a", "shadow": "#35636c", "pattern": "twill", "noise": 0.018, "roughness": 0.72},
    # band 2 - warm leather
    {"base": "#7a5136", "shadow": "#543525", "pattern": "leather", "noise": 0.026, "roughness": 0.62},
    # band 3 - sun-worn skin
    {"base": "#d8af8e", "shadow": "#b88766", "pattern": "skin", "noise": 0.011, "roughness": 0.52},
]


def _band_arrays(cfg, rng):
    """Return (base colour multiplier, height field, tile multiplier) for one atlas band."""
    ys = np.arange(BAND_HEIGHT, dtype=np.float32)[:, None]
    xs = np.arange(TEXTURE_SIZE, dtype=np.float32)[None, :]
    tile = np.ones((BAND_HEIGHT, TEXTURE_SIZE), dtype=np.float32)
    height = np.zeros((BAND_HEIGHT, TEXTURE_SIZE), dtype=np.float32)
    if cfg["pattern"] == "weave":
        weft = (ys % 10.0) < 1.8
        warp = (xs % 20.0) < 1.2
        tile *= 1.0 - 0.075 * weft
        tile *= 1.0 - 0.050 * warp
        tile *= 1.0 + 0.028 * np.sin(xs * 0.11 + ys * 0.07)
        # occasional stitch dashes in the shadow tone
        stitch = ((ys > 44) & (ys < 50) & ((xs % 32.0) < 16.0))
        tile = np.where(stitch, 0.82, tile)
        height = 0.55 * weft.astype(np.float32) + 0.75 * warp.astype(np.float32)
        height += 0.12 * np.sin(xs * 0.11 + ys * 0.07).astype(np.float32)
        height = np.where(stitch, 0.35, height)
    elif cfg["pattern"] == "twill":
        diagonal = ((xs + ys) % 14.0) < 3.0
        tile *= 1.0 - 0.065 * diagonal
        tile *= 1.0 + 0.020 * np.sin(ys * 0.17)
        height = 0.8 * diagonal.astype(np.float32)
    elif cfg["pattern"] == "leather":
        grain = (ys % 48.0) < 1.6
        tile *= 1.0 - 0.10 * grain
        scratches = rng.random((BAND_HEIGHT, TEXTURE_SIZE)) < 0.010
        tile = np.where(scratches, tile * 1.22, tile)
        pores = rng.random((BAND_HEIGHT, TEXTURE_SIZE)) < 0.035
        tile = np.where(pores, tile * 0.90, tile)
        height = 0.5 * grain.astype(np.float32) + 0.8 * scratches.astype(np.float32)
        height -= 0.4 * pores.astype(np.float32)
    else:  # skin
        freckles = rng.random((BAND_HEIGHT, TEXTURE_SIZE)) < 0.012
        tile = np.where(freckles, tile * 0.93, tile)
        tile *= 1.0 + 0.012 * np.sin(xs * 0.045) * np.cos(ys * 0.055)
        height = 0.3 * freckles.astype(np.float32)
        height += 0.05 * np.sin(xs * 0.045) * np.cos(ys * 0.055)
    noise = rng.normal(0.0, cfg["noise"], (BAND_HEIGHT, TEXTURE_SIZE)).astype(np.float32)
    base = np.array(rgb(cfg["base"]), dtype=np.float32)
    band_rgb = base[None, None, :] * np.clip(tile, 0.55, 1.18)[..., None]
    band_rgb = band_rgb * (1.0 + noise[..., None])
    return np.clip(band_rgb, 0.0, 1.0), height.astype(np.float32), tile.astype(np.float32)


def _save_texture(name: str, pixels: np.ndarray, colorspace: str, path: Path) -> dict:
    image = bpy.data.images.new(name, width=TEXTURE_SIZE, height=TEXTURE_SIZE, alpha=True)
    image.colorspace_settings.name = colorspace
    image.pixels.foreach_set(np.ascontiguousarray(pixels, dtype=np.float32).ravel())
    image.update()
    image.filepath_raw = str(path.resolve())
    image.file_format = "PNG"
    image.save()
    image.pack()
    return {
        "image": image,
        "path": str(path),
        "name": name,
        "colorspace": colorspace,
        "width": image.size[0],
        "height": image.size[1],
        "bytes": path.stat().st_size,
    }


def build_material_textures(texture_dir: Path) -> dict:
    """Author the 512px base atlas plus normal and roughness/metal maps deterministically."""
    texture_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(20261026)
    base_pixels = np.zeros((TEXTURE_SIZE, TEXTURE_SIZE, 4), dtype=np.float32)
    height_pixels = np.zeros((TEXTURE_SIZE, TEXTURE_SIZE), dtype=np.float32)
    rough_pixels = np.ones((TEXTURE_SIZE, TEXTURE_SIZE), dtype=np.float32)
    metal_pixels = np.zeros((TEXTURE_SIZE, TEXTURE_SIZE), dtype=np.float32)
    for band, cfg in enumerate(ATLAS_BANDS):
        y0 = band * BAND_HEIGHT
        y1 = y0 + BAND_HEIGHT
        band_rgb, height, tile = _band_arrays(cfg, rng)
        base_pixels[y0:y1, :, :3] = band_rgb
        base_pixels[y0:y1, :, 3] = 1.0
        height_pixels[y0:y1, :] = height
        variation = 0.10 * (tile - 1.0) + rng.normal(0.0, 0.012, (BAND_HEIGHT, TEXTURE_SIZE))
        rough_pixels[y0:y1, :] = np.clip(cfg["roughness"] + variation, 0.25, 1.0)
    # tangent-space normal map derived from the height field
    gradient_y, gradient_x = np.gradient(height_pixels)
    normal_x = -gradient_x * 1.2
    normal_y = -gradient_y * 1.2
    normal_z = np.ones_like(normal_x)
    length = np.sqrt(normal_x * normal_x + normal_y * normal_y + normal_z * normal_z)
    normal_pixels = np.stack(
        [normal_x / length * 0.5 + 0.5, normal_y / length * 0.5 + 0.5,
         normal_z / length * 0.5 + 0.5, np.ones_like(normal_x)], axis=-1)
    roughmetal_pixels = np.stack(
        [np.ones_like(rough_pixels), rough_pixels, metal_pixels, np.ones_like(rough_pixels)], axis=-1)

    atlas = _save_texture(TEXTURE_ATLAS_NAME, base_pixels, "sRGB", texture_dir / (TEXTURE_ATLAS_NAME + ".png"))
    normal = _save_texture(TEXTURE_NORMAL_NAME, normal_pixels, "Non-Color", texture_dir / (TEXTURE_NORMAL_NAME + ".png"))
    roughmetal = _save_texture(TEXTURE_ROUGHMETAL_NAME, roughmetal_pixels, "Non-Color",
                               texture_dir / (TEXTURE_ROUGHMETAL_NAME + ".png"))
    return {"base": atlas, "normal": normal, "roughmetal": roughmetal,
            "files": {"base": atlas, "normal": normal, "roughmetal": roughmetal}}


# --------------------------------------------------------------------------------------------------
# geometry builder
# --------------------------------------------------------------------------------------------------

class Builder:
    def __init__(self) -> None:
        self.verts: list[Vector] = []
        self.faces: list[list[int]] = []
        self.face_mat: list[int] = []
        self.face_uv: list[list[tuple[float, float]]] = []
        self.vert_bones: list[tuple[str, ...]] = []

    @staticmethod
    def _uv(point: Vector, band: int) -> tuple[float, float]:
        band_lo = band * (1.0 / TEXTURE_BANDS) + 0.018
        band_hi = (band + 1) * (1.0 / TEXTURE_BANDS) - 0.018
        u = point.x * 1.7 + point.y * 0.6 + point.z * 0.9
        u = u * 1.3
        u = u - math.floor(u)
        v = point.x * 0.5 + point.y * 1.1 + point.z * 1.4
        v = v * 1.7
        v = v - math.floor(v)
        return (u, band_lo + v * (band_hi - band_lo))

    def add(self, verts, faces, material: int, bones: tuple[str, ...], band: int) -> None:
        base = len(self.verts)
        self.verts.extend(Vector(v) for v in verts)
        for face in faces:
            if len(face) < 3:
                continue
            self.faces.append([base + int(i) for i in face])
            self.face_mat.append(material)
            self.face_uv.append([self._uv(self.verts[base + int(i)], band) for i in face])
        self.vert_bones.extend([tuple(bones)] * (len(self.verts) - base))


B = Builder()


def ring(cx: float, cy: float, z: float, rx: float, ry: float, sides: int, phase: float) -> list[tuple[float, float, float]]:
    return [
        (cx + rx * math.cos(phase + 2.0 * math.pi * i / sides),
         cy + ry * math.sin(phase + 2.0 * math.pi * i / sides),
         z)
        for i in range(sides)
    ]


def add_loft(sections, sides: int, material: int, bones: tuple[str, ...], band: int,
             cap_bottom: bool = True, cap_top: bool = True, phase: float | None = None) -> None:
    """sections: [(cx, cy, z, rx, ry), ...] bottom to top; rings lie in XY planes."""
    if phase is None:
        phase = math.pi / sides
    rings = [ring(cx, cy, z, rx, ry, sides, phase) for cx, cy, z, rx, ry in sections]
    verts: list[tuple[float, float, float]] = []
    for r in rings:
        verts.extend(r)
    faces: list[list[int]] = []
    for level in range(len(rings) - 1):
        for i in range(sides):
            a = level * sides + i
            b = level * sides + (i + 1) % sides
            c = (level + 1) * sides + (i + 1) % sides
            d = (level + 1) * sides + i
            faces.append([a, b, c, d])
    if cap_bottom:
        cx, cy, z0, _rx, _ry = sections[0]
        center = len(verts)
        verts.append((cx, cy, z0))
        for i in range(sides):
            faces.append([center, (i + 1) % sides, i])
    if cap_top:
        cx, cy, z1, _rx, _ry = sections[-1]
        center = len(verts)
        verts.append((cx, cy, z1))
        base = (len(rings) - 1) * sides
        for i in range(sides):
            faces.append([center, base + i, base + (i + 1) % sides])
    B.add(verts, faces, material, bones, band)


def add_box(center, size, material: int, bones: tuple[str, ...], band: int, yaw: float = 0.0) -> None:
    cx, cy, cz = center
    sx, sy, sz = (size[0] * 0.5, size[1] * 0.5, size[2] * 0.5)
    cos_y, sin_y = math.cos(yaw), math.sin(yaw)
    local = [
        (-sx, -sy, -sz), (sx, -sy, -sz), (sx, sy, -sz), (-sx, sy, -sz),
        (-sx, -sy, sz), (sx, -sy, sz), (sx, sy, sz), (-sx, sy, sz),
    ]
    verts = [(cx + x * cos_y - y * sin_y, cy + x * sin_y + y * cos_y, cz + z) for x, y, z in local]
    faces = [[0, 3, 2, 1], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]]
    B.add(verts, faces, material, bones, band)


def ellipsoid_geometry(center, radii, segments: int = 10, rings: int = 6):
    cx, cy, cz = center
    rx, ry, rz = radii
    verts = [(cx, cy, cz + rz)]
    for j in range(1, rings):
        phi = math.pi * j / rings
        r = math.sin(phi)
        z = math.cos(phi)
        for i in range(segments):
            theta = 2.0 * math.pi * i / segments
            verts.append((cx + rx * r * math.cos(theta), cy + ry * r * math.sin(theta), cz + rz * z))
    south = len(verts)
    verts.append((cx, cy, cz - rz))
    faces: list[list[int]] = []
    for i in range(segments):
        faces.append([0, 1 + i, 1 + (i + 1) % segments])
    for j in range(rings - 2):
        top = 1 + j * segments
        bottom = 1 + (j + 1) * segments
        for i in range(segments):
            faces.append([bottom + i, bottom + (i + 1) % segments, top + (i + 1) % segments, top + i])
    last = 1 + (rings - 2) * segments
    for i in range(segments):
        faces.append([south, last + (i + 1) % segments, last + i])
    return verts, faces


def add_ellipsoid(center, radii, material: int, bones: tuple[str, ...], band: int,
                  segments: int = 10, rings: int = 6, face_filter=None) -> None:
    verts, faces = ellipsoid_geometry(center, radii, segments, rings)
    if face_filter is not None:
        kept = []
        for face in faces:
            cx = sum(verts[i][0] for i in face) / len(face)
            cy = sum(verts[i][1] for i in face) / len(face)
            cz = sum(verts[i][2] for i in face) / len(face)
            if face_filter(Vector((cx, cy, cz))):
                kept.append(face)
        faces = kept
        used = sorted({i for face in faces for i in face})
        remap = {old: new for new, old in enumerate(used)}
        verts = [verts[i] for i in used]
        faces = [[remap[i] for i in face] for face in faces]
    B.add(verts, faces, material, bones, band)


def add_ribbon(path, widths, material: int, bones: tuple[str, ...], band: int, normal=(0.0, 1.0, 0.0)) -> None:
    points = [Vector(p) for p in path]
    normal_v = Vector(normal).normalized()
    verts: list[tuple[float, float, float]] = []
    for index, point in enumerate(points):
        if index == 0:
            tangent = points[1] - point
        elif index == len(points) - 1:
            tangent = point - points[index - 1]
        else:
            tangent = points[index + 1] - points[index - 1]
        tangent.normalize()
        width_dir = tangent.cross(normal_v)
        if width_dir.length < 1e-6:
            width_dir = Vector((1.0, 0.0, 0.0))
        width_dir.normalize()
        half = widths[index] * 0.5
        left = point - width_dir * half
        right = point + width_dir * half
        verts.append(tuple(left))
        verts.append(tuple(right))
    faces = []
    for row in range(len(points) - 1):
        a = row * 2
        faces.append([a, a + 1, a + 3, a + 2])
    B.add(verts, faces, material, bones, band)


def add_cape() -> None:
    rows, cols = 5, 5
    verts = []
    for row in range(rows + 1):
        t = row / rows
        z = 1.43 - 0.91 * t
        half = 0.18 + 0.09 * t
        base_y = -0.09 - 0.17 * math.sin(t * math.pi * 0.55) - 0.015 * t
        for col in range(cols + 1):
            c = col / cols
            x = -half + 2.0 * half * c
            fold = 0.022 * math.sin(c * 3.1 + t * 1.4) * t
            torn = -0.055 * (math.sin(col * 2.3) * 0.5 + 0.5) * (t ** 2.4)
            verts.append((x, base_y + fold, z + torn))
    stride = cols + 1
    faces = []
    for row in range(rows):
        for col in range(cols):
            a = row * stride + col
            b = a + 1
            c = (row + 1) * stride + col + 1
            d = (row + 1) * stride + col
            faces.append([a, b, c, d])
    B.add(verts, faces, CLOTH, ("chest", "cape_a", "cape_b", "cape_c"), 0)


# --------------------------------------------------------------------------------------------------
# character construction
# --------------------------------------------------------------------------------------------------

def build_character(textures):
    materials = make_materials(textures)

    # torso / tunic
    add_loft(
        [
            (0.0, 0.0, 0.88, 0.150, 0.105),
            (0.0, 0.0, 0.99, 0.166, 0.116),
            (0.0, 0.004, 1.08, 0.158, 0.113),
            (0.0, 0.008, 1.20, 0.188, 0.128),
            (0.0, 0.004, 1.32, 0.214, 0.139),
            (0.0, 0.0, 1.40, 0.192, 0.124),
        ],
        sides=8, material=CLOTH, bones=("hips", "spine", "chest"), band=1,
    )
    # tabard panel (ochre)
    add_ribbon(
        [(0.0, 0.132, 1.365), (0.0, 0.143, 1.22), (0.0, 0.143, 1.08), (0.0, 0.127, 0.965)],
        [0.165, 0.195, 0.215, 0.235], CLOTH, ("chest", "spine", "hips"), 0,
    )
    # neck
    add_loft([(0.0, 0.0, 1.425, 0.050, 0.055), (0.0, 0.0, 1.555, 0.047, 0.052)],
             sides=8, material=SKIN, bones=("neck", "chest"), band=3, cap_bottom=False, cap_top=False)
    # head + face
    add_ellipsoid((0.0, 0.012, 1.675), (0.098, 0.098, 0.118), SKIN, ("head", "neck"), 3, 10, 6)
    add_box((0.0, 0.118, 1.655), (0.030, 0.032, 0.052), SKIN, ("head",), 3)
    add_box((0.0, 0.114, 1.612), (0.050, 0.012, 0.009), LEATHER, ("head",), 2)
    for side in (-1.0, 1.0):
        add_box((side * 0.040, 0.105, 1.698), (0.032, 0.020, 0.016), ACCENT, ("head",), 3)
    # hood (open at the face) and point
    add_ellipsoid((0.0, -0.020, 1.705), (0.137, 0.143, 0.168), CLOTH, ("head", "neck"), 0, 12, 7,
                  face_filter=lambda c: (c.z > 1.715 or c.y < 0.030))
    add_loft([(0.0, -0.055, 1.795, 0.055, 0.055), (0.0, -0.112, 1.905, 0.006, 0.006)],
             sides=6, material=CLOTH, bones=("head",), band=0)
    # headband / brow shadow
    add_loft([(0.0, 0.008, 1.728, 0.106, 0.112), (0.0, 0.008, 1.756, 0.101, 0.107)],
             sides=10, material=LEATHER, bones=("head",), band=2, cap_bottom=False, cap_top=False)
    # scarf around the neck + short tail
    add_loft([(0.0, 0.0, 1.425, 0.073, 0.078), (0.0, 0.0, 1.487, 0.066, 0.071)],
             sides=8, material=CLOTH, bones=("neck", "chest"), band=1, cap_bottom=False, cap_top=False)
    add_ribbon([(-0.052, 0.095, 1.44), (-0.060, 0.118, 1.33), (-0.042, 0.126, 1.21)],
               [0.055, 0.072, 0.050], CLOTH, ("neck", "chest"), 1)

    # shoulder mantle (poncho collar)
    add_loft([(0.0, 0.0, 1.455, 0.120, 0.100), (0.0, -0.006, 1.365, 0.238, 0.170),
              (0.0, -0.010, 1.290, 0.296, 0.202)],
             sides=10, material=CLOTH, bones=("chest", "spine"), band=0, cap_bottom=False, cap_top=False)

    # cape
    add_cape()

    # belt + buckle
    add_loft([(0.0, 0.004, 0.985, 0.171, 0.121), (0.0, 0.004, 1.038, 0.169, 0.119)],
             sides=10, material=LEATHER, bones=("hips", "spine"), band=2, cap_bottom=False, cap_top=False)
    add_box((0.0, 0.125, 1.012), (0.052, 0.020, 0.045), ACCENT, ("hips",), 3)
    # chest shard
    add_ellipsoid((0.0, 0.146, 1.292), (0.024, 0.012, 0.038), ACCENT, ("chest",), 3, 4, 2)

    # satchel on the character's left hip
    add_box((-0.205, -0.012, 0.875), (0.118, 0.088, 0.150), LEATHER, ("hips",), 2)
    add_box((-0.205, -0.058, 0.930), (0.122, 0.020, 0.062), LEATHER, ("hips",), 2)
    # diagonal chest strap
    add_ribbon(
        [(0.170, 0.128, 1.375), (0.060, 0.146, 1.250), (-0.060, 0.146, 1.125), (-0.172, 0.096, 1.005)],
        [0.042, 0.042, 0.042, 0.042], LEATHER, ("chest", "spine", "hips"), 2,
    )

    # arms
    for side, suffix in ((1.0, "R"), (-1.0, "L")):
        upper = ("chest", "shoulder." + suffix, "upper_arm." + suffix, "forearm." + suffix)
        lower = ("upper_arm." + suffix, "forearm." + suffix, "hand." + suffix)
        add_loft(
            [
                (side * 0.160, 0.0, 1.380, 0.062, 0.064),
                (side * 0.190, 0.0, 1.280, 0.055, 0.057),
                (side * 0.215, 0.0, 1.150, 0.049, 0.050),
            ],
            sides=6, material=CLOTH, bones=upper, band=1,
        )
        add_loft(
            [
                (side * 0.215, 0.0, 1.145, 0.046, 0.047),
                (side * 0.228, 0.0, 1.030, 0.041, 0.042),
                (side * 0.240, 0.0, 0.915, 0.035, 0.036),
            ],
            sides=6, material=CLOTH, bones=lower, band=1,
        )
        # bracer
        add_loft([(side * 0.226, 0.0, 1.075, 0.052, 0.053), (side * 0.238, 0.0, 0.958, 0.046, 0.047)],
                 sides=6, material=LEATHER, bones=("forearm." + suffix, "hand." + suffix), band=2,
                 cap_bottom=False, cap_top=False)
        add_box((side * 0.276, 0.0, 1.030), (0.016, 0.030, 0.030), ACCENT,
                ("forearm." + suffix,), 3)
        # shoulder pad
        add_loft(
            [
                (side * 0.175, -0.002, 1.425, 0.072, 0.078),
                (side * 0.198, -0.002, 1.365, 0.088, 0.092),
                (side * 0.204, -0.002, 1.305, 0.072, 0.076),
            ],
            sides=8, material=CLOTH, bones=("shoulder." + suffix, "upper_arm." + suffix, "chest"), band=0,
        )
        # hand
        add_box((side * 0.248, 0.010, 0.862), (0.072, 0.078, 0.108), SKIN,
                ("hand." + suffix, "forearm." + suffix), 3)

    # legs
    for side, suffix in ((1.0, "R"), (-1.0, "L")):
        add_loft(
            [
                (side * 0.092, 0.0, 0.925, 0.076, 0.085),
                (side * 0.096, 0.0, 0.760, 0.071, 0.078),
                (side * 0.100, 0.0, 0.575, 0.061, 0.066),
            ],
            sides=6, material=CLOTH, bones=("hips", "thigh." + suffix, "shin." + suffix), band=1,
        )
        add_loft(
            [
                (side * 0.100, 0.0, 0.560, 0.057, 0.060),
                (side * 0.103, 0.0, 0.380, 0.050, 0.053),
                (side * 0.105, 0.0, 0.185, 0.044, 0.047),
            ],
            sides=6, material=CLOTH, bones=("thigh." + suffix, "shin." + suffix, "foot." + suffix), band=1,
        )
        # boot
        add_loft([(side * 0.105, 0.005, 0.225, 0.066, 0.070), (side * 0.105, 0.012, 0.135, 0.071, 0.078)],
                 sides=6, material=LEATHER, bones=("shin." + suffix, "foot." + suffix), band=2,
                 cap_bottom=False, cap_top=True)
        add_box((side * 0.105, 0.052, 0.072), (0.135, 0.255, 0.145), LEATHER,
                ("foot." + suffix, "shin." + suffix), 2)

    return materials


def make_materials(textures):
    materials = []
    atlas_image = textures["base"]["image"]
    normal_image = textures["normal"]["image"]
    roughmetal_image = textures["roughmetal"]["image"]

    def base(name):
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
        mat.use_backface_culling = False
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links
        bsdf = nodes.get("Principled BSDF")
        # painted base-colour atlas (sRGB)
        tex = nodes.new("ShaderNodeTexImage")
        tex.image = atlas_image
        tex.interpolation = "Linear"
        tex.location = (-560, 260)
        links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
        # tangent-space normal map (Non-Color)
        normal_tex = nodes.new("ShaderNodeTexImage")
        normal_tex.image = normal_image
        normal_tex.interpolation = "Linear"
        normal_tex.location = (-560, -40)
        normal_map = nodes.new("ShaderNodeNormalMap")
        normal_map.location = (-300, -40)
        normal_map.inputs["Strength"].default_value = 1.0
        links.new(normal_tex.outputs["Color"], normal_map.inputs["Color"])
        links.new(normal_map.outputs["Normal"], bsdf.inputs["Normal"])
        # baked roughness (G) / metallic (B) map, glTF metallic-roughness layout
        orm_tex = nodes.new("ShaderNodeTexImage")
        orm_tex.image = roughmetal_image
        orm_tex.interpolation = "Linear"
        orm_tex.location = (-560, -360)
        separate = nodes.new("ShaderNodeSeparateColor")
        separate.location = (-300, -360)
        links.new(orm_tex.outputs["Color"], separate.inputs["Color"])
        links.new(separate.outputs["Green"], bsdf.inputs["Roughness"])
        links.new(separate.outputs["Blue"], bsdf.inputs["Metallic"])
        materials.append(mat)
        return mat

    base(MATERIAL_NAMES[0])
    base(MATERIAL_NAMES[1])
    base(MATERIAL_NAMES[2])

    accent = bpy.data.materials.new(MATERIAL_NAMES[3])
    accent.use_nodes = True
    accent.use_backface_culling = False
    bsdf = accent.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (0.015, 0.055, 0.070, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.35
    bsdf.inputs["Metallic"].default_value = 0.05
    emission = rgb("#2fe3ff")
    try:
        bsdf.inputs["Emission Color"].default_value = (*emission, 1.0)
        bsdf.inputs["Emission Strength"].default_value = 2.0
    except KeyError:
        bsdf.inputs["Emission"].default_value = (*emission, 1.0)
        bsdf.inputs["Emission Strength"].default_value = 2.0
    materials.append(accent)
    return materials


# --------------------------------------------------------------------------------------------------
# mesh, armature, skinning
# --------------------------------------------------------------------------------------------------

def create_mesh_object(materials):
    mesh = bpy.data.meshes.new("Wayfarer_Mesh")
    mesh.from_pydata([tuple(v) for v in B.verts], [], B.faces)
    mesh.validate(verbose=False)
    for mat in materials:
        mesh.materials.append(mat)
    for index, poly in enumerate(mesh.polygons):
        poly.material_index = B.face_mat[index]
        poly.use_smooth = False
    uv_layer = mesh.uv_layers.new(name="UVMap")
    for poly in mesh.polygons:
        for loop_index in range(poly.loop_start, poly.loop_start + poly.loop_total):
            corner = loop_index - poly.loop_start
            uv_layer.data[loop_index].uv = B.face_uv[poly.index][corner]
    mesh.update()
    obj = bpy.data.objects.new("Wayfarer_Mesh", mesh)
    bpy.context.collection.objects.link(obj)
    return obj


def create_armature():
    arm_data = bpy.data.armatures.new("Wayfarer_Rig")
    arm_obj = bpy.data.objects.new("Wayfarer_Rig", arm_data)
    bpy.context.collection.objects.link(arm_obj)
    bpy.context.view_layer.objects.active = arm_obj
    arm_obj.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    for name, parent, head, tail, deform in BONES:
        bone = arm_data.edit_bones.new(name)
        bone.head = head
        bone.tail = tail
        bone.roll = 0.0
        bone.use_deform = deform
    for name, parent, _head, _tail, _deform in BONES:
        if parent:
            bone = arm_data.edit_bones[name]
            bone.parent = arm_data.edit_bones[parent]
            bone.use_connect = name in CONNECTED
    bpy.ops.object.mode_set(mode="OBJECT")
    for bone in arm_data.bones:
        bone.use_deform = dict((b[0], b[4]) for b in BONES)[bone.name]
    arm_obj.show_in_front = True
    return arm_obj


def segment_distance(point: Vector, head: Vector, tail: Vector) -> float:
    ab = tail - head
    length_sq = ab.length_squared
    if length_sq < 1e-9:
        return (point - head).length
    t = max(0.0, min(1.0, (point - head).dot(ab) / length_sq))
    return (point - (head + ab * t)).length


def skin(obj, arm_obj) -> dict:
    groups = {}
    for name, _parent, _head, _tail, deform in BONES:
        if deform:
            groups[name] = obj.vertex_groups.new(name=name)
    influence_counts = []
    min_sum = 9.9
    max_sum = 0.0
    zero_weight_vertices = 0
    for index, point in enumerate(B.verts):
        candidates = B.vert_bones[index]
        scored = []
        for bone_name in candidates:
            head, tail = BONE_BY_NAME[bone_name]
            distance = segment_distance(point, head, tail)
            scored.append((1.0 / ((distance + 0.018) ** 4.0), bone_name))
        scored.sort(reverse=True)
        scored = scored[:MAX_INFLUENCES]
        total = sum(value for value, _name in scored)
        if total <= 0.0:
            zero_weight_vertices += 1
            scored = [(1.0, candidates[0])]
            total = 1.0
        kept = [(value / total, name) for value, name in scored if value / total >= 0.025]
        renorm = sum(value for value, _name in kept)
        if not kept:
            kept = [(1.0, candidates[0])]
            renorm = 1.0
        weight_sum = 0.0
        for value, bone_name in kept:
            weight = value / renorm
            groups[bone_name].add([index], weight, "REPLACE")
            weight_sum += weight
        influence_counts.append(len(kept))
        min_sum = min(min_sum, weight_sum)
        max_sum = max(max_sum, weight_sum)
    modifier = obj.modifiers.new("Armature", "ARMATURE")
    modifier.object = arm_obj
    modifier.use_vertex_groups = True
    obj.parent = arm_obj
    obj.matrix_parent_inverse = arm_obj.matrix_world.inverted()
    return {
        "vertices": len(B.verts),
        "triangles": sum(len(face) - 2 for face in B.faces),
        "faces": len(B.faces),
        "zeroWeightVertices": zero_weight_vertices,
        "minWeightSum": round(min_sum, 6),
        "maxWeightSum": round(max_sum, 6),
        "maxInfluences": max(influence_counts) if influence_counts else 0,
        "meanInfluences": round(sum(influence_counts) / max(1, len(influence_counts)), 3),
    }


def add_facial_shape_key(obj) -> dict:
    """Add one safe facial morph target ("Smile") on the mouth-plate vertices only."""
    if obj.data.shape_keys is None:
        obj.shape_key_add(name="Basis", from_mix=False)
    key = obj.shape_key_add(name="Smile", from_mix=False)
    moved = 0
    max_offset = 0.0
    for vertex in key.data:
        co = vertex.co
        # mouth plate and lower cheeks: a few millimetres, never structural geometry
        if 1.585 <= co.z <= 1.640 and co.y >= 0.095 and abs(co.x) <= 0.060:
            rise = 0.005 * (1.0 - abs(co.x) / 0.060) + 0.002
            vertex.co.z += rise
            vertex.co.y += 0.0015
            moved += 1
            max_offset = max(max_offset, rise + 0.0015)
    return {"name": "Smile", "movedVertices": moved, "maxOffset": round(max_offset, 5)}


def triangle_count(obj) -> int:
    return sum(len(polygon.vertices) - 2 for polygon in obj.data.polygons)


def select_only(objects) -> None:
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.hide_set(False)
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]


def create_lod_meshes(obj, arm_obj) -> list:
    """Duplicate the skinned mesh and decimate copies into an explicit LOD chain."""
    lods = []
    for level, ratio in LOD_SPECS:
        copy = obj.copy()
        copy.data = obj.data.copy()
        copy.name = "Wayfarer_Mesh_" + level.upper()
        copy.data.name = copy.name + "_mesh"
        bpy.context.collection.objects.link(copy)
        for modifier in list(copy.modifiers):
            copy.modifiers.remove(modifier)
        select_only([copy])
        decimate = copy.modifiers.new("Decimate", "DECIMATE")
        decimate.decimate_type = "COLLAPSE"
        decimate.ratio = ratio
        decimate.use_collapse_triangulate = True
        bpy.ops.object.modifier_apply(modifier=decimate.name)
        copy.data.validate(verbose=False)
        copy.data.update()
        modifier = copy.modifiers.new("Armature", "ARMATURE")
        modifier.object = arm_obj
        modifier.use_vertex_groups = True
        copy.parent = arm_obj
        copy.matrix_parent_inverse = arm_obj.matrix_world.inverted()
        lods.append({"level": level, "object": copy, "ratio": ratio,
                     "triangles": triangle_count(copy), "vertices": len(copy.data.vertices)})
    select_only([arm_obj, obj])
    return lods


# --------------------------------------------------------------------------------------------------
# animation
# --------------------------------------------------------------------------------------------------

def rest_axis(arm_obj, bone_name: str, axis) -> Vector:
    matrix = arm_obj.data.bones[bone_name].matrix_local.to_3x3()
    return (matrix.inverted() @ Vector(axis)).normalized()


def rotation_quat(arm_obj, bone_name: str, rx: float, ry: float, rz: float) -> Quaternion:
    result = Quaternion((1.0, 0.0, 0.0, 0.0))
    for axis, angle in (((1.0, 0.0, 0.0), rx), ((0.0, 1.0, 0.0), ry), ((0.0, 0.0, 1.0), rz)):
        if abs(angle) > 1e-8:
            result = result @ Quaternion(rest_axis(arm_obj, bone_name, axis), angle)
    return result


def local_location(arm_obj, bone_name: str, delta) -> Vector:
    matrix = arm_obj.data.bones[bone_name].matrix_local.to_3x3()
    return matrix.inverted() @ Vector(delta)


def action_fcurves(action):
    """Blender 5.x layered actions expose F-curves through channelbags, not Action.fcurves."""
    for layer in action.layers:
        for strip in layer.strips:
            for channelbag in strip.channelbags:
                for fcurve in channelbag.fcurves:
                    yield fcurve


def pose_with_base(overrides) -> dict:
    pose = {name: tuple(BASE_POSE.get(name, (0.0, 0.0, 0.0))) for name in ANIM_BONES}
    for name, value in overrides.items():
        pose[name] = tuple(value[:3])
    return pose


def idle_sampler(frame: int):
    phase = 2.0 * math.pi * (frame - 1) / 72.0
    breath = math.sin(phase)
    sway = math.sin(phase * 0.5)
    overrides = {
        "spine": (-0.02 + 0.012 * breath, 0.0, -0.020 * sway),
        "chest": (-0.03 + 0.020 * breath, 0.0, 0.030 * sway),
        "neck": (0.012, 0.0, -0.012 * sway),
        "head": (0.02 - 0.022 * breath, 0.0, 0.075 * sway),
        "upper_arm.R": (0.03 + 0.030 * breath, -0.06, 0.0),
        "upper_arm.L": (0.03 - 0.030 * breath, 0.06, 0.0),
        "forearm.R": (0.16 + 0.020 * breath, 0.0, 0.0),
        "forearm.L": (0.16 - 0.020 * breath, 0.0, 0.0),
        "thigh.R": (-0.02, 0.0, 0.0),
        "thigh.L": (-0.02, 0.0, 0.0),
        "shin.R": (-0.05, 0.0, 0.0),
        "shin.L": (-0.05, 0.0, 0.0),
        "cape_a": (0.012 * breath, 0.0, 0.006 * sway),
        "cape_b": (0.020 * breath, 0.0, 0.010 * sway),
        "cape_c": (0.030 * breath, 0.0, 0.014 * sway),
    }
    pose = pose_with_base(overrides)
    hips_loc = (0.008 * sway, 0.0, 0.006 * breath)
    return pose, hips_loc


def run_sampler(frame: int):
    phase = 2.0 * math.pi * (frame - 1) / 24.0
    sin = math.sin(phase)
    cos = math.cos(phase)

    def leg(leg_phase):
        thigh = 0.74 * math.sin(leg_phase)
        knee = -0.16 - 0.78 * max(0.0, -math.sin(leg_phase))
        foot = 0.16 * math.sin(leg_phase + 0.6) - 0.04
        return thigh, knee, foot

    thigh_r, knee_r, foot_r = leg(phase + math.pi)
    thigh_l, knee_l, foot_l = leg(phase)
    overrides = {
        "hips": (-0.04, 0.0, 0.11 * sin),
        "spine": (-0.135, 0.0, -0.075 * sin),
        "chest": (-0.065, 0.0, 0.095 * sin),
        "neck": (0.06, 0.0, -0.02 * sin),
        "head": (0.10, 0.0, -0.03 * sin),
        "shoulder.R": (0.0, 0.0, 0.05 * sin),
        "shoulder.L": (0.0, 0.0, -0.05 * sin),
        "upper_arm.R": (0.70 * sin, -0.08, 0.0),
        "upper_arm.L": (-0.70 * sin, 0.08, 0.0),
        "forearm.R": (1.05 + 0.20 * sin, 0.0, 0.0),
        "forearm.L": (1.05 - 0.20 * sin, 0.0, 0.0),
        "hand.R": (0.05, 0.0, 0.0),
        "hand.L": (0.05, 0.0, 0.0),
        "thigh.R": (thigh_r, 0.0, 0.02),
        "shin.R": (knee_r, 0.0, 0.0),
        "foot.R": (foot_r, 0.0, 0.0),
        "thigh.L": (thigh_l, 0.0, -0.02),
        "shin.L": (knee_l, 0.0, 0.0),
        "foot.L": (foot_l, 0.0, 0.0),
        "cape_a": (-0.22 - 0.06 * sin, 0.0, 0.05 * sin),
        "cape_b": (-0.30 - 0.08 * math.sin(phase + 0.4), 0.0, 0.07 * sin),
        "cape_c": (-0.40 - 0.10 * math.sin(phase + 0.8), 0.0, 0.09 * sin),
    }
    pose = pose_with_base(overrides)
    hips_loc = (0.012 * sin, 0.004, 0.022 * math.cos(2.0 * phase) + 0.006)
    return pose, hips_loc


REACH_KEYS = {
    1: ({}, (0.0, 0.0, 0.0)),
    7: ({
        "spine": (-0.055, 0.0, -0.030), "chest": (-0.035, 0.0, -0.120),
        "neck": (0.02, 0.0, -0.060), "head": (0.04, 0.0, -0.100),
        "shoulder.R": (0.02, 0.0, -0.05),
        "upper_arm.R": (0.52, -0.18, 0.04), "forearm.R": (0.62, 0.0, 0.0), "hand.R": (-0.08, 0.0, 0.0),
        "upper_arm.L": (-0.14, 0.08, 0.0), "forearm.L": (0.24, 0.0, 0.0),
        "thigh.R": (0.02, 0.0, 0.0), "shin.R": (-0.16, 0.0, 0.0),
        "thigh.L": (-0.06, 0.0, 0.0), "shin.L": (-0.10, 0.0, 0.0),
    }, (0.0, 0.012, -0.020)),
    13: ({
        "spine": (-0.100, 0.0, -0.080), "chest": (-0.060, 0.0, -0.245),
        "neck": (0.08, 0.0, -0.115), "head": (0.13, 0.0, -0.180),
        "shoulder.R": (0.05, 0.0, -0.10),
        "upper_arm.R": (1.36, -0.22, 0.06), "forearm.R": (0.55, 0.0, 0.0), "hand.R": (0.12, 0.0, 0.0),
        "upper_arm.L": (-0.30, 0.20, 0.0), "forearm.L": (0.40, 0.0, 0.0),
        "thigh.R": (-0.12, 0.0, 0.02), "shin.R": (-0.34, 0.0, 0.0), "foot.R": (0.10, 0.0, 0.0),
        "thigh.L": (0.18, 0.0, -0.02), "shin.L": (-0.26, 0.0, 0.0), "foot.L": (0.13, 0.0, 0.0),
    }, (0.0, 0.036, -0.040)),
    21: ({
        "spine": (-0.120, 0.0, -0.120), "chest": (-0.095, 0.0, -0.300),
        "neck": (0.10, 0.0, -0.150), "head": (0.22, 0.0, -0.205),
        "shoulder.R": (0.08, 0.0, -0.12),
        "upper_arm.R": (1.74, -0.25, 0.08), "forearm.R": (0.28, 0.0, 0.0), "hand.R": (0.10, 0.0, 0.0),
        "upper_arm.L": (-0.44, 0.26, 0.0), "forearm.L": (0.50, 0.0, 0.0),
        "thigh.R": (-0.16, 0.0, 0.02), "shin.R": (-0.42, 0.0, 0.0), "foot.R": (0.12, 0.0, 0.0),
        "thigh.L": (0.22, 0.0, -0.02), "shin.L": (-0.32, 0.0, 0.0), "foot.L": (0.16, 0.0, 0.0),
    }, (0.0, 0.058, -0.050)),
    27: ({
        "spine": (-0.115, 0.0, -0.115), "chest": (-0.090, 0.0, -0.290),
        "neck": (0.10, 0.0, -0.145), "head": (0.20, 0.0, -0.195),
        "shoulder.R": (0.08, 0.0, -0.12),
        "upper_arm.R": (1.70, -0.24, 0.08), "forearm.R": (0.30, 0.0, 0.0), "hand.R": (0.24, 0.0, 0.0),
        "upper_arm.L": (-0.40, 0.25, 0.0), "forearm.L": (0.48, 0.0, 0.0),
        "thigh.R": (-0.14, 0.0, 0.02), "shin.R": (-0.40, 0.0, 0.0), "foot.R": (0.11, 0.0, 0.0),
        "thigh.L": (0.20, 0.0, -0.02), "shin.L": (-0.30, 0.0, 0.0), "foot.L": (0.15, 0.0, 0.0),
    }, (0.0, 0.054, -0.046)),
    35: ({
        "spine": (-0.070, 0.0, -0.055), "chest": (-0.045, 0.0, -0.130),
        "neck": (0.05, 0.0, -0.060), "head": (0.10, 0.0, -0.080),
        "upper_arm.R": (0.82, -0.16, 0.02), "forearm.R": (0.55, 0.0, 0.0), "hand.R": (0.06, 0.0, 0.0),
        "upper_arm.L": (-0.18, 0.12, 0.0), "forearm.L": (0.28, 0.0, 0.0),
        "thigh.R": (-0.06, 0.0, 0.0), "shin.R": (-0.18, 0.0, 0.0),
        "thigh.L": (0.08, 0.0, 0.0), "shin.L": (-0.12, 0.0, 0.0),
    }, (0.0, 0.024, -0.028)),
    43: ({
        "spine": (-0.030, 0.0, -0.015), "chest": (-0.025, 0.0, -0.040),
        "neck": (0.015, 0.0, -0.015), "head": (0.035, 0.0, -0.020),
        "upper_arm.R": (0.20, -0.10, 0.0), "forearm.R": (0.30, 0.0, 0.0),
        "upper_arm.L": (-0.05, 0.08, 0.0), "forearm.L": (0.20, 0.0, 0.0),
        "thigh.R": (-0.02, 0.0, 0.0), "shin.R": (-0.07, 0.0, 0.0),
        "thigh.L": (0.01, 0.0, 0.0), "shin.L": (-0.06, 0.0, 0.0),
    }, (0.0, 0.006, -0.006)),
    49: ({}, (0.0, 0.0, 0.0)),
}


def reach_sampler(frame: int):
    # exact key poses; intermediates are left to Blender's interpolation
    if frame in REACH_KEYS:
        overrides, hips_loc = REACH_KEYS[frame]
    else:
        lower = max(key for key in REACH_KEYS if key <= frame)
        overrides, hips_loc = REACH_KEYS[lower]
    # cape reacts to the torso twist with a smooth bell over the one-shot
    overrides = dict(overrides)
    bell = math.sin(math.pi * max(0.0, min(1.0, (frame - 1) / 48.0)))
    overrides.setdefault("cape_a", (-0.05 * bell, 0.0, 0.010 * bell))
    overrides.setdefault("cape_b", (-0.08 * bell, 0.0, 0.016 * bell))
    overrides.setdefault("cape_c", (-0.11 * bell, 0.0, 0.022 * bell))
    return pose_with_base(overrides), hips_loc


def create_action(arm_obj, name: str, frames, sampler, loop: bool):
    action = bpy.data.actions.new(name)
    action.use_fake_user = True
    arm_obj.animation_data.action = action
    for frame in frames:
        pose, hips_loc = sampler(frame)
        for bone_name in ANIM_BONES:
            pb = arm_obj.pose.bones[bone_name]
            pb.rotation_mode = "QUATERNION"
            rx, ry, rz = pose[bone_name]
            pb.rotation_quaternion = rotation_quat(arm_obj, bone_name, rx, ry, rz)
            pb.keyframe_insert("rotation_quaternion", frame=frame)
        hips = arm_obj.pose.bones["hips"]
        hips.location = local_location(arm_obj, "hips", hips_loc)
        hips.keyframe_insert("location", frame=frame)
    action.use_frame_range = True
    action.frame_start = float(frames[0])
    action.frame_end = float(frames[-1])
    arm_obj.animation_data.action = None
    track = arm_obj.animation_data.nla_tracks.new()
    track.name = name
    strip = track.strips.new(name, int(frames[0]), action)
    strip.name = name
    strip.action_frame_start = float(frames[0])
    strip.action_frame_end = float(frames[-1])
    return action


def create_animations(arm_obj):
    arm_obj.animation_data_create()
    specs = [
        ("idle", [1, 10, 19, 28, 37, 46, 55, 64, 73], idle_sampler, True),
        ("run", [1, 4, 7, 10, 13, 16, 19, 22, 25], run_sampler, True),
        ("reach", [1, 7, 13, 21, 27, 35, 43, 49], reach_sampler, False),
    ]
    actions = {}
    for name, frames, sampler, loop in specs:
        actions[name] = create_action(arm_obj, name, frames, sampler, loop)
    bpy.context.scene.render.fps = FPS
    bpy.context.scene.frame_start = 1
    bpy.context.scene.frame_end = 73
    for action in actions.values():
        try:
            keys = [float(key.co.x) for fcurve in action_fcurves(action) for key in fcurve.keyframe_points]
            if keys:
                action.use_frame_range = True
                action.frame_start = min(keys)
                action.frame_end = max(keys)
        except Exception:
            pass
    return actions


# --------------------------------------------------------------------------------------------------
# export
# --------------------------------------------------------------------------------------------------

def export_glb(path: Path, morph: bool = True) -> dict:
    record = {"path": str(path), "args": {}, "errors": [], "morph": morph}
    full = dict(
        filepath=str(path),
        export_format="GLB",
        export_apply=True,
        export_yup=True,
        use_selection=True,
        export_animations=True,
        export_skins=True,
        export_morph=morph,
        export_morph_normal=False,
        export_leaf_bone=False,
        export_materials="EXPORT",
        export_nla_strips=True,
        export_force_sampling=True,
        export_frame_range=False,
        export_image_format="AUTO",
        export_cameras=False,
        export_lights=False,
    )
    try:
        bpy.ops.export_scene.gltf(**full)
        record["args"] = full
    except TypeError as exc:
        record["errors"].append("full arg set rejected: " + str(exc))
        minimal = dict(
            filepath=str(path), export_format="GLB", export_apply=True, export_yup=True,
            use_selection=True, export_animations=True, export_skins=True,
            export_materials="EXPORT", export_nla_strips=True, export_force_sampling=True,
        )
        if morph:
            minimal["export_morph"] = True
        bpy.ops.export_scene.gltf(**minimal)
        record["args"] = minimal
    record["bytes"] = path.stat().st_size if path.exists() else 0
    return record


def export_fbx(path: Path) -> dict:
    record = {"path": str(path), "bytes": 0, "errors": []}
    kwargs = dict(
        filepath=str(path), object_types={"ARMATURE", "MESH"}, use_mesh_modifiers=True,
        add_leaf_bones=False, bake_anim=True, bake_anim_use_all_actions=False,
        bake_anim_use_nla_strips=True, bake_anim_force_startend_keying=True,
        bake_anim_step=1.0, bake_anim_simplify_factor=0.0, path_mode="COPY",
        embed_textures=True, axis_forward="-Z", axis_up="Y",
        apply_scale_options="FBX_SCALE_ALL", use_selection=True,
    )
    try:
        bpy.ops.export_scene.fbx(**kwargs)
    except TypeError as exc:
        record["errors"].append("full arg set rejected: " + str(exc))
        kwargs.pop("embed_textures", None)
        bpy.ops.export_scene.fbx(**kwargs)
    record["bytes"] = path.stat().st_size if path.exists() else 0
    return record


# --------------------------------------------------------------------------------------------------
# preview render
# --------------------------------------------------------------------------------------------------

def add_preview_scene(actions):
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 24
    scene.cycles.use_denoising = True
    scene.render.resolution_x = 640
    scene.render.resolution_y = 640
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    try:
        scene.view_settings.look = "AgX - Medium High Contrast"
    except Exception:
        pass

    world = bpy.data.worlds.new("Wayfarer_PreviewWorld")
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs["Color"].default_value = (0.035, 0.050, 0.080, 1.0)
        bg.inputs["Strength"].default_value = 0.7
    scene.world = world

    bpy.ops.mesh.primitive_plane_add(size=20.0, location=(0.0, 0.0, -0.002))
    floor = bpy.context.active_object
    floor.name = "Preview_Ground"
    floor_mat = bpy.data.materials.new("Preview_Ground")
    floor_mat.use_nodes = True
    bsdf = floor_mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (0.055, 0.065, 0.085, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.85
    floor.data.materials.append(floor_mat)

    def area(name, location, energy, size, color):
        light = bpy.data.lights.new(name, "AREA")
        light.energy = energy
        light.shape = "DISK"
        light.size = size
        light.color = color
        obj = bpy.data.objects.new(name, light)
        bpy.context.collection.objects.link(obj)
        obj.location = location
        direction = Vector((0.0, 0.0, 1.0)) - Vector(location)
        obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
        return obj

    area("Preview_Key", (3.0, 3.4, 4.2), 620.0, 3.5, (1.0, 0.88, 0.72))
    area("Preview_Fill", (-3.4, 2.2, 2.2), 230.0, 4.0, (0.62, 0.78, 1.0))
    area("Preview_Rim", (-0.8, -3.8, 3.6), 420.0, 2.5, (0.55, 0.9, 1.0))

    camera_data = bpy.data.cameras.new("Preview_Camera")
    camera = bpy.data.objects.new("Preview_Camera", camera_data)
    bpy.context.collection.objects.link(camera)
    camera_data.lens = 58.0
    scene.camera = camera

    # mute NLA while rendering a single action, then restore
    tracks = list(bpy.context.view_layer.objects["Wayfarer_Rig"].animation_data.nla_tracks)
    for track in tracks:
        track.mute = True
    default_action = bpy.context.view_layer.objects["Wayfarer_Rig"].animation_data.action
    rig = bpy.context.view_layer.objects["Wayfarer_Rig"]
    renders = []
    views = [
        ("hero_idle_front", "idle", 19, (2.55, 3.25, 1.72), (0.0, 0.0, 0.96)),
        ("hero_run", "run", 7, (2.85, 2.70, 1.55), (0.0, 0.05, 0.92)),
        ("hero_reach", "reach", 21, (2.65, 3.35, 1.80), (0.0, 0.12, 1.08)),
        ("hero_back", "idle", 37, (-2.55, -3.20, 1.72), (0.0, 0.0, 0.96)),
        ("hero_run_back", "run", 7, (-2.35, -2.95, 1.62), (0.0, 0.05, 0.95)),
        ("hero_detail", "idle", 19, (1.30, 2.05, 1.58), (0.0, 0.06, 1.42)),
    ]
    art_dir = Path(ART_SUBDIR)
    for name, action_name, frame, location, target in views:
        rig.animation_data.action = actions[action_name]
        scene.frame_set(frame)
        bpy.context.view_layer.update()
        camera.location = location
        camera.rotation_euler = (Vector(target) - Vector(location)).to_track_quat("-Z", "Y").to_euler()
        output = (art_dir / "renders" / (name + ".png")).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        scene.render.filepath = str(output)
        started = time.time()
        status = "pass"
        error = None
        try:
            bpy.ops.render.render(write_still=True)
        except Exception as exc:  # pragma: no cover - environment dependent
            status = "fail"
            error = str(exc)
            record = {"name": name, "status": status, "error": error}
            renders.append(record)
            continue
        renders.append({
            "name": name, "action": action_name, "frame": frame, "path": str(output),
            "bytes": output.stat().st_size if output.exists() else 0,
            "seconds": round(time.time() - started, 2), "status": status,
        })
    rig.animation_data.action = default_action
    for track in tracks:
        track.mute = False
    return renders


# --------------------------------------------------------------------------------------------------
# import verification
# --------------------------------------------------------------------------------------------------

def count_imported(glb: Path, kind: str) -> dict:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    result = {"status": "fail", "kind": kind, "errors": []}
    try:
        if kind == "glb":
            bpy.ops.import_scene.gltf(filepath=str(glb))
        else:
            bpy.ops.import_scene.fbx(filepath=str(glb))
    except Exception as exc:
        result["errors"].append(str(exc))
        return result
    meshes = [
        o for o in bpy.context.scene.objects
        if o.type == "MESH" and not any(c.name == "glTF_not_exported" for c in o.users_collection)
    ]
    armatures = [o for o in bpy.context.scene.objects if o.type == "ARMATURE"]
    actions = sorted(a.name for a in bpy.data.actions)
    materials = sorted({m.name for o in meshes for m in o.data.materials if m})
    images = sorted(i.name for i in bpy.data.images if i.name not in ("Render Result", "Viewer Node"))
    bounds_min = Vector((1e9, 1e9, 1e9))
    bounds_max = Vector((-1e9, -1e9, -1e9))
    for obj in meshes:
        for corner in obj.bound_box:
            point = obj.matrix_world @ Vector(corner)
            bounds_min.x = min(bounds_min.x, point.x)
            bounds_min.y = min(bounds_min.y, point.y)
            bounds_min.z = min(bounds_min.z, point.z)
            bounds_max.x = max(bounds_max.x, point.x)
            bounds_max.y = max(bounds_max.y, point.y)
            bounds_max.z = max(bounds_max.z, point.z)
    bones = len(armatures[0].data.bones) if armatures else 0
    morph_targets = 0
    for obj in meshes:
        if obj.data.shape_keys:
            morph_targets += max(0, len(obj.data.shape_keys.key_blocks) - 1)
    result.update({
        "status": "pass" if meshes and armatures and actions else "fail",
        "meshes": len(meshes),
        "vertices": sum(len(o.data.vertices) for o in meshes),
        "armatures": len(armatures),
        "bones": bones,
        "morphTargets": morph_targets,
        "actions": len(actions),
        "actionNames": actions,
        "materials": materials,
        "images": images,
        "bounds": {
            "min": [round(value, 4) for value in bounds_min],
            "max": [round(value, 4) for value in bounds_max],
        },
    })
    return result


# --------------------------------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------------------------------

def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    parser = argparse.ArgumentParser(description="Generate the Wayfarer hero asset")
    parser.add_argument("--repo", default=os.environ.get("GYPSY_REPO", str(ABSOLUTE_DEFAULT_REPO)))
    parser.add_argument("--skip-render", action="store_true")
    return parser.parse_args(argv)


def main() -> int:
    args = parse_args()
    repo = Path(args.repo).resolve()
    asset_dir = repo / ASSET_SUBDIR
    game_dir = repo / GAME_SUBDIR
    art_dir = repo / ART_SUBDIR
    for directory in (asset_dir / "textures", game_dir, art_dir / "renders"):
        directory.mkdir(parents=True, exist_ok=True)

    started = time.time()
    report = {
        "schema": "gypsy.hero.generate/v1",
        "script": str(Path(__file__).resolve()),
        "blender": bpy.app.version_string,
        "started": iso_now(),
        "fps": FPS,
        "warnings": [],
        "errors": [],
    }
    log("Blender " + bpy.app.version_string + " / " + str(repo))
    try:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        scene = bpy.context.scene
        scene.render.fps = FPS
        scene.unit_settings.system = "METRIC"
        scene.unit_settings.scale_length = 1.0

        textures = build_material_textures(asset_dir / "textures")
        bpy.context.scene.render.image_settings.file_format = "PNG"
        texture_bytes = {key: meta["bytes"] for key, meta in textures["files"].items()}
        log("textures " + json.dumps(texture_bytes))
        materials = build_character(textures)
        obj = create_mesh_object(materials)
        arm_obj = create_armature()
        weight_stats = skin(obj, arm_obj)
        lods = create_lod_meshes(obj, arm_obj)
        shape_key = add_facial_shape_key(obj)
        bpy.context.view_layer.objects.active = arm_obj
        actions = create_animations(arm_obj)
        action_records = [
            {"name": name, "firstFrame": int(action.frame_range[0]), "lastFrame": int(action.frame_range[1]),
             "seconds": round((action.frame_range[1] - action.frame_range[0]) / FPS, 3)}
            for name, action in actions.items()
        ]
        log("mesh verts=" + str(weight_stats["vertices"]) + " tris=" + str(weight_stats["triangles"]) +
            " bones=" + str(len(BONES)) + " actions=" + str(len(actions)) +
            " lodTris=" + str([lod["triangles"] for lod in lods]) +
            " morph=" + shape_key["name"] + " moved=" + str(shape_key["movedVertices"]))

        bounds_min = Vector((1e9, 1e9, 1e9))
        bounds_max = Vector((-1e9, -1e9, -1e9))
        for vertex in obj.data.vertices:
            point = obj.matrix_world @ vertex.co
            for axis in range(3):
                bounds_min[axis] = min(bounds_min[axis], point[axis])
                bounds_max[axis] = max(bounds_max[axis], point[axis])

        glb = asset_dir / "wayfarer.glb"
        select_only([arm_obj, obj])
        glb_export = export_glb(glb, morph=True)
        log("glb " + str(glb_export["bytes"]) + " bytes")
        shutil.copyfile(glb, game_dir / "wayfarer.glb")
        fbx = asset_dir / "wayfarer.fbx"
        select_only([arm_obj, obj])
        fbx_export = export_fbx(fbx)
        log("fbx " + str(fbx_export["bytes"]) + " bytes")

        lod_records = []
        for lod in lods:
            lod_path = asset_dir / ("wayfarer_" + lod["level"] + ".glb")
            select_only([arm_obj, lod["object"]])
            lod_export = export_glb(lod_path, morph=False)
            lod_records.append({
                "level": lod["level"], "ratio": lod["ratio"], "file": lod_path.name,
                "triangles": lod["triangles"], "vertices": lod["vertices"],
                "bytes": lod_export["bytes"], "sha256": sha256(lod_path),
                "export": lod_export,
            })
            log("lod " + lod["level"] + " tris=" + str(lod["triangles"]) + " bytes=" + str(lod_export["bytes"]))
            lod["object"].hide_render = True
            lod["object"].hide_set(True)
        lods_manifest = {
            "schema": "gypsy.hero.lods/v1",
            "generator": "scripts/hero/generate_wayfarer.py",
            "blender": bpy.app.version_string,
            "base": {"file": glb.name, "triangles": weight_stats["triangles"]},
            "lods": [{key: value for key, value in lod.items() if key != "export"} for lod in lod_records],
            "godotImport": {
                "generate_lods": True,
                "note": "LOD0 is integrated under Player; the Godot glTF import also generates renderer LODs "
                        "(meshes/generate_lods=true) and the explicit LOD GLBs are tracked for the next LOD pass.",
            },
        }
        with open(asset_dir / "wayfarer_lods.json", "w", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(lods_manifest, indent=2) + "\n")
        select_only([arm_obj, obj])

        renders = []
        if not args.skip_render:
            try:
                renders = add_preview_scene(actions)
            except Exception as exc:  # keep the asset even if the preview renderer fails
                report["warnings"].append("preview render failed: " + str(exc))
                traceback.print_exc()
        blend_path = art_dir / "wayfarer.blend"
        bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
        log("blend " + str(blend_path))

        # Verify the exports by re-importing them into a clean scene.
        reimport_glb = count_imported(glb, "glb")
        reimport_fbx = count_imported(fbx, "fbx") if fbx.exists() else {"status": "skipped"}
        reimport_lods = []
        for record in lod_records:
            imported = count_imported(asset_dir / record["file"], "glb")
            imported["level"] = record["level"]
            reimport_lods.append(imported)
        fbx_clean = (
            fbx.exists() and fbx_export["bytes"] > 0 and
            reimport_fbx.get("status") == "pass" and reimport_fbx.get("bones", 0) >= 15 and
            reimport_fbx.get("actions", 0) >= 3 and fbx.stat().st_size <= 4 * 1024 * 1024
        )
        if fbx.exists() and not fbx_clean:
            report["warnings"].append("FBX round-trip was not clean; the FBX was removed")
            fbx.unlink()
        report["reimport"] = {"glb": reimport_glb, "fbx": reimport_fbx, "fbxClean": fbx_clean, "lods": reimport_lods}

        game_glb = game_dir / "wayfarer.glb"
        report.update({            "finish": iso_now(),
            "seconds": round(time.time() - started, 2),
            "assets": {
                "glb": {"path": str(glb), "bytes": glb.stat().st_size if glb.exists() else 0,
                        "sha256": sha256(glb) if glb.exists() else None},
                "gameGlb": {"path": str(game_glb), "bytes": game_glb.stat().st_size if game_glb.exists() else 0,
                            "sha256": sha256(game_glb) if game_glb.exists() else None},
                "fbx": {"path": str(fbx), "bytes": fbx.stat().st_size if fbx.exists() else 0,
                        "sha256": sha256(fbx) if fbx.exists() else None, "clean": fbx_clean},
                "textures": {key: {field: value for field, value in meta.items() if field != "image"}
                             for key, meta in textures["files"].items()},
                "lods": lod_records,
                "lodsManifest": str(asset_dir / "wayfarer_lods.json"),
                "blend": str(blend_path),
            },
            "mesh": {
                **weight_stats,
                "bounds": {
                    "min": [round(value, 4) for value in bounds_min],
                    "max": [round(value, 4) for value in bounds_max],
                    "height": round(bounds_max.z - bounds_min.z, 4),
                },
                "materials": MATERIAL_NAMES,
            },
            "rig": {
                "bones": [name for name, _p, _h, _t, _d in BONES],
                "boneCount": len(BONES),
                "deformBones": sum(1 for item in BONES if item[4]),
            },
            "actions": action_records,
            "shapeKey": shape_key,
            "export": {"glb": glb_export, "fbx": fbx_export, "lods": [lod["export"] for lod in lod_records]},
            "renders": renders,
        })
        (art_dir / "generation-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

        failures = []
        if report["assets"]["glb"]["bytes"] <= 0 or report["assets"]["glb"]["bytes"] > 2 * 1024 * 1024:
            failures.append("GLB missing or over the 2 MB budget")
        if report["assets"]["glb"]["sha256"] != report["assets"]["gameGlb"]["sha256"]:
            failures.append("game GLB mirror does not match assets/hero GLB")
        if weight_stats["zeroWeightVertices"] != 0:
            failures.append("unskinned vertices: " + str(weight_stats["zeroWeightVertices"]))
        if abs(weight_stats["minWeightSum"] - 1.0) > 0.001 or abs(weight_stats["maxWeightSum"] - 1.0) > 0.001:
            failures.append("weights are not normalized")
        if reimport_glb.get("status") != "pass" or reimport_glb.get("actions", 0) < 3:
            failures.append("GLB re-import did not show mesh + armature + 3 actions")
        if not (1.70 <= (bounds_max.z - bounds_min.z) <= 2.00):
            failures.append("hero height outside 1.70-2.00 m")
        base_triangles = weight_stats["triangles"]
        lod_triangles = [record["triangles"] for record in lod_records]
        if len(lod_records) < 2:
            failures.append("explicit LOD chain missing (need LOD1 and LOD2)")
        previous = base_triangles
        for level, triangles in zip([record["level"] for record in lod_records], lod_triangles):
            if triangles >= previous:
                failures.append("LOD " + level + " is not lighter than the previous level")
            previous = triangles
        if lod_triangles and min(lod_triangles) < 150:
            failures.append("LOD2 triangle count is below the 150-triangle floor")
        if shape_key["movedVertices"] < 4:
            failures.append("Smile shape key moved fewer than 4 vertices")
        if reimport_glb.get("morphTargets", 0) < 1:
            failures.append("GLB re-import did not show the Smile morph target")
        if reimport_glb.get("bones", 0) < len(BONES):
            failures.append("GLB re-import bone count is below the rig spec")
        if len(reimport_glb.get("images", [])) < 3:
            failures.append("GLB does not carry the base/normal/roughness texture set")
        for record in reimport_lods:
            if (record.get("status") != "pass" or record.get("bones", 0) < 20
                    or record.get("actions", 0) < 3):
                failures.append("LOD " + record["level"] + " re-import is incomplete")
        for failure in failures:
            report["errors"].append(failure)
        (art_dir / "generation-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        if failures:
            for failure in failures:
                print("WAYFARER_GEN_FAIL " + failure, file=sys.stderr)
            return 1
        print("WAYFARER_GEN_OK glb=" + str(glb) + " bytes=" + str(glb.stat().st_size) +
              " bones=" + str(len(BONES)) + " actions=" + str(len(actions)) +
              " tris=" + str(weight_stats["triangles"]) + " lods=" + str(len(lod_records)) +
              " morph=" + shape_key["name"] + " maps=" + str(len(textures["files"])))
        return 0
    except Exception as exc:
        traceback.print_exc()
        report["errors"].append(str(exc))
        report["finish"] = iso_now()
        report["seconds"] = round(time.time() - started, 2)
        try:
            (art_dir / "generation-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        except Exception:
            pass
        print("WAYFARER_GEN_FAIL " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
