# ADR-013 — Phase 5: mobile, live iteration and performance; second-engine gate

- **Status:** accepted, 2026-10-26 (autonomous Phase-5 build; mobile/live/perf proven, second engine blocked)
- **Scope:** Android package gate, live watcher, performance baseline, and the second-engine/Phase-6 gate.
- **Related:** [ADR-003](ADR-003-workstream-architecture.md) (phase 5), [ADR-009](ADR-009-vertical-slice.md),
  [ADR-010](ADR-010-slice-orchestrator.md), [ADR-011](ADR-011-toolpacks.md), [PHASE-5-EVIDENCE.md](PHASE-5-EVIDENCE.md),
  [PHASE-6-GATE.md](PHASE-6-GATE.md).

## Context

Phase 5 asks for live iteration, mobile export and a second engine. The machine has Godot 4.7.2 with Android export
templates, but no Android SDK/JDK at the start; Unity's licence is now proven (batchmode smoke); UE5 fails its VRAM gate; Flax has no
proven headless path. The honest outcome must distinguish a proven mobile package from an unverified device launch and a
blocked second engine.

## Decision

1. **Mobile gate = build/package/signature, not device launch.** Install portable OpenJDK 17 and Android SDK 35
   (build-tools 35.0.0), add an Android export preset and project icon, enable ETC2/ASTC, export a debug APK with a local
   debug keystore, then verify package id, native ABI and signature with aapt2/apksigner. On-device launch is recorded as
   not tested because no device/emulator was used.
2. **Reproducible Android path:** scripts/build_android.ps1 and toolpacks/mobile.android.json; slices/mobile.json runs it
   through the orchestrator; capability engine.godot.mobile is partial.
3. **Live iteration is a watcher, not hot reload:** workstream/live.py snapshots paths, debounces, and reruns demo/verify
   on changes; it reports runner failures and never edits files. It is explicitly mtime+size only.
4. **Performance baseline has declared budgets:** three headless demos, median <= 5 s, p95 <= 8 s, frames=143 each, plus
   a windowed movie-maker capture with GPU render <= 16.67 ms/frame. The result is a baseline, not a promise across
   hardware.
5. **Second engine is not faked:** Unity licence is now proven via batchmode smoke, but no Unity slice exists; UE5
   fails the 8 GB VRAM gate (4 GB actual); Flax has no demonstrated headless build/run. The Phase-5 gate "same slice on
   two engines" is therefore blocked, while the mobile package gate and live/perf work pass.
6. **Phase 6 remains gated:** the UE5 adapter is not built because the hardware gate fails; it needs a machine that
   meets the gate or a remote build.

## Acceptance criteria

| Gate | Result |
| --- | --- |
| Android export | PASS — signed debug APK, package com.c7imi.projectgypsy, arm64-v8a |
| APK package check | PASS — aapt2 badging + apksigner certificate |
| On-device launch | NOT TESTED — no device/emulator |
| Live watcher | PASS — change detection/debounce/runner tests; real --once demo run 2.726 s |
| Performance | PASS — median 2.605 s, p95 2.605 s, GPU 0.56 ms/frame, frames=143 |
| Second engine | BLOCKED — Unity licence 198; UE5 VRAM gate; Flax no headless |
| Phase 6 UE5 | BLOCKED — hardware gate |

## Out of scope

Android release signing/Play Store, emulator/device performance, iOS, hot reload, engine port, UE5 adapter on this
hardware, Unity activation, and mobile UI/input design (interface standard remains parked).

## Consequences

**Positive:** the slice now packages for Android with real signature/package evidence; the fast loop has a deterministic
watcher; performance has a baseline and budgets; blocked gates are recorded with exact evidence.

**Negative / risks:** APK is debug/arm64 only and not launched; watcher is not hot reload and can retrigger on .godot
churn; benchmark is prototype-scale; second-engine gate remains unmet; mobile adds a target but not a tested product.

## Verification

[PHASE-5-EVIDENCE.md](PHASE-5-EVIDENCE.md) and [PHASE-6-GATE.md](PHASE-6-GATE.md) record the actual outputs.
