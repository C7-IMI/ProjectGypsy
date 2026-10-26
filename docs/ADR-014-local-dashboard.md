# ADR-014 — local GUI dashboard

- **Status:** accepted, 2026-10-26
- **Scope:** the local-only graphical control panel and its four views.
- **Related:** [ADR-012](ADR-012-thin-console.md), [ADR-003](ADR-003-workstream-architecture.md),
  [DASHBOARD.md](DASHBOARD.md), [DEFERRED.md](../DEFERRED.md).

## Context

The user asked for all four mocked control-panel directions: Studio Board as the default, the others as views, all in a
dark theme. The CLI already exposes every action and state. A GUI must not hide the CLI, invent approvals, expose a
remote service, or accept arbitrary commands from a browser.

## Decision

1. **One local app, four tabs.** Studio Board (default), Mission Control, Command Hybrid and Director's Table are
   views over the same state; the selection is remembered and the tab layout is dark-only.
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
7. **The four views map to one state contract:** /api/state (slices, artifacts, gates, phases, machine, metrics,
   commands), /api/artifact (metadata/raw), /api/diff and /api/job.
8. **The game's interface standard remains parked (PG-D4).** This is developer tooling, not the game UI.

## Acceptance criteria

| Gate | Criterion |
| --- | --- |
| Four views | tabs render, Studio Board default, dark-only |
| State | dynamic slices/artifacts/gates from current files |
| Actions | whitelisted, confirmation, token, observable job |
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

[DASHBOARD.md](DASHBOARD.md) has launch/usage and [design/dashboard](../design/dashboard) holds the sources and
screenshots; tests are in workstream/tests/test_dashboard.py.
