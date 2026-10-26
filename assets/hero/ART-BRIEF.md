# Wayfarer — hero art brief

Status: original prototype asset for Gypsy Studio. Generated in-repo; no external IP, textures or models.
Owner: hero/character workstream. Source of truth: `scripts/hero/generate_wayfarer.py`.

## Identity

The **Wayfarer** is the lone trail-walker who gathers signal crystals across the twilight arena. The
silhouette must read at third-person camera distance (7-10 m): hooded head, layered shoulder mantle,
draped back cape, wrapped forearms, side satchel, heavy boots. Quiet, practical, a little weathered.

## Visual direction

- **Stylized low-poly**, deliberately faceted. Flat shading, chunky planes, no photoreal detail.
- **Readable silhouette first.** Hood peak, mantle shoulder line and cape break the humanoid outline.
- **Hand-painted-feeling atlas**, not a photoreal PBR set. One 256×256 authored atlas with four bands:
  weathered ochre cloak, deep teal tunic/ trousers, warm leather, sun-worn skin. Woven/stitch noise
  lives in the texture; UVs may tile within a band.
- **One accent.** Emissive cyan (`#2fe3ff`) reserved for the eyes, chest shard, belt buckle and bracer
  studs; it ties the hero to the signal crystals. Accent must stay small (under ~3% of screen pixels).
- **No gore, no logos, no text, no external character likeness.**

Palette (sRGB):

| Role | Hex |
| --- | --- |
| Cloak base / weave shadow | `#c99a68` / `#9a6c45` |
| Tunic + trousers teal | `#4a7f8a` / `#35636c` |
| Leather | `#7a5136` / `#543525` |
| Skin | `#d8af8e` |
| Emissive accent | `#2fe3ff` |
| Boots | `#4a3426` (leather band, darkened by the boot shape) |

## Proportions and scale

- Metric scale. Feet on `z = 0`, hood peak ≈ **1.91 m** (head ≈ 1.79 m). Roughly 6.5 heads tall, stylized.
- Shoulder span ≈ 0.44 m; cape width ≈ 0.52 m at the hem. Narrow enough for the 0.4 m-radius capsule.
- Origin at the feet, **front = +Y in Blender** (exported glTF/Godot front = **−Z**, matching the
  player's forward axis). No object-level scale; 1 Blender unit = 1 m.

## Rig

20-bone humanoid deformation skeleton, rest A-pose, meters:

```text
root
└─ hips
   ├─ spine ─ chest ─ neck ─ head
   │           ├─ shoulder.L ─ upper_arm.L ─ forearm.L ─ hand.L
   │           └─ shoulder.R ─ upper_arm.R ─ forearm.R ─ hand.R
   ├─ thigh.L ─ shin.L ─ foot.L
   └─ thigh.R ─ shin.R ─ foot.R
```

`.L` is the character's left (`x < 0` when facing +Y). Skinning is computed from bone-segment
distance, restricted to an anatomically sensible bone set per body part, normalised, maximum four
influences per vertex. Every vertex must carry weight; no rigid unskinned shells.

## Actions

All authored at 24 fps, sampled to glTF:

| Clip | Frames | Length | Use |
| --- | --- | --- | --- |
| `idle` | 1–73 | 3.0 s | Seamless loop: breathing, weight shift, subtle head drift. |
| `run` | 1–25 | 1.0 s | Seamless loop: contact/pass/contact run cycle, opposing arm swing, knee bend, hip bob and counter-twist. |
| `reach` | 1–49 | 2.0 s | One-shot: step in, right arm extends to crystal height, torso twist, grab hold, settle back. |

Exported glTF clip lengths read back as 3.04 s / 1.04 s / 2.04 s because Blender's force-sampled
export includes the end frame; the authored loops still start and end on matching poses.

Game mapping: speed > 0.8 m/s on the floor → `run`; otherwise `idle`; crystal collection → `reach`
(one-shot, then back to locomotion). Animations must never gate movement or the demo contract.

## Materials and texture

| Slot | Material | Notes |
| --- | --- | --- |
| 0 | `Wayfarer_Cloth` | Shared atlas; UV band 0 ochre (cape/hood/mantle/tabard), band 1 teal (tunic/trousers). |
| 1 | `Wayfarer_Leather` | Atlas band 2; belt, satchel, strap, bracers, boots, headband. |
| 2 | `Wayfarer_Skin` | Atlas band 3; head, neck, hands, nose. |
| 3 | `Wayfarer_Accent` | Emissive cyan; eyes, chest shard, buckle, studs. Matte. |

- Texture: 256×256 PNG atlas generated procedurally and embedded in the GLB; the source PNG is tracked
  at `assets/hero/textures/wayfarer_atlas.png`.
- All four materials export double-sided (the low-poly cape/mantle are open shells); roughness 0.74 cloth, 0.68 leather, 0.52 skin.
- No normal maps, no external images, no sky/HDRI dependencies.

## Technical budget

- One skinned mesh, ≤ 8,000 triangles (target ~2k), ≤ 1 texture (256²), ≤ 4 materials, 20 bones. Shipped: **1,126 triangles, 716 source vertices (2,162 glTF vertex records across flat/UV seams), 20 joints, 4 materials, 1 embedded 256² PNG, GLB 282,668 bytes, FBX 707,356 bytes.**
- GLB ≤ 2 MB. FBX optional, ≤ 4 MB, no external texture files.
- Export: GLB (Y-up, skins, NLA-strip animations, force sampling, embedded image). FBX 7.4 with baked
  NLA strips and embedded texture.
- Deliverables: tracked GLB + FBX under `assets/hero/`, source generator under `scripts/hero/`,
  Godot mirror at `game/assets/hero/wayfarer.glb` (the engine cannot load `res://` outside `game/`).

## Godot integration

- Instance the GLB under `Player` at local `y = −0.9` so the feet meet the capsule bottom (`Player`
  sits at `y = 0.9`); scale 1.0, rotation 0.
- Remove the placeholder capsule/visor meshes; **keep the `CollisionShape3D`** and the
  `CharacterBody3D` movement, autopilot, collectible and `GYPSY_DEMO_OK` contract untouched.
- `HeroVisual` script maps speed → idle/run and collection → reach. Missing clips warn once and never
  break movement.
- Verify with: headless demo, windowed movie capture, a hero preview orbit capture, and the
  non-Blender asset validator.

## Provenance and limits

- Authored procedurally in this repository (Blender 5.2.3 headless). Project asset, no third-party
  licence obligations; no generative-AI image model was used.
- Prototype quality: not a production hero. Limitations to record honestly: no facial rig/expression,
  no cloth or physics simulation, no separate cape bones, no LODs, animation is keyframe-authored and
  sampled at 24 fps, and the atlas is a stylistic aid rather than a full painted texture set.
