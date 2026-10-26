# ProjectGypsy

A game. The repository is its working home. The engine, target platforms and interface standard are not chosen yet
(see [`DEFERRED.md`](DEFERRED.md) PG-D3/PG-D4); the workstream can select and pin an engine per project.

## Start here

- [`AGENTS.md`](AGENTS.md) — read first; entry point for any model working here.
- [`TOOLCHAIN.md`](TOOLCHAIN.md) — installed engines, art/audio/build tools, paths and the PATH loader.
- [`docs/README.md`](docs/README.md) — all seven ADRs (engines, art pipeline, workstream architecture, generative
  media, character/animation automation, Blender import matrix, language boundaries) and the Phase-0 evidence.
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

Phase 0 exists: engine/tool probes, hardware gates, capability and project manifests, unit tests, a Godot headless
smoke pass, a Blender 5.2 golden import matrix (Godot pass; Unity/UE5 blocked), the ADRs and the installed toolchain. Not built yet: a chosen engine for the game, game code, build/export
adapters, rendered capture, orchestrator/console, records infrastructure. See `docs/ENGINE-SMOKE.md` and
`DEFERRED.md`.
