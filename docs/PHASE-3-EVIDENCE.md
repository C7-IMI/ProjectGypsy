# PHASE-3-EVIDENCE.md — toolpacks, validators and provenance

Recorded 2026-10-26. Phase-3 proof for [ADR-011](ADR-011-toolpacks.md). State is under
workstream/state/toolpacks/ (gitignored); this file and the manifests are the committed evidence.

## Gate results

| Gate | Result |
| --- | --- |
| Toolpack manifests | PASS — toolpacks check: 2 valid (art.import.golden, audio.musicgen) |
| Art/import action | PASS — Blender golden kit -> glTF validation -> Godot 4.7.2 import, 10.045 s in the slice |
| Art JSON validators | PASS — godot.status=pass; rigged_character.animations=3 (>=3); lod_set.meshes=4 (>=4) |
| Art text validator | PASS after a real fail-closed catch: an initial "Godot 4.7.2" string did not exist as a contiguous string; validator failed, the check was corrected to "4.7.2", rerun passed |
| Audio action | PASS — local MusicGen 3.94 s clip, 252,204 bytes, 32 kHz mono PCM; RMS 0.034003 (min 0.01) |
| Toolpack slice | PASS — slices run toolpacks: 2/2 steps, 45.233 s, one state/ledger path |
| Provenance | PASS — run id, manifest SHA-256, argv, exit, timings, tools, licence, artifact hashes, validator results |
| Tests | PASS — 98 tests OK (44 new toolpack tests); no Godot/network needed by the tests |
| Capabilities | PASS — 38 capability manifests parse |

## Artifact hashes (from the slice run toolpacks-20261026T064400Z-0ab7ee)

| Artifact | Bytes | SHA-256 |
| --- | --- | --- |
| workstream/state/import-matrix.json | 48,274 | 024b2da2807fe5f423dcebbaca3b11af7017183263dd5d4d317b5ef260094e54 |
| docs/IMPORT-MATRIX.md | 3,721 | 9098d5ac68bf2a35a6516554f1ff8f8bd4b43d868c0dba4d96bf32e1ec3b533b |
| artifacts/toolpacks/musicgen.wav | 252,204 | ae55d84aa8a3e361d2605e439bee914d5fc03b0e82de69f0899be87d32acab29 |

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
- The art action regenerates the tracked docs/IMPORT-MATRIX.md (timestamp/hash); that is expected evidence, not a
  hand edit.
- There is no ComfyUI toolpack yet: a ComfyUI server has a start/stop lifecycle and is already exercised directly in
  ADR-008. A future pack can own that lifecycle explicitly.
- No retries, no model call, no arbitrary shell; state is local and gitignored.
