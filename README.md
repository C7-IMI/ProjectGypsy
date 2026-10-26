# ProjectGypsy

A game. Phase 1 is a playable **Godot 4.7.2 PC** slice; the interface standard and other platforms remain open
(PG-D4). The workstream selects and pins an engine per project.

## Start here

- [`AGENTS.md`](AGENTS.md) — read first; entry point for any model working here.
- [`TOOLCHAIN.md`](TOOLCHAIN.md) — installed engines, art/audio/build tools, paths and the PATH loader.
- [`docs/README.md`](docs/README.md) — all ten ADRs (engines, art pipeline, workstream architecture, generative
  media, character/animation automation, Blender import matrix, language boundaries, MCP/local tools, vertical slice,
  slice orchestrator) and the generated evidence.
- [`workstream/README.md`](workstream/README.md) — the Phase-0 CLI: engine registry, hardware gates, capability and
  project manifests, checks, Godot smoke test.

## Rules and decisions

- [`ProjectPack.md`](ProjectPack.md) — the standing rules, this copy's revision **PG-1**; Part 11 is this
  repository's overlay.
- [`ProjectPack-NOTES.md`](ProjectPack-NOTES.md) — how the pack resolves here: placeholders, §8.1 decisions, §8.2
  inventory, what is in force, the §11 mapping.
- [`ProjectPack-ADDENDUM-Interface.md`](ProjectPack-ADDENDUM-Interface.md) — interface design/redesign rules,
  **parked and not in force** because this is a game, not a website.
- [`DEFERRED.md`](DEFERRED.md) — the work deliberately not done, and what unblocks it.
- [`TOOL-INVENTORY.md`](TOOL-INVENTORY.md) — full installed-tool inventory, open-source replacements, hardware limits.

## Status

Phase 0 + Phase 1 + Phase 2 exist: engine/tool probes, hardware gates, manifests, tests, a playable Godot slice with
headless demo/export/capture, a manifest-driven slice orchestrator with state, artifact hashes and multi-slice reports,
records and the pack check list, a golden Blender import matrix (Godot pass; Unity/UE5 blocked), MCP/ComfyUI/Poly Haven
tooling, the ADRs and the installed toolchain. Not built yet: art/character pipeline, UI, audio, console/live editing,
mobile or performance budgets. See `docs/PHASE-2-EVIDENCE.md` and `DEFERRED.md`.
