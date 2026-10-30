# ADR-021 — Asset registry and state-derived metrics

- **Status:** accepted, 2026-10-30.
- **Scope:** read-only asset inventory/provenance and observability over existing state.
- **Related:** [IMPROVEMENT-ROADMAP.md](IMPROVEMENT-ROADMAP.md), [ADR-019](ADR-019-cache-quality.md),
  [ADR-020](ADR-020-remote-cache.md), [DASHBOARD.md](DASHBOARD.md).

## Context

Gypsy had hashed build artifacts and a project catalog, but no single inventory of source/game assets and no aggregated
view of run, cache and quality health. Both are read-only views over existing data; neither is proof that a build works.

## Decision

1. **Asset registry** (workstream/assets.py): deterministic read-only scan of default roots assets/, game/assets/ and
   unity/LeftBehind/Assets, excluding generated/import/build/cache directories. Records path, root, bytes, SHA-256,
   media kind, modified time, duplicate-content groups and provenance warnings. Media kind is extension-based.
2. **Provenance sidecar** assets/registry/provenance.json (gypsy.asset-provenance/v1): optional per-path licence/source
   records. Missing or malformed provenance is a warning, never a fabricated clearance; the current checkout has no
   sidecar, so all 30 assets report unknown provenance.
3. **Metrics** (workstream/metrics.py): deterministic aggregation of task/slice/toolpack state, cache stats, quality gate
   and latest timestamps into gypsy.metrics/v1. Missing state is empty; corrupt/unexpected files become problems, not
   invented values.
4. **Surfaces:** the assets and metrics CLI commands, /api/assets and /api/metrics, and Insights cards for run metrics and
   asset registry. The Projects view remains the catalog; Assets is not the build Artifacts view.
5. No dependency graph, importer settings, engine outputs or legal clearance are claimed. Those remain roadmap items.

## Evidence

- Asset scan: 30 assets, 9,255,627 bytes, 3 roots; 13 images, 7 models, 10 text; 7 duplicate-content groups (20 files);
  1 warning (no provenance registry); 0 errors; ~0.354 s.
- Metrics: 11 task runs (9 pass, 2 fail), median 26.564 s, p95 276.385 s; 7/7 slices; 89 toolpack actions (83 pass);
  cache 1 hit/7 misses/7 stores, remote 0 errors; quality gate passed; problems [].
- Tests: 22 asset tests + 27 metrics tests; full suite 505 tests OK at implementation time.
- Dashboard: Insights cards show 30 assets / 13 images / 7 models / 1 warning and 11 runs / 9 pass / 2 fail / median.

## Limits

- Registry is extension-based; it does not parse dependency graphs, importer settings or per-engine outputs.
- Provenance is a sidecar warning, not a licence review or legal approval.
- Metrics are state-derived, not live wall-clock or OpenTelemetry traces; no network or engine instrumentation.
- stateDir is echoed as provided; different path spellings produce different documents.
- Dashboard metrics depend on latest state files; a missing state directory shows empty data, never guesses.
