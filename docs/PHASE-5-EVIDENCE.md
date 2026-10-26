# PHASE-5-EVIDENCE.md — mobile, live iteration, performance and second-engine gate

Recorded 2026-10-26. Phase-5 proof for [ADR-013](ADR-013-phase5-mobile-live-perf.md).

## Gate results

| Gate | Result |
| --- | --- |
| Android APK export | PASS — build/ProjectGypsy.apk, 28,305,095 bytes, SHA-256 f48e40d936cdba73434198e63e067b27f737b9bf0e64b18a3095d8f2b2f822fd (this build; debug APK bytes are build-instance/timestamp specific, package/cert stable) |
| APK package | PASS — com.c7imi.projectgypsy, versionName 0.1.0, native-code arm64-v8a |
| APK signature | PASS — CN=Android Debug, cert SHA-256 140c76ffd9cedc7192a80967a1cd47b93b082c9638a1f590f8539fddc559d581 |
| On-device launch | NOT TESTED — no Android device/emulator used; not claimed |
| Live watcher | PASS — 34 tests; real --once demo run 2.726 s, exit 0 |
| Performance | PASS — 3 demos: 2.612/2.602/2.605 s, median 2.605 s, p95 2.605 s, frames=143, GPU render 0.56 ms/frame |
| Budgets | PASS — median <=5 s, p95 <=8 s, GPU <=16.67 ms/frame |
| Second engine | BLOCKED — see below |
| Tests / capabilities | 172 tests; 42 capability manifests |

## Mobile toolchain

- OpenJDK 17.0.20.1 portable under GameTools/Java; Android SDK platform-tools + platforms;android-35 +
  build-tools;35.0.0 under GameTools/AndroidSdk.
- Godot editor settings export/android/android_sdk_path and java_sdk_path set; project icon added; ETC2/ASTC enabled;
  Android preset exports ../build/ProjectGypsy.apk.
- Reproduce: powershell -File scripts/build_android.ps1, or slices run mobile (toolpacks/mobile.android.json).
- The APK is a debug/arm64 package; release signing, Play Store and device launch are out of scope.

## Live iteration

    python workstream/live.py --paths game --once --command demo

Actual output: [live] run 1 (once): ok (2.726s), exit 0. The watcher uses mtime+size, debounces, records runner
exceptions, and is not engine hot reload. Tests cover add/modify/delete, debounce, iteration limits and failures.

## Performance

    python workstream/gypsy.py game bench --runs 3

Actual: median 2.605 s, p95 2.605 s, GPU 0.56 ms/frame, logicPassed=true, renderPassed=true. Evidence:
workstream/state/game-benchmark.json (gitignored). This is headless logic wall time plus movie-maker GPU render time,
not gameplay FPS.

## Second-engine gate (blocked)

| Engine | Evidence | Verdict |
| --- | --- | --- |
| Unity 6000.6.7f1 | batchmode on a minimal project: "No valid Unity Editor license found. Please activate your license." exit 198 | BLOCKED (licence) |
| Unreal Engine 5.8.4 | probe gate: GPU VRAM 4.0 GB below the 8 GB minimum (free D: 60.0 GB meets 60) | BLOCKED (hardware) |
| Flax 1.13 | probe notes: experimental adapter; no headless build/run demonstrated | BLOCKED (no proven path) |

Therefore the ADR-003 Phase-5 gate "same slice runs on two engines" is not met and is recorded, not faked.
Mobile package gate and live/perf gates are met; device launch is unverified.

## Commands

    powershell -File scripts/build_android.ps1
    python workstream/gypsy.py slices run mobile
    python workstream/gypsy.py game bench --runs 3
    python workstream/live.py --paths game --once --command demo
    python -m unittest discover -s workstream/tests

## Limits

- APK not launched on a device/emulator; no Android performance or input validation.
- Debug keystore only; no release signing.
- Watcher is not hot reload; .godot churn can retrigger it.
- Benchmark is prototype-scale and machine-specific.
- Unity/UE5/Flax gates remain blocked; Phase 6 is recorded in PHASE-6-GATE.md.
