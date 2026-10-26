# Wayfarer — hero art brief

Status: original prototype asset for Gypsy Studio, extended in the hero production pass. Generated
in-repo; no external IP, textures or models. Owner: hero/character workstream. Source of truth:
`scripts/hero/generate_wayfarer.py`.

## Identity

The **Wayfarer** is the lone trail-walker who gathers signal crystals across the twilight arena. The
silhouette must read at third-person camera distance (7-10 m): hooded head, layered shoulder mantle,
draped back cape, wrapped forearms, side satchel, heavy boots. Quiet, practical, a little weathered.

## Visual direction

- **Stylized low-poly**, deliberately faceted. Flat shading, chunky planes, no photoreal detail.
- **Readable silhouette first.** Hood peak, mantle shoulder line and cape break the humanoid outline.
- **Hand-painted-feeling maps**, not a photoreal PBR set. One 512×512 base-colour atlas with four bands:
  weathered ochre cloak, deep teal tunic/trousers, warm leather, sun-worn skin. Woven/stitch noise
  lives in the texture; UVs may tile within a band.
- **Material maps (production pass):** a 512×512 tangent-space normal map (weave/twill/leather/skin
  height field) and a 512×512 roughness/metal map in glTF metallic-roughness layout (G = roughness,
  B = metal). All three are authored procedurally by the generator.
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

23-bone deformation skeleton (22 deform bones + root), rest A-pose, meters:

```text
root
└─ hips
   ├─ spine ─ chest ─ neck ─ head
   │           ├─ shoulder.L ─ upper_arm.L ─ forearm.L ─ hand.L
   │           ├─ shoulder.R ─ upper_arm.R ─ forearm.R ─ hand.R
   │           └─ cape_a ─ cape_b ─ cape_c        ← production-pass cape chain
   ├─ thigh.L ─ shin.L ─ foot.L
   └─ thigh.R ─ shin.R ─ foot.R
```

`.L` is the character's left (`x < 0` when facing +Y). Skinning is computed from bone-segment
distance, restricted to an anatomically sensible bone set per body part, normalised, maximum four
influences per vertex. Every vertex must carry weight; no rigid unskinned shells. The cape grid is
weighted to chest + `cape_a/b/c` so it bends with the chain.

## Actions

All authored at 24 fps, sampled to glTF:

| Clip | Frames | Length | Use |
| --- | --- | --- | --- |
| `idle` | 1–73 | 3.0 s | Seamless loop: breathing, weight shift, subtle head drift, cape sway. |
| `run` | 1–25 | 1.0 s | Seamless loop: contact/pass/contact run cycle, opposing arm swing, knee bend, hip bob, cape trailing. |
| `reach` | 1–49 | 2.0 s | One-shot: step in, right arm extends to crystal height, torso twist, grab hold, cape reaction, settle back. |

Exported glTF clip lengths read back as 3.04 s / 1.04 s / 2.04 s because Blender's force-sampled
export includes the end frame; the authored loops still start and end on matching poses.

Game mapping: speed > 0.8 m/s on the floor → `run`; otherwise `idle`; crystal collection → `reach`
(one-shot, then back to locomotion). Animations must never gate movement or the demo contract.

## Facial morph (optional, safe)

One shape key `Smile` is exported as a glTF morph target on every primitive: 12 mouth-plate vertices
move ≤ 7.25 mm upward/forward, leaving eyes, hood and rig untouched. It is exported and validated but
not driven by the slice; a later hook can set the blend-shape weight on collect.

## Materials and texture

| Slot | Material | Notes |
| --- | --- | --- |
| 0 | `Wayfarer_Cloth` | Base atlas + normal + roughness map; UV band 0 ochre (cape/hood/mantle/tabard), band 1 teal (tunic/trousers). |
| 1 | `Wayfarer_Leather` | Same map set; atlas band 2; belt, satchel, strap, bracers, boots, headband. |
| 2 | `Wayfarer_Skin` | Same map set; atlas band 3; head, neck, hands, nose. |
| 3 | `Wayfarer_Accent` | Emissive cyan; eyes, chest shard, buckle, studs. Constant PBR values, no maps. |

- Maps (all tracked under `assets/hero/textures/`, embedded in the GLB): `wayfarer_atlas.png` (512²,
  sRGB), `wayfarer_normal.png` (512², Non-Color), `wayfarer_roughmetal.png` (512², Non-Color).
- All four materials export double-sided (the low-poly cape/mantle are open shells).
- No external images, sky or HDRI dependencies.

## LOD chain (production pass)

| Level | File | Triangles | Notes |
| --- | --- | --- | --- |
| LOD0 | `assets/hero/wayfarer.glb` | 1,126 | Integrated under `Player`; also gets Godot's generated renderer LODs. |
| LOD1 | `assets/hero/wayfarer_lod1.glb` | 615 | Decimated copy, same 23-bone rig and idle/run/reach clips. |
| LOD2 | `assets/hero/wayfarer_lod2.glb` | 306 | Decimated copy, same rig and clips. |

`assets/hero/wayfarer_lods.json` records the ratios, triangle counts and SHA-256s. The explicit LOD
GLBs are deliverables for the next runtime LOD pass; the current slice renders LOD0.

## Technical budget

- One skinned mesh, ≤ 8,000 triangles (target ~2k), 3 texture maps (512²), 4 materials, 23 bones.
  Shipped: **1,126 triangles, 716 source vertices (2,162 glTF vertex records across flat/UV seams),
  1,126/615/306 LOD triangles, 23 joints, 4 materials, 3 embedded 512² PNGs, GLB 904,964 bytes,
  FBX 1,149,484 bytes.**
- GLB ≤ 2 MB. FBX optional, ≤ 4 MB, no external texture files. LOD GLBs ~0.8 MB each.
- Export: GLB (Y-up, skins, NLA-strip animations, force sampling, embedded images, morph target).
  FBX 7.4 with baked NLA strips and embedded maps.
- Deliverables: tracked GLB + LOD GLBs + LOD manifest + FBX under `assets/hero/`, source generator
  under `scripts/hero/`, Godot mirror at `game/assets/hero/wayfarer.glb` (the engine cannot load
  `res://` outside `game/`).

## Godot integration

- Instance the GLB under `Player` at local `y = −0.9` so the feet meet the capsule bottom (`Player`
  sits at `y = 0.9`); scale 1.0, rotation 0.
- Remove the placeholder capsule/visor meshes; **keep the `CollisionShape3D`** and the
  `CharacterBody3D` movement, autopilot, collectible and `GYPSY_DEMO_OK` contract untouched.
- `HeroVisual` script maps speed → idle/run and collection → reach. Missing clips warn once and never
  break movement.
- Verify with: Blender generation, hidden/unhidden validator, headless demo, windowed movie capture,
  a hero preview orbit capture, and the non-Blender asset validator.

## Provenance and limits

- Authored procedurally in this repository (Blender 5.2.3 headless). Project asset, no third-party
  licence obligations; no generative-AI image model was used.
- Prototype-plus quality, not a production hero. Honest limits: LOD1/LOD2 are decimated (not
  retopologised) and not wired to runtime LOD switching; the maps are procedural rather than painted;
  one `Smile` morph only (no facial rig); no cloth simulation; weights are distance-based with up to
  four influences; animation is keyframe-authored at 24 fps.
