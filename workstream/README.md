# Workstream (Phase 0)

The studio-harness skeleton described in [docs/ADR-003-workstream-architecture.md](../docs/ADR-003-workstream-architecture.md).
It is deliberately small: detection, manifests and checks first; adapters and the orchestrator come later.

## Commands

\`\`\`text
python workstream/gypsy.py engines probe [--json]          # detect engines, hardware gates, stale registry entries
python workstream/gypsy.py engines smoke godot [--json]    # headless Godot project boots and exits 0
python workstream/gypsy.py tools probe [--json]            # verify the installed GameTools manifest
python workstream/gypsy.py capabilities list|check [--json]
python workstream/gypsy.py project init --path game --engine godot --version 4.7.2 --targets pc
python workstream/gypsy.py project show [--path game]
python workstream/gypsy.py check [--project .] [--json]
\`\`\`

Run the tests:

\`\`\`text
python -m unittest discover -s workstream/tests -v
\`\`\`

## What is real in Phase 0

- Engine registry by binary probe, not registry metadata; hardware gate; Unity licence presence; Godot export-template
  detection; UE5 stale-registry reporting.
- Project manifest pinning engine/version/adapter/targets and refusing mismatches or non-empty directories.
- Capability manifests with schema validation.
- Tool manifest verification.
- Godot headless smoke test (the reference adapter).

## What is not built yet

Engine adapters beyond detection/smoke, build/export automation, capture harness, artifact store, orchestrator state
machine, console. Those are registered as deferred work (DEFERRED.md) rather than claimed. See
[docs/ADR-003-workstream-architecture.md](../docs/ADR-003-workstream-architecture.md) for the phase plan.
