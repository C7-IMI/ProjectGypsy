# ADR-019 — Action cache, opt-in parallel execution, quality gates and project catalog

- **Status:** accepted, 2026-10-30.
- **Scope:** workstream execution, dashboard, quality evidence and project discovery.
- **Related:** [IMPROVEMENT-ROADMAP.md](IMPROVEMENT-ROADMAP.md), [ADR-010](ADR-010-slice-orchestrator.md),
  [ADR-011](ADR-011-toolpacks.md), [ADR-014](ADR-014-local-dashboard.md), [DASHBOARD.md](DASHBOARD.md).

## Context

The research roadmap identified four P0 gaps: no action-level cache, coarse sequential execution, no executable
visual/performance gate, and no catalog/onboarding layer. The workstream already had hashed artifacts and
manifest-level resume, but a changed input could rerun an entire slice and the cache was not reusable.

## Decision

1. **Content-addressed local action cache** in workstream/cache.py, under workstream/state/cache. It is opt-in: a step or
   action must declare a cache object with explicit repo-relative inputs, exact artifacts and optional tool versions.
   The key includes identity, argv/args, cwd, platform, declared inputs and tool versions. Only passing actions are
   stored. A hit restores artifacts atomically and skips the command; toolpack hits re-run validators. Failures and
   timeouts are never cached. CLI: cache stats|list|clear, plus --force and --no-cache.
2. **Opt-in bounded parallel execution** for independent slices/actions, 1–8 workers, deterministic result ordering,
   pending-only cancellation and task-level state. Default remains sequential (1 worker).
3. **Executable quality gates**: visual regression against a tracked baseline (Pillow, fail-closed on missing
   dependency/dimension mismatch) and explicit performance budgets from the real benchmark. Wired as the opt-in
   visual slice/toolpack. Baseline updates are deliberate.
4. **Project catalog**: read-only discovery of project.gypsy.json with health, duplicates and optional state; golden-path
   Unity/Godot templates. The catalog is manifest health, not engine/build health.
5. **Dashboard UX**: Insights view, honest empty states, live logs via SSE with polling fallback, actionable failures and
   cache/scheduler cards. It remains local-only with the existing token/Origin/whitelist/CSP controls.
6. **Evidence, not claims**: emulator launch and Unity hero import are tracked with real reports and screenshots; physical
   device and generic Unity import remain explicitly untested.

## Consequences

**Positive:** repeated validation is cached (verified 0.0 s hit vs 0.188 s miss), independent work can be parallelized,
visual/perf regressions fail closed, and project discovery/onboarding is not hand-maintained.

**Limits:** cache is opt-in and only stores exact repo-relative artifacts; parallel assumes independent work and
cancellation does not kill already-running processes; visual baselines are machine/renderer-sensitive; catalog health is
manifest-only; the emulator pass is not a physical-device pass.

## Evidence

- cache and parallel tests: workstream/tests/test_cache.py, test_orchestrator.py, test_toolpacks.py.
- quality: workstream/tests/test_quality.py, toolpacks/quality.visual.json, slices/visual.json,
  assets/test/baselines/game-frame.png, workstream/state/quality/gate.json.
- catalog/templates: workstream/catalog.py, workstream/tests/test_catalog.py, templates/unity-project/,
  templates/godot-project/.
- dashboard: workstream/tests/test_dashboard.py, design/dashboard-v2/live-overview.png, live-insights.png.
- emulator: docs/DEVICE-LAUNCH.md, docs/DEVICE-EVIDENCE.json, docs/evidence/device-game.png.
- Unity import: docs/evidence/unity-hero-import-report.json, scripts/unity_hero_import.ps1.
