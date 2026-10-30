# Workstream — Gypsy Studio CLI (Phase 0-5)

The Gypsy Studio harness described in [docs/ADR-003-workstream-architecture.md](../docs/ADR-003-workstream-architecture.md):
engine/tool detection, manifests and checks (Phase 0), a playable Godot slice (Phase 1), a manifest-driven orchestrator
(Phase 2), toolpacks (Phase 3), a read-only console (Phase 4), and live/performance/mobile gates (Phase 5).

## Hero pipeline

The first hero asset and pipeline are reproducible:

    python workstream/gypsy.py toolpacks run hero.wayfarer
    python workstream/gypsy.py slices run hero

See `docs/ART-DIRECTION.md`, `docs/ADR-017-hero-character-pipeline.md`, `assets/hero/` and `scripts/hero/`.

## Extensions

Safe self-extension lives in `extensions/` and is reviewed/registered through the CLI:

    python workstream/gypsy.py extension list|show|validate|test|register|disable|remove|run|reload

See `extensions/README.md` and [ADR-016](../docs/ADR-016-self-extension.md). The core is not self-modified.

## Commands

```text
python workstream/gypsy.py engines probe [--json]          # detect engines, hardware gates, stale registry entries
python workstream/gypsy.py engines smoke godot [--json]    # headless Godot project boots and exits 0
python workstream/gypsy.py tools probe [--json]            # verify the installed GameTools manifest
python workstream/gypsy.py capabilities list|check [--json]
python workstream/gypsy.py toolkit list|show|probe|capabilities [--json]
python workstream/gypsy.py toolkit actionforge catalog [--json]
python workstream/gypsy.py toolkit actionforge fetch --project <dir> --clips idle_loop,walk_loop --rig
python workstream/gypsy.py project init --path <dir>              # default: Unity 6000.6.7f1 / PC
python workstream/gypsy.py project init --path game --engine godot --version 4.7.2 --targets pc  # legacy Godot
python workstream/gypsy.py project show [--path game]
python workstream/gypsy.py check [--project .] [--json]
python workstream/gypsy.py game demo|build|capture|verify [--path game]
python workstream/gypsy.py slices list|plan|run|status [--all] [--resume] [--force] [--parallel N] [--no-cache]
python workstream/gypsy.py toolpacks list|check|run [--action] [--parallel N] [--force] [--no-cache]
python workstream/gypsy.py cache stats|list|clear [--json] [--yes]
python workstream/gypsy.py cache serve [--host 127.0.0.1] [--port 8767] [--root DIR]
python workstream/gypsy.py cache remote [--json]
python workstream/gypsy.py assets [--root DIR] [--registry FILE] [--write] [--json]
python workstream/gypsy.py metrics [--write] [--json]
python workstream/gypsy.py provenance sign ARTIFACT... [--write FILE] [--state-dir DIR]
python workstream/gypsy.py provenance verify FILE [--state-dir DIR]
python workstream/gypsy.py provenance sbom [--write FILE]
python workstream/gypsy.py cache serve [--host 127.0.0.1] [--port 8767] [--root DIR]
python workstream/gypsy.py cache remote [--url URL] [--json]
python workstream/gypsy.py catalog [--root DIR] [--json] [--save-state]
python workstream/gypsy.py console board|preview|diff [--json]
python workstream/gypsy.py game bench [--runs 3]
python workstream/gypsy.py dashboard [--port 8765] [--no-open]
python workstream/live.py --paths game --once --command demo
```

## Remote action cache (loopback, opt-in)

The local content-addressed cache stays primary. A remote HTTP cache can act as a fallback
source on a local miss and a best-effort push target on a successful store. It is loopback-only
by default and every cache endpoint requires a bearer token.

```text
# server: the token comes from the environment, never from argv or the command line
$env:GYPSY_REMOTE_CACHE_TOKEN = "<long random token>"
python workstream/gypsy.py cache serve --port 8767

# client: enable the remote for slices/toolpacks/extension runs in this shell
$env:GYPSY_REMOTE_CACHE_URL = "http://127.0.0.1:8767"
$env:GYPSY_REMOTE_CACHE_TOKEN = "<same token>"
python workstream/gypsy.py cache remote --json   # reachable/authenticated status, no token echoed
python workstream/gypsy.py cache stats --json    # local + remote counters
```

- Local first: on a local miss the client fetches the entry, verifies every blob by SHA-256,
  materialises them into the local cache, then restores normally. Successful local stores are
  pushed blob-first, then the entry. Remote failures are counted (`remoteHits`, `remoteStores`,
  `remoteErrors`, `lastError`) and never fail a run.
- Server: stdlib ThreadingHTTPServer on loopback only (a non-loopback bind is refused); bearer
  token required on every `/v1/` endpoint, with `/healthz` as unauthenticated liveness only.
  Entry and blob ids are 64 lowercase hex; bodies are bounded (entry 1 MiB, blob 32 MiB by
  default), Content-Length is required, chunked bodies are refused; blob PUT must match its
  SHA-256 and GET re-verifies the stored bytes. Errors are small JSON documents with no secrets
  or stack traces. There is no shell, no arbitrary command and no path traversal.
- Limits: no TLS, no multi-user authorisation, no remote deletion or eviction; this is a trusted
  loopback development cache, not an internet service. `cache clear` clears the local cache only.
- Explicit opt-in: both environment variables must be set (or an ActionCache is given a client);
  otherwise caching is exactly local-only and makes no network calls.
Run the tests:

```text
python -m unittest discover -s workstream/tests -v
```

## What is real

- Engine registry by binary probe, not registry metadata; hardware gate; Unity licence presence; Godot export-template
  detection; UE5 stale-registry reporting.
- Project manifest pinning engine/version/adapter/targets and refusing mismatches or non-empty directories.
- Capability manifests with schema validation.
- Tool manifest verification.
- Godot headless smoke test (the reference adapter).
- Phase-1 game adapter: headless demo, Windows export, exported-binary demo, windowed movie capture.
- Phase-2 orchestrator: gypsy.slice/v1 manifests (`slices/`), ordered/dependent steps, resumable state, artifact
  SHA-256 ledger, multi-slice task report, opt-in parallel scheduling and a content-addressed action cache
  (`cache.py`, `gypsy cache stats|list|clear|serve|remote`). An opt-in loopback HTTP
  remote cache (`remote_cache.py`, bearer token, SHA-256 verified both ways, bounded bodies) can share
  entry/blobs between isolated caches without weakening the local-only default.
- Phase-3 toolpacks: gypsy.toolpack/v1 manifests (`toolpacks/`), explicit argv actions, file/json/text/WAV/PNG/GLB
  validators, artifact hashes and provenance, opt-in action caching and bounded parallel actions; real packs for golden
  Blender->Godot import, MusicGen audio, Android APK and visual/performance quality gates.
- Reusable toolkit registry (`toolkit.py`, `toolkits/`): validated plugins, offline list/show/capabilities/catalog, and
  the ActionForge adapter (`toolkit actionforge fetch`) which fetches CC0 rig/animation GLBs with GLB validation,
  project-root confinement, atomic writes, SHA-256 provenance and `NOTICE.md` ([ADR-015](../docs/ADR-015-actionforge-toolkit.md)).
- Phase-5 live watcher (mtime/debounce, no hot reload), performance baseline with budgets, mobile package gate and a
  verified emulator launch (physical device still untested).
- Phase-4 console: read-only terminal board, artifact preview and git diff; no writes, no server, no new capability.
- Dashboard: Overview/Insights/Projects/Slices/Artifacts/Runs/Mission/Commands/Review, live logs via SSE with polling
  fallback, cache/scheduler cards with honest empty states, and actionable failures.
- Project catalog: read-only discovery of `project.gypsy.json` manifests with health, duplicate detection and an optional
  state file; golden-path Unity/Godot templates under `templates/`.
- Asset registry: read-only hashed inventory under `assets/`, `game/assets/` and `unity/LeftBehind/Assets`, with
  duplicate-content groups and provenance warnings (`workstream/assets.py`, `gypsy assets`).
- Metrics: state-derived task/slice/toolpack/cache/quality aggregates (`workstream/metrics.py`, `gypsy metrics`,
  `/api/metrics`), surfaced as Insights cards; not live OpenTelemetry.
- Provenance: HMAC-SHA256 signed artifact manifests and a deterministic SBOM (`workstream/provenance.py`,
  `gypsy provenance sign|verify|sbom`); local integrity, not PKI/code signing.

## What is not built yet

Generic Unity adapter/mobile parity, UE5 hardware, Flax headless, true hot reload and a physical Android device pass
remain open. Animation authoring/retargeting/import and toolkits beyond ActionForge are not automated. The remote cache
has no TLS, multi-user authorisation, remote eviction, remote deletion or remote execution/worker fleet. Those are
registered as deferred or external gates (DEFERRED.md) rather than claimed. See
[docs/ADR-003-workstream-architecture.md](../docs/ADR-003-workstream-architecture.md) for the phase plan.