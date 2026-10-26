# ADR-018 — Unity is the default for new projects (Stage A)

- **Status:** accepted, 2026-10-26; Stage A only. The current ProjectGypsy game remains Godot until the separate
  UltraBlade 2 migration completes.
- **Decision owner:** operator.
- **Scope:** default engine for newly initialized Gypsy projects.
- **Related:** [ADR-001](ADR-001-engines.md), [ADR-009](ADR-009-vertical-slice.md), [UNITY-SLICE.md](UNITY-SLICE.md),
  [UNITY-PORT-INSTRUCTIONS.md](UNITY-PORT-INSTRUCTIONS.md), [../unity/LeftBehind](../unity/LeftBehind).

## Context

Unity 6000.6.7f1 is installed, licensed, and proven on Windows: LeftBehind builds a Windows player, runs the
three-collectible demo, and captures a frame. Unity is therefore a credible production engine here. It is not yet at
full Gypsy parity: the Unity Android Build Support module is not installed, the hero/art pipeline is Godot-only, the
asset import matrix is Godot-first, and engine.unity.build is proven through the LeftBehind toolpack rather than as a
generic adapter.

Continuing to make Godot the implied default for every new project would understate what has been proven and force the
operator to override a legacy choice. Continuing to call the current Godot game a Unity project would be false.

## Decision

1. **Stage A:** new projects created with the Gypsy project init command default to **Unity 6000.6.7f1**, target PC.
   The engine and version remain overridable. A different installed Unity version must be passed explicitly.
2. **The existing ProjectGypsy game remains Godot** until Stage B migrates it. The current game/project.gypsy.json is
   not relabelled or silently rewritten.
3. **Stage B is a separate port in the UltraBlade 2 repository.** The migration instructions are in
   [UNITY-PORT-INSTRUCTIONS.md](UNITY-PORT-INSTRUCTIONS.md); the current session must not touch that repo.
4. **No parity claim.** Unity default means PC new-project default. Mobile requires Unity Android Build Support; hero
   integration, asset import and a generic Unity adapter remain work to be done and verified.
5. **No fake default.** If a new project needs mobile, the operator must install the Unity Android module and the agent
   must build/launch/verify it; the default manifest alone is not evidence.
6. **Godot remains the complete legacy pipeline** and is retained until Unity passes the same acceptance markers and
   capture.

## Consequences

**Positive:** new projects start on the engine with the strongest licence/build evidence for PC; the existing game is
not destabilized; the migration gets a clear owner/repo boundary.

**Negative / risks:** a new Unity project starts without the Godot hero/mobile/import pipeline; Unity Android is not
installed; the default version is pinned to the current install and must be overridden on another machine. These are
recorded rather than hidden.

## Non-goals

Migrating the current game in this repository, deleting Godot, claiming Unity mobile before the module/build exists, or
claiming Unity asset/hero parity before the Stage B port is verified.
