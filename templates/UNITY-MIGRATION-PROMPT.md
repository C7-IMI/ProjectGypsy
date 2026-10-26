# Copy-paste prompt — UltraBlade 2 Unity migration (Stage B)

Replace the two placeholders, then paste this into the new UltraBlade 2 session.

---

You are the coding agent for **UltraBlade 2**. We are migrating the proven ProjectGypsy game/hero to Unity as the
production pipeline. This is a port with real acceptance evidence, not an engine toggle.

- Gypsy Studio checkout: <GYPSY_HOME>
- UltraBlade 2 checkout: <ULTRABLADE_HOME>
- Read first: <GYPSY_HOME>/docs/GYPSY-AGENT-GUIDE.md and <GYPSY_HOME>/docs/UNITY-PORT-INSTRUCTIONS.md
- Also read the target project's AGENTS.md / AGENTS.gypsy.md if present.

Do not modify <GYPSY_HOME>, its records, or its Godot game. Work only in <ULTRABLADE_HOME>. Do not delete or call the
Godot project migrated. Do not commit or push unless the operator asks.

## Goal

Migrate the current game to Unity 6000.6.7f1 as a full production pipeline:

1. Create the Unity project and project.gypsy.json with engine unity, version 6000.6.7f1, target pc (add mobile only
   after Unity Android Build Support is installed).
2. Port the same three-collectible gameplay contract: CharacterController movement, autopilot, crystals, follow camera,
   deterministic demo that prints exactly GYPSY_DEMO_OK collected=3 frames=<n> and exits 0.
3. Port the Wayfarer hero: wayfarer.fbx (23 bones incl. cape_a/b/c, idle/run/reach, Smile blend shape, 512² maps),
   runtime LODGroup/LOD switching, driven Smile, spring cape, visible 1280x720 capture.
4. Build a Windows player, run the demo, capture a frame, and inspect it.
5. Install Unity Android Build Support only if mobile is required; build/launch a signed debug APK and capture
   screenshot + logcat. Do not claim mobile before that.
6. Add a Unity toolpack/slice with marker/capture validators, capability manifests, docs and records.
7. Run Gypsy checks/tests and report exact commands, exit codes, markers, artifact paths, visibility, and limits.

## Current known state

- Unity licence is active; LeftBehind builds/runs on Windows.
- Unity Windows Standalone Build Support is installed.
- **Unity Android Build Support is NOT installed.**
- Unity engine build support is proven through LeftBehind, not a general adapter.
- The hero LOD sources are GLB; Unity does not import glTF natively. Export LOD1/LOD2 to FBX or approve a glTF package.
- Device launch in the current host is blocked by an emulator multi-instance error; use a clean host/device and record
  real evidence.

## Stop conditions

Stop and report if Unity Android is required but missing, the hero import fails, the marker cannot be produced, capture
cannot show the hero, or Gypsy/Unity cannot be found. Never fake a build, marker, capture or device pass.
