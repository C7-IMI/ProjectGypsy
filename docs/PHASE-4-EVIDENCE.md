# PHASE-4-EVIDENCE.md — read-only thin console

Recorded 2026-10-26. Phase-4 proof for [ADR-012](ADR-012-thin-console.md). The console is read-only; this file and the
test output are the evidence.

## Gate results

| Gate | Result |
| --- | --- |
| Board | PASS — task-20261026T064601Z: 8/8 steps, 3 artifacts, 79.909 s; phase1/quality/toolpacks rows |
| Preview | PASS — artifacts/game/frame.png: 33,187 bytes, SHA-256 89d0d329..., PNG 1280x720 |
| Diff | PASS — read-only git diff --stat/--name-status; worktree/staged/commit variants |
| No writes | PASS — tree unchanged after board/preview/diff (read-only git only) |
| No separate service | PASS — console is part of the same CLI (gypsy console ...) |
| Tests | PASS — 138 tests OK (40 console tests); no Godot/network required |
| Capabilities | PASS — 39 capability manifests parse |

## Board output (actual)

    task task-20261026T064601Z: PASS (8/8 steps, 3 artifacts, 79.909s)
      phase1: PASS (3/3 steps, 3 artifacts, 12.793s)
      quality: PASS (3/3 steps, 0 artifacts, 21.465s)
      toolpacks: PASS (2/2 steps, 0 artifacts, 45.64s)
    artifacts: 3 declared, 3 present, 0 missing (109225705 bytes)
    approvals: 0 pending - no approval workflow; gates are automated
    state: workstream/state/slices/task-20261026T064601Z.json

## Preview output (actual)

    artifacts/game/frame.png  kind=png  33187 bytes  sha256=89d0d32945894c2b280ca98be9daadd822e692dc6ab78699471efd7b4435864d
      PNG 1280x720

## Commands

    python workstream/gypsy.py console board
    python workstream/gypsy.py console board --json
    python workstream/gypsy.py console preview artifacts/game/frame.png
    python workstream/gypsy.py console diff
    python workstream/gypsy.py console diff --staged
    python workstream/gypsy.py console diff --commit HEAD~2

## Limits

- Text-only preview cannot judge art/audio quality; it reports structure/hash.
- The board shows recorded artifact sizes; preview hashes the live file and does not reconcile against an older ledger.
- Diff omits untracked files; there is no approval workflow (the board says so).
- No live watch mode, GUI, browser, playback or self-extension; live iteration is Phase 5, extension remains deferred.
