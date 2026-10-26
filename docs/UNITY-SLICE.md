# LeftBehind — Unity 6 slice

**Project:** LeftBehind (second-engine proof; the Phase-1 engine remains Godot, ADR-009)
**Engine:** Unity 6000.6.7f1 · Windows Standalone
**Location:** unity/LeftBehind

## What was built

A Unity port of the three-collectible slice:

- procedural 30×30 arena, four platforms, lights and a follow camera
- capsule player with CharacterController movement
- three collectible emissive crystals
- deterministic `--demo` autopilot using the real CharacterController path
- Windows player built by `BuildLeftBehind.Build`
- windowed `ScreenCapture` frame

## Evidence (2026-10-26)

| Gate | Result |
| --- | --- |
| Unity batchmode build | **PASS** — `LEFTBEHIND_BUILD Succeeded`, `Build/LeftBehind.exe` 667,136 B, data 95,921,964 B |
| Demo | **PASS** — `GYPSY_DEMO_OK collected=3 frames=74`, exit 0 |
| Capture | **PASS** — 1280×720 PNG, 27,596 B, SHA-256 6da0cd856193417f6e48992ac9076952291bc08e2ae446ad72ccd9867844010d |
| Player log | `artifacts/leftbehind/player.log` |
| Build log | `artifacts/leftbehind/build.log` |
| Toolpack | `leftbehind.unity` passed build/demo/capture |
| Slice | `slices run leftbehind` passed 1/1 |

## Commands

    powershell -File scripts/build_unity_leftbehind.ps1
    powershell -File scripts/run_unity_leftbehind.ps1 -Mode demo
    powershell -File scripts/run_unity_leftbehind.ps1 -Mode capture
    python workstream/gypsy.py toolpacks run leftbehind.unity
    python workstream/gypsy.py slices run leftbehind

The build wrapper waits for `LEFTBEHIND_BUILD Succeeded`; the demo wrapper asserts
`GYPSY_DEMO_OK collected=3`; capture requires a visible window (the hidden-window attempt failed and is recorded).

## What this proves / does not prove

**Proved:** the same gameplay contract (move, collect three, camera, deterministic marker) runs on a second engine,
builds to a Windows player, and renders a frame. This satisfies the ADR-003 Phase-5 second-engine portion of the gate.

**Not proved:** Unity asset import of the Blender golden kit (the import matrix remains Godot-only), hero art,
character pipeline, mobile Unity, playmode editor tests, performance profiling, or that LeftBehind is the final game
name/content. The Unity project uses procedural primitives for this port; it is a technical proof, not the art slice.

## Project manifest

`unity/LeftBehind/project.gypsy.json` pins Unity 6000.6.7f1 / adapter `unity-6` / `pc`, with the autonomous decision
recorded. The Godot project remains the Phase-1 choice; this is a per-project second-engine proof.
