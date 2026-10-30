# Godot golden-path project template

A lightweight, copyable starting point for a **new** Gypsy Studio project that explicitly chooses
Godot 4.7.2 / PC. Godot is the complete legacy/reference pipeline ([ADR-009](../../docs/ADR-009-vertical-slice.md))
but it is **not** the default for new projects: new projects default to Unity 6000.6.7f1 / PC
([ADR-018](../../docs/ADR-018-unity-default.md)) unless the operator chooses Godot and the choice is
recorded in `project.gypsy.json`. This template records that explicit choice.

It is a **template, not a project**: the manifest here is
[project.gypsy.template.json](project.gypsy.template.json), a name the project catalog deliberately
ignores; only a file named exactly `project.gypsy.json` is a project.

## What is proven, and what is not

- Godot 4.7.2 is installed and proven here: the deterministic headless demo marker, a Windows export
  and a windowed movie-maker capture are recorded in
  [PHASE-1-EVIDENCE.md](../../docs/PHASE-1-EVIDENCE.md). Headless has no renderer, so a capture needs a
  desktop session and is evidence, not a quality claim.
- The signed Android debug APK is package-verified, but **on-device launch is untested**
  ([DEVICE-LAUNCH.md](../../docs/DEVICE-LAUNCH.md)); do not claim a device pass.
- The hero character pipeline and the Blender import matrix are Godot/Blender-first
  ([ADR-017](../../docs/ADR-017-hero-character-pipeline.md),
  [ADR-006](../../docs/ADR-006-blender-import-matrix.md), [IMPORT-MATRIX.md](../../docs/IMPORT-MATRIX.md))
  and are useful references; they are not inherited automatically.
- Unity (the new-project default) has its own golden path:
  [templates/unity-project/README.md](../unity-project/README.md).

## 1. Initialize the project

From the Gypsy checkout, with `<GYPSY_HOME>` replaced by its path:

    python "$GYPSY_HOME\workstream\gypsy.py" project init \
      --path "<PROJECT_DIR>" --engine godot --version 4.7.2 --targets pc

`project init` writes the real `project.gypsy.json` with the hardware gate of the machine that ran
it; do not replace it with the template below. It refuses a non-empty directory unless `--force` is
passed, so pass `--force` only for an existing project after checking the installed engine and
version. Then:

    python "$GYPSY_HOME\workstream\gypsy.py" project show --path "<PROJECT_DIR>"
    python "$GYPSY_HOME\workstream\gypsy.py" check --project "<PROJECT_DIR>"

Godot export templates must be installed before a build is claimed; `gypsy engines probe` reports
whether they are present.

## 2. Add the agent instructions

Copy [AGENTS.gypsy.md](AGENTS.gypsy.md) into the new project, replace `<GYPSY_HOME>`, and append it to
the project's `AGENTS.md` (or keep it as `AGENTS.gypsy.md` and reference it from `AGENTS.md`). The
engine-neutral block is [templates/AGENTS.gypsy.md](../AGENTS.gypsy.md); this one adds the Godot pin. The
canonical guide is [docs/GYPSY-AGENT-GUIDE.md](../../docs/GYPSY-AGENT-GUIDE.md).

## 3. Create the Godot project

Create or open a Godot 4.7.2 project in `<PROJECT_DIR>` and keep the Gypsy manifest at the project
root. Do not add a second manifest and do not overwrite the generated one.

## 4. Recommended slices and toolpacks

These are references in the Gypsy checkout. They are **not** copied into the new project automatically:
a new project does not inherit this repository's slices, toolpacks or game code
([docs/GYPSY-AGENT-GUIDE.md](../../docs/GYPSY-AGENT-GUIDE.md) section 4).

- **Slices:** the `phase1` pattern ([slices/phase1.json](../../slices/phase1.json): demo, build,
  capture) and `quality` ([slices/quality.json](../../slices/quality.json): `check_all`, unit tests,
  records guard) are the closest references; `hero` and `mobile` show the art and APK patterns.
  The slice runner executes steps against the Gypsy checkout root (`--dir` selects the manifests), so
  a slice written for a new project must be verified against that project before it is claimed; until
  then use `gypsy check --project`, `gypsy game ... --path` where the adapter applies, and Godot's
  own commands.
- **Toolpacks:** [toolpacks/art.import.golden.json](../../toolpacks/art.import.golden.json)
  (Blender golden kit to Godot import), [toolpacks/audio.musicgen.json](../../toolpacks/audio.musicgen.json)
  (local MusicGen-small audio; weights are CC-BY-NC, prototype only),
  [toolpacks/hero.wayfarer.json](../../toolpacks/hero.wayfarer.json) (hero generation/validation/capture)
  and [toolpacks/mobile.android.json](../../toolpacks/mobile.android.json) (Godot Android debug APK).
  Adapt them for the new project; they are not installed into it.

## 5. Acceptance and verification

- `gypsy check --project <dir>` passes and reports the engine actually installed.
- A demo claim names the exact headless command and the marker it printed. The Phase-1 contract is
  `GYPSY_DEMO_OK collected=3 frames=<n>` with exit 0; a different project defines its own contract and
  must record it.
- A build claim names a non-empty exported binary and the export preset used.
- A capture claim names a frame or video that was read back; headless capture is not a renderer proof.
- A mobile claim requires a built, package-verified APK; on-device launch is untested here until a real
  device run is recorded.
- The project's own records are updated with the computed version; never write a pass without evidence.
- The project catalog lists the project with health `ok`:

      python "$GYPSY_HOME\workstream\catalog.py" --root "<PARENT_DIR>"
      python "$GYPSY_HOME\workstream\catalog.py" --root "<PARENT_DIR>" --validate

## 6. Related

- [ADR-009](../../docs/ADR-009-vertical-slice.md) - the Godot Phase-1 engine decision and acceptance gates.
- [ADR-018](../../docs/ADR-018-unity-default.md) - why new projects default to Unity instead.
- [PHASE-1-EVIDENCE.md](../../docs/PHASE-1-EVIDENCE.md) - the generated Godot evidence.
- [workstream/catalog.py](../../workstream/catalog.py) - the project catalog used above.
