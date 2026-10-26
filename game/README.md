# game/ — ProjectGypsy Phase-1 vertical slice

A minimal Godot 4.7.2 PC slice that proves the game loop end to end: a 3D arena with a floor and
four jumpable platforms, a WASD-driven player capsule, three collectible crystals and a third-person
follow camera. The engine is pinned for this slice in [project.gypsy.json](project.gypsy.json); the
Phase-1 engine choice is recorded in [ADR-009](../docs/ADR-009-vertical-slice.md); a different engine is a port, not a toggle.

There is deliberately **no HUD or interface design**: interface work is parked (ProjectPack PG-D4),
so the slice uses 3D primitives and materials only.

## Run it interactively

```powershell
& "$env:LOCALAPPDATA\Microsoft\WinGet\Links\godot_console.exe" --path game
```

Controls:

| Input | Action |
| --- | --- |
| W / A / S / D (or arrow keys) | Move the player capsule |
| Space | Jump (platforms are 0.5 m and 1.0 m high; apex is ~1.2 m) |

The camera follows the player at a fixed offset. Touching a crystal collects it: it disappears and
stops monitoring. Walking off the arena resets the player to the spawn point. Input actions are
registered in `scripts/main.gd` at start-up, so no editor input-map setup is required.

## Headless demo contract

```powershell
godot_console.exe --headless --path game -- --demo
```

- Success prints exactly one marker line to stdout:

  ```text
  GYPSY_DEMO_OK collected=3 frames=<n>
  ```

  and exits with code **0**. `frames` is the physics-frame count at which the third crystal was
  collected (60 physics ticks per second; bounded by `MAX_DEMO_FRAMES = 900`).
- Failure prints `GYPSY_DEMO_FAIL <reason>` and exits with code **1**.

The demo is not a cutscene and not a teleport: `scripts/main.gd` enables the player's autopilot,
which sets a world-space direction toward the nearest uncollected crystal every physics frame, and
`scripts/player.gd` moves the capsule through the normal `move_and_slide()` path. Collection uses
the same `Area3D` pickup code a human triggers. Given the fixed 60 Hz physics tick the frame count is
deterministic, so the run can be repeated and compared.

Headless Godot uses a dummy renderer (ADR-001): this proves game logic and the collection mechanic, not rendered
output. `python workstream/gypsy.py game capture` records a windowed 1280×720 movie (72 frames) and extracts a frame;
see `docs/PHASE-1-EVIDENCE.md`.

## Android package

From the repository root:

    powershell -File scripts/build_android.ps1

This produces a signed arm64 debug APK at build/ProjectGypsy.apk and verifies the package id and signature. It needs the
portable JDK 17/Android SDK listed in TOOLCHAIN.md. The APK has not been launched on a device/emulator; no device
behaviour is claimed. See docs/PHASE-5-EVIDENCE.md.

## Layout

| Path | Purpose |
| --- | --- |
| `project.godot` | Project config; main scene, 60 Hz physics, GL Compatibility renderer |
| `scenes/main.tscn` | Arena: floor, four platforms, player, three crystals, camera, light |
| `scenes/player.tscn` | Capsule player body (CharacterBody3D) |
| `scenes/crystal.tscn` | Collectible crystal (Area3D pickup) |
| `scripts/main.gd` | Input actions, demo autopilot, marker/exit contract |
| `scripts/player.gd` | WASD movement, jump, gravity, fall reset |
| `scripts/crystal.gd` | Pickup detection and one-shot collection |
| `scripts/camera_follow.gd` | Smooth fixed-offset follow camera |
| `project.gypsy.json` | Pinned engine manifest (schema `gypsy.project/v1`) |
| `export_presets.cfg` | Windows Desktop preset exporting to `../build/ProjectGypsy.exe` |

## Known limitations

- The Windows export preset is **verified**: `game build` produced `build/ProjectGypsy.exe` (109,127,680 bytes) and
the exported binary runs the headless demo; see `docs/PHASE-1-EVIDENCE.md`.
- Headless runs cannot render; visual evidence comes from the windowed `game capture` path.
- One mechanic only: walk/jump/collect. Enemies, scoring, audio, saving and UI are later slices.
