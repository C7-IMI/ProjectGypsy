# scripts/hero — Wayfarer hero pipeline

Original, reproducible way of building and validating the Phase-1 hero. No third-party models,
textures or network access. Sources of truth: `generate_wayfarer.py` (Blender 5.2.3) and
`validate_wayfarer.py` (Python standard library only).

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

Writes:

- `assets/hero/wayfarer.glb` — runtime asset, embedded texture, 20-joint skin, idle/run/reach.
- `assets/hero/wayfarer.fbx` — FBX 7.4 with embedded texture, only kept when the round-trip is clean.
- `assets/hero/textures/wayfarer_atlas.png` — tracked 256² source atlas.
- `game/assets/hero/wayfarer.glb` — byte-identical mirror for `res://` (Godot cannot load outside `game/`).
- `artifacts/hero/wayfarer.blend`, `generation-report.json`, `renders/*.png` — ignored evidence.
- Marker on success: `WAYFARER_GEN_OK glb=... bytes=... bones=20 actions=3 tris=1126`.

The generator authors the geometry (hand-built lofts, ellipsoids, ribbons), the atlas, the
20-bone rig, deterministic distance-based skin weights and the three actions. It re-imports the GLB
and FBX in a clean Blender scene and removes the FBX if that round-trip is not clean.

## Validate without Blender (non-network)

```powershell
python scripts/hero/validate_wayfarer.py --json artifacts/hero/validation.json
```

Parses the GLB JSON/BIN chunks directly and checks files, budgets, skin joints, inverse bind
matrices, per-vertex weights, bounds, triangle count, materials, embedded texture, animation names
and durations, the byte-identical Godot mirror, and the `Player`/`Hero` integration. Exit 0 and
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
- `game/scenes/hero_preview.tscn` is a render-only front 3/4 showroom used for capture.
- `game/scenes/hero_integration_check.tscn` asserts idle -> run -> reach -> idle on the real main scene.

## Windowed captures (requires a desktop session)

```powershell
python workstream/gypsy.py game capture
& "$env:LOCALAPPDATA\Microsoft\WinGet\Links\godot.exe" --path game --write-movie (Join-Path (Get-Location) "artifacts/hero/hero-preview.avi") --fixed-fps 30 res://scenes/hero_preview.tscn -- --capture
```

The movie path must be absolute for the second command. Convert with ffmpeg, then inspect
`artifacts/game/frame.png` and `artifacts/hero/hero-preview-*.png`.

## Integration changes made outside the asset

- Camera follow offset reduced from `(0, 7, 10)` to `(0, 4.2, 6.0)` so the 1.9 m hero is legible.
- A low-energy shadowless `Fill` directional light added to `main.tscn` for back readability.
- The player now faces the autopilot direction as well as the manual input direction.

## Known limits

- No facial rig, cloth/mantle simulation, cape bones or LODs; the atlas is stylized, not painted.
- The FBX round-trips in Blender but Godot uses the GLB; no Unity/UE5 import of this hero was run.
- Godot extracts the embedded atlas to `game/assets/hero/wayfarer_wayfarer_atlas.png` on import;
  that file and `*.import` are generated engine metadata.
- Records and commits are intentionally left to the Lead; this workstream does not edit them.

Evidence: `artifacts/hero/generation-report.json`, `validation.json`, `evidence.json`,
`renders/`, `hero-preview.mp4`, and `artifacts/game/frame.png`.
