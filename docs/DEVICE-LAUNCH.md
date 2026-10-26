# Android device launch — current gate

**Status: BLOCKED by the host's emulator launch path, not claimed as a device pass.**

## What exists

- build/ProjectGypsy.apk — 28,449,841 B, signed debug arm64 APK; package com.c7imi.projectgypsy.
- Android SDK at %LOCALAPPDATA%\Programs\GameTools\AndroidSdk.
- Emulator 37.2.12 installed.
- System image system-images;android-35;google_apis;x86_64 installed.
- AVDs Gypsy_API35 and Gypsy_API35b created (Pixel 6 profile).
- WHPX is installed and reported usable by emulator-check accel.

## Attempts

    emulator -avd Gypsy_API35b -no-window -gpu swiftshader/off -no-audio -no-snapshot ...
    ERROR | It seems too many emulator instances are running on this machine. Aborting.
    WARNING | QEMU main loop exits abnormally with code 1
    adb devices -> (empty)

The host reports this even after killing every emulator/qemu process and deleting both AVD multiinstance.lock files. A
freshly created AVD shows the same error. No ADB device is registered, so the APK has not been installed or launched.
This is recorded as an environment/host block, not a game failure.

## Retry path

1. Reboot the Windows host (clears the stale emulator multi-instance state) or run in a fresh user session.
2. Verify no emulator/qemu processes and no multiinstance.lock under the AVD.
3. Start:

       & "$env:LOCALAPPDATA\Programs\GameTools\AndroidSdk\emulator\emulator.exe" -avd Gypsy_API35b -no-window -gpu swiftshader_indirect -no-audio -no-snapshot
       & "$env:LOCALAPPDATA\Programs\GameTools\AndroidSdk\platform-tools\adb.exe" wait-for-device

4. Install/launch:

       adb install -r build/ProjectGypsy.apk
       adb shell monkey -p com.c7imi.projectgypsy -c android.intent.category.LAUNCHER 1
       adb exec-out screencap -p > artifacts/android/device.png

5. Capture the screenshot and logcat, then update this file and the records with the real result.

## What is not claimed

No device-launch pass, no mobile performance measurement, no touch/input validation, no release signing. The APK package
and signature checks are separate and do pass.
