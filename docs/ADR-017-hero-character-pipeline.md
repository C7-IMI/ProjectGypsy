# ADR-017 — Hero art and character pipeline

- **Status:** accepted, 2026-10-26; first hero asset built and integrated into the Godot slice.
- **Decision owner:** operator; implemented autonomously as the missing PG-D17 work.
- **Scope:** art direction, procedural authoring, rig, actions, textures, export, validation, engine integration.
- **Related:** [ART-DIRECTION.md](ART-DIRECTION.md), [ADR-002](ADR-002-art-pipeline.md), [ADR-005](ADR-005-character-animation-automation.md), [ADR-009](ADR-009-vertical-slice.md), [assets/hero/ART-BRIEF.md](../assets/hero/ART-BRIEF.md), [scripts/hero/README.md](../scripts/hero/README.md), [DEFERRED.md](../DEFERRED.md).

## Context

The slice had a playable capsule and collectibles but no hero art/character pipeline. PG-D17 recorded the gap: no hero brief, no rigged asset, no animation set, no texture/material pass and no engine integration. The machine has Blender 5.2.3 and Godot 4.7.2, but no sculpt/hair/cloth tooling and only 4 GB VRAM; a photoreal or sculpt-heavy hero is not the right first deliverable. The correct first pass is a stylized, original, low-poly character that exercises the real pipeline end-to-end.

## Decision

1. **Original character, original assets.** The hero is the **Wayfarer**: a hooded traveller with an ochre mantle, deep-teal tunic, leather boots/satchel and cyan emissive eyes/chest shard. No external models, textures, face scans or third-party IP. The art direction is [ART-DIRECTION.md](ART-DIRECTION.md); the asset brief is [assets/hero/ART-BRIEF.md](../assets/hero/ART-BRIEF.md).
2. **Generator is the source of truth.** scripts/hero/generate_wayfarer.py is a reproducible Blender 5.2.3 headless generator: geometry, 256x256 procedural atlas, 20-joint armature, normalized distance-based skin weights, three actions and GLB/FBX export with re-import verification. Committed exports are the build artifacts; the generator is how they are regenerated.
3. **Real rig and animation.** 20 joints (19 deform), max three influences, normalized weights, no unweighted vertices. Actions: idle (3.04 s), run (1.04 s), reach (2.04 s), all authored at 24 fps on the same armature.
4. **Asset and texture.** 716 source verts / 1,126 triangles, height 1.905 m, feet at the origin, four materials and one embedded 256x256 atlas. The GLB is the engine asset; FBX is a compatibility export and is byte-nondeterministic.
5. **Godot integration preserves gameplay.** The visual is instanced under Player at local y = -0.9; the capsule collision remains. hero_visual.gd selects idle/run from player speed and a one-shot reach on collection; missing clips warn, never gate movement. Autopilot, crystal collection and the GYPSY_DEMO_OK marker are unchanged.
6. **Validation is non-Blender and non-network.** scripts/hero/validate_wayfarer.py parses the GLB directly and checks files, GLB magic, rig/skin/weights, three actions, bounds, materials, embedded texture, mirror hash and the Godot integration. The hero toolpack and slice make generation/validation/capture repeatable.
7. **Capture is evidence.** The gameplay capture and the front/back hero preview are reviewed; a hero that is invisible, mis-scaled, untextured or breaks the demo is a failure, not a complete pipeline.
8. **Honest prototype boundary.** This is prototype art, not final production art. No facial rig, cloth/cape simulation, LODs, normal maps, exported-binary windowed capture or Unity/UE5/Android hero import in this pass.

## Evidence

- Generator: exit 0, WAYFARER_GEN_OK glb=... bytes=282668 bones=20 actions=3 tris=1126; GLB and atlas byte-identical on rerun; FBX round-trip clean.
- Validator: exit 0, HERO_VALIDATE_OK checks=60 bones=20 actions=3 tris=1126 glb=282668B (60/60).
- Godot: headless demo exit 0 with HERO_VISUAL ready clips=[idle, reach, run] missing=[] and GYPSY_DEMO_OK collected=3 frames=143; integration check HERO_CHECK_OK idle->run->reach->idle.
- Build/verify/capture: game verify demo/build/capture True; game capture produced artifacts/game/frame.png (1280x720) with the hero visible; preview contact sheet shows idle/run/reach.
- Asset hashes: GLB fca6793997fb312ff4d3a070b2618f90f09d213d996688237af940737f8de051; atlas 28d6d134dd87a4973cd1ab0476f07d79b4b8eb7c84b556ff28e6a21982e71441.
- Toolpack hero.wayfarer and slice hero exercise generate -> validate -> capture; toolpacks check accepts them.

## Consequences

**Positive:** the project has a real hero asset, rig, action set, texture/material pass, engine integration and a reproducible validation path. Future characters can copy the generator/validator/integration contract instead of starting from a capsule.

**Negative / risks:** the art is deliberately prototype low-poly; the gameplay camera is still distant and the back is darker than the preview. FBX is not byte-reproducible. The pipeline is Blender-version pinned. No device/UE5 hero levels exist. These are recorded, not hidden.

## Non-goals

Production sculpting, facial animation, cloth/hair simulation, LOD chain, normal/roughness texture authoring, mocap, third-party asset marketplaces, Unity/UE5/Android hero integration.
