# ADR-017 — Hero art and character pipeline

- **Status:** accepted, 2026-10-26; first hero asset built and integrated into the Godot slice.
- **Decision owner:** operator; implemented autonomously as the missing PG-D17 work.
- **Scope:** art direction, procedural authoring, rig, actions, textures, export, validation, engine integration.
- **Related:** [ART-DIRECTION.md](ART-DIRECTION.md), [ADR-002](ADR-002-art-pipeline.md), [ADR-005](ADR-005-character-animation-automation.md), [ADR-009](ADR-009-vertical-slice.md), [assets/hero/ART-BRIEF.md](../assets/hero/ART-BRIEF.md), [scripts/hero/README.md](../scripts/hero/README.md), [DEFERRED.md](../DEFERRED.md).

## Context

The slice had a playable capsule and collectibles but no hero art/character pipeline. PG-D17 recorded the gap: no hero brief, no rigged asset, no animation set, no texture/material pass and no engine integration. The machine has Blender 5.2.3 and Godot 4.7.2, but no sculpt/hair/cloth tooling and only 4 GB VRAM; a photoreal or sculpt-heavy hero is not the right first deliverable. The correct first pass is a stylized, original, low-poly character that exercises the real pipeline end-to-end.

## Decision

1. **Original character, original assets.** The hero is the **Wayfarer**: a hooded traveller with an ochre mantle, deep-teal tunic, leather boots/satchel and cyan emissive eyes/chest shard. No external models, textures, face scans or third-party IP. The art direction is [ART-DIRECTION.md](ART-DIRECTION.md); the asset brief is [assets/hero/ART-BRIEF.md](../assets/hero/ART-BRIEF.md).
2. **Generator is the source of truth.** scripts/hero/generate_wayfarer.py is a reproducible Blender 5.2.3 headless generator: geometry, 512x512 base/normal/roughmetal maps, a 23-joint armature with a 3-bone cape chain, normalized distance-based skin weights, three actions, a Smile morph, LOD1/LOD2 exports and GLB/FBX export with re-import verification. Committed exports are the build artifacts; the generator is how they are regenerated.
3. **Real rig and animation.** 20 joints (19 deform), max three influences, normalized weights, no unweighted vertices. Actions: idle (3.04 s), run (1.04 s), reach (2.04 s), all authored at 24 fps on the same armature.
4. **Asset and texture.** 1,126 triangles, height 1.905 m, feet at the origin, four materials, 512x512 base/normal/roughmetal maps, a Smile morph and LOD1 (615 tris) / LOD2 (306 tris) variants. The GLB is the engine asset; FBX is a compatibility export and is byte-nondeterministic.
5. **Godot integration preserves gameplay.** The visual is instanced under Player at local y = -0.9; the capsule collision remains. hero_visual.gd selects idle/run from player speed and a one-shot reach on collection; missing clips warn, never gate movement. Autopilot, crystal collection and the GYPSY_DEMO_OK marker are unchanged.
6. **Validation is non-Blender and non-network.** scripts/hero/validate_wayfarer.py parses the GLB directly and checks files, GLB magic, rig/skin/weights, cape motion, three actions, bounds, materials/maps, Smile morph, LODs, mirror hash and the Godot integration. The hero toolpack and slice make generation/validation/capture repeatable.
7. **Capture is evidence.** The gameplay capture and the front/back hero preview are reviewed; a hero that is invisible, mis-scaled, untextured or breaks the demo is a failure, not a complete pipeline.
8. **Honest production-pass boundary.** This is a production-shaped prototype, not final art: LOD1/LOD2 exist but the slice renders LOD0 only; the Smile morph is exported but not driven in gameplay; the maps are procedural, not hand-painted; there is no facial rig, cloth simulation or runtime LOD switching; no Unity/UE5/Android hero import in this pass.

## Evidence

- Generator (production pass): exit 0, WAYFARER_GEN_OK glb=... bytes=904964 bones=23 actions=3 tris=1126 lods=2 morph=Smile maps=3; GLB/LODs/maps byte-identical on rerun; FBX round-trip clean.
- Validator: exit 0, HERO_VALIDATE_OK checks=94 bones=23 actions=3 tris=1126 lods=2 maps=3 morph=Smile glb=904964B (94/94).
- Godot: headless demo exit 0 with HERO_VISUAL ready clips=[idle, reach, run] missing=[] and GYPSY_DEMO_OK collected=3 frames=143; integration check HERO_CHECK_OK idle->run->reach->idle.
- Build/verify/capture: game verify demo/build/capture True; game capture produced artifacts/game/frame.png (1280x720) with the hero visible; preview contact sheet shows idle/run/reach.
- Asset: GLB 904,964 B (3ce15953...); LOD1 877,796 B; LOD2 832,252 B; FBX 1,149,484 B; 512x512 base/normal/roughmetal maps.
- Toolpack hero.wayfarer and slice hero exercise generate -> validate -> capture; toolpacks check accepts them.

## Consequences

**Positive:** the project has a real hero asset, rig, action set, texture/material pass, engine integration and a reproducible validation path. Future characters can copy the generator/validator/integration contract instead of starting from a capsule.

**Negative / risks:** the art is deliberately prototype low-poly; the gameplay camera is still distant and the back is darker than the preview. FBX is not byte-reproducible. The pipeline is Blender-version pinned. No device/UE5 hero levels exist. These are recorded, not hidden.

## Non-goals

Production sculpting/retopology, facial rig, cloth/hair simulation, runtime LOD switching, hand-painted texture authoring, mocap, third-party asset marketplaces, Unity/UE5/Android hero integration.
