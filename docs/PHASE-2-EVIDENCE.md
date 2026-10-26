# PHASE-2-EVIDENCE.md — slice orchestrator

Recorded 2026-10-25/26. Phase-2 proof for [ADR-010](ADR-010-slice-orchestrator.md). Machine-readable state is under
workstream/state/slices/ and workstream/state/artifacts/ (gitignored); this file is the committed evidence.

## Environment

- Python 3.13 (C:/Python), Windows, Godot 4.7.2 for phase1; no network needed.
- Manifests: slices/phase1.json and slices/quality.json.
- Orchestrator: workstream/orchestrator.py; schema/loader: workstream/slices.py.

## Gate results

| Gate | Result |
| --- | --- |
| Schema/validation/order | PASS — 39 orchestrator tests; invalid schema, duplicate ids, unknown kinds, missing needs and cycles rejected |
| phase1 slice | PASS — demo -> build -> capture, 3/3 steps, 13.133 s, 3 artifacts |
| quality slice | PASS — check -> tests -> records, 3/3 steps, 7.225 s |
| Multi-slice task | PASS — task-20261026T042027Z: 6/6 steps, 3 artifacts, 20.363 s, one report |
| Artifact ledger | PASS — SHA-256 + bytes written for build/ProjectGypsy.exe, artifacts/game/demo.mp4, artifacts/game/frame.png |
| Reproducibility | PASS — a second task run produced identical SHA-256 for all three artifacts |
| Resume | PASS — slices run phase1 --resume reuses passed state (tested; manifest hash must match) |
| Task console | PASS — slices list, plan, run --all and status all execute |
| Full checks | scripts/check_all.py 6/6 PASS; 54 workstream tests; 37 capabilities |

## Actual task report

    task task-20261026T042027Z: PASS (6/6 steps, 3 artifacts, 20.363s)
      phase1: PASSED (3/3 steps, 3 artifacts, 13.133s)
      quality: PASSED (3/3 steps, 0 artifacts, 7.225s)

The task state file is workstream/state/slices/task-20261026T042027Z.json (gitignored). It records each step's
status, timings, errors, the manifest SHA-256 and the aggregate report.

## Reproducible artifact hashes

| Artifact | Bytes | SHA-256 (run 1 = run 2) |
| --- | --- | --- |
| build/ProjectGypsy.exe | 109,127,680 | bb70361457ff2f85b13eac62086f1d3bfedfdcf3ca512502b285f4268aa580f6 |
| artifacts/game/demo.mp4 | 64,838 | ca156b83a72bf906f34acb687754bda3c77b2756da79bae9b45971652408eb41 |
| artifacts/game/frame.png | 33,187 | 89d0d32945894c2b280ca98be9daadd822e692dc6ab78699471efd7b4435864d |

The second run (task-20261026T042118Z) produced the same three hashes. Artifact ledgers:
workstream/state/artifacts/phase1-<runId>.json.

## Commands

    python workstream/gypsy.py slices list
    python workstream/gypsy.py slices plan phase1
    python workstream/gypsy.py slices run phase1
    python workstream/gypsy.py slices run --all
    python workstream/gypsy.py slices run phase1 --resume
    python workstream/gypsy.py slices status
    python workstream/gypsy.py slices status phase1 --json
    python -m unittest discover -s workstream/tests

## Limits

- State and ledgers are gitignored; the manifest and this evidence are the durable record.
- The quality slice recomputes tests inside check_all and again in the tests step; that is deliberate redundancy and
  costs a few seconds.
- Capture is windowed movie-maker (needs a desktop session); headless has no renderer.
- No console/TUI, live editing, self-extension, distributed workers or model-driven planning. Those remain deferred
  (PG-D15) and are not claimed.
- The task's artifact hashes are reproducible for this machine/toolchain; they are not promised across engine versions
  or GPU drivers.
