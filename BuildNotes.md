# BuildNotes - the changelog

Current version: 2026.10.25.012

BuildNotes is ProjectGypsy's dated, versioned changelog (`<CHANGELOG>` in the pack). Newest entry first; versions
are `YYYY.M.D.NNN` with a zero-padded sequence, and the next one is computed by
[scripts/next-version.py](scripts/next-version.py) rather than typed. [Retrace.md](Retrace.md) is the prompt log these
entries answer. Records are guarded by [scripts/records_check.py](scripts/records_check.py) and run by
[scripts/check_all.py](scripts/check_all.py).

## How versions 001-008 were assigned

No changelog existed before this bootstrap, so the bootstrap assigned versions 2026.10.25.001-008 to the commits
already in `git log`, oldest first; 2026.10.25.009 is the Phase-1 build and 2026.10.25.010 records its
verification/audit fixes. From the next version on, the number is computed by the script.

Verification recorded for the whole tree on 2026-10-25 at commit `534d801` - not per historical commit:
`python -m unittest discover -s workstream/tests` -> 13 tests OK; `python workstream/gypsy.py check` -> PASS;
`python scripts/check_all.py` -> PASS. Entries below cite the evidence that existed when the commit was made
rather than claiming a re-run that did not happen.

This changelog has **no generated documentation copies yet**. There is no contract artefact or other derived record
to generate (PG-D7 does not apply); the game export and captures are generated artefacts under gitignored `build/` and
`artifacts/`. [scripts/records_check.py](scripts/records_check.py) checks the source, its `Current version:` header and
[Retrace.md](Retrace.md); it will compare generated copies when they exist.

## 2026.10.25.012

**Phase-2 audit fixes: portable quality slice, task --force, status corrections.**

- Date: 2026-10-25
- Commit: this change.
- Change: the orchestrator's check_all handler now runs scripts/check_all.py (pack checks) instead of gypsy.check_all, so
  the quality slice is portable to a clean runner; run_task accepts force and the CLI passes --all --force through;
  stale Phase-0/15-test/orchestrator-not-built status text and the Phase-2 evidence Python version were corrected;
  slices/README documents the real dependencies.
- Verification: 54 tests OK; slices run quality in a simulated clean environment (no Godot/GameTools) PASS 3/3;
  slices run --all --force PASS 6/6 with resumed=false and all 3 phase1 steps attempted; scripts/check_all.py 6/6 PASS,
  37 capabilities.

## 2026.10.25.011

**Phase 2: manifest-driven slice orchestrator, durable state, artifact ledger and multi-slice task.**

- Date: 2026-10-25/26
- Commit: this change.
- Change: workstream/slices.py (gypsy.slice/v1 schema/loader/validator/ordering), workstream/orchestrator.py
  (handlers, run_slice, run_task, atomic state, artifact SHA-256 ledger, resume), slices/phase1.json and
  slices/quality.json, slices/README.md; CLI slices list|plan|run|status; 39 orchestrator tests; ADR-010 and
  PHASE-2-EVIDENCE; capabilities workstream.slice_orchestrator and workstream.artifact_ledger.
- Verification: slices run --all -> 6/6 steps, 3 artifacts, 20.363 s, one task report; phase1 13.133 s, quality
  7.225 s; second run produced identical SHA-256 for the exe, mp4 and frame; resume phase1 PASS; 54 workstream tests;
  scripts/check_all.py 6/6 PASS; gypsy check PASS; capabilities 37.

## 2026.10.25.010

**Phase-1 audit fixes: CI-safe tests, verified game gate, status/records corrections.**

- Date: 2026-10-25
- Commit: this change.
- Change: environment-dependent workstream tests now skip on a clean CI runner while keeping local assertions; the CI
  check list was proven in a simulated clean environment; `game verify` now requires capture to pass; subprocess
  output is decoded as UTF-8; stale Phase-0/Phase-1 status text, engine-open references, capture timing and the
  records closure note were corrected; BuildNotes/Retrace updated.
- Verification: `scripts/check_all.py` 6/6 PASS (15 tests local; 7 skipped and PASS in the simulated CI environment);
  `python workstream/gypsy.py game verify` demo/build/capture PASS; `game demo` marker `GYPSY_DEMO_OK collected=3
  frames=143`; capture 72 frames at 1280x720.

## 2026.10.25.009

**Phase-1 autonomous build - playable Godot 4.7.2 PC slice, workstream game adapter, records/checks bootstrap.**

- Date: 2026-10-25
- Commit: `d3c4f7f` (Phase-1 slice/records/adapter; this entry records it).
- Change: `game/` Godot 4.7.2 vertical slice (movement, three collectibles, camera, deterministic demo, Windows
  export preset); `workstream/game.py` plus `gypsy game demo|build|capture|verify`; ADR-009 and
  `docs/PHASE-1-EVIDENCE.md`; the records/check system (`Retrace.md`, this file,
  `scripts/next-version.py`, `scripts/records_check.py`, `scripts/check_all.py`,
  `scripts/install-hooks.py`, `.githooks/pre-commit`, `.github/workflows/checks.yml`); `test_game.py`
  and the `game.demo`/`game.vertical_slice` capabilities. Closes PG-D1, PG-D2, PG-D3 (engine choice) and PG-D5
  (docs index + links guard).
- Verification (run at this tree): `game demo` -> `GYPSY_DEMO_OK collected=3 frames=143`, exit 0, 2.6 s;
  `game build` -> `build/ProjectGypsy.exe`, 109,127,680 bytes, 2.6 s; exported binary headless -> same marker,
  exit 0; `game capture` -> 72 frames at 1280x720, 30 fps, MP4 2.4 s + frame; `game verify` -> demo/build/capture
  PASS; `scripts/check_all.py` -> 6/6 PASS, 14 workstream tests, 35 capability manifests; `gypsy check` PASS.

## 2026.10.25.008

**MCP bridge, Blender/Godot MCP, ComfyUI SD1.5 and Poly Haven integration.**

- Date: 2026-10-25
- Commit: `534d801`
- Change: `tools/mcp/` (MCP bridge, `servers.json`, `mcp_call.py`, PowerShell wrapper), `tools/comfyui/`
  (start/stop/generate), `tools/polyhaven/polyhaven.py` (CC0 public API, no key), `docs/ADR-008-mcp-and-free-local-tools.md`,
  eight capability manifests, and updates to `TOOLCHAIN.md`, `TOOL-INVENTORY.md` and `docs/README.md`.
- Evidence: `TOOLCHAIN.md` and `docs/ADR-008-mcp-and-free-local-tools.md` record the measured results
  (ComfyUI 512x512, 20 steps, 28.2 s; Godot MCP `get_godot_version` returned 4.7.2.stable; Poly Haven writes CC0
  plus SHA-256 provenance). Re-checked by this bootstrap only through the capability JSON parse and
  `python workstream/gypsy.py check` (PASS at this HEAD).

## 2026.10.25.007

**Fix import-matrix metadata, Godot status and ADR-006 golden-kit wording.**

- Date: 2026-10-25
- Commit: `b5ff4a1`
- Change: added the per-run export metadata to `docs/IMPORT-MATRIX.md` and `scripts/import_matrix.py`,
  corrected the Godot capture maturity in `docs/ENGINE-SMOKE.md` (`partial` -> `planned`) and the golden-kit
  wording in `docs/ADR-006-blender-import-matrix.md`; updated `DEFERRED.md` and `README.md`.
- Evidence: the corrected statements are the ones carried in `docs/IMPORT-MATRIX.md` and
  `docs/ENGINE-SMOKE.md`; the matrix's own evidence is the Godot headless import result recorded there.

## 2026.10.25.006

**Character/animation automation, Blender import matrix and language boundaries (ADR-005 to ADR-007).**

- Date: 2026-10-25
- Commit: `eb8be37`
- Change: `docs/ADR-005-character-animation-automation.md`, `docs/ADR-006-blender-import-matrix.md`,
  `docs/ADR-007-language-boundaries.md`, `docs/IMPORT-MATRIX.md`, `scripts/import_matrix.py`,
  `assets/test/golden/generate_golden.py` (golden static, rigged, morph and LOD/collision assets) and nine
  capability manifests.
- Evidence: `docs/IMPORT-MATRIX.md` records the golden kit's Blender round-trip pass, glTF validator result (no
  errors; one expected `NODE_SKINNED_MESH_NON_ROOT` warning) and the Godot 4.7.2 headless import pass (three
  animations on the rigged asset, four LOD meshes). Unity (no licence), UE5 (hardware gate) and Flax (no headless
  path) are recorded as blocked or untested, not passed.

## 2026.10.25.005

**Phase 0 audit fixes: planned maturity, real side effects and MusicGen JSON validity.**

- Date: 2026-10-25
- Commit: `5601d96`
- Change: corrected capability maturity to `planned` where nothing is demonstrated, removed claimed side effects
  that did not happen, fixed `tools/musicgen/generate.py` JSON validity, and brought `DEFERRED.md`,
  `ProjectPack-NOTES.md`, `ProjectPack-ADDENDUM-Interface.md`, `TOOLCHAIN.md`, `TOOL-INVENTORY.md`,
  `docs/ADR-003-workstream-architecture.md`, `docs/ENGINE-SMOKE.md`, `workstream/` and the art capability
  manifests in line with what was verified.
- Evidence: this bootstrap re-ran `python -m unittest discover -s workstream/tests` (13 tests OK) and
  `python workstream/gypsy.py check` (PASS) at the current HEAD; the suite exists because of 2026.10.25.004 and
  these fixes.

## 2026.10.25.004

**Phase 0 workstream: engine registry, manifests, ADRs and the MusicGen prototype.**

- Date: 2026-10-25
- Commit: `f0a8529`
- Change: `workstream/gypsy.py` (engines probe, smoke, tools probe, capabilities, project init/show, check),
  `workstream/tests/test_gypsy.py` (13 tests), capability manifests, `workstream/README.md`,
  `docs/ADR-001-engines.md` to `docs/ADR-004-generative-media.md`, `docs/ENGINE-SMOKE.md`,
  `docs/README.md`, `TOOLCHAIN.md`, `tools/tool-env.ps1`, `tools/musicgen/` and `.gitignore`.
- Evidence: `docs/ENGINE-SMOKE.md` is the Phase-0 evidence (Godot 4.7.2 headless smoke passes; Unity, UE5 and
  Flax recorded with their gates). Re-run at the current HEAD by this bootstrap: 13 tests OK, `gypsy check` PASS.

## 2026.10.25.003

**Game-dev tooling inventory, open-source replacements and hardware limits.**

- Date: 2026-10-25
- Commit: `a4c8bc9`
- Change: added `TOOL-INVENTORY.md` (installed engines, art/audio/build tools, Python libraries, versions, paths
  and provenance) and recorded the open-source replacements and the machine's hardware limits; updated
  `DEFERRED.md` (for example PG-D10, PG-D11, PG-D12) and `README.md`.
- Evidence: the versions and paths in `TOOL-INVENTORY.md`; they are claims from the install/verification that made
  this commit, and are not re-probed by this records bootstrap.

## 2026.10.25.002

**Apply the ProjectPack from C7NTRY and park the interface design/redesign material in an addendum.**

- Date: 2026-10-25
- Commit: `6628fbe`
- Change: added `ProjectPack.md` (revision PG-1, base C7NTRY pack 2.5), `ProjectPack-NOTES.md`,
  `ProjectPack-ADDENDUM-Interface.md`, `AGENTS.md` and `DEFERRED.md`; updated `README.md`.
- Evidence: the verification table at the end of `ProjectPack-NOTES.md` (the 16 parked blocks were re-extracted
  and found byte-for-byte inside the addendum; the working pack carries no parked rule; encoding and links checked).

## 2026.10.25.001

**Initial commit.**

- Date: 2026-10-25
- Commit: `5ec1489`
- Change: created the repository and tracked `README.md`.
- Evidence: the commit itself; there was no check suite at this point.

---

Next version: run `python scripts/next-version.py`.