# Templates

- [AGENTS.gypsy.md](AGENTS.gypsy.md) — portable instruction block for a target project's `AGENTS.md`.
- [UNITY-MIGRATION-PROMPT.md](UNITY-MIGRATION-PROMPT.md) — copy-paste Stage B prompt for the UltraBlade 2 Unity migration.
  Copy it, replace `<GYPSY_HOME>`, and keep it near the top so the harness reads it before coding.

## Golden-path project templates

- [unity-project/README.md](unity-project/README.md) — the golden path for a new **Unity 6000.6.7f1 / PC**
  project (the default, [ADR-018](../docs/ADR-018-unity-default.md)): init commands, the Unity agent block, and
  recommended slices/toolpacks to adapt (never inherited automatically).
- [godot-project/README.md](godot-project/README.md) — the golden path for a project that explicitly chooses
  **Godot 4.7.2 / PC** (the complete legacy/reference pipeline, [ADR-009](../docs/ADR-009-vertical-slice.md)).
- Both are **templates, not projects**: their manifests are `project.gypsy.template.json`, which the
  [project catalog](../workstream/catalog.py) ignores because only a file named exactly `project.gypsy.json`
  is a project.
- The canonical detailed guide is [docs/GYPSY-AGENT-GUIDE.md](../docs/GYPSY-AGENT-GUIDE.md).
