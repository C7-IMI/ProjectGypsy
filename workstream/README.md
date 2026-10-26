# Workstream (Phase 0-2)

The studio harness described in [docs/ADR-003-workstream-architecture.md](../docs/ADR-003-workstream-architecture.md):
engine/tool detection, manifests and checks (Phase 0), a playable Godot slice (Phase 1), and a manifest-driven slice
orchestrator with state and artifact hashes (Phase 2).

## Commands

```text
python workstream/gypsy.py engines probe [--json]          # detect engines, hardware gates, stale registry entries
python workstream/gypsy.py engines smoke godot [--json]    # headless Godot project boots and exits 0
python workstream/gypsy.py tools probe [--json]            # verify the installed GameTools manifest
python workstream/gypsy.py capabilities list|check [--json]
python workstream/gypsy.py project init --path game --engine godot --version 4.7.2 --targets pc
python workstream/gypsy.py project show [--path game]
python workstream/gypsy.py check [--project .] [--json]
python workstream/gypsy.py game demo|build|capture|verify [--path game]
python workstream/gypsy.py slices list|plan|run|status [--all] [--resume] [--force]
python workstream/gypsy.py toolpacks list|check|run [--action]
python workstream/gypsy.py console board|preview|diff [--json]
```

Run the tests:

```text
python -m unittest discover -s workstream/tests -v
```

## What is real

- Engine registry by binary probe, not registry metadata; hardware gate; Unity licence presence; Godot export-template
  detection; UE5 stale-registry reporting.
- Project manifest pinning engine/version/adapter/targets and refusing mismatches or non-empty directories.
- Capability manifests with schema validation.
- Tool manifest verification.
- Godot headless smoke test (the reference adapter).
- Phase-1 game adapter: headless demo, Windows export, exported-binary demo, windowed movie capture.
- Phase-2 orchestrator: gypsy.slice/v1 manifests (`slices/`), ordered/dependent steps, resumable state, artifact
  SHA-256 ledger, multi-slice task report and the `slices` CLI.
- Phase-3 toolpacks: gypsy.toolpack/v1 manifests (`toolpacks/`), explicit argv actions, file/json/text/WAV/PNG/GLB
  validators, artifact hashes and provenance; real packs for golden Blender->Godot import and MusicGen audio.
- Phase-4 console: read-only terminal board, artifact preview and git diff; no writes, no server, no new capability.

## What is not built yet

Engine adapters beyond Godot, console/TUI, live editing and self-extension. Those are registered as deferred work
(DEFERRED.md) rather than claimed. See
[docs/ADR-003-workstream-architecture.md](../docs/ADR-003-workstream-architecture.md) for the phase plan.