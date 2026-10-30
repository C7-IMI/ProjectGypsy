# ADR-023 — Explicit asset dependency graph and byte budgets

- **Status:** accepted, 2026-10-30.
- **Scope:** declared asset-to-asset dependencies, graph validation and per-media byte budgets.
- **Related:** [ADR-021](ADR-021-assets-metrics.md), [ADR-017](ADR-017-hero-character-pipeline.md),
  [IMPROVEMENT-ROADMAP.md](IMPROVEMENT-ROADMAP.md).

## Decision

1. Assets/registry/dependencies.json (gypsy.asset-dependencies/v1) declares explicit nodes and edges with a
   human-readable basis. Only declared edges are used; Gypsy does not infer importer or engine dependencies.
2. The graph builder (workstream/asset_graph.py) joins the dependency sidecar to the asset registry, validates
   unknown/missing nodes, self-edges and cycles, and computes deterministic roots, leaves and topological layers.
3. Per-media byte budgets come from the sidecar budgets object (or explicit caller budgets). An unconfigured budget is
   **not-configured**, not a pass; a configured exceeded budget is a finding.
4. The payload is gypsy.asset-graph/v1, JSON-safe and atomically writable. CLI: asset-graph. API: /api/asset-graph.
   Dashboard: Insights Asset graph card.
5. The real hero sidecar records only derivations that are documented: base GLB to LOD1/LOD2 and the FBX export, with
   the generator/ADR basis. Other assets are nodes without invented edges.

## Evidence

- 31 nodes, 3 declared edges, 28 roots, 30 leaves, 2 layers, 0 cycles, 0 unlayered.
- Budgets (sidecar): image 2,810,207 / 10,485,760; model 6,379,508 / 10,485,760; audio 0; text 70,643 / 1,048,576;
  binary 0; status ok, no findings.
- 25 graph tests pass; full suite 554 tests at integration time (current count will grow).
- Dashboard card/API read the same graph; no guessed edges.

## Limits

- No importer/engine output graph, no per-file budgets, no automatic GLB/FBX dependency parsing.
- The graph is only as good as the sidecar; unknown nodes are findings, not silently ignored.
- Budgets are byte totals per media kind, not texture resolution, draw-call, memory or licence budgets.
- A clean graph does not prove a build or legal clearance.
