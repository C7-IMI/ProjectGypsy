# ADR-010 — Phase 2: manifest-driven slice orchestrator

- **Status:** accepted, 2026-10-25 (autonomous Phase-2 build)
- **Scope:** the slice schema, orchestrator, state, artifact ledger and multi-slice task report.
- **Related:** [ADR-003](ADR-003-workstream-architecture.md) (phases and gates), [ADR-009](ADR-009-vertical-slice.md)
  (Phase-1 slice), [PHASE-2-EVIDENCE.md](PHASE-2-EVIDENCE.md) (generated evidence), [DEFERRED.md](../DEFERRED.md).

## Context

Phase 1 proved one slice: game demo, build and capture. The Phase-2 gate is: **a multi-slice task runs unattended
with one report and reproducible artifacts**. Doing that by hand from a prompt is not acceptable evidence: the command
list, dependencies, state and artifact hashes must live in the repository and survive a rerun.

## Decision

1. **Slices are manifests, not prose.** Each slices/<id>.json is a gypsy.slice/v1 object with ordered steps, explicit
   needs, required, timeouts, a project path and declared artifacts.
2. **Two slices form the first task:**
   - phase1 — game.demo -> game.build -> game.capture; artifacts: build/ProjectGypsy.exe,
     artifacts/game/demo.mp4, artifacts/game/frame.png.
   - quality — check_all -> tests -> records; no binary artifacts.
3. **The orchestrator is deterministic and stdlib-only.** It resolves a stable topological order, rejects duplicate
   ids, unknown kinds, missing dependencies and cycles, then executes through a handler registry. Handlers are
   explicit; there is no arbitrary shell, no model call, no hidden retry loop.
4. **State is durable and resumable.** Each slice writes workstream/state/slices/<slice>.json atomically: per-step
   status, timings, errors, manifest SHA-256. --resume skips steps that passed under the same manifest; --force
   starts clean.
5. **Artifacts get a ledger.** After a passing slice, declared artifacts are hashed (SHA-256 + bytes) into
   workstream/state/artifacts/<slice>-<runId>.json; a missing declared artifact fails the slice.
6. **A task is multiple slices with one report.** slices run --all runs the manifests in order, writes
   workstream/state/slices/task-<timestamp>.json, and stops on the first failed slice; the console output is the one
   report.
7. **The CLI is a thin surface:** python workstream/gypsy.py slices list|plan|run|status. The orchestrator is
   importable and testable without Godot; environment handlers are lazy.

## Acceptance criteria

| Gate | Criterion |
| --- | --- |
| Schema | invalid manifests return errors; valid manifests load |
| Ordering | stable topological order; cycles/missing deps rejected |
| Run | a slice runs unattended; required failure skips dependents; result is JSON-safe |
| Resume | a passed step is skipped with matching manifest; --force reruns |
| Artifacts | ledger has SHA-256 and bytes; missing artifact fails |
| Task | phase1 + quality run in one command with one aggregate report |
| Reproducibility | a second task run yields the same artifact hashes |
| Tests | orchestrator tests pass without Godot; full suite passes |

## Out of scope

Arbitrary shell steps, model-driven planning, automatic dependency installation, console/TUI, live editing,
self-extension and distributed workers. Those remain deferred (PG-D15) or later phases.

## Consequences

**Positive:** the Phase-1 evidence becomes a declared, repeatable task; hashes and resume remove "it worked once";
the orchestrator is the seam for future slices without a new bespoke script per task.

**Negative / risks:** manifests are code-adjacent and need review; state files are gitignored so only the report and
committed manifests are durable; a handler registry means new step kinds need code, not just JSON.

## Verification

[PHASE-2-EVIDENCE.md](PHASE-2-EVIDENCE.md) records the actual slices run --all report, hashes, second-run
reproducibility and test output.
