# ADR-014 — local GUI dashboard

- **Status:** accepted, 2026-10-26; **amended 2026-10-26** (operations console default; classic four views preserved)
- **Scope:** the local-only graphical control panel: operations console and classic views.
- **Related:** [ADR-012](ADR-012-thin-console.md), [ADR-003](ADR-003-workstream-architecture.md),
  [DASHBOARD.md](DASHBOARD.md), [DEFERRED.md](../DEFERRED.md).

## Context

The user asked for all four mocked control-panel directions: Studio Board as the default, the others as views, all in a
dark theme. The CLI already exposes every action and state. A GUI must not hide the CLI, invent approvals, expose a
remote service, or accept arbitrary commands from a browser.

## Decision

1. **One local app, operations console default, classic views preserved.** The default `/` is an Overview with a
   run-detail drill-down. Studio Board, Mission Control, Command Hybrid and Director's Table remain at `/classic` as
   views over the same state; the tab selection is remembered and the app is dark-only.
2. **Localhost only.** workstream/dashboard.py binds 127.0.0.1 (default 8765), serves no external assets, sets CSP and
   anti-framing headers, and is started by python workstream/gypsy.py dashboard.
3. **Fixed command whitelist.** Actions are an enumerated map of argv lists (no shell string, no arbitrary argv from the
   browser); every action shows its command before running and writes state through the existing CLI.
4. **Token-protected mutations.** The HTML carries a per-process random token; POST /api/run requires it and a
   localhost Origin. Reads are state/artifacts/diff only.
5. **Read-only until an explicit action.** Board, gates, hashes, previews and logs never mutate the tree. There is no
   approval queue; the gate panel says so.
6. **Jobs are observable.** One action at a time; output is streamed by polling /api/job and clipped; completion
   refreshes state.
7. **One state contract:** /api/state (slices, artifacts, gates, phases, machine, metrics, commands, runs),
   /api/runs and /api/run?id= (run detail), /api/artifact (metadata/raw), /api/diff and /api/job.
8. **The game's interface standard remains parked (PG-D4).** This is developer tooling, not the game UI.

## Acceptance criteria

| Gate | Criterion |
| --- | --- |
| Views | overview is default; run detail opens a run; all four classic views render at /classic; dark-only |
| State | dynamic slices/artifacts/gates/runs from current files |
| Actions | whitelisted, confirmation, token, observable job; retries map to real commands |
| Read-only | no writes from board/preview/refresh |
| Safety | localhost bind, CSP, traversal rejection, no shell |
| Tests | dashboard tests pass without Godot; full suite passes |

## Out of scope

Remote/multi-user access, authentication beyond the local token, Electron/Tauri packaging, game UI, approval workflow,
arbitrary command runner, mobile layout perfection.

## Consequences

**Positive:** the system is operable visually without hiding commands; four views share one contract; actions are
auditable; the app can run over SSH port-forward or a local browser.

**Negative / risks:** browser UI adds a moving part; a running job blocks another; state/artifact preview can be stale
between polls; the token is per-process and not a multi-user security model.

## Verification

[DASHBOARD.md](DASHBOARD.md) has launch/usage. [design/dashboard-v2](../design/dashboard-v2) holds the default
operations console sources/screenshots; [design/dashboard](../design/dashboard) holds the classic four views; tests are
in workstream/tests/test_dashboard.py.
