# Toolpacks (Phase 3)

Toolpacks are JSON manifests for a tool or small tool chain: declared tools and licence, explicit
argv actions, declared artifacts, and validators that must pass before the run counts. They are
executed by [workstream/toolpacks.py](../workstream/toolpacks.py) and wrapped by the CLI.

    python workstream/gypsy.py toolpacks list
    python workstream/gypsy.py toolpacks check
    python workstream/gypsy.py toolpacks run art.import.golden
    python workstream/gypsy.py toolpacks run audio.musicgen

A toolpack step can also be declared in a slice:

    {"id": "audio", "kind": "toolpack", "needs": [], "timeout": 300,
     "args": {"toolpack": "audio.musicgen", "action": "generate"}}

## Real toolpacks

| Manifest | Action | Artifacts | Validators |
| --- | --- | --- | --- |
| art.import.golden.json | python scripts/import_matrix.py | workstream/state/import-matrix.json, docs/IMPORT-MATRIX.md | Godot status pass, rigged character animations >= 3, LOD meshes >= 4, doc contains 4.7.2 |
| audio.musicgen.json | tools/musicgen/musicgen.ps1 | artifacts/toolpacks/musicgen.wav | 16-bit PCM WAV, >= 3 s, RMS >= 0.01 |

The art pack regenerates the Blender golden kit, round-trips GLB/FBX, validates glTF and imports
into Godot 4.7.2. The audio pack uses local MusicGen-small; its weights are CC-BY-NC 4.0 and the
result is prototype-only until reviewed.

## Rules

- argv is a list, run with shell=False; a shell string is refused.
- cwd and artifacts are repo-relative; artifacts may use one trailing glob segment.
- Declared artifacts are SHA-256 hashed and validators run after the command, pass or fail.
- Missing artifacts or failed validators fail the action; a failed action stops later actions.
- State is atomic JSON under workstream/state/toolpacks/ (gitignored); the declared licence, tools
  and argv are copied into every state document.
- No retries, no model call, no arbitrary shell.

See [ADR-011](../docs/ADR-011-toolpacks.md) and [PHASE-3-EVIDENCE.md](../docs/PHASE-3-EVIDENCE.md).
