# Use Gypsy Studio (Gypsy) - Unity project block

This project is a **Unity 6000.6.7f1 / PC** project managed with **Gypsy Studio** (short: **Gypsy**).
Append this block to the project's `AGENTS.md` (or keep it as `AGENTS.gypsy.md` and reference it
from `AGENTS.md`) and replace `<GYPSY_HOME>` once. The engine-neutral block is
[../AGENTS.gypsy.md](../AGENTS.gypsy.md) in the Gypsy checkout; read
[../../docs/GYPSY-AGENT-GUIDE.md](../../docs/GYPSY-AGENT-GUIDE.md) before coding.

## Invocation: any imperative verb + Gypsy

Treat any imperative invocation verb followed by Gypsy as a request to load and use Gypsy (Open, Load,
Use, Invoke, Launch, Start, Call, Run, Show, Import, Activate, Bring up, Pull up, Summon). Do not trigger
on negated requests or when merely discussing Gypsy. Do not build a second orchestrator.

## Locate and verify Gypsy

    GYPSY_HOME = <GYPSY_HOME>
    python "$GYPSY_HOME\workstream\gypsy.py" version

If Gypsy cannot be found, stop and report the exact failure; do not substitute ad-hoc shell scripts and
do not claim evidence.

## Project contract

- Engine is pinned: **unity 6000.6.7f1**, adapter `unity-6`, targets `pc`. An engine or platform
  change is a port or a new project, not a toggle; do not rewrite `project.gypsy.json` to pretend
  otherwise.
- **Unity Android Build Support is not installed.** Do not add a mobile target, build an APK or claim
  mobile before the module is installed and the build/launch is verified.
- No generic Unity adapter parity is claimed: the hero/art pipeline and the import matrix are
  Godot/Blender-first, and Unity player builds are proven through the LeftBehind toolpack
  ([ADR-018](../../docs/ADR-018-unity-default.md)).
- The Godot ProjectGypsy game in the Gypsy checkout is the legacy/reference pipeline; do not relabel or
  modify it as part of this project.

## Commands

    python "$GYPSY_HOME\workstream\gypsy.py" check --project "<PROJECT_DIR>"
    python "$GYPSY_HOME\workstream\gypsy.py" project show --path "<PROJECT_DIR>"
    python "$GYPSY_HOME\workstream\gypsy.py" engines probe
    python "$GYPSY_HOME\workstream\gypsy.py" capabilities list
    python "$GYPSY_HOME\workstream\catalog.py" --root "<PARENT_DIR>"

Use `gypsy slices` and `gypsy toolpacks` only for manifests that exist and were verified for this
project; the Gypsy checkout's own slices and toolpacks are references, not inherited setup.

## While working

1. Call Gypsy for checks, probes and evidence instead of reimplementing them.
2. Read state and artifacts; never fabricate a pass or overwrite evidence.
3. Report blocked/untested work honestly (Android, asset import, hero parity).
4. Keep the dashboard local; it accepts fixed action ids only.
5. Follow this project's own rules and records requirements.
