# AGENTS.md — Gypsy Studio

Entry point for any model working in this repository. Read this file, then the documents it names, before acting.

## What this repository is

**Gypsy Studio** (short: **Gypsy**) is the local workstream/orchestration and evidence tool for game projects.
This repository's Phase 1 game runs on **Godot 4.7.2, PC** ([ADR-009](./docs/ADR-009-vertical-slice.md)); other
platforms and the game's interface standard remain open (PG-D4). The checkout directory and Python/manifest identifiers
still say `ProjectGypsy` / `gypsy`; do not rename them as a branding change. The engine-selection mechanism is built
([`docs/ADR-001-engines.md`](./docs/ADR-001-engines.md), `workstream/gypsy.py`); the Phase-1 choice can be overridden by
a new project manifest, but an engine change is a port, not a toggle. **New projects default to Unity 6000.6.7f1/PC**
([ADR-018](./docs/ADR-018-unity-default.md)); this existing Godot game is the legacy/reference implementation until the
separate UltraBlade 2 Stage B migration is verified. Do not relabel the current game. Do not describe Gypsy Studio as a website, a web application or a console, and do not apply web interface
rules to it.

## Use Gypsy Studio in every project

### Invocation trigger: any invocation verb + “Gypsy”

Treat **any imperative invocation verb followed by Gypsy** as a request to load/use Gypsy. This is not limited to a
fixed phrase: **Open Gypsy**, **Load Gypsy**, **Use Gypsy**, **Invoke Gypsy**, **Launch Gypsy**, **Start Gypsy**,
**Call Gypsy**, **Run Gypsy**, **Show Gypsy**, **Import Gypsy**, **Activate Gypsy**, **Bring up Gypsy**, **Pull up
Gypsy**, **Summon Gypsy**, etc. all trigger it. Case-insensitive. Do not trigger on negated requests (e.g. “do not
open Gypsy”) or when merely discussing Gypsy.

1. Resolve `GYPSY_HOME` (or this checkout) and verify `python "$env:GYPSY_HOME\workstream\gypsy.py" version`.
2. **Load/import Gypsy**: read `docs/GYPSY-AGENT-GUIDE.md` and, in another project, the target `AGENTS.gypsy.md`
   block. Do not create a duplicate or an ad-hoc orchestrator.
3. Check `http://127.0.0.1:8765/api/state`. If it is down, start
   `python "$env:GYPSY_HOME\workstream\gypsy.py" dashboard --no-open` and wait for the endpoint.
4. If the request is to **open/launch/show/bring up** Gypsy, open or report `http://127.0.0.1:8765/`. If it is to
   **use/run/invoke/call** Gypsy, route the current task through the Gypsy CLI and start with
   `gypsy check --project <dir>` (or `gypsy check` in this checkout).
5. Report the dashboard URL, the current slices/gates, and what Gypsy was used for. If Gypsy cannot be found or
   started, report the exact failure. Do not fake the URL, the commands or the state.

When starting or working on any game project, call **Gypsy Studio** instead of reimplementing workstream probes, checks,
slices, toolpacks or evidence. The portable instructions and copy-paste template are:

- [`docs/GYPSY-AGENT-GUIDE.md`](./docs/GYPSY-AGENT-GUIDE.md) — canonical agent guide (new + existing projects).
- [`templates/AGENTS.gypsy.md`](./templates/AGENTS.gypsy.md) — append to a target project's `AGENTS.md`; replace
  `<GYPSY_HOME>` with this checkout.

Verify the CLI before trusting it: `python workstream/gypsy.py version`. If Gypsy cannot be found, report the block;
do not substitute ad-hoc shell orchestration and do not claim evidence.

### Toolkit requests: "add XXX to the toolkit"

**Standing operator rule:** whenever the operator asks to add "XXX" to the toolkit — in any wording — **extend Gypsy
Studio** so the tool is reusable by every future project. It is **not** a project-local script, a one-off toolpack, or
a hack inside one game. A toolkit addition is complete only when it has:

1. a plugin under [`workstream/toolkits/`](./workstream/toolkits/) registered and validated by
   [`workstream/toolkit.py`](./workstream/toolkit.py);
2. `gypsy toolkit` commands — the generic `list`, `show`, `probe` and `capabilities`, plus the tool's own verbs;
3. a capability manifest under [`workstream/capabilities/`](./workstream/capabilities/);
4. documentation in [`TOOLCHAIN.md`](./TOOLCHAIN.md), [`TOOL-INVENTORY.md`](./TOOL-INVENTORY.md) and an ADR;
5. tests that need no network, plus the Retrace/BuildNotes entries.

**ActionForge is the reference implementation** — [ADR-015](./docs/ADR-015-actionforge-toolkit.md),
`gypsy toolkit actionforge catalog|fetch`.

## What governs your work

In this order:

1. **[`ProjectPack.md`](./ProjectPack.md)** — the standing rules, this copy's revision **PG-1** (base: C7NTRY's
   pack 2.5). Parts 1–10 are the portable pack and the operator's standing rules; **Part 11 is this repository's own
   overlay** — 13 rules adapted from C7NTRY's 24.
2. **[`ProjectPack-NOTES.md`](./ProjectPack-NOTES.md)** — how the pack resolves *here*: the placeholders, the §8.1
   answers, the §8.2 inventory, which rules are actually in force, the §11 mapping, and the parked interface list.
   When the pack and this repository differ, this file says how, and it is the file to correct if it is wrong.
3. **[`ProjectPack-ADDENDUM-Interface.md`](./ProjectPack-ADDENDUM-Interface.md)** — interface design/redesign
   material, **parked and not in force**. Read its first page so you know what is parked. Do not apply it, quote it as
   a requirement, or restore any of it without the recorded operator decision it asks for.
4. **[`TOOLCHAIN.md`](./TOOLCHAIN.md)** — installed engines, art/audio/build tools, paths, versions and the
   `tools/tool-env.ps1` PATH loader. Read it before claiming a tool exists.
5. **[`docs/README.md`](./docs/README.md)** — the ADRs: engines (001), art pipeline (002), workstream architecture
   (003), generative media (004), character/animation automation (005), Blender import matrix (006), language
   boundaries (007), MCP/free local tools (008), vertical slice (009), slice orchestrator (010), toolpacks (011),
   thin console (012), phase-5 mobile/live/perf (013), local dashboard (014), ActionForge toolkit (015), plus
   [`docs/DASHBOARD.md`](./docs/DASHBOARD.md), [`docs/GYPSY-AGENT-GUIDE.md`](./docs/GYPSY-AGENT-GUIDE.md),
   [`docs/ADR-016-self-extension.md`](./docs/ADR-016-self-extension.md),
   [`docs/ADR-017-hero-character-pipeline.md`](./docs/ADR-017-hero-character-pipeline.md),
   [`docs/ADR-018-unity-default.md`](./docs/ADR-018-unity-default.md),
   [`docs/ADR-019-cache-quality.md`](./docs/ADR-019-cache-quality.md),
   [`docs/ADR-020-remote-cache.md`](./docs/ADR-020-remote-cache.md),
   [`docs/ADR-021-assets-metrics.md`](./docs/ADR-021-assets-metrics.md),
   [`docs/ADR-022-provenance.md`](./docs/ADR-022-provenance.md),
   [`docs/ADR-023-asset-graph.md`](./docs/ADR-023-asset-graph.md),
   [`docs/ADR-024-remote-worker.md`](./docs/ADR-024-remote-worker.md),
   [`docs/ADR-025-traces.md`](./docs/ADR-025-traces.md),
   [`docs/UNITY-SLICE.md`](./docs/UNITY-SLICE.md),
   [`docs/ENGINE-SMOKE.md`](./docs/ENGINE-SMOKE.md), [`docs/IMPORT-MATRIX.md`](./docs/IMPORT-MATRIX.md),
   the PHASE-1..5 evidence files and [`docs/PHASE-6-GATE.md`](./docs/PHASE-6-GATE.md).
6. **[`workstream/README.md`](./workstream/README.md)** — the CLI: `engines probe|smoke`, `tools probe`,
   `capabilities`, `toolkit list|show|probe|capabilities` and `toolkit actionforge catalog|fetch`, `project`,
   `extension list|show|validate|test|register|disable|remove|run|reload`, `game demo|build|capture|verify`,
   `slices list|plan|run|status`, `toolpacks list|check|run`,
   `console board|preview|diff`, `dashboard`, `game bench`, `live`, `check`.
7. **[`DEFERRED.md`](./DEFERRED.md)** — the work deliberately not done. Read the entry covering an area before you
   change that area, and do not quietly close a deferred item by implementing it halfway.
8. **[`README.md`](./README.md)** — the repository entry point and index.

## The rules that bind every turn

- **Never claim a check you did not run.** Report exactly what was verified, by what command, and what was not
  (§1.10, P1, Part 11.2).
- **This is a game, not a web app.** No design-language, mockup-first, visual-bar, viewport, token-lint,
  accessibility-pass or browser-gate rule applies until the addendum is restored or replaced by a recorded decision
  (PG-1, Part 11.1). If a request needs interface design, say the standard is parked and treat the choice as the
  operator's — do not invent one.
- **Verify by running** the build or the test that proves the change, and read back what you captured (§2.18). If no
  build exists yet, say so rather than implying a verification. Evidence lives in `docs/ENGINE-SMOKE.md`,
  `docs/IMPORT-MATRIX.md`, and the PHASE-1..5 evidence files plus PHASE-6-GATE.
- **Record the work.** A change is not finished until its [Retrace.md](./Retrace.md) and [BuildNotes.md](./BuildNotes.md)
  entries exist, with a version from [`scripts/next-version.py`](./scripts/next-version.py) (§2.1).
  [`scripts/check_all.py`](./scripts/check_all.py) guards the records.
- **One list of checks:** [`scripts/check_all.py`](./scripts/check_all.py); the tracked pre-commit hook and the
  GitHub Actions caller both run it, and its coverage guard compares the two (§2.22–§2.23). Never keep a second list.
- **Records and peer projects are separate** (Part 11.5): C7NTRY, C7NC, C7NTAX, C7TNL, C7NTRL and the other C7-IMI
  projects are peers. A prompt asked here is logged here; nothing crosses without explicit instruction.
- **Nothing fake in the build** (Part 11.6): no dead controls, no pretend features; unavailable behaviour says so.
  An engine capability that is hardware-gated or licence-blocked is reported as such, not tested halfway
  (`engine.ue5.build` is `blocked`; Unity build/demo/capture is proven by LeftBehind, asset import is not).
- **Generated media is prototype-only until licensed.** MusicGen-small weights are CC-BY-NC 4.0; every generated
  asset needs provenance and human approval (ADR-004). Never ship it as a commercial asset.
- **Background agents are evidence only after they are read** (§10.8). A dispatch is not progress; read the status
  *and* the work before recording it.
- **Handle text carefully** (§2.32): UTF-8 without a BOM, no round-trip through PowerShell, read back what you wrote.

## First action in a new session

1. Read this file, `ProjectPack-NOTES.md` §2.31, `DEFERRED.md`, `TOOLCHAIN.md` and `docs/README.md`.
2. Check `git status` and the newest records entry — if the records do not exist yet, say so rather than pretending.
3. Run `python workstream/gypsy.py engines probe` and `python workstream/gypsy.py check` before trusting the
   environment; report what they actually print.
4. Run `python scripts/check_all.py` and `python workstream/gypsy.py slices run --all` before trusting the tree; report
   what they print. `--all` now includes the Phase-3 toolpacks slice and takes longer.
5. Ask what the session is for, then run the matching prompt from `ProjectPack.md` Part 3 — **P1** only if the
   bootstrap is incomplete, otherwise **P2** onward. Prompts P4 and P16 are parked; do not renumber the others.

## What has been built (do not overstate it)

Phase 0-5 exist: engine/tool probes, hardware gates, manifests, a Godot headless smoke, a playable Godot 4.7.2 PC slice
with demo/export/capture, a manifest-driven slice orchestrator with state/artifact hashes, toolpacks with
validators/provenance, a read-only terminal console, a live watcher, a performance baseline, a signed Android debug
APK, the Gypsy Studio operations console and classic four-view dashboard; **LeftBehind** proves the same slice on Unity 6
(build, demo and capture); an action-level content cache, opt-in parallel execution, visual/performance quality gates, a
project catalog with golden-path templates, the Projects/Insights/live-log dashboard and an authenticated loopback
remote action cache, asset registry/provenance warnings, state-derived metrics and local HMAC provenance/SBOM, an explicit asset dependency/budget graph, TLS remote worker (allowlisted read-only jobs) and local traces; records and the one pack check list; the
ADRs; a golden Blender import matrix; MCP/ComfyUI/Poly Haven tooling, the safe self-extension pipeline and the first hero
art/character pipeline (runtime LOD, driven Smile, spring cape). The Android **emulator launch passes** (boot, install,
launch, render, screenshot, logcat); a physical device, touch/audio/rotation/performance and release signing remain
untested. Unity hero FBX import is proven; UE5 remains hardware-blocked. See `docs/PHASE-5-EVIDENCE.md`,
`docs/UNITY-SLICE.md`, `docs/ADR-017-hero-character-pipeline.md`, `docs/ADR-019-cache-quality.md`,
`docs/DEVICE-LAUNCH.md`, `docs/PHASE-6-GATE.md`, `docs/DASHBOARD.md` and `DEFERRED.md`.