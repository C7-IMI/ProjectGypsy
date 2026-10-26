# Gypsy Studio

**Gypsy Studio** (short: **Gypsy**) is the local workstream, orchestration and evidence tool for game projects. It is
not itself the game: Phase 1 of this repository is a playable **Godot 4.7.2 PC** slice; the interface standard and other
platforms remain open (PG-D4). The workstream selects and pins an engine per project.

> **Name:** the product/application is **Gypsy Studio / Gypsy**. The checkout directory, Python package and manifest
> schema retain `ProjectGypsy` / `gypsy` identifiers; do not rename those as a branding change.

## Open Gypsy

Say **Open Gypsy**, **Load Gypsy** or **Use Gypsy** (case-insensitive) to tell a coding agent to load Gypsy Studio and
use it. **Open** ensures the local dashboard is running at http://127.0.0.1:8765/ and summarizes state; **Load** imports
the guide/template; **Use** routes the current task through the Gypsy CLI. In another project, all three mean “import
Gypsy”: read [the agent guide](docs/GYPSY-AGENT-GUIDE.md) and the target project's copy of
[templates/AGENTS.gypsy.md](templates/AGENTS.gypsy.md).

## Start here

- [`AGENTS.md`](AGENTS.md) — read first; entry point for any model working here.
- [`docs/GYPSY-AGENT-GUIDE.md`](docs/GYPSY-AGENT-GUIDE.md) — how an agent uses Gypsy on a new or existing project.
- [`templates/AGENTS.gypsy.md`](templates/AGENTS.gypsy.md) — copy-paste instruction block for a target project's `AGENTS.md`.
- [`TOOLCHAIN.md`](TOOLCHAIN.md) — installed engines, art/audio/build tools, paths and the PATH loader.
- [`docs/README.md`](docs/README.md) — all ADRs (001-014: engines, art pipeline, workstream architecture, generative media, character/animation,
  Blender import, language boundaries, MCP/local tools, vertical slice, orchestrator, toolpacks, console, Phase-5) and
  the generated evidence.
- [`workstream/README.md`](workstream/README.md) — the Phase-0-5 CLI: engine registry, hardware gates, manifests,
  checks, Godot slice, slices/orchestrator, toolpacks, console, live watcher and performance bench.

## Rules and decisions

- [`ProjectPack.md`](ProjectPack.md) — the standing rules, this copy's revision **PG-1**; Part 11 is this
  repository's overlay.
- [`ProjectPack-NOTES.md`](ProjectPack-NOTES.md) — how the pack resolves here: placeholders, §8.1 decisions, §8.2
  inventory, what is in force, the §11 mapping.
- [`ProjectPack-ADDENDUM-Interface.md`](ProjectPack-ADDENDUM-Interface.md) — interface design/redesign rules,
  **parked and not in force** because this is a game, not a website.
- [`DEFERRED.md`](DEFERRED.md) — the work deliberately not done, and what unblocks it.
- [`TOOL-INVENTORY.md`](TOOL-INVENTORY.md) — full installed-tool inventory, open-source replacements, hardware limits.
- [`design/control-panel/README.md`](design/control-panel/README.md) — four control-panel directions; the implemented local GUI is [docs/DASHBOARD.md](docs/DASHBOARD.md).
- [`docs/DASHBOARD.md`](docs/DASHBOARD.md) — launch and use the local dark dashboard.
- [`design/dashboard-v2/README.md`](design/dashboard-v2/README.md) — Gypsy Studio operations console: overview, run detail, mission, commands, review, slices, artifacts; classic views at `/classic`.

## Status

Phase 0 + 1 + 2 + 3 + 4 + 5 exist: engine/tool probes, hardware gates, manifests, tests, a playable Godot slice with
headless demo/export/capture, a manifest-driven slice orchestrator with state and artifact hashes, toolpacks with
validators/provenance for golden Blender->Godot import and local MusicGen audio, a read-only terminal console, records
and the pack check list, the ADRs, MCP/ComfyUI/Poly Haven tooling and the installed toolchain. Also present: a live
watcher, performance baseline, a signed Android debug APK (not device-tested), the Gypsy Studio operations console and the LeftBehind Unity 6 second-engine slice. Not built yet: hero art/character
pipeline, self-extension; second engine is proven by Unity LeftBehind; UE5 is hardware-blocked. See `docs/PHASE-5-EVIDENCE.md`, `docs/PHASE-6-GATE.md`
and `DEFERRED.md`.
