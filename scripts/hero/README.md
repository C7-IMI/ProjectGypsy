# scripts/hero — Wayfarer hero pipeline

Original, reproducible way of building and validating the hero. No third-party models, textures or
network access. Sources of truth: `generate_wayfarer.py` (Blender 5.2.3) and
`validate_wayfarer.py` (Python standard library only).

Production pass: 512px base/normal/roughness-metal maps, a 23-bone rig with a three-bone cape chain,
explicit LOD1/LOD2 exports and a safe `Smile` facial morph target. The Godot slice still instances
LOD0 only; LOD1/LOD2 are tracked assets for the next LOD/runtime pass.

## Prerequisites

| Tool | Path / version |
| --- | --- |
| Blender | `C:\Program Files\Blender Foundation\Blender 5.2\blender.exe` (5.2.3 LTS) |
| Godot | `%LOCALAPPDATA%\Microsoft\WinGet\Links\godot.exe` (4.7.2) |
| Python | repository Python (`C:\Python\python.exe`, 3.14) |

## Build the asset (Blender, headless)

```powershell
& "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe" --background --factory-startup `
  --python scripts/hero/generate_wayfarer.py -- --repo (Get-Location).Path
```

`--skip-render` skips the Cycles review renders (fast asset iteration); the full run takes a few
seconds of asset work plus the renders.

Writes:

- `assets/hero/wayfarer.glb` — LOD0 runtime asset, 3 embedded 512² maps, 23-joint skin,
  idle/run/reach, `Smile` morph target.
- `assets/hero/wayfarer_lod1.glb`, `wayfarer_lod2.glb` — explicit decimated LOD meshes, each with
  the full rig and all three clips.
- `assets/hero/wayfarer_lods.json` — LOD manifest (levels, ratios, triangle counts, hashes).
- `assets/hero/wayfarer.fbx` — FBX 7.4 with embedded maps, kept only when the round-trip is clean.
- `assets/hero/textures/wayfarer_atlas.png` — 512² sRGB base-colour atlas.
- `assets/hero/textures/wayfarer_normal.png` — 512² tangent-space normal map (Non-Color).
- `assets/hero/textures/wayfarer_roughmetal.png` — 512² roughness/metal map (Non-Color, glTF ORM layout).
- `game/assets/hero/wayfarer.glb` — byte-identical mirror for `res://` (Godot cannot load outside `game/`).
- `artifacts/hero/wayfarer.blend`, `generation-report.json`, `renders/*.png` — ignored evidence.
- Marker on success (current run): `WAYFARER_GEN_OK glb=... bytes=904964 bones=23 actions=3 tris=1126 lods=2 morph=Smile maps=3`.

The generator authors the geometry (hand-built lofts, ellipsoids, ribbons), the three texture maps, the
23-bone rig (including `cape_a/b/c`), deterministic distance-based skin weights, the `Smile` shape
key, the LOD chain and the three actions. It re-imports the GLB, LOD GLBs and FBX in clean Blender
scenes and removes the FBX if that round-trip is not clean.

## Validate without Blender (non-network)

```powershell
python scripts/hero/validate_wayfarer.py --json artifacts/hero/validation-report.json
```

Parses the GLB JSON/BIN chunks directly and checks files, budgets, the LOD chain and manifest, skin
joints (including the cape chain), inverse bind matrices, per-vertex weights, bounds, the facial morph
target, the three 512² texture maps and their material wiring (base/normal/metallic-roughness), cape
animation in idle and run, animation names and durations, the byte-identical Godot mirror, and the
`Player`/`Hero` integration including Godot's generated-LOD import setting. Exit 0 and
`HERO_VALIDATE_OK ...` on success, exit 1 and `HERO_VALIDATE_FAIL ...` otherwise.

## Import and run in Godot

```powershell
& "$env:LOCALAPPDATA\Microsoft\WinGet\Links\godot.exe" --headless --path game --import
& "$env:LOCALAPPDATA\Microsoft\WinGet\Links\godot.exe" --headless --path game -- --demo
& "$env:LOCALAPPDATA\Microsoft\WinGet\Links\godot.exe" --headless --path game res://scenes/hero_integration_check.tscn
```

- `game/scenes/player.tscn` instances `res://assets/hero/wayfarer.glb` as `Hero` at local
  `y = -0.9`; the `CapsuleShape3D` collision stays, the old capsule/visor meshes are gone.
- `game/scripts/hero_visual.gd` maps speed to idle/run and collection to the one-shot reach clip.
  The rig animation now includes the cape chain; the `Smile` morph is exported but not driven by the
  slice (optional later hook).
- `game/scenes/hero_preview.tscn` is a render-only front 3/4 showroom used for capture.
- `game/scenes/hero_integration_check.tscn` asserts idle -> run -> reach -> idle on the real main scene.

## Windowed captures (requires a desktop session)

```powershell
& "$env:LOCALAPPDATA\Microsoft\WinGet\Links\godot.exe" --path game --write-movie (Join-Path (Get-Location) "artifacts/hero/hero-preview.avi") --fixed-fps 30 res://scenes/hero_preview.tscn -- --capture
```

The movie path must be absolute for the command. Convert with ffmpeg, then inspect
`artifacts/game/frame.png` and `artifacts/hero/hero-preview-*.png`.

## Integration changes made outside the asset

- Camera follow offset reduced from `(0, 7, 10)` to `(0, 4.2, 6.0)` so the 1.9 m hero is legible.
- A low-energy shadowless `Fill` directional light added to `main.tscn` for back readability.
- The player now faces the autopilot direction as well as the manual input direction.

## Known limits

- LOD1/LOD2 are explicit tracked exports with the full rig and clips, but the slice renders LOD0 only;
  runtime LOD switching is not wired yet. Each LOD GLB embeds the full texture set, so they are larger
  than strictly necessary (~0.8 MB) until a shared texture/atlas pass.
- The decimated LOD exports can emit a Blender glTF exporter "mesh is not valid" warning (the LODs
  still re-import with 23 bones and 3 clips); production LODs should be retopologised rather than
  decimated.
- The `Smile` morph is exported and validated but not played by the slice.
- The maps are procedurally authored (weave/grain/scratch height fields), not hand-painted; roughness
  and metal are baked into one map; the metal channel is zero for cloth/leather/skin (brass stays a
  constant material value).
- The GLB, both LOD GLBs and the three texture maps are byte-identical across generator runs; the FBX
  embeds exporter metadata and is not byte-stable (it still round-trips cleanly).
- The FBX round-trips in Blender but Godot uses the GLB; no Unity/UE5 import of this hero was run.
- Godot extracts the embedded maps to `game/assets/hero/wayfarer_<name>.png` on import; those files
  and `*.import` are generated engine metadata.
- Records and commits are intentionally left to the Lead; this workstream does not edit them.

Evidence: `artifacts/hero/generation-report.json`, `validation-report.json`, `evidence.json`,
`renders/`, `hero-preview.mp4`, and `artifacts/game/frame.png`.
