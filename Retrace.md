# Retrace - the prompt log

Retrace is ProjectGypsy's prompt log (`<PROMPT_LOG>` in the pack). Every request is recorded here in the order
it was made: its date, a one-line request, its status, and the commit or evidence it produced. The newest entry is
at the bottom and the prompt numbers are contiguous from 1.

Read it with [BuildNotes.md](BuildNotes.md), the dated versioned changelog. `python scripts/records_check.py` (run
by `python scripts/check_all.py`) fails if an entry loses its number or status, if BuildNotes is not newest-first,
if BuildNotes' `Current version:` header disagrees with its newest heading, or if a version repeats.

## How this log was started, and the one limitation in entries 1-13

This log starts on 2026-10-25 with the first Phase-1 build. Entries 1-13 are reconstructed from the session's
prompt-history summary because the earlier conversation was compacted: each request line is the summary's one-line
request, **not a verbatim quotation**, and per-prompt durations were not preserved. From entry 14 on, the request is
appended as written and the duration is recorded. Stating the gap is required by §2.1 (nothing is complete while
records disagree with the work) and §11.4; it is reported to the Lead in the bootstrap report.

Each entry has:

- **Request** - one line, quoted from the prompt or from its recorded summary.
- **Status** - Completed, In progress or Blocked. A request that changed nothing says so explicitly.
- **Version** - the BuildNotes version the change produced, or why no version belongs to it.
- **Commit/evidence** - the commit hash, or the file and observation that are the evidence.

## 1 - 2026-10-25

- Request: Create the private repository ProjectGypsy.
- Status: Completed
- Version: 2026.10.25.001
- Commit/evidence: `5ec1489` - Initial commit; `README.md` is the only tracked file.

## 2 - 2026-10-25

- Request: Copy the C7NTRY ProjectPack into this repository, apply it, and park the interface design/redesign
  material in an addendum.
- Status: Completed
- Version: 2026.10.25.002
- Commit/evidence: `6628fbe` - `ProjectPack.md`, `ProjectPack-NOTES.md`,
  `ProjectPack-ADDENDUM-Interface.md`, `AGENTS.md` and `DEFERRED.md`. The application of the pack is verified in
  the table at the end of `ProjectPack-NOTES.md`.

## 3 - 2026-10-25

- Request: Discuss the workstream application and agent architecture.
- Status: Completed - a discussion; it changed no tracked file of its own.
- Version: none of its own; the architecture was written up later in 2026.10.25.004.
- Commit/evidence: `docs/ADR-003-workstream-architecture.md`, added by `f0a8529` (2026.10.25.004).

## 4 - 2026-10-25

- Request: The engines are installed; choose one per project.
- Status: Completed - the decision mechanism was built, and the actual choice was left to the operator as recorded
  in `DEFERRED.md` PG-D3.
- Version: 2026.10.25.004 for the mechanism (engine registry, `docs/ADR-001-engines.md`); the choice itself has no
  version because it is still open.
- Commit/evidence: `docs/ADR-001-engines.md` and `workstream/gypsy.py` in `f0a8529`; PG-D3 in `DEFERRED.md`.

## 5 - 2026-10-25

- Request: Inventory the installed applications.
- Status: Completed
- Version: 2026.10.25.003
- Commit/evidence: `a4c8bc9` - `TOOL-INVENTORY.md` records versions, paths and provenance for the installed
  engines, art/audio/build tools and Python libraries.

## 6 - 2026-10-25

- Request: Install ImageMagick and the game-development tools.
- Status: Completed - a machine-level install; the repository records what was verified, not the installer run.
- Version: 2026.10.25.003
- Commit/evidence: `TOOLCHAIN.md` (commands and versions) and `TOOL-INVENTORY.md` (provenance), committed in
  `a4c8bc9`; `TOOLCHAIN.md` was added by `f0a8529` (2026.10.25.004).

## 7 - 2026-10-25

- Request: Compare open-source alternatives and consider YuE2.
- Status: Completed - an investigation; it produced records, no code.
- Version: 2026.10.25.003 (open-source replacements in `TOOL-INVENTORY.md`) and 2026.10.25.004
  (`docs/ADR-004-generative-media.md`).
- Commit/evidence: `TOOL-INVENTORY.md` in `a4c8bc9`; YuE2's Linux + 24 GB BF16 GPU requirement is registered as
  `DEFERRED.md` PG-D10 and is not claimed as installed.

## 8 - 2026-10-25

- Request: Install MusicGen.
- Status: Completed - installed and smoke-tested as a prototype path only (CC-BY-NC weights).
- Version: 2026.10.25.004 (prototype path and `tools/musicgen/`), corrected by 2026.10.25.005.
- Commit/evidence: `f0a8529` added `tools/musicgen/generate.py` and `tools/musicgen/musicgen.ps1`; `5601d96`
  fixed the MusicGen JSON validity; the non-commercial licence is recorded in `docs/ADR-004-generative-media.md`
  and `TOOLCHAIN.md`.

## 9 - 2026-10-25

- Request: Design the ADRs and the workstream.
- Status: Completed
- Version: 2026.10.25.004
- Commit/evidence: `f0a8529` - `docs/ADR-001-engines.md` through `docs/ADR-004-generative-media.md`,
  `docs/ENGINE-SMOKE.md`, `workstream/` (registry, manifests, capability schemas, 13 unit tests) and
  `tools/tool-env.ps1`.

## 10 - 2026-10-25

- Request: Write ADRs 001-007 and the golden import matrix.
- Status: Completed
- Version: 2026.10.25.004 (ADR-001 to ADR-004), 2026.10.25.006 (ADR-005 to ADR-007, golden kit, import matrix) and
  2026.10.25.007 (matrix metadata and Godot-status corrections).
- Commit/evidence: `f0a8529`, `eb8be37` and `b5ff4a1`; the matrix evidence is `docs/IMPORT-MATRIX.md`
  (Blender round-trip pass, glTF validation, Godot 4.7.2 headless import pass; Unity, UE5 and Flax recorded as
  blocked or untested, not passed).

## 11 - 2026-10-25

- Request: Explain the AAA character and art requirements.
- Status: Completed - an explanation; it changed no tracked file of its own.
- Version: none of its own; the requirements were written up in 2026.10.25.006.
- Commit/evidence: `docs/ADR-005-character-animation-automation.md`, added by `eb8be37` (2026.10.25.006); the
  honest limits and the deferred pipeline are in `DEFERRED.md` PG-D17.

## 12 - 2026-10-25

- Request: Ask about MCP and the Blender tools.
- Status: Completed - an investigation; it changed no tracked file of its own.
- Version: none of its own; the answer became the next install slice.
- Commit/evidence: the decision and its limits are `docs/ADR-008-mcp-and-free-local-tools.md`, added by
  `534d801` (2026.10.25.008); the integration is recorded in prompt 13.

## 13 - 2026-10-25

- Request: Install the MCP bridge, the Blender and Godot MCP servers, ComfyUI with SD1.5, and the Poly Haven
  downloader.
- Status: Completed - installed and smoke-tested on this machine.
- Version: 2026.10.25.008
- Commit/evidence: `534d801` - `tools/mcp/` (bridge and `servers.json`), `tools/comfyui/`,
  `tools/polyhaven/`, `docs/ADR-008-mcp-and-free-local-tools.md` and eight capability manifests. Measured
  results are recorded in `TOOLCHAIN.md` and `docs/ADR-008-mcp-and-free-local-tools.md`; nothing here is
  re-verified by this bootstrap except the capability JSON parse in `scripts/check_all.py`.

## 14 - 2026-10-25

- Request: Run the full autonomous Phase-1 build (slices, subagents, no stopping until complete).
- Status: Completed - Phase-1 slice, export, capture, workstream game adapter and records/checks are verified.
- Version: 2026.10.25.009
- Commit/evidence: `game/` and `docs/PHASE-1-EVIDENCE.md`; demo `GYPSY_DEMO_OK collected=3 frames=143`;
  `build/ProjectGypsy.exe` 109,127,680 bytes and its headless demo pass; capture 72 frames at 1280x720;
  `game verify` and `scripts/check_all.py` (6/6 PASS, 15 tests, 35 capabilities) pass.

---

## 15 - 2026-10-25

- Request: Fix the Phase-1 audit findings and re-verify the build, records and CI gate.
- Status: Completed.
- Version: 2026.10.25.010
- Commit/evidence: CI-safe test skips (simulated clean runner PASS), `game verify` now requires capture, UTF-8
  subprocess decoding, status/engine/records corrections; `scripts/check_all.py` 6/6 PASS, 15 tests local.

---

## 16 - 2026-10-25

- Request: Keep going; build the next unblocked phase (Phase-2 workstream orchestrator).
- Status: Completed.
- Version: 2026.10.25.011
- Commit/evidence: slices/phase1.json + slices/quality.json, workstream/slices.py, workstream/orchestrator.py,
  slices CLI and 39 orchestrator tests; slices run --all 6/6 steps/3 artifacts in 20.363 s; second run identical
  artifact hashes; 54 tests; scripts/check_all.py 6/6; ADR-010 and docs/PHASE-2-EVIDENCE.md.

---

## 17 - 2026-10-25

- Request: Fix the Phase-2 audit findings and re-verify the orchestrator.
- Status: Completed.
- Version: 2026.10.25.012
- Commit/evidence: portable quality check (clean-runner simulation PASS 3/3), task --force (resumed=false, all steps
  attempted), stale status corrections; 54 tests; scripts/check_all.py 6/6; 37 capabilities.

---

## 18 - 2026-10-26

- Request: Do the rest of the phases in succession; keep going. Phase 3 first.
- Status: Completed (Phase 3).
- Version: 2026.10.25.013
- Commit/evidence: toolpack runner/validators (44 tests), art.import.golden + audio.musicgen toolpacks,
  slices/toolpacks.json + orchestrator handler, CLI; art import PASS and MusicGen WAV PASS with validators and
  SHA-256 provenance; slices run toolpacks 2/2 in 45.233 s; 98 tests; check_all 6/6; 38 capabilities.

---

## 19 - 2026-10-26

- Request: Continue through the remaining phases; Phase 4 next.
- Status: Completed (Phase 4).
- Version: 2026.10.25.014
- Commit/evidence: read-only terminal console (board/preview/diff), 40 tests, CLI wiring, ADR-012/PHASE-4-EVIDENCE;
  board 8/8 steps, preview frame 1280x720 with live SHA-256, diff read-only, no writes; 138 tests; check_all 6/6;
  39 capabilities.

---

## 20 - 2026-10-26

- Request: Do the rest of the phases in succession; Phase 5/6 next.
- Status: Phase 5 complete for mobile/live/performance; second engine BLOCKED; Phase 6 UE5 BLOCKED.
- Version: 2026.10.25.015
- Commit/evidence: Android debug APK 28,305,095 bytes signed/package-verified; live watcher 34 tests + real --once;
  game bench median 2.605 s/p95 2.605 s/GPU 0.56 ms; Unity exit 198, UE5 4 GB < 8 GB, Flax no headless; 172 tests;
  42 capabilities.

---

## 21 - 2026-10-26

- Request: Audit Phases 3-5 and fix the findings.
- Status: Completed.
- Version: 2026.10.25.016
- Commit/evidence: seeded MusicGen (identical SHA-256 across two runs), --no-doc art import (tracked docs unchanged),
  status/count/APK reproducibility corrections; 172 tests; check_all 6/6; 42 capabilities.

---

## 22 - 2026-10-26

- Request: Decide whether a GUI is needed; mock several versions or give CLI instructions.
- Status: Completed — decision and four mockups delivered; CLI usage documented; nothing implemented.
- Version: 2026.10.25.017
- Commit/evidence: design/control-panel/ (Studio Board, Mission Control, Command Hybrid, Director's Table; HTML + PNG)
  and README with recommendation and current CLI commands; no game/workstream code changed.

---

## 23 - 2026-10-26

- Request: implement all four control-panel mockups (Studio Board default, rest as views, dark) and finish remaining phases.
- Status: Completed — local dashboard implemented; remaining phases are hardware/licence/art-direction gated.
- Version: 2026.10.25.018
- Commit/evidence: workstream/dashboard.py, design/dashboard app + four screenshots, CLI dashboard, ADR-014,
  docs/DASHBOARD.md, 9 tests; four views render; token/whitelist action API; 181 tests; 43 capabilities.

---

## 24 - 2026-10-26

- Request: After the dashboard, finish remaining phases; attempt device validation.
- Status: Device launch remains blocked — emulator install failed on a corrupt ZIP; dashboard complete.
- Version: 2026.10.25.019
- Commit/evidence: docs/PHASE-5-EVIDENCE emulator note; no code claim changed; 181 tests/43 capabilities remain.

---

## 25 - 2026-10-26

- Request: Add a ready-to-import SD1.5 workflow and verify it in ComfyUI.
- Status: Completed.
- Version: 2026.10.25.020
- Commit/evidence: tools/comfyui/workflows/projectgypsy-sd15-basic.json, verify_workflow.py and README; UI load via
  Chromium/CDP showed 7 nodes and no missing models; API-equivalent run produced a verified PNG; 181 tests.

---

## 26 - 2026-10-26

- Request: Check Unity now that a licence is present.
- Status: Completed — licence and batchmode smoke PASS; Unity slice adapter not built.
- Version: 2026.10.25.021
- Commit/evidence: engines smoke unity exit 0, GYPSY_UNITY_SMOKE_OK in 50.891 s; licence.proven true from state;
  import matrix regenerated; 181 tests/44 capabilities. No second-engine claim.

---

## 27 - 2026-10-26

- Request: Create a Unity project named LeftBehind and prove the same slice on Unity.
- Status: Completed.
- Version: 2026.10.25.022
- Commit/evidence: LeftBehind Unity 6 build, headless demo GYPSY_DEMO_OK collected=3 frames=74, 1280x720 capture;
  toolpack/slice pass; docs/UNITY-SLICE.md; 181 tests/46 capabilities; second-engine gate met.

---

## 28 - 2026-10-26

- Request: Mock a more intuitive, user-friendly and robust dashboard.
- Status: Completed — two redesign mockups plus rationale; not implemented.
- Version: 2026.10.25.023
- Commit/evidence: design/dashboard-v2/overview.png, run-detail.png, HTML/CSS source and README; 1600x1000 Chromium
  renders; 181 tests/46 capabilities unchanged.

---

## 29 - 2026-10-26

- Request: Build all of the redesigned dashboard (overview and run detail).
- Status: Completed — default operations console, run history/detail API, classic views preserved.
- Version: 2026.10.25.024
- Commit/evidence: / overview and /?view=run live in Chromium; /classic preserved; 10 dashboard tests, 182 total;
  token-protected leftbehind_demo action passed; check_all 6/6.

---

## 30 - 2026-10-26

- Request: Do the same for the rest of the screens.
- Status: Completed — Mission, Commands, Review, Slices and Artifacts added to the operations console.
- Version: 2026.10.25.025
- Commit/evidence: live-mission/commands/review/slices/artifacts PNGs; deep-link views; 182 tests; check_all 6/6.

---

## 31 - 2026-10-26

- Request: Rename to Gypsy Studio/Gypsy and add instructions for coding agents using Gypsy on new/existing projects.
- Status: Completed.
- Version: 2026.10.25.026
- Commit/evidence: docs/GYPSY-AGENT-GUIDE.md and templates/AGENTS.gypsy.md; app/CLI/docs branded Gypsy Studio; live
  screenshots refreshed; 182 tests; check_all 6/6.

---

## 32 - 2026-10-26

- Request: Make “Open Gypsy” trigger Gypsy being called up or imported.
- Status: Completed.
- Version: 2026.10.25.027
- Commit/evidence: trigger documented in AGENTS.md, docs/GYPSY-AGENT-GUIDE.md, templates/AGENTS.gypsy.md and README;
  exact dashboard/verification steps included; 182 tests; check_all 6/6.

---

## 33 - 2026-10-26

- Request: Also make “Load Gypsy” and “Use Gypsy” trigger Gypsy.
- Status: Completed.
- Version: 2026.10.25.028
- Commit/evidence: trigger table in AGENTS, guide, template and README; Open/Load/Use semantics documented; 182 tests;
  check_all 6/6.

---

## 34 - 2026-10-26

- Request: Make any invocation command followed by “Gypsy” trigger it.
- Status: Completed.
- Version: 2026.10.25.029
- Commit/evidence: generalized trigger in AGENTS/guide/template/README; examples and negations documented; 182 tests;
  check_all 6/6.

---

## 35 - 2026-10-26

- Request: Add ActionForge to Gypsy for all future projects, under the standing rule that "add XXX to the toolkit" means
  extending Gypsy Studio with a reusable toolkit integration, not a project-local hack.
- Status: Completed — toolkit registry, ActionForge adapter, CLI, capability manifests, docs and 33 toolkit tests.
- Version: 2026.10.26.001
- Commit/evidence: workstream/toolkit.py and workstream/toolkits/actionforge.py; `gypsy toolkit
  list|show|probe|capabilities` and `toolkit actionforge catalog|fetch`; toolkit.actionforge (partial) and
  workstream.toolkit capability manifests; ADR-015; 215 tests OK (1 skip); check_all 6/6; `gypsy check` PASS with 48
  capabilities; probe HTTP 200; a temp-project real fetch wrote rig 618,624 bytes and idle_loop 87,216 bytes.

---

## 36 - 2026-10-26

- Request: Build both missing pieces — hero art/character pipeline and self-extension — and complete the project.
- Status: Completed; device launch and UE5 remain gated.
- Version: 2026.10.26.002
- Commit/evidence: Wayfarer GLB/FBX/atlas, 20-bone rig, idle/run/reach, Godot integration with marker preserved,
  hero validator/toolpack/slice; safe extension registry/CLI/lockfile/lifecycle; ADR-016/017; 272 tests, 50 capabilities,
  check_all 6/6.

---

Next prompt number: 37. The version list is [BuildNotes.md](BuildNotes.md); the checks are
[scripts/check_all.py](scripts/check_all.py).