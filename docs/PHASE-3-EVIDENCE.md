# PHASE-3-EVIDENCE.md — toolpacks, validators and provenance

Recorded 2026-10-26. Phase-3 proof for [ADR-011](ADR-011-toolpacks.md). State is under
workstream/state/toolpacks/ (gitignored); this file and the manifests are the committed evidence.

## Gate results

| Gate | Result |
| --- | --- |
| Toolpack manifests | PASS — toolpacks check: 3 valid at current tree (art.import.golden, audio.musicgen, mobile.android) |
| Art/import action | PASS — Blender golden kit -> glTF validation -> Godot 4.7.2 import, 9.7 s with --no-doc |
| Art JSON validators | PASS — godot.status=pass; rigged_character.animations=3 (>=3); lod_set.meshes=4 (>=4) |
| Tracked docs | PASS — art toolpack uses --no-doc, so slices run --all does not rewrite tracked docs/IMPORT-MATRIX.md |
| Audio action | PASS — local MusicGen 3.94 s clip, 252,204 bytes, 32 kHz mono PCM; seeded (Seed 1234) RMS 0.2018 (min 0.01); two seeded runs produced identical SHA-256 |
| Toolpack slice | PASS — slices run toolpacks: 2/2 steps, 45.233 s, one state/ledger path |
| Provenance | PASS — run id, manifest SHA-256, argv, exit, timings, tools, licence, artifact hashes, validator results |
| Tests | PASS — 98 tests at Phase-3 close (44 new toolpack tests); current full suite 172 |
| Capabilities | PASS — 42 capability manifests at current tree |

## Artifact hashes (from the slice run toolpacks-20261026T064400Z-0ab7ee)

| Artifact | Bytes | SHA-256 |
| --- | --- | --- |
| workstream/state/import-matrix.json | 48,274 | b4d7cbebf4d1463f58615004047900e8416b54809585003825c9fcbf953493f0 |
| artifacts/toolpacks/musicgen.wav | 252,204 | fe1f4038c69fc3abf452c683f796f0df1db78bf85a06e632514273e72d460533 |

The toolpack state files also carry per-validator details (JSON check count, WAV seconds/channels/framerate/frames/RMS)
and the declared licence and tools.

## Commands

    python workstream/gypsy.py toolpacks list
    python workstream/gypsy.py toolpacks check
    python workstream/gypsy.py toolpacks run art.import.golden
    python workstream/gypsy.py toolpacks run audio.musicgen
    python workstream/gypsy.py slices run toolpacks
    python workstream/gypsy.py slices status toolpacks --json

## What is proven

- The art chain generated/round-tripped/validated/imported the golden kit and the Godot import result passed
  machine checks, not just an exit code.
- The audio chain generated a local WAV and its duration/non-silence were validated.
- Both runs have SHA-256 artifact ledgers and a declared tool/licence provenance record.
- A missing artifact, failed validator or failed command fails the action and stops the chain (toolpack tests).

## Limits

- This proves structure/import/provenance, not art quality. The golden kit is test geometry; MusicGen is
  CC-BY-NC 4.0 prototype audio.
- The art action now writes only the JSON state (--no-doc); tracked docs/IMPORT-MATRIX.md is left untouched by the
toolpack and by slices run --all.
- There is no ComfyUI toolpack yet: a ComfyUI server has a start/stop lifecycle and is already exercised directly in
  ADR-008. A future pack can own that lifecycle explicitly.
- No retries, no model call, no arbitrary shell; state is local and gitignored.
