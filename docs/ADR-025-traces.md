# ADR-025 — Local state-derived traces

- **Status:** accepted, 2026-10-30.
- **Scope:** hierarchical run/slice/step/toolpack traces from recorded state.
- **Related:** [ADR-021](ADR-021-assets-metrics.md), [IMPROVEMENT-ROADMAP.md](IMPROVEMENT-ROADMAP.md).

## Decision

1. Workstream/traces.py emits gypsy.trace/v1: run traces with nested slice/step or toolpack action spans, deterministic
   IDs, parent IDs, start/end/duration, status, attributes (engine, cache, artifacts, errors) and canonical ordering.
2. It reads task, slice and toolpack state; missing/corrupt state becomes a problem span/error, never an invented
   successful span.
3. It optionally emits a local OTEL-compatible shape, but explicitly does not claim live instrumentation, a collector,
   network export or distributed context propagation.
4. CLI: gypsy traces [--otel] [--write]. API: /api/traces. Dashboard: Insights Run traces card.
5. No external telemetry dependency; this is local observability, not production OTel.

## Evidence

- 61 traces / 191 spans; 53 ok, 8 error, 0 unset; 0 problem traces; 0 problem spans.
- Trace sources include 11 task, 7 slice, 28 toolpack and 15 toolpack-action traces.
- 21 trace tests; full suite after integration to be recorded.

## Limits

- Not live instrumentation; no span events, logs, metrics, resource attributes, sampling or remote export.
- Trace IDs are deterministic local identifiers, not W3C guaranteed random IDs.
- Missing state is empty/problem, not reconstructed; no end-to-end action causality beyond recorded parent links.
