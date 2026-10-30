# Use Gypsy Studio (Gypsy) - Godot project block

This project is a **Godot 4.7.2 / PC** project managed with **Gypsy Studio** (short: **Gypsy**). Godot is
the complete legacy/reference pipeline; new Gypsy projects default to Unity, so this project exists
because Godot was chosen explicitly ([ADR-018](../../docs/ADR-018-unity-default.md),
[ADR-009](../../docs/ADR-009-vertical-slice.md)). Append this block to the project's `AGENTS.md` (or
keep it as `AGENTS.gypsy.md` and reference it from `AGENTS.md`) and replace `<GYPSY_HOME>` once.
The engine-neutral block is [../AGENTS.gypsy.md](../AGENTS.gypsy.md); read
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

- Engine is pinned: **godot 4.7.2**, adapter `godot-4`, targets `pc` (add `mobile` only with a
  recorded decision and a package-verified build). An engine change is a port or a new project, not a
  toggle.
- The demo contract is a deterministic headless run with a marker and exit 0; a screenshot alone is not
  a gameplay pass.
- Headless has no renderer: capture needs a desktop session and is evidence, not a quality claim.
- Android: the debug APK is package-verified, but on-device launch is untested; do not claim a device
  pass before a real launch is recorded.
- The Unity default ([ADR-018](../../docs/ADR-018-unity-default.md)) does not apply to this project; do
  not relabel it.

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
3. Report blocked/untested work honestly (device launch, import, art pipeline).
4. Keep the dashboard local; it accepts fixed action ids only.
5. Follow this project's own rules and records requirements.
