# BuildNotes - the changelog

Current version: 2026.10.30.007

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

## 2026.10.30.007

**Build the roadmap P0: execution cache, opt-in parallelism, quality gates, catalog and Insights UI; close device/Unity import evidence.**

- Date: 2026-10-30
- Commit: this change.
- Change: content-addressed local action cache and bounded parallel scheduler (workstream/cache.py; slices/toolpacks
  --parallel/--no-cache/--force; cache stats/list/clear); visual/performance quality gates and opt-in visual slice;
  project catalog + gypsy catalog CLI, API and Unity/Godot golden-path templates; Insights/live-log/actionable-error
  dashboard; emulator launch evidence; Unity hero FBX import proof; extension temp-cleanup hardening; docs/ADR-019 and
  records.
- Verification: 412 tests OK (3 skipped), check_all 6/6; real cache hit 0.0 s vs 0.188 s; quality gate
  changed 0/921600 with median 2.811 s, p95 2.811 s, GPU 0.87 ms, frames 143; emulator boot/install/launch/render +
  screenshot/logcat; Unity import UNITY_HERO_IMPORT_OK bones=23.

## 2026.10.26.006

**Add a research-backed improvement roadmap for Gypsy.**

- Date: 2026-10-30
- Commit: this change.
- Change: docs/IMPROVEMENT-ROADMAP.md — primary-source research (GameCI, Bazel remote cache, Backstage, Unreal Horde
  and Gauntlet, OpenUSD, MaterialX/OCIO, Insights, GdUnit4/GUT, OpenTelemetry, DORA, Git LFS, sccache) translated into
  prioritized P0/P1/P2 workstreams for action caching, parallel scheduling, engine adapters, QA, asset governance,
  developer experience, agent safety, observability and supply chain.
- Verification: document written; links checked by check_all; 282 tests; no code behavior changed.

## 2026.10.26.005

**Stage A: Unity is the default for new projects; UltraBlade 2 port brief added.**

- Date: 2026-10-26
- Commit: this change.
- Change: gypsy project init now defaults to Unity 6000.6.7f1 / PC (overridable); ADR-018 records Stage A while the
  current Godot game remains legacy until Stage B; docs/UNITY-PORT-INSTRUCTIONS.md and
  templates/UNITY-MIGRATION-PROMPT.md provide the copy-paste migration brief; agent guide, template, README, docs index,
  workstream README and TOOLCHAIN updated; default-init test added.
- Verification: project init with only --path writes unity 6000.6.7f1 (unity-6) / pc; ProjectTests default test passes;
  full suite 282 tests OK (2 skipped); check_all 6/6.

## 2026.10.26.004

**Add runtime hero LOD, driven facial expression and spring cape; retry device launch.**

- Date: 2026-10-26
- Commit: this change.
- Change: hero manager now owns LOD0/LOD1/LOD2 with distance-driven switching (9 m/14 m), driven Smile morph on
  collection, and spring-driven cape_a/b/c secondary motion; player scene instanced all three LODs while preserving
  collision; integration check asserts forced and distance LOD switching, face value and cape bones; hero toolpack adds
  a systems action and HERO_SYSTEMS_OK validator. Device launch retried with a windowed emulator; it exits after 11 s
  without ADB; docs/DEVICE-LAUNCH.md updated.
- Verification: HERO_SYSTEMS_OK lods=3 face=driven cape=driven; HERO_CHECK_OK; GYPSY_DEMO_OK frames=143; hero slice
  passed with generation, validation, systems and capture; game capture passed; 281 tests; check_all 6/6.

## 2026.10.26.003

**Hero production pass, extension process containment, and Android emulator attempt.**

- Date: 2026-10-26
- Commit: this change.
- Change: Wayfarer production pass — 23-bone rig (3 cape bones), 512² base/normal/roughmetal maps, Smile morph,
  LOD1 (615 tris) / LOD2 (306 tris), larger GLB/FBX, updated generator/validator/toolpack; self-extension opt-in
  Windows Job Object containment (kill-on-close, active-process/memory limits, process-tree timeout kill, honest
  fallback); Android SDK emulator 37.2.12 + API 35 system image + AVD Gypsy_API35b installed; device launch blocked at
  the host emulator's multi-instance error before ADB registration, documented in docs/DEVICE-LAUNCH.md.
- Verification: Blender production generation exit 0, WAYFARER_GEN_OK bytes=904964 bones=23 actions=3 lods=2 morph=Smile
  maps=3; validator HERO_VALIDATE_OK checks=94; Godot headless demo x2 exit 0 GYPSY_DEMO_OK frames=143;
  HERO_CHECK_OK; production hero slice passed; 9 containment tests; full suite 281 tests OK (2 skipped); 50
  capabilities; check_all pending final. Device launch is NOT claimed.

## 2026.10.26.002

**Complete the missing hero art/character pipeline and safe self-extension.**

- Date: 2026-10-26
- Commit: this change.
- Change: original Wayfarer hero (Blender 5.2.3 generator, 20-joint rig, idle/run/reach, 256² atlas, GLB/FBX, non-Blender
  validator, Godot integration preserving collision/autopilot/marker, preview/showroom captures, hero toolpack and
  slice); safe self-extension pipeline (extensions.py, gypsy extension CLI, isolated manifests/capability/lockfile,
  dry-run, register/review gate, disable/remove/reload, negative tests, example extension and capability); ADR-016,
  ADR-017, ART-DIRECTION and status/doc updates.
- Verification: Blender generation exit 0, WAYFARER_GEN_OK bytes=282668 bones=20 actions=3 tris=1126; validator exit 0
  HERO_VALIDATE_OK checks=60 (60/60); Godot headless demo x2 exit 0 with GYPSY_DEMO_OK collected=3 frames=143;
  integration check HERO_CHECK_OK; game verify/capture pass; hero slice passed; extension test 55/55 plus lifecycle and
  negative paths; full suite 272 tests OK (2 skipped); capabilities 50; toolpacks 5; slices 6; check_all 6/6.

## 2026.10.26.001

**Add the ActionForge toolkit and a reusable toolkit registry for future projects.**

- Date: 2026-10-26
- Commit: this change.
- Change: operator request: "Add ActionForge to Gypsy for all future projects. If I say add 'XXX' to the toolkit, that
  means Gypsy should be extended (or plugin created, etc.) to include that tool as part of the Studio for future use."
  AGENTS.md now carries the standing rule; workstream/toolkit.py validates plugins and provides
  `toolkit list|show|probe|capabilities`; workstream/toolkits/actionforge.py adds `toolkit actionforge catalog|fetch`;
  capability manifests toolkit.actionforge (partial) and workstream.toolkit; ADR-015 plus TOOLCHAIN, TOOL-INVENTORY,
  docs/README, README, workstream README and agent guide/template updated; tests in workstream/tests/test_toolkit.py.
- Verification: `python -m unittest discover -s workstream/tests -v` -> 215 tests, OK (1 skip); `python
  workstream/gypsy.py check` -> PASS (capabilities 48, tools 16); `python workstream/gypsy.py capabilities check` ->
  48 capability files, 0 errors; `python scripts/check_all.py` -> 6/6 PASS; `toolkit probe actionforge` -> reachable,
  HTTP 200 (HEAD, 2026-10-26T06:04:42-05:00); a real fetch smoke in a temp project wrote rig-human.glb (618,624 bytes,
  SHA-256 1e6c4f98...) and idle_loop.glb (87,216 bytes, SHA-256 fbc6fcdc...) with provenance + NOTICE, then the temp
  project was removed. Network is not used by the test suite; mocked fetch tests cover writes, idempotence, conflicts,
  path escape and invalid GLB.

## 2026.10.25.029

**Generalize the Gypsy invocation trigger to any invocation verb + Gypsy.**

- Date: 2026-10-26
- Commit: this change.
- Change: AGENTS, docs/GYPSY-AGENT-GUIDE.md, templates/AGENTS.gypsy.md and README now treat any imperative invocation
  verb followed by Gypsy (Open, Load, Use, Invoke, Launch, Start, Call, Run, Show, Import, Activate, Bring up, Pull up,
  Summon, etc.) as load/use Gypsy. Negations do not trigger. Open/launch/show bring up the dashboard; load/import read the
  guide/template; use/run/invoke/call route the task through the CLI starting with check.
- Verification: docs links resolve; 182 tests; check_all 6/6; dashboard state 200.

## 2026.10.25.028

**Add Load Gypsy and Use Gypsy trigger phrases.**

- Date: 2026-10-26
- Commit: this change.
- Change: AGENTS, docs/GYPSY-AGENT-GUIDE.md, templates/AGENTS.gypsy.md and README now treat Open Gypsy, Load Gypsy and
  Use Gypsy (case-insensitive) as instructions to load/verify Gypsy and use it. Open brings up/reports the dashboard;
  Load imports the guide/template; Use routes the current task through the Gypsy CLI, starting with gypsy check.
- Verification: docs links resolve; 182 tests; check_all 6/6; dashboard /api/state HTTP 200.

## 2026.10.25.027

**Add “Open Gypsy” as an explicit agent trigger.**

- Date: 2026-10-26
- Commit: this change.
- Change: root AGENTS, docs/GYPSY-AGENT-GUIDE.md, templates/AGENTS.gypsy.md and README now define the case-insensitive
  trigger “Open Gypsy” as: load Gypsy, verify the CLI, ensure the local dashboard is responding, report/open the URL and
  summarize slices/gates; outside the Gypsy checkout it also means import the guide/template and use Gypsy.
- Verification: guide commands checked against `gypsy dashboard --help`; docs links resolve; 182 tests; check_all 6/6.

## 2026.10.25.026

**Rename product surface to Gypsy Studio and add portable agent instructions.**

- Date: 2026-10-26
- Commit: this change.
- Change: Gypsy Studio/Gypsy naming in the app title/brand, classic title, CLI description/version, README, AGENTS and
  dashboard docs; docs/GYPSY-AGENT-GUIDE.md for coding agents on new and existing projects; templates/AGENTS.gypsy.md
  copy-paste harness block; KEEPING repository paths, Python package and manifest schema identifiers unchanged.
- Verification: live Chromium screenshots show Gypsy Studio; `gypsy version` prints Gypsy Studio; docs links resolve;
  tests 182; check_all 6/6.

## 2026.10.25.025

**Add the remaining operations-console screens.**

- Date: 2026-10-26
- Commit: this change.
- Change: Mission, Commands, Review, Slices and Artifacts views in the default console; deep links ?view=mission,
  commands, review, slices, artifacts; command whitelist run/copy actions; phase ladder and machine state; release
  readiness and evidence; artifact library; new live screenshots; docs and tests updated.
- Verification: live Chromium captures of all five screens; dashboard tests 10 OK; full suite 182 tests OK; check_all 6/6.
  No new capabilities; commands remain the fixed whitelist.

## 2026.10.25.024

**Implement the operations-console dashboard: overview + run detail.**

- Date: 2026-10-26
- Commit: this change.
- Change: new default app at / (design/dashboard-v2) with Workspace overview and Run detail views; run history/detail
  backend (/api/runs, /api/run?id=, runs in /api/state); fixed actions leftbehind, leftbehind_build/demo/capture;
  responsive dark layout; search, grouped gates, pipeline, runs, artifacts, checklist; run step timeline, logs,
  validator table, retries and copy controls; original four-view app served at /classic.
- Verification: dashboard tests 10 OK; full suite 182 tests OK (1 skip); API state has 5 slices/46 capabilities and
  deduped runs; GET /api/run returns steps/artifacts/validators; live Chromium screenshots overview + run detail;
  POST leftbehind_demo through the token-protected API passed. check_all 6/6.

## 2026.10.25.023

**Dashboard redesign mockups: operations console with run detail.**

- Date: 2026-10-26
- Commit: this change.
- Change: design/dashboard-v2/ with overview.html/png and run-detail.html/png, shared mockups.css and README rationale;
  next-action overview, pipeline strip, runs table, recent artifacts, grouped gates, and a run-detail view with step
  timeline, logs, validator evidence and retry/copy controls; root README link. Mockups only; current app unchanged.
- Verification: both 1600x1000 PNGs rendered in Chromium; check_all links/encoding; 181 tests/46 capabilities unchanged.

## 2026.10.25.022

**LeftBehind: Unity 6 second-engine slice builds, runs and captures.**

- Date: 2026-10-26
- Commit: this change.
- Change: unity/LeftBehind Unity 6000.6.7f1 project (procedural arena, CharacterController player, three crystals,
  camera, deterministic --demo autopilot); BuildLeftBehind.Build; build/run wrappers; toolpacks/leftbehind.unity.json;
  slices/leftbehind.json; project.gypsy.json; capabilities engine.unity.build (stable), engine.unity.demo and
  engine.unity.capture; docs/UNITY-SLICE.md and engine/gate/status updates.
- Verification: Unity batchmode build LEFTBEHIND_BUILD Succeeded (exe 667,136 B; data 95,921,964 B); headless player
  GYPSY_DEMO_OK collected=3 frames=74 exit 0; windowed capture 1280x720 PNG SHA-256 6da0cd85...; toolpack
  leftbehind.unity passed build/demo/capture; slices run leftbehind passed; 181 tests; 46 capabilities; second-engine
  gate now met (Godot + Unity). UE5/Flax remain blocked; device launch untested.

## 2026.10.25.021

**Unity licence verified: batchmode smoke passes; adapter not yet built.**

- Date: 2026-10-26
- Commit: this change.
- Change: engines smoke unity (temp project, C# editor smoke, licence evidence in state); detect_unity reads the smoke
  evidence for licence.proven; CLI accepts unity; capability engine.unity.batchmode; engine.unity.build moved from
  blocked to planned; ENGINE-SMOKE/TOOLCHAIN/TOOL-INVENTORY/DEFERRED/ADR-005/006/013 updated; import matrix regenerated
  with Unity marked "licence proven, adapter not run"; dashboard gate text updated.
- Verification: Unity batchmode exit 0, entitlements resolved, GYPSY_UNITY_SMOKE_OK version=6000.6.7f1 in 50.891 s;
  gypsy engines probe --save reports unity licence.proven true; import matrix PASS godot; 181 tests; 44 capabilities.
  No Unity slice/build is claimed.

## 2026.10.25.020

**ComfyUI: ready-to-import SD1.5 workflow verified in the UI.**

- Date: 2026-10-26
- Commit: this change.
- Change: tools/comfyui/workflows/projectgypsy-sd15-basic.json (CheckpointLoaderSimple -> CLIP text -> KSampler ->
  VAEDecode -> SaveImage, installed v1-5 checkpoint, no Qwen/Z-Image nodes); tools/comfyui/verify_workflow.py
  (structural/link validation, /object_info checkpoint check, UI-graph to API conversion, run + sidecar);
  workflows/README.md; ComfyUI README/TOOLCHAIN links.
- Verification: workflow loaded into ComfyUI 0.42.1 UI via Chromium/CDP with 7 nodes, no missing models/errors;
  verifier passed and produced artifacts/comfyui/20261026T030013-workflow-0.png; 181 tests, 43 capabilities unchanged.

## 2026.10.25.019

**Record the Android emulator attempt as blocked; keep the dashboard final.**

- Date: 2026-10-26
- Commit: this change.
- Change: docs/PHASE-5-EVIDENCE records that the emulator package download produced a corrupt ZIP and no AVD/device
  test was possible; no code or capability claim changed. Dashboard remains the local UI (ADR-014).
- Verification: check_all at 181 tests/43 capabilities; no new tests; UI screenshots unchanged.

## 2026.10.25.018

**Local dark GUI dashboard: four views, token actions, artifact previews.**

- Date: 2026-10-26
- Commit: this change.
- Change: workstream/dashboard.py (localhost-only server, /api/state, /api/job, /api/artifact, /api/diff,
  token-protected /api/run with a fixed argv whitelist); design/dashboard/ (dark single-page app, Studio Board
  default, Mission Control, Command Hybrid, Director's Table; screenshots); CLI dashboard; 9 dashboard tests;
  ADR-014, docs/DASHBOARD.md and capability workstream.dashboard. The game interface remains parked.
- Verification: 181 tests OK; /api/state returns 4 slices/172 tests/42 capabilities/2 blocked; browser screenshots
  for all four views; POST /api/run requires token (403 without), live_once job passed; artifact raw PNG served;
  traversal rejected; 43 capabilities.

## 2026.10.25.017

**Control-panel mockups: four GUI directions and a CLI usage guide.**

- Date: 2026-10-26
- Commit: this change.
- Change: design/control-panel/ with four 1440x900 mockups (Studio Board, Mission Control, Command Hybrid, Director's
  Table), editable HTML sources, rendered PNGs and README; comparison/recommendation and exact current CLI invocation;
  root README link. These are proposals for local developer tooling, not the game interface; nothing is wired in and
  PG-D4 remains parked.
- Verification: mockups render at 1440x900 with Microsoft Edge headless; links/encoding checked by scripts/check_all.py;
  all figures match the current workstream (4 slices, 172 tests, 42 capabilities, 2 blocked gates).

## 2026.10.25.016

**Phase-3/5 audit fixes: deterministic audio, read-only import toolpack, status counts.**

- Date: 2026-10-26
- Commit: this change.
- Change: MusicGen wrapper accepts -Seed and audio.musicgen uses Seed 1234 (two runs byte-identical); import_matrix
  accepts --no-doc and art.import.golden uses it, so the art toolpack (and slices run --all) no longer rewrites tracked
  docs/IMPORT-MATRIX.md; removed the doc-text validator; corrected ADR/PHASE-3/PHASE-5/toolpacks/slices/README/workstream
  status, ADR counts and APK-hash reproducibility note; AGENTS status remains Phase 0-5.
- Verification: art toolpack PASS with doc unchanged; seeded audio twice identical SHA-256
  fe1f4038c69fc3abf452c683f796f0df1db78bf85a06e632514273e72d460533, RMS 0.2018; 172 tests; scripts/check_all.py 6/6;
  42 capabilities.

## 2026.10.25.015

**Phase 5: Android package, live watcher, performance baseline; second-engine/UE5 gates recorded.**

- Date: 2026-10-26
- Commit: this change.
- Change: portable JDK 17 + Android SDK 35 + debug keystore; Android preset/icon/ETC2; scripts/build_android.ps1,
  toolpacks/mobile.android.json, slices/mobile.json; game bench command and budgets; workstream/live.py + 34 tests;
  CLI live; capabilities engine.godot.mobile, perf.game.benchmark, live.iteration; ADR-013, PHASE-5-EVIDENCE,
  PHASE-6-GATE; project manifest targets pc+mobile.
- Verification: signed arm64 APK 28,305,095 bytes, package com.c7imi.projectgypsy, apksigner verified; game bench
  median 2.605 s/p95 2.605 s/GPU 0.56 ms; live --once 2.726 s; 172 tests; second engine BLOCKED (Unity 198, UE5 VRAM,
  Flax no headless); UE5 Phase 6 BLOCKED; 42 capabilities.

## 2026.10.25.014

**Phase 4: read-only terminal console (board, preview, diff).**

- Date: 2026-10-26
- Commit: this change.
- Change: workstream/console.py (read-only board from slice/task state, artifact preview with SHA-256/type metadata,
  read-only git diff), 40 console tests, CLI console board|preview|diff, ADR-012 and PHASE-4-EVIDENCE, capability
  workstream.console; fixed console state-dir scoping so preview/diff do not require it.
- Verification: board task-20261026T064601Z 8/8 steps, 3 artifacts, 79.909 s; preview frame.png 1280x720 SHA-256
  89d0d329...; diff read-only; no writes; 138 tests; scripts/check_all.py 6/6; 39 capabilities.

## 2026.10.25.013

**Phase 3: toolpacks, validators and provenance for art/import and audio.**

- Date: 2026-10-26
- Commit: this change.
- Change: workstream/toolpacks.py (gypsy.toolpack/v1 schema, strict validation, explicit argv, atomic state, SHA-256
  artifact ledger, file/json/text/wav/png/glb validators); 44 toolpack tests; toolpacks/art.import.golden.json and
  toolpacks/audio.musicgen.json; slices/toolpacks.json and the orchestrator toolpack handler; CLI toolpacks
  list|check|run; ADR-011 and PHASE-3-EVIDENCE; capability workstream.toolpack; docs/IMPORT-MATRIX regenerated by the
  art toolpack.
- Verification: toolpacks check 2 valid; art.import.golden PASS (Godot status pass, rigged animations 3, LOD meshes 4,
  doc validator); audio.musicgen PASS (3.94 s WAV, 32 kHz mono PCM, RMS 0.034); slices run toolpacks PASS 2/2 in
  45.233 s with hashes/provenance; 98 tests; scripts/check_all.py 6/6; 38 capabilities.

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