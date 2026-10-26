# ADR-012 — Phase 4: read-only thin console

- **Status:** accepted, 2026-10-26 (autonomous Phase-4 build)
- **Scope:** the terminal console, its read-only contract and the CLI-parity gate.
- **Related:** [ADR-003](ADR-003-workstream-architecture.md) (phase 4), [ADR-010](ADR-010-slice-orchestrator.md),
  [PHASE-4-EVIDENCE.md](PHASE-4-EVIDENCE.md).

## Context

Phases 1-3 give a playable slice, a manifest orchestrator and toolpacks. The Phase-4 gate is a thin console
(task board, preview, diffs, approvals) that adds no capability the CLI lacks. A web UI would collide with the parked
interface addendum and add a server; a curses UI adds terminal state without evidence. The useful thing is a stable,
read-only presentation of state that already exists.

## Decision

1. **Terminal-only, read-only presentation.** workstream/console.py renders three views:
   - board: latest task state or per-slice state; PASS/FAIL, step counts, durations, artifact totals, errors;
   - preview: live artifact size/hash/kind plus PNG dimensions, WAV duration/channels/rate, JSON keys, GLB header;
   - diff: read-only git stat/name-status for worktree, staged or a guarded revision.
2. **No writes, no server, no browser, no curses.** The console never mutates state, artifacts, records or git.
3. **No new capability.** The console is exposed as gypsy console board|preview|diff, i.e. it is part of the same
   CLI; every value is derived from slice state, artifacts or git. There is no separate console daemon.
4. **Approvals are not invented.** No approval workflow exists; the board states "0 pending - no approval workflow;
   gates are automated" rather than pretending a queue.
5. **Failures are presentable.** Missing state, missing artifact, unavailable git and bad revisions return a clear
   message/exit code; they never crash a board.
6. **Preview reports the live hash**, not the ledger hash from a previous run; reconciliation is explicitly a later
   concern, not silently claimed.

## Acceptance criteria

| Gate | Criterion |
| --- | --- |
| Board | renders latest task/slices from real state, no state message otherwise |
| Preview | SHA-256 + type metadata for real artifacts; PNG/WAV/JSON/GLB handled |
| Diff | read-only git stat/name-status; staged/commit variants; no writes |
| No writes | tree unchanged after board/preview/diff |
| CLI parity | commands live in the CLI; no separate service or capability |
| Tests | console tests pass without Godot/network |

## Out of scope

GUI/browser console, live watch mode, approval mutations, artifact ledger-vs-live reconciliation, untracked-file
diff, media playback and rich image preview. Live iteration is Phase 5 and self-extension remains deferred (PG-D15).

## Consequences

**Positive:** one place to read task/artifact/diff state without parsing logs; read-only by construction; no new
interface standard needed; works over SSH/terminal.

**Negative / risks:** text-only preview cannot judge art quality; board trusts recorded sizes; diff omits untracked
files; console is not an approval system.

## Verification

[PHASE-4-EVIDENCE.md](PHASE-4-EVIDENCE.md) records board/preview/diff output, no-write audit and test counts.
