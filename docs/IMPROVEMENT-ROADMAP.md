# Gypsy improvement roadmap — research-backed

**Status:** research/recommendations, 2026-10-30. This is not a claim that these features exist. Current verified state:
Unity 6000.6.7f1 is the default for new projects (Stage A), the ProjectGypsy game remains the Godot reference until Stage B,
LeftBehind proves Windows Unity build/demo/capture, the hero pipeline has runtime LOD/Smile/cape systems, and safe
self-extension exists. There are 6 slices, 50 capabilities and 282 tests.

The guidance below is deliberately about the **production system**, not about adding more one-off game features.

## Executive summary — the ten highest-leverage changes

1. **Add a content-addressed action cache and a remote cache.** Gypsy currently has manifest-level resume, not action-level
   cache keys. Cache Godot/Unity/Blender imports, builds, captures and tests by inputs, tool versions, environment,
   platform and command. This is the biggest speed and reproducibility win.
2. **Run independent work in parallel under a real DAG scheduler.** Add parallel groups, worker slots, leases,
   cancellation, retries with backoff, and per-step logs. Sequential toolpack actions and slices leave most of a
   16-core/64 GB machine idle.
3. **Make engine support a generic adapter, not per-proof toolpacks.** Unity support is currently the LeftBehind proof;
   add a generic Unity adapter, Android Build Support detection/install guidance, asset-import validation and a
   platform matrix. The current default cannot yet claim mobile Unity.
4. **Make quality gates executable, not narrative.** Add visual regression, performance budgets, deterministic session
   tests, device/emulator farms, test-impact selection and flaky-test quarantine. Gauntlet and Horde show the shape of
   this for Unreal; GameCI shows the basic CI shape for Unity.
5. **Treat content as a dependency graph.** Add an asset registry and dependency graph, hashes, provenance/licence,
   variant/LOD validation, and import contracts. OpenUSD, MaterialX and OpenColorIO are the mature standards to align
   with for scene composition, materials and colour.
6. **Add a developer portal / golden-path layer.** Backstage's catalog and software templates are a proven model: make
   project creation, ownership, docs, run commands and health visible from one catalog entry. Gypsy has manifests and a
   dashboard, but no catalog or templated onboarding.
7. **Make observability first-class.** Emit OpenTelemetry-style traces, metrics and logs for every run/action; measure
   DORA-style flow (lead time, deployment frequency, failed-deployment recovery, change-failure rate) plus Gypsy-specific
   cache hit rate, queue time and first-run success. Unreal Insights shows how deep game-runtime tracing can go.
8. **Make agent execution safe and reproducible.** Enforce workspace leases/write scopes instead of advisory scopes,
   sandbox subprocesses, record model/prompt/tool versions, support resume and deterministic tool contracts, and add an
   agent evaluation harness. The current team write scopes are only advisory.
9. **Harden the supply chain.** Sign builds/artifacts, generate SBOM/provenance, pin toolchains, scan secrets, enforce
   retention/GC, and fail closed on unverified engine/device/tool states.
10. **Measure end-to-end, not just per-slice.** Add a small set of product/engineering metrics and review them every
    iteration; otherwise improvements become feature accretion.

## What Gypsy already does well

- Project manifest pins engine/version/adapter/targets, with hardware gates.
- Slice/toolpack state and artifact SHA-256 provenance.
- Manifest-level resume (skip passed steps when the manifest is unchanged).
- Safe self-extension with review gate and lockfile.
- A local dashboard and a CLI that remains the source of truth.
- Explicit blocked/untested states instead of fake passes.
- A real hero asset and a second-engine Unity proof.

These are a good base. The main gap is not another feature; it is **throughput, feedback speed, and enforceable quality**.

## Research findings and implications

| Mature pattern | Evidence | What Gypsy should copy |
| --- | --- | --- |
| Remote/action caching | Bazel remote caching; sccache remote storage | Content-addressed action outputs shared across runs/machines; cache keys include inputs and toolchains |
| Build/test automation for games | GameCI Unity Builder/Test Runner | Engine-specific CI actions, test reports and license handling, but behind one Gypsy adapter |
| Remote execution + build farm | Unreal Horde remote execution and build automation | Offload compilation/import/build to workers; queue, retry, leases, analytics |
| Session-based functional tests | Unreal Gauntlet | Multi-process/multi-client sessions, puppeteering, result validation, device matrix |
| Device fleet | Horde mobile/console device manager | Reserve/lease devices, run install/launch/capture/logcat, quarantine unhealthy devices |
| Developer portal and golden paths | Backstage software catalog/templates | Project catalog, ownership, templates and one-command onboarding |
| Scene composition and variants | OpenUSD | Dependency graph, references, variants, LOD/asset composition |
| Material/colour interchange | MaterialX and OpenColorIO | Portable materials and consistent colour management across Blender/Unity/Godot |
| Game runtime tracing | Unreal Insights | Trace capture and analysis for frame time, memory, load and gameplay events |
| Test frameworks | GdUnit4 and GUT | Godot unit/scene tests integrated into CI, with coverage and headless runs |
| Delivery metrics | DORA | Measure flow and recovery, not only test counts |
| Telemetry standard | OpenTelemetry | One trace/metric/log model for CLI, workers, dashboard and engines |
| Large-asset versioning | Git LFS | Keep binaries out of normal Git history; pair with a content store |
| Compiled-artifact cache | sccache | Reuse compilation outputs locally or remotely |

## Detailed recommendations

### 1. Execution engine: action graph, cache, workers

**Problem:** a slice is a coarse ordered list; a toolpack action is a subprocess. Resume only helps when the manifest is
unchanged. A changed asset or code path usually reruns the whole run. One job at a time leaves CPU/RAM unused.

**Change:**
- Model every action as a node: command, cwd, input file hashes, environment, tool version, platform, declared outputs.
- Compute a cache key; store outputs and logs in a local content-addressed store.
- Add a remote cache/worker protocol; keep credentials and artifact transfer explicit.
- Add a DAG scheduler with parallel groups, resource limits, leases, cancellation and retry policy.
- Add cache diagnostics: hit/miss reason, invalidated input, tool-version mismatch.
- Add artifact retention and garbage collection by age/size/run type.

**Acceptance:** a second unchanged run hits the cache and skips build/import/capture; a one-line asset edit reruns only
dependent actions; two independent toolpacks run concurrently; a cancelled run kills its process tree and releases
leases.

### 2. Engine adapters and platform matrix

**Problem:** Unity has a Windows proof (LeftBehind), but no generic adapter, no Android Build Support, and no Unity
asset-import path. The new-project default is Unity while the production pipeline is still becoming Unity-capable.

**Change:**
- Define one engine adapter interface: detect, project-create, import, build, demo, capture, device, profile, clean.
- Add a Unity adapter with Windows and Android targets; install Android Build Support and verify a real device/emulator.
- Add Godot and Unity import matrices for the same golden assets; record per-platform results.
- Add a platform matrix to the project manifest and dashboard; fail closed when a target is unverified.
- Keep the Godot reference until Unity passes the same markers and captures.

**Acceptance:** a new project can be created, built, run and captured on Unity Windows; Android is either verified or
explicitly blocked with the missing module named.

### 3. Quality: visual, performance, sessions, devices

**Problem:** tests prove logic and markers, but not look, feel, frame time, memory, load time, device behaviour or
multi-process sessions.

**Change:**
- Add screenshot capture with fixed resolution/seed/quality and perceptual image diff; store baselines per engine,
  renderer, GPU class and resolution; require explicit approval for baseline changes.
- Add performance budgets (frame p95, memory, load time, draw calls, shader variants) and fail when they regress.
- Add Gauntlet-style session tests: multiple processes, client/server, input replay, quiescence and result checks.
- Add a device/emulator farm with leases, install, launch, screenshot, logcat and crash capture.
- Add flaky-test quarantine and test-impact selection: map changed files/assets to tests.
- Add soak/soak-long runs and deterministic replay for gameplay regressions.

**Acceptance:** a rendering regression fails a visual gate; a 20% frame-time regression fails a budget; a device run
produces screenshot/logcat; a known flaky test is quarantined and reported, not silently green.

### 4. Content pipeline and asset governance

**Problem:** asset scripts and a few validators exist, but no dependency graph, asset registry, variant/LOD contract or
cross-engine material/colour contract.

**Change:**
- Add an asset registry: asset id, source path, hashes, dependencies, importer settings, engine outputs, licence,
  provenance, owner, approval state.
- Adopt or align with OpenUSD for scene composition/variants and MaterialX/OpenColorIO for materials/colour.
- Validate missing references, broken dependencies, LOD/variant completeness, texture budgets, collision coverage and
  platform import settings.
- Use Git LFS or a content store for large binaries; keep source hashes and import reports.
- Make import deterministic: pinned DCC versions, pinned export settings, golden round-trip reimport.

**Acceptance:** changing a source asset invalidates exactly its dependents; a missing LOD/variant or licence field
fails; the same golden asset imports into Godot and Unity with recorded results.

### 5. Developer experience and project catalog

**Problem:** the dashboard is a good custom console, but onboarding and discovery still depend on reading docs. Project
creation, capability discovery, ownership and health are not one coherent surface.

**Change:**
- Add a project catalog (Backstage-style) with owner, engine, targets, capabilities, run history, docs and golden-path
  templates.
- Add templates for new Unity/Godot projects with standard slices, checks, CI and agent instructions.
- Make the dashboard task-oriented: next action, live logs via SSE/WebSocket, error remediation, filters, keyboard
  navigation, deep links, run comparison and artifact diff.
- Keep CLI parity and publish every dashboard action as a copyable command.
- Add a first-run wizard that detects tools/engines/licenses/devices and reports the exact missing prerequisites.

**Acceptance:** a new project can be stood up from one template with one command; a user can identify the next action and
open its logs in one click.

### 6. Agent and team execution

**Problem:** Team write scopes are advisory; agents can overlap and corrupt each other's work. Agent/model/prompt/cost
provenance is incomplete.

**Change:**
- Enforce workspace leases and write scopes at the tool layer; reject conflicting writes rather than warning.
- Sandbox subprocesses and isolate per-run workspaces; make cleanup and resume deterministic.
- Record model, prompt version, tool version, approvals and cost per task.
- Add an agent evaluation suite: task success, evidence correctness, regression rate, cost/latency.
- Add review gates for self-extension and generated content; no self-modifying core.

**Acceptance:** two agents cannot write the same file concurrently without an explicit lease; every run can be replayed
from recorded metadata; an evaluation suite catches a prompt/tool regression.

### 7. Observability and delivery metrics

**Problem:** current state is polling JSON and per-run logs; there is no unified trace/metric model or flow metric.

**Change:**
- Emit OpenTelemetry traces for run → step → action → engine process, with attributes for engine, version, cache hit,
  artifact size and failure class.
- Use Unreal Insights/Godot profiler/engine captures as linked artifacts, not ad-hoc files.
- Measure cache hit rate, build/test duration, queue time, first-run success, flake rate, device pass rate and
  recovery time; add DORA-style flow metrics.
- Add retention/rollups so metrics stay cheap.

**Acceptance:** a slow run can be diagnosed from a trace and cache diagnostics; trends are visible over time.

### 8. Security, supply chain and reliability

**Change:**
- Sign builds and artifacts; generate SBOM and provenance; verify at consumption.
- Pin toolchains and dependencies; lock plugins/extensions; scan secrets and licences.
- Add backup/restore and crash-safe state; corrupt state should fail closed with a recovery path.
- Add network-retry/backoff and offline mode; no hidden downloads during builds.
- Treat extension code as reviewed code, not a sandbox; keep the Job Object containment and document its limits.

**Acceptance:** a tampered artifact/build fails verification; a lost state directory can be rebuilt from the cache/registry;
an offline build either works or reports the exact missing dependency.

### 9. Game-quality features

- Save/load compatibility and migration tests.
- Input remapping and controller hot-plug tests.
- Localization key coverage and font fallback checks.
- Accessibility checks (contrast, subtitles, motion settings) when the interface standard is restored.
- Min-spec GPU/CPU matrix and memory ceilings.
- Crash reporting and automated triage; deterministic replay for bug reports.
- Content budgets (texture, mesh, audio, shader) enforced per platform.

## Prioritized roadmap

### P0 — next 1–2 weeks (high impact, low risk)

1. Action-level cache keys and a local CAS; report hit/miss reasons.
2. Parallel scheduler for independent toolpack actions and slices; per-step logs; cancellation.
3. Dashboard live log streaming and next-action error remediation.
4. Golden-path templates for Unity and Godot projects.
5. Visual baseline + one performance budget on the hero slice.
6. Asset validator for missing dependencies and LOD/variant completeness.
7. Make Unity Android Build Support detection explicit; never show mobile as available without it.

### P1 — next 1–2 months

1. Remote cache and remote workers; artifact store with retention/GC.
2. Generic Unity adapter; Windows + Android; device/emulator farm.
3. Gauntlet-style session tests and deterministic input replay.
4. Asset registry + dependency graph; USD/MaterialX/OCIO alignment.
5. OpenTelemetry traces/metrics + DORA dashboard.
6. Enforced agent leases/write scopes and agent evaluation suite.
7. Signed artifacts/SBOM/provenance.

### P2 — quarter

1. Remote build farm with queueing, scheduler and cost controls.
2. Full multi-engine import matrix and platform matrix.
3. Automated content/art review and render regression at scale.
4. Self-hosted/internal developer portal with catalog, templates and ownership.
5. Agent-generated extension marketplace with review, signing and revocation (not automatic self-modification).

## Metrics to track

- **Flow:** lead time, deployment frequency, failed-deployment recovery time, change-failure rate (DORA).
- **Speed:** median/p95 build, import, test, capture and full-slice time; queue time; cache hit rate.
- **Quality:** flaky rate, escaped defects, visual-diff pass rate, performance-budget pass rate, device pass rate.
- **Scale:** runs per day, concurrent workers, artifact storage, cost per run.
- **Agent:** task success, evidence-correctness, review rejection rate, tokens/cost, time to green.
- **Content:** assets validated/failed, missing dependencies, licence/provenance gaps, import failures by engine.

## Concrete Gypsy changes to start with

- Extend the slice schema with parallel groups, resource class, cache policy and retry policy.
- Extend toolpack actions with input/output declarations and cache-key fields.
- Add a run-level environment fingerprint (OS, engine, SDK, DCC, GPU, driver, Python/Node versions).
- Add a cache state directory with content hashes and eviction metadata.
- Add a worker protocol and a local queue before remote workers.
- Add an error taxonomy: environment, licence, tool missing, asset invalid, build failed, test failed, device failed,
  flaky, cancelled.
- Add a dashboard action that copies the exact failing command and opens the run detail.
- Store visual/performance baselines as versioned artifacts with approval records.
- Add a project catalog entry for every project.gypsy.json.

## Risks and trade-offs

- A content cache can hide non-hermetic dependencies; require cache-key validation and occasional clean builds.
- Remote workers add credential/artifact-transfer risk; use least privilege and signed artifacts.
- Visual/perf baselines are noisy across GPUs/drivers; segment by hardware/renderer and allow explicit recalibration.
- More automation can encourage false confidence; retain human review gates for art, gameplay and release decisions.
- A developer portal can become a second source of truth; keep manifests/CLI canonical and generate the catalog from them.

## Sources

- [GameCI — Introduction](https://game.ci/docs/)
- [GameCI — Unity Builder](https://game.ci/docs/github/builder)
- [GameCI — Unity Test Runner](https://game.ci/docs/github/test-runner)
- [Bazel — Remote Caching](https://bazel.build/remote/caching)
- [Backstage — Software Catalog](https://backstage.io/docs/features/software-catalog/)
- [Backstage — Software Templates](https://backstage.io/docs/features/software-templates/)
- [Unreal Engine — Horde](https://dev.epicgames.com/documentation/en-us/unreal-engine/horde-in-unreal-engine)
- [Unreal Engine — Gauntlet](https://dev.epicgames.com/documentation/en-us/unreal-engine/gauntlet-automation-framework-in-unreal-engine)
- [OpenUSD — Introduction](https://openusd.org/release/intro.html)
- [MaterialX](https://materialx.org/)
- [OpenColorIO](https://opencolorio.org/)
- [Unreal Insights](https://dev.epicgames.com/documentation/en-us/unreal-engine/unreal-insights-in-unreal-engine)
- [GdUnit4](https://github.com/MikeSchulze/gdUnit4)
- [GUT — Godot Unit Test](https://github.com/bitwes/Gut)
- [OpenTelemetry — What is OpenTelemetry?](https://opentelemetry.io/docs/what-is-opentelemetry/)
- [DORA — software delivery performance metrics](https://dora.dev/guides/dora-metrics-four-keys/)
- [Git LFS](https://git-lfs.com/)
- [sccache](https://github.com/mozilla/sccache)
