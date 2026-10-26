# ADR-015 — ActionForge toolkit and the reusable toolkit registry

- **Status:** accepted, 2026-10-26
- **Scope:** a first-class toolkit/plugin mechanism in Gypsy Studio, the ActionForge CC0 animation-library adapter,
  its licence/provenance rules, network and path safety, and what remains manual.
- **Related:** [ADR-002](ADR-002-art-pipeline.md) (art contract and validators), [ADR-003](ADR-003-workstream-architecture.md)
  (studio harness, capability bus, self-extension safety), [ADR-004](ADR-004-generative-media.md) (licence discipline),
  [ADR-011](ADR-011-toolpacks.md) (toolpacks and provenance), [TOOLCHAIN.md](../TOOLCHAIN.md),
  [TOOL-INVENTORY.md](../TOOL-INVENTORY.md), [workstream/README.md](../workstream/README.md).
- **Out of scope:** animation authorship, motion editing, retargeting, loop/foot-slide QA, engine import and any
  redistribution of the ActionForge application.

## Context

The operator asked, verbatim:

> "Add ActionForge to Gypsy for all future projects. If I say add 'XXX' to the toolkit, that means Gypsy should be
> extended (or plugin created, etc.) to include that tool as part of the Studio for future use."

ActionForge ([actionforge.app](https://actionforge.app/)) is a browser-based Mixamo alternative. Its humanoid rig is
`https://actionforge.app/assets/animation-library/rig/rig-human.glb`; animation clips are
`https://actionforge.app/assets/animation-library/animations/<clip_id>.glb`. The animation library is **CC0** (no
attribution required); the ActionForge application code is **(c) CGstuff**.

Before this change, adding an asset source would have meant another one-off script, another download path and another
provenance format. The operator's standing rule makes the reusable shape the requirement: a toolkit request extends
**Gypsy Studio**, not one game project.

## Decision

### D1 — A validated toolkit registry, not per-tool CLI branches

`workstream/toolkit.py` discovers plugins in `workstream/toolkits/*.py` and validates a small module contract:
`TOOLKIT_ID`, `NAME`, `SUMMARY`, `LICENSE`, `STATUS`, `KIND`, `CAPABILITY`, `HOME`, `COMMANDS`, `describe()`
and `probe()`. Each plugin may register verbs; `configure`, `run` and `render` are standard so the CLI does not know
any tool by name. Registry validation also checks that the plugin's capability manifest exists, parses, matches its id
and has an allowed maturity. `gypsy check` runs that validation.

Generic commands:

```text
python workstream/gypsy.py toolkit list [--json]
python workstream/gypsy.py toolkit show actionforge [--json]
python workstream/gypsy.py toolkit probe actionforge [--json]
python workstream/gypsy.py toolkit capabilities [--json]
```

`list`, `show` and `capabilities` are offline registry operations. `probe` is the plugin's explicit network check.

### D2 — ActionForge scope and fetch interface

```text
python workstream/gypsy.py toolkit actionforge catalog [--json]
python workstream/gypsy.py toolkit actionforge fetch --project <dir> --clips idle_loop,walk_loop --rig \
    [--dest assets/actionforge] [--force] [--json]
```

- The curated catalog contains 20 known clip ids (idle, locomotion, sword, unarmed combat and reactions). `fetch`
  also accepts any other known id matching `^[a-z][a-z0-9_]{0,63}$`; such an id is marked `catalogued: false` in
  provenance and reported as a warning. There is no remote catalog scraping.
- Fetched layout under `--dest` (default `assets/actionforge`):
  `rig/rig-human.glb`, `animations/<clip_id>.glb`, `provenance.json` and `NOTICE.md`.
- A rerun with identical bytes is idempotent: files, provenance and `NOTICE.md` stay byte-identical. A differing
  existing file is refused with a conflict and a non-zero exit unless `--force` is passed.
- Loop hints in the catalog are derived from clip names; they are not verified by playback.

### D3 — Licence and provenance

The animation library is CC0, so attribution is not required. Provenance is still recorded because the project's rules
require it and because a later licence question must be answerable from the file:

- `provenance.json` uses schema `gypsy.actionforge-provenance/v1` and records the source, licence, URL, project-relative
  path, clip id, curated flag, SHA-256, byte count and retrieval time for every file. Entries are merged across fetches.
- `NOTICE.md` states the CC0 status, records that the ActionForge application code is (c) CGstuff and is not
  downloaded, and lists the files with their hashes.
- No ActionForge application code or unrelated asset is downloaded.

### D4 — Network, path and write safety

- Downloads use Python's standard-library `urllib` directly. There is no shell, no subprocess and no third-party
  dependency.
- Every payload must be a complete binary glTF v2 file: `glTF` magic, version 2 and a header length equal to the
  received byte count. Invalid payloads are not written.
- `--dest` must be project-relative and must resolve inside the project root; absolute paths, drive/UNC anchors and
  `..` segments are rejected before any download. Each file's parent is checked again after it exists.
- Writes are atomic: temp file in the destination directory, flush, `os.replace`. Text is UTF-8 with LF and no BOM.
- There is a 64 MiB per-file safety limit and a per-request timeout.
- `probe` sends a HEAD to the rig URL and falls back to a ranged GET only when HEAD is not allowed (405/501). It
  reports `reachable`, status, method, timestamp and the exact error; an offline failure is a non-zero result, never a
  faked success. It checks one URL, not every clip.
- The test suite never reaches the internet: downloads are injected or `urllib.request.urlopen` is patched with local
  fixtures. Offline commands are tested with a patched opener that fails if called.

### D5 — What is not automated

- Animation authoring, motion editing, retargeting, loop/foot-slide validation and engine import remain manual or
  future work. This adapter fetches a library; it does not animate a character.
- The catalog is curated by hand and can go stale. Unknown-but-known ids are accepted, but the toolkit does not crawl
  ActionForge to discover them.
- ActionForge is a hosted service: availability, rate limits and future URL changes are outside this repository's
  control. A failed probe or fetch is reported as a failure.
- No ActionForge application is installed, embedded or redistributed.

## Acceptance criteria

| Gate | Criterion |
| --- | --- |
| Registry | Plugin discovery validates the contract, ids, statuses, commands and capability link; broken plugins fail loudly |
| Offline | `list`, `show`, `capabilities` and `catalog` work with no network |
| CLI | The documented `toolkit` commands dispatch; unknown toolkits and unsafe destinations fail non-zero |
| Catalog | All 20 curated ids resolve to their URLs; arbitrary safe ids are accepted and unsafe ids rejected |
| Fetch | Selected rig/clips are written atomically with the expected layout |
| Integrity | Every file passes binary glTF v2 validation; SHA-256 and byte count are recorded |
| Idempotence | A repeated identical fetch leaves file, provenance and notice bytes unchanged |
| Overwrite | A differing file is refused without `--force` and replaced with it |
| Confinement | An escaping or absolute `--dest` is refused before downloading |
| Honesty | Invalid GLB, download failure and offline probe return failure and an exact error |
| Tests | The toolkit suite passes without network; the full workstream suite passes |
| Records | BuildNotes/Retrace entries and the capability manifests are present and validated |

## Consequences

**Positive:** any future "add XXX to the toolkit" request has one shape; ActionForge assets can be fetched into any
Gypsy project with reproducible provenance; the registry, capability check and tests are independent of the game;
offline use is preserved.

**Negative / risks:** the registry is a new public-ish interface and needs review when it changes; ActionForge URL or
catalogue changes break fetches until the adapter is updated; the catalog loop hints are not playback-verified; the
fetched CC0 library still needs human art-direction and retargeting work before it belongs in a game.

## Verification

Observed on 2026-10-26 in this checkout:

| Command or action | Observation |
| --- | --- |
| `python -m unittest discover -s workstream/tests -v` | 215 tests, OK (1 skipped) |
| `python workstream/gypsy.py toolkit list --json` | one registered toolkit: `actionforge`, status `partial`, licence includes CC0 |
| `python workstream/gypsy.py toolkit show actionforge --json` | 20 curated clips, 2 commands (`catalog`, `fetch`) |
| `python workstream/gypsy.py toolkit capabilities --json` | `toolkit.actionforge` manifest exists, maturity `partial` |
| `python workstream/gypsy.py toolkit probe actionforge --timeout 5 --json` | `reachable: true`, HTTP 200, HEAD, checked 2026-10-26T06:04:42-05:00 |
| Real fetch smoke in a temp project (`--clips idle_loop --rig`) | rig 618,624 bytes SHA-256 `1e6c4f98...`; idle_loop 87,216 bytes SHA-256 `fbc6fcdc...`; `provenance.json` + `NOTICE.md` written; temp project removed |
| `python workstream/gypsy.py check` | PASS, capabilities 48, tools 16, project `-` |
| `python workstream/gypsy.py capabilities check` | 48 capability files, 0 errors |
| `python scripts/check_all.py` | 6/6 PASS (records, encoding, links, capabilities, 215 tests, callers) |

The only network calls in this verification were the explicit probe and the temp-project fetch. The test suite uses
no network; downloads are injected or `urllib.request.urlopen` is patched with local fixtures. The toolkit tests are
in [`workstream/tests/test_toolkit.py`](../workstream/tests/test_toolkit.py).
