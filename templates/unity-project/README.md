# Unity golden-path project template

A lightweight, copyable starting point for a **new** Gypsy Studio project on Unity. New projects default
to Unity 6000.6.7f1 / PC ([ADR-018](../../docs/ADR-018-unity-default.md)), which is why this is the first
of the two golden paths. It is a **template, not a project**: the manifest here is
[project.gypsy.template.json](project.gypsy.template.json), a name the project catalog deliberately
ignores; only a file named exactly `project.gypsy.json` is a project.

## What is proven, and what is not

- Unity 6000.6.7f1 is installed, licensed and proven on Windows by [LeftBehind](../../unity/LeftBehind):
  it builds a Windows player, runs the deterministic three-collectible demo and captures a frame
  ([UNITY-SLICE.md](../../docs/UNITY-SLICE.md)).
- **Unity Android Build Support is not installed.** Do not add a mobile target, build an APK or claim
  mobile until the module is installed and a real build/launch is verified.
- There is no generic Unity adapter and no full Godot parity yet: the hero/art pipeline and the import
  matrix are Godot/Blender-first, and `engine.unity.build` is proven through the LeftBehind toolpack
  rather than as a reusable adapter ([ADR-018](../../docs/ADR-018-unity-default.md)).
- Do not relabel the existing Godot game as Unity and do not claim a feature this template does not
  prove.

## 1. Initialize the project

From the Gypsy checkout, with `<GYPSY_HOME>` replaced by its path:

    python "$GYPSY_HOME\workstream\gypsy.py" project init \
      --path "<PROJECT_DIR>" --engine unity --version 6000.6.7f1 --targets pc

`project init` writes the real `project.gypsy.json`, including the hardware gate of the machine that
ran it; do not replace that file with the template below. It refuses a non-empty directory unless
`--force` is passed, so pass `--force` only for an existing project after checking the installed
engine and version. Then:

    python "$GYPSY_HOME\workstream\gypsy.py" project show --path "<PROJECT_DIR>"
    python "$GYPSY_HOME\workstream\gypsy.py" check --project "<PROJECT_DIR>"

The template manifest documents the fields init writes: [project.gypsy.template.json](project.gypsy.template.json).

## 2. Add the agent instructions

Copy [AGENTS.gypsy.md](AGENTS.gypsy.md) into the new project, replace `<GYPSY_HOME>`, and append it to
the project's `AGENTS.md` (or keep it as `AGENTS.gypsy.md` and reference it from `AGENTS.md`). The
engine-neutral block is [templates/AGENTS.gypsy.md](../AGENTS.gypsy.md); this one adds the Unity pin. The
canonical guide is [docs/GYPSY-AGENT-GUIDE.md](../../docs/GYPSY-AGENT-GUIDE.md).

## 3. Create the Unity project

Create or open a Unity 6000.6.7f1 project in `<PROJECT_DIR>` (Unity Hub or the Editor). Keep the Gypsy
manifest at the project root; Gypsy is the orchestration and evidence layer, not a replacement for the
Unity project. Do not invent a second manifest.

## 4. Recommended slices and toolpacks

These are references in the Gypsy checkout. They are **not** copied into the new project automatically:
a new project does not inherit this repository's slices, toolpacks or game code
([docs/GYPSY-AGENT-GUIDE.md](../../docs/GYPSY-AGENT-GUIDE.md) section 4).

- **Slices:** start from the `quality` pattern ([slices/quality.json](../../slices/quality.json):
  `check_all`, the workstream unit tests and the records guard). Add a demo/build/capture slice only
  after the project has a deterministic demo marker and a build path. The slice runner executes steps
  against the Gypsy checkout root (`--dir` selects the manifests), so a slice written for a new
  project must be verified against that project before it is claimed; until then use
  `gypsy check --project` plus Unity's own build and test commands.
- **Toolpacks:** [toolpacks/leftbehind.unity.json](../../toolpacks/leftbehind.unity.json) is the proven
  Unity Windows-player reference (build, demo and capture with validators); adapt that pattern for the
  new project. `hero.wayfarer`, `art.import.golden`, `audio.musicgen` and `mobile.android` are
  Godot/Blender- or Godot-Android-specific and are not Unity-ready
  ([toolpacks/README.md](../../toolpacks/README.md)).

## 5. Acceptance and verification

- `gypsy check --project <dir>` passes and reports the engine actually installed.
- Any demo claim carries a deterministic marker and its exact command; do not claim playability from a
  screenshot alone.
- Any build claim names a non-empty Windows player; any capture claim names a frame that was read back.
- No Android/mobile claim until Unity Android Build Support is installed and a build and launch are
  verified.
- The project's own records are updated with the computed version; never write a pass without evidence.
- The project catalog lists the project with health `ok`:

      python "$GYPSY_HOME\workstream\catalog.py" --root "<PARENT_DIR>"
      python "$GYPSY_HOME\workstream\catalog.py" --root "<PARENT_DIR>" --validate

## 6. Related

- [ADR-018](../../docs/ADR-018-unity-default.md) - Unity is the default for new projects.
- [UNITY-PORT-INSTRUCTIONS.md](../../docs/UNITY-PORT-INSTRUCTIONS.md) - the Stage B UltraBlade 2 port.
- [UNITY-SLICE.md](../../docs/UNITY-SLICE.md) - the LeftBehind build/demo/capture evidence.
- [workstream/catalog.py](../../workstream/catalog.py) - the project catalog used above.
