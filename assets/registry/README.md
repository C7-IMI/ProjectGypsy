# Asset registry

Read-only asset registry for the repository. It answers "what assets exist, what are their hashes,
which bytes are duplicated, and what provenance/licence is recorded for them?" and nothing else: it
does not import, convert, move or delete an asset.

The implementation is [workstream/assets.py](../../workstream/assets.py) and the tests are
[workstream/tests/test_assets.py](../../workstream/tests/test_assets.py). This file documents the
optional provenance sidecar and the scan rules; the scan output is the truth, not this page.

## Run it

    python workstream/assets.py                 # human summary over the default roots
    python workstream/assets.py --json          # gypsy.asset-registry/v1 payload
    python workstream/assets.py --validate      # exit 1 on scan errors or an invalid payload
    python workstream/assets.py --save-state    # write workstream/state/assets.json (gitignored)
    python workstream/assets.py --state PATH    # print a saved payload after validating it
    python workstream/assets.py --root PATH --root PATH2 --registry PATH

`--validate` fails on scan errors and payload problems. It does not treat unknown provenance as a
pass: missing provenance is reported as warnings and the counts say so.

## Default roots and what is skipped

Default roots: `assets/`, `game/assets/` and `unity/LeftBehind/Assets/`. Each root in the payload
reports its asset count and its ignored-file count.

- Pruned directories (case-insensitive): `Library`, `obj`, `build`, `import`, `imports`, `Temp`,
  `Logs`, `node_modules`, `__pycache__`, engine caches, plus any directory whose name starts with
  a dot.
- Skipped files: generated engine metadata and temp files (`.meta`, `.import`, `.uid`, `.tmp`,
  `.bak`, `.swp`, `.log`), OS metadata (`.DS_Store`, `Thumbs.db`, `desktop.ini`), hidden files
  and files ending in `~`.
- The provenance sidecar itself is never listed as an asset.
- Repeated or overlapping roots are counted once and reported as a warning.

Media kind is decided by extension only: image (png, jpg, exr, psd, svg, ...), model (glb, gltf,
fbx, blend, ...), audio (wav, ogg, mp3, ...), text (md, json, gd, cs, unity, ...), otherwise
binary. An unknown or missing extension is classified binary rather than guessed from content.

## Payload

Top level: `schema`, `generated`, `roots`, `assets`, `duplicates`, `count`, `totalBytes`,
`counts`, `registry`, `provenance`, `warnings`, `errors`. Each asset has `path`, `root`,
`bytes`, `sha256`, `media`, `modified` (UTC), `duplicate`, `provenance` and `warnings`;
assets are sorted by path and duplicate groups by SHA-256.

## Provenance sidecar (optional)

The scan looks for `assets/registry/provenance.json` by default (override with `--registry`). This is
a lightweight sidecar, not the full ADR-002 D5 provenance record: it records only what is written
here, and every gap stays a warning.

```json
{
  "schema": "gypsy.asset-provenance/v1",
  "assets": [
    {
      "path": "assets/hero/wayfarer.fbx",
      "license": "CC0-1.0",
      "source": "generated in this repository from the Wayfarer art brief",
      "author": "Gypsy build",
      "approved": true,
      "notes": "prototype character; see ADR-017"
    }
  ]
}
```

Rules:

- `path` is what the scan reports: repository-relative POSIX inside the checkout, absolute POSIX
  outside it. Matching is exact, then case-insensitive (Windows).
- `license` is the only field a scan interprets; when it is missing or not a string the asset gets
  a warning.
- Unknown extra keys are preserved and reported back; they are not validated.
- Missing file: one warning and every asset's provenance is unknown. Malformed JSON, a wrong
  `schema`, a non-list `assets` or a bad entry: warnings, not crashes; nothing is silently passed.
- A registry entry for a path that was not scanned is reported as a warning (stale registry).
- Missing provenance is never reported as a pass, and a recorded licence is not a legal clearance:
  [ADR-002](../../docs/ADR-002-art-pipeline.md) D5 is the provenance contract, and AI-generated
  content still follows [ADR-004](../../docs/ADR-004-generative-media.md).

## State

`--save-state` writes the validated payload to `workstream/state/assets.json` atomically
(gitignored). It is a comparison cache, not a source of truth: always rescan, and a stale state file
must not be shown as current asset health.

## Limits

- Read-only: no import, conversion, dependency graph, importer settings or engine outputs. The
  asset-dependency work in [docs/IMPROVEMENT-ROADMAP.md](../../docs/IMPROVEMENT-ROADMAP.md) is
  separate and is not claimed here.
- Hashes are SHA-256 of file bytes; `modified` is the filesystem mtime, not a content-freshness
  proof.
- Duplicate content is reported, not resolved. This repository keeps both `assets/hero/` sources and
  Godot's copies under `game/assets/`, so identical bytes are expected and shown.
- Not yet wired into `workstream/gypsy.py`, the dashboard or [scripts/check_all.py](../../scripts/check_all.py);
  it has a standalone entry point. Wiring is a separate integration change.
