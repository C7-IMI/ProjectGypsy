# Android device launch — verified on emulator

**Status: PASS on the Android emulator; physical-device launch is still untested.**

This supersedes the earlier host-block record. The stale emulator multi-instance state was cleared, `Gypsy_API35b`
booted, the signed APK installed, the activity launched, the game rendered, and a screenshot/logcat were captured.

## Evidence

- [DEVICE-EVIDENCE.json](DEVICE-EVIDENCE.json) — machine-readable summary, commands, hashes, limits.
- [evidence/device-game.png](evidence/device-game.png) — rendered game screenshot, 2400×1080, SHA-256
  `9ACEC7BADC49F9A2F915F0FAF4D489053C187D304050E0A2233D94F8176F5CD3`.
- Raw artifacts (gitignored): `artifacts/device/` including SUMMARY.json, screenshot, logcat, boot/teardown logs.
- APK: 28,449,841 B, SHA-256 `AFCC1978057FF6A7D489A5CC50E26367A7E5A18BEB1981E30A7D659B8DA8C7BB`,
  package com.c7imi.projectgypsy, versionName 0.1.0, arm64-v8a.

## Real run

- AVD: `Gypsy_API35b` (Pixel 6 profile, API 35, x86_64, Android 15, 1080×2400).
- Host: Windows 10.0.26300, emulator 37.2.12.0, ADB 1.0.41, WHPX usable.
- Boot with host GPU: 36,013 ms; ADB device online.
- Install: `adb install -r build/ProjectGypsy.apk` → **Success**.
- Launch: `adb shell am start -W -n com.c7imi.projectgypsy/com.godot.game.GodotAppLauncher`
  → `Status: ok`, cold launch 8,513 ms, app PID 1545.
- Renderer: OpenGL ES 3.1 via Android Emulator, NVIDIA T600 host GPU.
- Scene log: `OnGodotSetupCompleted`, `HERO_VISUAL ready clips=["idle","reach","run"] missing=[]`,
  `OnGodotMainLoopStarted`; 0 Godot errors, 0 fatal exceptions in the final logcat.
- Teardown: emulator killed; no adb/emulator/qemu processes or AVD lock entries left.

## Block encountered and worked around

With `-gpu swiftshader_indirect`, the emulator booted and the app launched but rendered black:

    E/godot: ERROR: SceneShaderGLES3: Program linking failed:
    Fragment shader active uniforms exceed GL_MAX_FRAGMENT_UNIFORM_VECTORS (261)

Re-running the same build with emulator `-gpu host` rendered correctly. This is a host-renderer limitation, not a
game/build change. The black frame is retained as failure evidence; it is not counted as a pass.

## What is still not claimed

- Physical Android device launch.
- Touch, input, rotation, audio, suspend/resume and performance validation on device.
- Release signing / Play Store delivery.
- The APK is debug-signed; the emulator used ARM translation for an arm64-only APK.

## Reproduce

    powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build_android.ps1
    & "$env:LOCALAPPDATA\Programs\GameTools\AndroidSdk\emulator\emulator.exe" -avd Gypsy_API35b -no-window -gpu host -no-audio -no-snapshot -no-boot-anim -no-metrics -port 5554
    adb wait-for-device
    adb install -r build/ProjectGypsy.apk
    adb shell am start -W -n com.c7imi.projectgypsy/com.godot.game.GodotAppLauncher
    adb exec-out screencap -p > artifacts/device/screenshot-device-game.png
