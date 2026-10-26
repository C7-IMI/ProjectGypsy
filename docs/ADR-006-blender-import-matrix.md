# ADR-006 — Blender 5.2.3 LTS to engine import matrix and golden assets

**Status:** Accepted, 2026-10-25 · **Decision owner:** operator (activation/hardware decisions) · **Reviewer:** Lead
**Scope:** how Blender-exported assets are proven importable by the engines this workstream targets.
**Related:** [ADR-001](ADR-001-engines.md) (engine adapters) · [ADR-002](ADR-002-art-pipeline.md) (export contract,
provenance) · [ADR-003](ADR-003-workstream-architecture.md) (capability bus) · [ADR-005](ADR-005-character-animation-automation.md)
(character pipeline) · [IMPORT-MATRIX.md](IMPORT-MATRIX.md) (generated evidence) ·
[DEFERRED.md](../DEFERRED.md) PG-D16.

## Context

1. **Import is where a neutral export fails.** Axes, units, transforms, leaf bones, animation sampling, morph targets
   and material channels are the usual places where a file that looks right in Blender arrives wrong in an engine.
2. **The engines are not equally testable here.** Godot 4.7.2 imports headlessly; Unity 6000.6.7f1 has no licence
   (batchmode exits 198); UE 5.8.4 fails its hardware gate (4 GB VRAM, 51.5 GB free on D:); Flax 1.13 has no
   demonstrated headless path ([ENGINE-SMOKE.md](ENGINE-SMOKE.md)). Only Blender and Godot can be exercised locally.
3. **The matrix is already implemented, not hypothetical.** [assets/test/golden/generate_golden.py](../assets/test/golden/generate_golden.py)
   builds four golden sources and their GLB/FBX exports; [scripts/import_matrix.py](../scripts/import_matrix.py)
   re-imports them in Blender, validates the glTF, imports them into Godot and records blocked engines; the generated
   report is [IMPORT-MATRIX.md](IMPORT-MATRIX.md) plus `workstream/state/import-matrix.json`, capability
   `art.import.matrix` (maturity **partial**). This ADR formalises that kit as the contract, so a future upgrade has
   something exact to fail against and "it imports" is never a claim without a matrix cell.

## Decision

Adopt a committed **golden-asset kit** and a **per-engine, per-format import matrix**. Every asset class is exported
from its `.blend` source with pinned Blender 5.2.3 settings, re-imported and measured in Blender, validated as glTF,
and asserted in each engine that can actually run. Blocked engines are recorded as blocked with their evidence, never
as a pass.

### D1 — Golden asset kit

| Asset | Class | Source invariants | What the matrix asserts today |
| --- | --- | --- | --- |
| `static_cube` | static + material | 2 m cube at z = 1, one Principled material | loads, 1 mesh, material present, Blender round-trip counts match |
| `rigged_character` | skinned + clips | 3-bone armature (root/spine/hand), weighted mesh, 3 NLA clips (Idle/Wave/Turn, 24 frames) | loads, 1+ mesh, 3 animations, skin present, glTF validation |
| `morph_face` | morph/face | mesh with Basis + Smile shape key | loads, 1 mesh, shape keys survive both formats |
| `lod_set` | LOD + collision | `character_LOD0/1/2` plus `character_COLLISION`, four meshes | loads, 4 meshes, names preserved |

Each asset keeps its `.blend` source, GLB and FBX export, and the Blender round-trip counts in
`artifacts/golden/golden-report.json` (gitignored). The kit is a **connectivity and contract** test, not art quality.

### D2 — Format policy per engine

| Engine | Primary | Secondary | Status here | Evidence / note |
| --- | --- | --- | --- | --- |
| Godot 4.7.2 | **glTF/GLB** | not content-asserted | **PASS (import)** | headless `--import` + scene assertions pass; headless has no renderer and export templates are missing |
| Unity 6000.6.7f1 | **FBX** (ModelImporter) | glTF needs a package (not installed) | **BLOCKED** | no licence; batchmode exit 198 |
| UE 5.8.4 | **FBX** (native importer) | glTF needs a plugin (unverified) | **BLOCKED** | hardware gate: 4 GB < 8 GB, 51.5 GB < 60 GB |
| Flax 1.13 | FBX or glTF | — | **NOT TESTED** | experimental; no headless build/run path demonstrated |

glTF is the primary *validation* format because it is open, JSON-inspectable and supportable by the installed
glTF tooling ([Khronos glTF](https://registry.khronos.org/glTF/)). FBX stays the interchange for Unity and UE5 because
it is their native path; a project that targets only Godot exports glTF and skips FBX. Unity's glTF route needs an
extra package (e.g. glTFast) and UE's needs a plugin; neither is part of this matrix, so both are deferred, not assumed.

### D3 — Pinned Blender 5.2.3 export settings

The kit pins these explicitly (values as implemented in `generate_golden.py`):

| Format | Setting | Pinned value | Why |
| --- | --- | --- | --- |
| glTF | `export_format` | `GLB` | one file, embedded buffers, deterministic packaging |
| glTF | `export_yup` | `True` | glTF is Y-up; engines consume the converted axes |
| glTF | `export_apply` | `True` | modifiers applied, no live modifiers in the engine |
| glTF | `export_animations`, `export_force_sampling` | `True` | sampled animation, stable key count |
| glTF | `export_nla_strips` | `True` | one named NLA track per clip becomes one named animation |
| glTF | `export_morph`, `export_skins`, `export_materials` | `True`, `True`, `EXPORT` | shape keys, skin joints, materials carried |
| FBX | `object_types` | `{"ARMATURE", "MESH"}` | no cameras/lights/helpers in an asset export |
| FBX | `add_leaf_bones` | `False` | avoids extra terminal joints (Blender's default is `True`) |
| FBX | `apply_scale_options` | `FBX_SCALE_ALL` | scene unit/global scale applied consistently (default is `FBX_SCALE_NONE`) |
| FBX | `axis_forward` / `axis_up` | `-Z` / `Y` | FBX Y-up conversion; same as the exporter defaults |
| FBX | `bake_anim` + NLA | `True`, strips `True`, all-actions `False`, step `1.0`, force start/end `True`, simplify `0.0` | one take per named clip, sampled every frame, no simplification |
| FBX | `path_mode`, `embed_textures` | `COPY`, `False` | textures copied beside the file, never embedded; final material truth stays ADR-002 |
| FBX | `use_selection` | `False` | whole-kit export; per-asset export should select explicitly (O8) |

**Defaults the kit relies on, not yet pinned:** glTF `export_leaf_bone=False`, `export_def_bones=False`,
`export_optimize_animation_size=True`, `export_frame_range=False`; FBX `apply_unit_scale=True`, `global_scale=1.0`,
`use_space_transform=True`, `bake_space_transform=False`, `primary_bone_axis=Y`, `secondary_bone_axis=X`,
`use_armature_deform_only=False`, `mesh_smooth_type=OFF`, `use_tspace=False`. Pinning the silent ones is O7.

### D4 — FBX quirks the matrix pins and asserts

| Quirk | Blender 5.2.3 default | Pin / assertion |
| --- | --- | --- |
| **File version** | exporter writes FBX 7.4 binary; header version int **7400** (verified) | the version follows the Blender/exporter, not a setting the kit changes — assert the header and record it with the Blender version |
| **Axes** | `-Z` forward, `Y` up, `use_space_transform=True` converts Blender Z-up | assert a direction marker arrives as the engine's convention (Unity +Z, UE +X), not an assumed one |
| **Units** | FBX is centimetre-based; `apply_unit_scale=True` with `global_scale=1.0`; kit pins `FBX_SCALE_ALL` | assert the imported asset measures the source size in metres |
| **Transforms** | `bake_space_transform=False`; object transforms become node transforms | assert no live non-uniform scale; apply transforms in the source before export |
| **Leaf bones** | `add_leaf_bones=True` adds a terminal bone per chain | pinned `False`; assert joint count equals the armature's bones |
| **Bone axes** | `primary_bone_axis=Y`, `secondary_bone_axis=X` | keep defaults and assert roll/orientation; retargeting depends on it (ADR-005 O2) |
| **Animation sampling** | `bake_anim=True`, step 1, simplify `1.0` | kit pins simplify `0.0`; assert clip names, frame count and duration |
| **NLA vs actions** | both paths exist and change take naming | kit pins NLA strips (one named track per clip), all-actions off; assert 3 clips on the rigged asset |
| **Smoothing / tangents** | `mesh_smooth_type=OFF`, `use_tspace=False` | not pinned by the kit — engines may smooth differently; pinning is O7 |
| **Morph targets** | shape keys export as FBX blend shapes | assert names and count (Basis + Smile) after import |
| **Materials** | FBX has no metallic-roughness standard; Principled maps approximately | material **truth** is the ADR-002 descriptor; assert material slot names and channel intent, never FBX texture paths |
| **Armature deform-only** | `use_armature_deform_only=False` exports control bones too | for game rigs, pin deform-only to keep Rigify's 706-bone control rig out of the engine (ADR-005 O3) |

### D5 — Headless assertions

| Layer | Assertion today | Planned extension |
| --- | --- | --- |
| Blender export | exporter exits 0; `.blend` saved; GLB and FBX exist with recorded sizes | per-asset selection and a golden manifest of expected counts |
| Blender round-trip | re-import each export into an empty scene; assert objects/meshes/armatures/actions/shape keys/materials | assert joint names, morph names, clip durations, AABB and units |
| glTF validation | `gltf-transform validate` reports no errors; warnings recorded, not hidden (`NODE_SKINNED_MESH_NON_ROOT`) | fail the matrix on warnings once the expected-warning allowlist is versioned |
| Godot | headless `--import`, then a `SceneTree` script loads each GLB and prints mesh/animation counts; matrix fails on mismatch | assert skeleton bone count, morph count, material slots, AABB scale; FBX content case |
| Unity | not run — no licence (batchmode exit 198) | `-batchmode -executeMethod` import and log assertions after activation |
| UE5 | not run — hardware gate | `UnrealEditor-Cmd` import on a gated/remote machine |
| Flax | not run — no headless path | adapter first, then the same assertions |

A failed assertion names expected and observed values. An engine whose precondition fails is recorded as
`blocked: <reason>`; an absent engine is `not installed`, never `pass`.

### D6 — Add-on smoke tests

- Add-ons are enabled with `bpy.ops.preferences.addon_enable(module=...)`; `addon_utils.enable` returned False for
  Rigify in the probe, so automation uses the operator form.
- **Rigify (bundled):** metarig creation and `pose.rigify_generate()` were run headless — 159-bone metarig → 706-bone
  rig. The smoke test must assert a **deform-only** subset and export, not the whole control rig.
- **glTF and FBX exporters are bundled** in Blender 5.2.3 and enabled at factory startup; their generator string
  (`Khronos glTF Blender I/O v5.2.41`) and FBX version 7400 are recorded per run.
- Every add-on added later needs a capability manifest, a version pin, a smoke test that **can fail**, and a removal
  path (ADR-003 self-extension). No paid add-on is a dependency. Add-on tests are not yet automated (PG-D16).

### D7 — Version compatibility policy

- **Pin Blender 5.2.x LTS** (installed 5.2.3). The golden expected values belong to that minor; on a Blender upgrade,
  re-run the kit and review every changed count before blessing the new baseline.
- **Pin the engine versions per project** (ADR-001: Godot 4.7.2, Unity 6000.6.7f1, UE 5.8.4, Flax 1.13). A mismatch is
  refused by the project manifest; the matrix records the version it ran against.
- **Matrix cells have three states — pass, pending, blocked — and a blocked cell carries its evidence** (licence,
  gate, no headless path). A blocked cell expires only when its gate changes and the run repeats. No CI runs Unity or
  UE5 here; the matrix is a local/remote gate (PG-D16), recorded with the machine and versions.

### D8 — Report format

`scripts/import_matrix.py` writes `workstream/state/import-matrix.json` and regenerates [IMPORT-MATRIX.md](IMPORT-MATRIX.md).
The JSON holds the Blender version; per-asset export errors, round-trip counts and paths; glTF validation status and
warnings; the engine matrix with status and reason; and Godot's import exit, results and failures. It exits non-zero on
any failure and prints `IMPORT_MATRIX PASS|FAIL`; the record is committed, `artifacts/` is not.

## Blocked or gated here

| Engine | Status | Evidence |
| --- | --- | --- |
| Godot 4.7.2 | import **PASS**; export/render pending | `IMPORT-MATRIX.md` scene assertions; export templates missing; headless has no renderer |
| Unity 6000.6.7f1 | **BLOCKED — licence** | batchmode exit 198, "No valid Unity Editor license found" ([ENGINE-SMOKE.md](ENGINE-SMOKE.md)) |
| UE 5.8.4 | **BLOCKED — hardware gate** | 4 GB VRAM < 8 GB; 51.5 GB free < 60 GB; capability `engine.ue5.build` is `blocked` |
| Flax 1.13 | **NOT TESTED — experimental** | editor detected; no headless build/run demonstrated |

## Consequences

- A Blender or engine upgrade has an exact regression target; a format claim is backed by a matrix cell.
- Costs: two formats to maintain, a golden kit to regenerate, FBX quirks to keep pinned, and two engines that cannot
  be proven on this machine until the licence/hardware changes.
- The kit is deliberately low-art: it proves connectivity, not visual fidelity; materials are simple Principled
  shaders and a texture-embedded case is next. Golden counts are version-sensitive — an unexplained change is a
  signal, not noise.

## Alternatives rejected

| Alternative | Why rejected |
| --- | --- |
| glTF only | Unity and UE5 do not import glTF natively; FBX is their path |
| FBX only | binary and opaque to validation; glTF gives the open, inspectable check |
| Trust engine defaults and eyeball the editor | unmeasured, unreproducible, and blocked for two engines here |
| Test only in a GUI | no headless assertion, no matrix cell, no CI path |
| Skip golden assets until the game exists | import defects then surface inside a paid art pipeline |
| Claim Unity/UE5 import from a file conversion alone | conversion is not import; the engine must load and be asserted |

## Open decisions

- **O1/O2 Unity activation; UE5 hardware or remote.** Unity cells stay blocked until a licence exists; UE5 needs
  gated or cloud hardware (PG-D11/PG-D13).
- **O3 Flax headless path.** Keep as experimental until a build/run command is demonstrated.
- **O4 glTF route for Unity/UE.** Which package/plugin (e.g. glTFast) is acceptable, if any, alongside FBX.
- **O5 Bone naming and humanoid mapping.** Unity Humanoid avatar, UE mannequin skeleton, Godot `Skeleton3D`;
  retarget policy follows the engine choice (ADR-005 O2).
- **O6 FPS and clip convention.** 30 fps is proposed (Godot's import default) and must be written into the shared asset
  spec before animation volume grows.
- **O7 Pin the remaining silent defaults.** `export_optimize_animation_size`, `mesh_smooth_type`, tangents, and
  `export_frame_range`; decide per-asset selection vs whole-kit export (O8).
- **O8 Per-asset export.** The kit exports everything at once; asset production should export an explicit selection and
  assert the expected object set.
- **O9 Texture-embedded material case.** Today's goldens use simple materials; a normal/ORM/alpha texture case is the
  next matrix asset.
- **O10 .blend sources in Git LFS**, and the retention policy for golden exports (`artifacts/` is gitignored).

## Evidence

| Claim | Observation |
| --- | --- |
| Golden kit and matrix run | `docs/IMPORT-MATRIX.md`, generated 2026-10-25T22:12:58-05:00 by `scripts/import_matrix.py` |
| Blender round-trip | static/morph/LOD pass both formats; rigged GLB 3 actions, FBX 3 actions (IMPORT-MATRIX tables) |
| glTF validation | Khronos validator via `gltf-transform validate`: no errors; `rigged_character` warning `NODE_SKINNED_MESH_NON_ROOT` recorded |
| Godot import | headless `--import` plus `SceneTree` assertions: static 1 mesh, rigged 3 animations, morph loaded, LOD 4 meshes |
| Blender exporter defaults | queried from the RNA API on 5.2.3: `add_leaf_bones=True`, `apply_scale_options=FBX_SCALE_NONE`, `bake_anim_simplify_factor=1.0`, axis `-Z`/`Y`, `mesh_smooth_type=OFF` — the kit pins the first three differently |
| FBX and glTF versions | FBX probe header `Kaydara FBX Binary`, version int **7400** (7.4); glTF probe reports `Khronos glTF Blender I/O v5.2.41`, glTF 2.0 |
| Unity / UE5 / Flax | blocked/gated per `ENGINE-SMOKE.md`; no import claim made |
| Add-on smoke | Rigify enable + generation verified manually (159 → 706 bones); not yet automated (PG-D16) |
