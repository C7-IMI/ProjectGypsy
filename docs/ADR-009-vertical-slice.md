# ADR-009 — Phase 1: Godot 4.7.2 PC vertical slice

- **Status:** accepted, 2026-10-25 (autonomous build under the operator's full-autonomy instruction)
- **Scope:** the first playable ProjectGypsy slice, the engine choice for this slice, and its acceptance gates.
- **Related:** [ADR-001](ADR-001-engines.md) (engine mechanism), [ADR-003](ADR-003-workstream-architecture.md)
  (phases), [ADR-005](ADR-005-character-animation-automation.md) (later character work), [ADR-006](ADR-006-blender-import-matrix.md)
  (import contract), [PHASE-1-EVIDENCE.md](PHASE-1-EVIDENCE.md) (generated evidence), [DEFERRED.md](../DEFERRED.md).

## Context

The operator instructed a full autonomous build with slices and subagents. The engine mechanism (ADR-001) is built,
but no engine had been chosen for the game; the operator also wants engine choice per project and may override.
Hardware: T600 4 GB, 64 GB RAM, Windows; Godot is the only engine with a proven headless loop here (Unity has no
licence, UE5 fails the hardware gate, Flax has no headless path).

## Decision

1. **Engine for this slice: Godot 4.7.2, PC target, adapter `godot-4`.** The choice is recorded in
   `game/project.gypsy.json`; a different engine is a new project/port, not a toggle (ADR-001).
2. **Scope is deliberately small:** a 3D world of primitives/flat-shaded meshes, a player capsule with WASD movement,
   three collectible crystals, a follow camera, and collision. **No UI/HUD design** — interface design remains parked
   (PG-D4); the demo is judged by world state, a marker line and a capture.
3. **A deterministic headless demo is the primary gate.** `godot --headless --path game -- --demo` auto-pilots the
   player to collect all three crystals within a bounded frame budget, prints `GYPSY_DEMO_OK collected=3 frames=<n>`
   and exits 0; failure prints `GYPSY_DEMO_FAIL <reason>` and exits non-zero.
4. **Build:** export the Windows Desktop preset to `build/ProjectGypsy.exe` with the pinned 4.7.2 export templates.
5. **Capture is evidence, not a quality claim:** attempt a windowed movie-maker capture and convert it with FFmpeg;
   headless has no renderer, so capture is recorded separately from logic proof.
6. **All of it is reproducible from one command:** `python workstream/gypsy.py game verify` runs demo + build +
   capture attempt and writes evidence under `workstream/state/`.

## Acceptance criteria

| Gate | Criterion |
| --- | --- |
| Demo | marker `GYPSY_DEMO_OK collected=3 frames=<n>`, exit 0, repeatable |
| Build | export preset exits 0 and produces a non-empty `build/ProjectGypsy.exe` |
| Capture | windowed movie-maker path produces a non-empty video and a frame; if the engine blocks it, it is reported as blocked, not passed |
| Checks | `python workstream/gypsy.py check` and the records/check list pass |
| Records | `Retrace.md` and `BuildNotes.md` entries in the same commit; version computed |

## Out of scope

Art direction, sculpt/retopo/rig/animation, UI/UX (parked), audio, multiplayer, mobile, content volume, accessibility
and performance tuning beyond a recorded frame budget. Those stay human-directed (ADR-005) or deferred.

## Consequences

**Positive:** a real playable slice with machine-checkable evidence; the engine choice is explicit and portable;
the workstream gains its first game adapter.

**Negative / risks:** Godot-specific code; a later engine change is a port; the slice's visual quality is prototype
primitives; capture depends on a desktop session.

## Verification

Generated evidence lives in [PHASE-1-EVIDENCE.md](PHASE-1-EVIDENCE.md), and machine-readable copies under
`workstream/state/game-*.json`.

## Open questions

- Art direction and content scope for the next slice (ADR-005 / PG-D17).
- Whether to keep PC-only for Phase 2 or add a mobile gate (ADR-001).
- Whether the renderer/capture path should use movie-maker or OBS for future evidence.

## Amendment 2026-10-26

[ADR-018](ADR-018-unity-default.md) makes Unity 6000.6.7f1/PC the default for newly initialized projects.
This ADR's Godot Phase-1 choice still describes the current ProjectGypsy game until the separate UltraBlade 2 Stage B
migration is verified; it is not silently relabelled.
