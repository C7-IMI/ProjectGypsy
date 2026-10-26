# IMPORT-MATRIX.md — Blender 5.2 golden-asset import matrix

Generated 2026-10-25T22:28:03-05:00 by scripts/import_matrix.py. This is Phase-0 evidence for
[ADR-006](ADR-006-blender-import-matrix.md); it is not an art-quality claim.

## Result

| Engine | Version | glTF/GLB | FBX | Status | Evidence / reason |
| --- | --- | --- | --- | --- | --- |
| Godot | 4.7.2 | PASS | not supported natively | PASS | headless --import + scene assertions: {"lod_set": {"animations": 0, "loaded": true, "meshes": 4}, "morph_face": {"animations": 0, "loaded": true, "meshes": 1}, "rigged_character": {"animations": 3, "loaded": true, "meshes": 1}, "static_cube": {"animations": 0, "loaded": true, "meshes": 1}} |
| Unity | 6000.6.7f1 | blocked | blocked | blocked: no licence | batchmode exited 198: No valid Unity Editor license found (docs/ENGINE-SMOKE.md) |
| UE5 | 5.8.4 | blocked | blocked | blocked: hardware gate | GPU VRAM 4.0 GB is below the 8 GB declared minimum; D: free space 51.5 GB is below the 60 GB declared minimum |
| Flax | 1.13 | not tested | not tested | experimental: not tested | experimental adapter; no headless build/run demonstrated |

## Blender round-trip

Blender 5.2.3 LTS exports each source to GLB and FBX, then re-imports each export into an empty scene.
Counts below are what Blender itself read back; the engine is what the engine read.

| Asset | Format | Objects | Meshes | Armatures | Actions | Shape keys | Materials | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| static_cube | glb | 1 | 1 | 0 | 0 | 0 | 1 | pass |
| static_cube | fbx | 1 | 1 | 0 | 0 | 0 | 1 | pass |
| rigged_character | glb | 3 | 2 | 1 | 3 | 0 | 1 | pass |
| rigged_character | fbx | 2 | 1 | 1 | 3 | 0 | 1 | pass |
| morph_face | glb | 1 | 1 | 0 | 0 | 2 | 1 | pass |
| morph_face | fbx | 1 | 1 | 0 | 0 | 2 | 1 | pass |
| lod_set | glb | 4 | 4 | 0 | 0 | 0 | 4 | pass |
| lod_set | fbx | 4 | 4 | 0 | 0 | 0 | 4 | pass |

## glTF validation (Khronos validator via gltf-transform)

| File | Status | Warning codes |
| --- | --- | --- |
| lod_set.glb | pass | - |
| morph_face.glb | pass | - |
| rigged_character.glb | pass | NODE_SKINNED_MESH_NON_ROOT |
| static_cube.glb | pass | - |

A warning is recorded, not hidden: NODE_SKINNED_MESH_NON_ROOT is expected with Blender's armature export and is
checked by the engine import test rather than treated as a pass by itself.

## Export metadata (recorded per run)

| Asset | glTF generator | glTF version | FBX header |
| --- | --- | --- | --- |
| static_cube | Khronos glTF Blender I/O v5.2.41 | 2.0 | 7400 (7.4) |
| rigged_character | Khronos glTF Blender I/O v5.2.41 | 2.0 | 7400 (7.4) |
| morph_face | Khronos glTF Blender I/O v5.2.41 | 2.0 | 7400 (7.4) |
| lod_set | Khronos glTF Blender I/O v5.2.41 | 2.0 | 7400 (7.4) |

## Pinned baseline

| Item | Value |
| --- | --- |
| Blender | 5.2.3 LTS |
| glTF export | GLB, apply modifiers, Y-up, animations, morphs, skins, NLA strips, force sampling |
| FBX export | FBX 7400, -Z forward / Y up, apply scale all, no leaf bones, bake animation via NLA strips |
| Godot | 4.7.2, headless import + scripted scene assertions |
| Unity | installed, no licence -> blocked |
| Unreal | 5.8.4, hardware gate fails (4 GB VRAM / free disk) -> blocked |
| Flax | 1.13, experimental -> not tested |

## Not tested / next

- Unity and UE5 FBX/glTF import on this machine: blocked by licence/hardware; re-run on an activated/higher-spec machine.
- Flax import: no demonstrated headless path.
- Add-on smoke tests (Rigify, retopo/UV add-ons): not yet automated; ADR-006 records the policy.
- Material/texture channel round-trip: the golden assets use simple Principled materials; a texture-embedded case is next.
- Rendered capture after import: capture capability is still planned.
