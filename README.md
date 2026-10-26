# ProjectGypsy

A game. Phase 1 is a playable **Godot 4.7.2 PC** slice; the interface standard and other platforms remain open
(PG-D4). The workstream selects and pins an engine per project.

## Start here

- [`AGENTS.md`](AGENTS.md) — read first; entry point for any model working here.
- [`TOOLCHAIN.md`](TOOLCHAIN.md) — installed engines, art/audio/build tools, paths and the PATH loader.
- [`docs/README.md`](docs/README.md) — all ten ADRs (engines, art pipeline, workstream architecture, generative
  media, character/animation automation, Blender import matrix, language boundaries, MCP/local tools, vertical slice,
  slice orchestrator) and the generated evidence.
- [`workstream/README.md`](workstream/README.md) — the Phase-0-2 CLI: engine registry, hardware gates, manifests,
  checks, Godot smoke/slice commands, and the phase-2 slices orchestrator.

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

Phase 0 + 1 + 2 + 3 + 4 + 5 exist: engine/tool probes, hardware gates, manifests, tests, a playable Godot slice with
headless demo/export/capture, a manifest-driven slice orchestrator with state and artifact hashes, toolpacks with
validators/provenance for golden Blender->Godot import and local MusicGen audio, a read-only terminal console, records
and the pack check list, the ADRs, MCP/ComfyUI/Poly Haven tooling and the installed toolchain. Also present: a live
watcher, performance baseline and a signed Android debug APK (not device-tested). Not built yet: hero art/character
pipeline, self-extension, second engine; UE5 is hardware-blocked. See `docs/PHASE-5-EVIDENCE.md`, `docs/PHASE-6-GATE.md`
and `DEFERRED.md`.
