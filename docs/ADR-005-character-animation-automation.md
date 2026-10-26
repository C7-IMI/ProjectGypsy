# ADR-005 — Character and animation automation: automate the loop, not the taste

**Status:** Accepted, 2026-10-25 · **Decision owner:** operator (art direction, approvals) · **Reviewer:** Lead
**Scope:** how characters are generated, evaluated, critiqued, tweaked, approved, exported and validated.
**Related:** [ADR-002](ADR-002-art-pipeline.md) (sources, validators, provenance) · [ADR-003](ADR-003-workstream-architecture.md)
(capability bus, verification harness) · [ADR-004](ADR-004-generative-media.md) (generated media) ·
[ADR-006](ADR-006-blender-import-matrix.md) (engine import) · [ADR-007](ADR-007-language-boundaries.md) ·
[TOOLCHAIN.md](../TOOLCHAIN.md) · [DEFERRED.md](../DEFERRED.md) PG-D15, PG-D17, PG-D18.

## Context

1. **The goal** is a human-directed character pipeline: blockout, sculpt, retopo, UV, materials, rig, skin, animation,
   expression, LOD and engine import — with agents operating deterministic tools and humans holding taste.
2. **What exists.** Blender 5.2.3 LTS runs headless: export/re-import of GLB and FBX, Rigify enable and generation, and
   a 256×256 EEVEE render were all exercised on 2026-10-25 (Evidence). Godot 4.7.2 imports the golden kit headlessly
   (ADR-006). Unity has no licence, UE 5.8.4 fails its hardware gate, Flax has no headless path.
3. **Nothing in this pipeline is built.** The capability manifests are `planned` — `art.character.blockout`,
   `art.character.retopo`, `art.character.rig`, `art.character.validate`, `art.animation.retarget`,
   `art.lookdev.turntable` — and `art.import.matrix` is `partial`. No orchestrator or console exists (PG-D15), and
   the hero character and art direction do not exist (PG-D17); the Phase-1 engine is chosen (Godot 4.7.2, ADR-009).
   **Amendment 2026-10-26:** Unity licence is now proven via batchmode smoke; no Unity import/character pipeline is claimed
   yet.
4. **Hardware:** T600 **4 GB VRAM**, 64 GB RAM, C: 242.3 GB / D: **51.5 GB** free (re-checked). 4 GB is workable for
   game-scale sculpt/retopo/animation, but high-poly sculpting, large textures and production renders must be bounded.
   No mocap or capture hardware, and no drawing tablet, is recorded in [TOOL-INVENTORY.md](../TOOL-INVENTORY.md).
5. **Taste is not automatable here.** Silhouette, appeal, style, deformation feel and motion quality are human
   decisions. The agent's job is candidate generation, measurement, evidence and bookkeeping. The machine does not
   approve its own character work.

## Decision

Automate the loop: **generate** candidate sets, **evaluate** them with deterministic gates, **critique** them against
a written rubric, **tweak** parameters and re-run — then a human approves the promotion. Every stage produces
evidence and a record; no stage is approved by passing gates alone.

### D1 — The four automation modes

| Mode | Agent does | Outputs | Human role | Failure behaviour |
| --- | --- | --- | --- | --- |
| **Generate** | runs `bpy`/CLI to produce N candidates from a spec, seed and budgets | candidate sources, descriptors, previews | sets the spec and the candidate count | no candidate produced → stop and report, never hand-edit a candidate into shape |
| **Evaluate** | runs gates and measurements (D2, `art.character.validate`) | JSON gate report, contact sheet, diffs | reads the report; may waive a soft gate only in writing | a red hard gate blocks promotion |
| **Critique** | model or human writes a critique against the rubric: silhouette, appeal, readability, deformation, motion | written critique with evidence links; no score without evidence | judges and records the decision | critique is advisory; it never promotes |
| **Tweak** | applies parameter deltas (proportions, tri budget, weights, curves), re-runs and diffs against the previous candidate | new candidate revision + diff record | approves the tweak direction | two failed tweaks on the same gate → change method, not the parameter |

### D2 — Stages and gates

| Stage | Capability (maturity) | Hard gate (machine-checkable) | Human gate |
| --- | --- | --- | --- |
| Brief / proportions | none (human) | scale convention and budget declared before work; reference provenance recorded | style, concept, proportions |
| Blockout | `art.character.blockout` (planned) | metres/scale correct, proxy inside budget, silhouette proxy captured | silhouette and proportion approval |
| Sculpt | none — human work | poly cap for the high-poly source, non-manifold count, self-intersection report | form and detail approval |
| Retopo / UV | `art.character.retopo` (planned) | manifold where required, quad/pole bands, no UV overlap, 0–1 range, island padding, texel-density band | topology and UV layout approval |
| Materials | ADR-002 texture pipeline | descriptor channels complete, colour space, texel density, provenance record | look approval |
| Rig / skin | `art.character.rig` (planned) | bone count/naming against the skeleton spec, single root, every vertex weighted, sum ≈ 1, ≤ 4 influences, no zero-weight verts | deformation tests |
| Animation / retarget | `art.animation.retarget` (planned) | fps and range, loop first/last pose match, root motion continuity, foot-slide under threshold, no scale keys | motion approval |
| Verification | `art.character.validate` (planned) | every gate has a failing fixture; report lists pass/fail per gate and revision | reviews the aggregate |
| Lookdev / review | `art.lookdev.turntable` (planned) | expected frame count, resolution, no blank frames | the only place "looks right" is decided |
| Import | `art.import.matrix` (partial) | ADR-006 assertions pass for the export format used | engine-import acceptance |
| Performance | `perf.profile`, `perf.optimize` (planned) | measured before/after on a fixed scene; reversible; budget recorded | approves the quality/performance trade-off |

Poly budgets, texel-density bands and LOD ratios are **art-direction decisions** and have no default here; ADR-002 O5
records that the operator owns them. Mechanical gates have exactly one threshold each and fail by naming expected
and observed values. Every new gate is proven red on a broken fixture before it is trusted (§1.5).

### D3 — Candidate sets and promotion

- Candidate id: `CHAR-<name>-<stage>-<n>`, with a parameters JSON (including seed), the source file, previews and the
  gate report. The gallery is the set of candidates, not a chat.
- Blockout, rig and retopo stages generate at least **3 candidates** when the stage is being explored; a single
  candidate is acceptable only for a mechanical re-run of an approved spec.
- Candidates live in `artifacts/` (gitignored) with their record; the **approved** source is promoted to
  `assets/src/characters/<name>/` as a new revision. An approved revision is never overwritten — a tweak creates the
  next revision.
- The comparison is a **contact sheet plus measurements** (tri count, height, bone count, loop delta), not a claim in
  prose. Losers stay in the record until the stage's approval is superseded; retention policy is open (O9).

### D4 — Review bundle and approval

The console is deferred (PG-D15) and interface design is parked (PG-D4). What is decided now is the **bundle the
console will present**, so approval does not wait for UI:

- gate report (JSON) and a one-page summary; turntable frames or MP4; ImageMagick contact sheet; the GLB/FBX pair;
  diff against the previous revision; critique text; provenance record; and the proposed approval record.
- Approval is a JSON record in `records/approvals/`: candidate id, stage, approver, decision
  (`approved`/`rejected`/`needs-changes`), timestamp, evidence hash, notes. A promotion without one fails validation.
- Rendered evidence is **evidence, not a quality judgement**: a captured turntable proves the file is viewable, not
  that the character is good. Only the human gate decides the latter.

### D5 — Tools, roles and hardware

| Role | Who / what | Status and limit |
| --- | --- | --- |
| Art direction, approval | human art director / operator | the only approver of taste and promotion |
| Execution | agent via Blender `bpy` and CLI tools | deterministic, logged, headless-verified |
| DCC | Blender 5.2.3 LTS | sculpt, retopo, rig, animation, bake, export, render |
| Auto-rig | Rigify (bundled add-on) | enabled with `bpy.ops.preferences.addon_enable`; a 159-bone metarig generated a 706-bone rig headless |
| Mesh processing | MeshLab, trimesh, scipy | decimation/remesh/inspection — **not** quad retopology |
| Textures | Krita, Material Maker, Blender bake | via ADR-002 sources and provenance |
| Review media | ImageMagick, FFmpeg, Blender EEVEE | contact sheets, turntables; a 256×256 headless render was verified |
| Import validation | Godot 4.7.2 headless; ADR-006 kit | import-only on this machine |
| Explicit non-tools | paid auto-retopo (no licence), mocap/face capture (no hardware), AI mesh generation (ADR-004, non-commercial), console (PG-D15) | not installed, not pretended |

### D6 — Provenance, AI and licensing

- The `.blend` is the source of truth (ADR-002, Git LFS); bakes, textures and engine files are generated derivatives
  with records. The character record adds rig/skeleton spec id, clip names and fps to the ADR-002 record.
- AI-assisted concepts, textures or meshes are imported sources under ADR-004: prototype-only while the model licence
  is CC BY-NC, human-approved, and never shipped without a licence review and a provenance record.
- No generated art without provenance; a missing record is a validator failure, not a warning.

### D7 — Phased delivery

| Phase | Deliverable | Gate |
| --- | --- | --- |
| 0 (this ADR) | this decision + the planned capability manifests | reviewed; no code claimed |
| 1 | one static character part: blockout → retopo → UV → material → GLB/FBX; gate report + turntable; Godot import | all hard gates green, human approval, ADR-006 `static_cube`/`rigged_character` assertions pass |
| 2 | rig + skin (Rigify variant or custom), two looping clips, deform-only export; Godot import | deformation review, import assertions, loop gate |
| 3 | candidate sets, evaluate/critique/tweak loop, review bundles and approval records | a stage completes with 3 candidates and one recorded approval |
| 4 | face/morphs and hand-keyed performance animation (no mocap) | morph naming/count gates, performance review |
| 5 | LOD/collision, perf budgets (`perf.*`, PG-D18), engine profiles | measured budget on a fixed scene; Unity after licence, UE gated |
| 6 | console presentation of the same bundles (PG-D15) | adds no capability the CLI lacks |

## Honest limits

- **Rigify is not a game rig.** Headless generation worked (159-bone metarig → 706-bone rig), but the default control
  rig is far over a game bone budget; a deform-only export profile and a decided Rigify variant (or a custom rig) are
  open (O3). `addon_utils.enable("rigify")` returned False — automation must use the operator form, which worked.
- **Sculpt and retopo are not automated here.** Agents can block out and remesh; MeshLab's remesher is not quad
  retopology, and no auto-retopo tool is installed.
- **Automatic weights are unverified on production meshes.** The weight gates check mechanics, not deformation.
- **No mocap, face capture or tablet is recorded.** Performance animation is hand-keyed/reference-driven until
  hardware exists (PG-D11); foot-slide/retarget gates therefore run on authored or library motion, not live capture.
- **Rendered review is proven only at probe size:** one 256×256 EEVEE render (26,831 B) succeeded; production-size
  turntables and their cost on a 4 GB GPU are unmeasured.
- **Import is proven only in Godot.** Unity (no licence) and UE5 (gate) cannot be validated here; Flax has no headless
  path. ADR-006 records them as blocked, not passed.
- **The loop does not exist yet:** no orchestrator, no console, no approval store, no capability implementations.

## Consequences

- The executable parts stay deterministic and auditable; taste stays with a person who signs a record.
- Costs: candidate generation multiplies files and review time; gates need maintenance; a hero character is weeks of
  human art even with the loop working. The 4 GB GPU bounds sculpt density and render quality.
- A failed gate names its expected/observed pair, so the next tweak is informed rather than a guess.
- Approval records create a defensible provenance trail for asset-store, AI and licence questions (ADR-002/ADR-004).

## Alternatives rejected

| Alternative | Why rejected |
| --- | --- |
| Fully autonomous character generation | acceptance is human; an agent approving its own taste hides the decision (pack §11.6) |
| GUI automation of Blender or the engine editors | brittle and unverifiable; `bpy` and CLIs are deterministic and logged |
| AI mesh/texture generation as the production source now | hardware and licence gates (ADR-004); provenance would be prototype-only |
| Buy mocap/face capture now | no hardware budget decision (PG-D11) and no character brief yet |
| One-shot pipeline with no candidate sets | hides the choice; approval becomes a rubber stamp |
| Treat a green gate as approval | gates check mechanics, not appeal |
| Build the review console first | a UI over an unbuilt loop automates nothing (ADR-003, PG-D15) |
| Use Rigify's 706-bone rig as-is for engines | exceeds a game bone/influence budget; needs a deform-only variant |

## Open questions

- **O1 Art direction and roster.** Style, character list, poly/texel/LOD budgets — operator decisions; PG-D4 covers
  interfaces, not art, so no standard exists.
- **O2 Engine and humanoid mapping.** Unity Humanoid avatar, UE mannequin skeleton, Godot `Skeleton3D`: bone naming
  and retarget policy follow the engine choice (Phase 1: Godot 4.7.2, ADR-009).
- **O3 Rig choice.** Rigify basic-human variant vs a custom game rig; bone budget; deform-only export default.
- **O4 Human capacity.** Who sculpts, retopos and approves, and is a tablet available? Not verified.
- **O5 AI character policy.** May generated concepts/meshes enter, and under which licence (ADR-004)?
- **O6 FPS and loop policy.** 30 fps is proposed (Godot's import default); clips, root motion and loop tolerance need
  one written convention.
- **O7 Approval authority.** Operator only, or a delegated artist? Where the approval record lives (records/).
- **O8 Mocap/tablet budget.** PG-D11; revisit only with a concrete need.
- **O9 Candidate retention.** How long losers are kept in `artifacts/` before pruning.
- **O10 Perf budgets.** No budget exists until a playable slice (PG-D18); a perf "pass" on the wrong scene is worse
  than none.

## Evidence

| Claim | Observation |
| --- | --- |
| Blender headless works | `blender -b --factory-startup` ran `bpy` export/import/render scripts on 2026-10-25; GLB 3,224 B and FBX 27,052 B re-imported |
| Rigify headless | `bpy.ops.preferences.addon_enable(module="rigify")` → enabled; human metarig 159 bones; `pose.rigify_generate()` → 706-bone rig |
| Add-on enable quirk | `addon_utils.enable("rigify")` returned False; the `bpy.ops.preferences` operator worked |
| Headless render | EEVEE 256×256 PNG written (26,831 B); Blender 5.2 engine enum is `BLENDER_EEVEE` |
| Godot import | `docs/IMPORT-MATRIX.md`: headless import + scripted scene assertions pass for the golden kit; 3 animations on the rigged asset |
| Unity / UE5 / Flax | `docs/ENGINE-SMOKE.md`: Unity batchmode exit 198 (no licence), UE5 gate fails (4 GB < 8 GB, 51.5 GB < 60 GB), Flax no headless path — no import claimed |
| Capability state | manifests exist but are `planned` (`art.character.*`, `art.animation.retarget`, `art.lookdev.turntable`, `perf.*`); `art.import.matrix` is `partial` |
| No automation built | no `record`/`approval` store, no orchestrator, no candidate script in the tree; this ADR is the decision, not the implementation |
| No mocap/tablet | not in [TOOL-INVENTORY.md](../TOOL-INVENTORY.md); not verified — O4/O8 |
