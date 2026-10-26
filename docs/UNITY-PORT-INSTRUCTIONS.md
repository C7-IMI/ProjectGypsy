# Unity migration / port instructions — Stage B for UltraBlade 2

**Use this from the UltraBlade 2 repository/session.** Do not run Stage B in the ProjectGypsy checkout. The current
ProjectGypsy game stays Godot as the legacy/reference implementation. This is a port with explicit acceptance evidence,
not an engine toggle.

## 0. Roles and boundaries

- Source of truth for the current game: the ProjectGypsy checkout at <GYPSY_HOME>.
- Destination: the separate UltraBlade 2 checkout at <ULTRABLADE_HOME>.
- Gypsy Studio CLI: python "<GYPSY_HOME>/workstream/gypsy.py".
- Read <GYPSY_HOME>/docs/GYPSY-AGENT-GUIDE.md before starting.
- Do not modify the ProjectGypsy checkout, its records, or its Unity LeftBehind proof.
- Do not delete the Godot project or call it migrated before the Unity markers/captures pass.

## 1. Preflight

1. Verify Gypsy:

       python "<GYPSY_HOME>/workstream/gypsy.py" version
       python "<GYPSY_HOME>/workstream/gypsy.py" check --project "<ULTRABLADE_HOME>"

2. Inspect Unity:

       "C:/Program Files/Unity 6000.6.7f1/Editor/Unity.exe" -version

   - Licence must be active; LeftBehind proves the current licence.
   - Windows Standalone Build Support is installed.
   - **Android Build Support is NOT installed.** If mobile is in scope, install it through Unity Hub first. Until then,
     Unity mobile is not available and must not be claimed.

3. Snapshot the destination:
   - Git status must be clean or the existing changes must be explicitly owned.
   - Create/keep a project manifest at the destination root.

4. Inventory the source assets to port:
   - Godot game scene/scripts under <GYPSY_HOME>/game/.
   - Hero FBX <GYPSY_HOME>/assets/hero/wayfarer.fbx (23 bones, 3 clips, 512² maps).
   - Hero LOD sources wayfarer_lod1.glb / wayfarer_lod2.glb — Unity does not import glTF natively; export them as FBX
     from Blender or add an approved glTF package. Do not assume Unity can load the GLBs.
   - Textures, art brief, validation report and reference captures.

## 2. Create the Unity project

From the destination:

    python "<GYPSY_HOME>/workstream/gypsy.py" project init       --path "<ULTRABLADE_HOME>"       --engine unity --version 6000.6.7f1 --targets pc

Project init now defaults to Unity/PC when engine and version are omitted, but pass them explicitly so the manifest is
unambiguous.

Then:

    python "<GYPSY_HOME>/workstream/gypsy.py" check --project "<ULTRABLADE_HOME>"

Do not overwrite an existing project.gypsy.json. Add mobile to targets only when the Android module is installed and a
real APK build is planned.

## 3. Port gameplay first

Port the same contract before art:

- a player CharacterController/CharacterBody equivalent with the same movement speed, gravity and autopilot;
- three collectibles and collection state;
- follow camera;
- the deterministic demo path that prints exactly:

      GYPSY_DEMO_OK collected=3 frames=<n>

  and exits 0; failure prints GYPSY_DEMO_FAIL and exits 1;
- preserve the same gameplay acceptance: three collected, bounded frames, headless execution, exit code.

Use the LeftBehind Unity project as the build/demo reference: <GYPSY_HOME>/unity/LeftBehind/ and
<GYPSY_HOME>/toolpacks/leftbehind.unity.json. Do not copy it blindly; its scene and scripts are a minimal second-engine
proof.

## 4. Port the hero

1. Import wayfarer.fbx into Unity; verify:
   - 23 bones incl. cape_a/b/c;
   - clips idle/run/reach;
   - Smile blend shape on the skinned mesh;
   - 512² base/normal/roughness maps.
2. Build a prefab under the player visual. Preserve the CharacterController/collision. Recommended:
   - Animator Controller with Idle/Run/Reach states;
   - SkinnedMeshRenderer + blend shape proxy for Smile;
   - LODGroup with LOD0/1/2 (export LOD1/2 to FBX or add glTF support);
   - C# equivalents of the Godot systems: speed to idle/run, collect to Reach + Smile, distance to LOD, spring cape.
3. Validate visually at the same ~1.9 m scale, feet on ground, forward direction matching the controller.

## 5. Build, demo, capture

Add a Unity Editor build method analogous to BuildLeftBehind.Build, and a Gypsy toolpack/slice with:

- build action: Unity batchmode BuildPipeline.BuildPlayer to Windows player;
- demo action: headless/player run, log artifact, marker validation;
- capture action: windowed run, screenshot/movie artifact, PNG validator.

Required evidence:

    a build success line in the log
    GYPSY_DEMO_OK collected=3 frames=<n>
    a 1280x720 capture with the hero visible

Use a visible window for ScreenCapture; hidden-window capture failed in the LeftBehind work and is recorded there.

## 6. Android/mobile (only after installing the module)

1. Install Unity Android Build Support (SDK/NDK/JDK) via Unity Hub.
2. Add the Android target and build a signed debug APK.
3. Launch on an emulator or device and capture a screenshot plus logcat.
4. Only then claim a mobile pass. If the launch is blocked, record the exact host/device failure; do not fake it.

## 7. Gypsy integration

- Add capability manifests for the verified Unity systems (build/demo/capture/mobile).
- Add a Unity toolpack and slice with validators for the marker and capture.
- Update project.gypsy.json, project docs, AGENTS.md/target AGENTS.gypsy.md, records, and automation.
- Keep the Godot implementation as the reference until Unity passes all acceptance checks. Then make Unity the default
  for this project.

## Acceptance matrix

| Gate | Required evidence |
| --- | --- |
| Project | project.gypsy.json pins Unity 6000.6.7f1/adapter and targets |
| Build | Windows player built by batchmode, build log success |
| Demo | exact GYPSY_DEMO_OK marker, exit 0 |
| Gameplay | 3 collectibles, movement/autopilot, no regression |
| Hero | 23 bones, 3 clips, Smile, maps, LODs, visible capture |
| Capture | 1280x720 frame inspected |
| Mobile | module installed, APK built, launched, screenshot/logcat |
| Records | Gypsy checks pass and evidence is committed |

## Stop conditions

Stop and report the exact block if:

- Unity Android Build Support is absent and mobile is required;
- the hero FBX/LOD import fails;
- the marker cannot be produced;
- capture cannot show the hero;
- Gypsy or Unity cannot be found.

Never substitute “it should work” for a run. Never mark Stage B complete from a passing manifest alone.
