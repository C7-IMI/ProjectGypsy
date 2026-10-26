# Slices (Phase 2)

Declared work for the Phase-2 orchestrator in [docs/ADR-010-slice-orchestrator.md](../docs/ADR-010-slice-orchestrator.md).
A slice is a JSON manifest, not prose: ordered steps, explicit needs, timeouts and the artifacts the run must leave
behind. The manifests here are executed by [workstream/orchestrator.py](../workstream/orchestrator.py) and loaded and
validated by [workstream/slices.py](../workstream/slices.py). Both are standard library only and importable without
Godot; the CLI surface in ADR-010 is a thin wrapper on top of their functions.

## Files

| File | Slice | Steps | Artifacts |
| --- | --- | --- | --- |
| [phase1.json](phase1.json) | phase1 (project: game) | demo -> build -> capture | build/ProjectGypsy.exe, artifacts/game/demo.mp4, artifacts/game/frame.png |
| [quality.json](quality.json) | quality (project: repository root) | check -> tests -> records | none |
| [toolpacks.json](toolpacks.json) | toolpacks (project: repository root) | art import -> audio | toolpack state ledgers under workstream/state/toolpacks (gitignored) |
| [mobile.json](mobile.json) | mobile (project: repository root) | Android APK toolpack | build/ProjectGypsy.apk |
| [leftbehind.json](leftbehind.json) | leftbehind (project: repository root) | Unity build → demo → capture toolpack | artifacts/leftbehind/{build.log,player.log,frame.png} |
| [hero.json](hero.json) | hero (project: repository root) | Wayfarer generate → validate → capture toolpack | assets/hero/{wayfarer.glb,wayfarer.fbx}, artifacts/game/frame.png |

The slices are independent manifests: phase1 proves the game vertical slice again from a clean state; quality proves
the pack check list, the workstream unit tests and the records guard; toolpacks proves golden import + audio; mobile
builds the Android APK; leftbehind proves the Unity second engine; hero proves the Wayfarer character pipeline. A task
runs them in manifest order and stops at the first failing slice; quality does not require Godot, only Python and git.

## Schema: gypsy.slice/v1

    {
      "schema": "gypsy.slice/v1",
      "id": "phase1",
      "project": "game",
      "artifacts": ["build/ProjectGypsy.exe"],
      "steps": [
        {"id": "demo", "kind": "game.demo", "needs": [], "required": true, "timeout": 300, "args": {}}
      ]
    }

| Field | Required | Meaning |
| --- | --- | --- |
| schema | yes | must be exactly gypsy.slice/v1 |
| id | yes | unique slice id; also names the state file |
| project | yes | repo-relative project directory handed to handlers as project_dir ("." is the repo root) |
| artifacts | yes | repo-relative paths; a missing path fails the slice after a passing step run |
| steps | yes | non-empty ordered list of step objects |

Step fields:

| Field | Required | Meaning |
| --- | --- | --- |
| id | yes | unique in the slice; letters, digits, dot, underscore, dash; at most 64 characters |
| kind | yes | one of game.demo, game.build, game.capture, check_all, tests, records, command |
| needs | no | step ids that must pass first; defaults to [] |
| required | no | defaults to true; a failed or skipped required step fails the slice |
| timeout | no | seconds, positive; defaults to 300; scaled by run_slice(timeout_scale=...) |
| args | no | handler-specific object, defaults to {} |

Validation errors: wrong schema, bad/missing ids, duplicate step ids, unknown kind, missing needs, dependency cycles,
non-boolean required, non-positive timeout, non-object args, and absolute or parent-escaping project/artifact paths.
Ordering is a stable topological order: declaration order breaks ties. Artifact paths and project paths are resolved
against the project root passed to the orchestrator, never against this directory.

## Handlers

The orchestrator looks up a handler by step kind in orchestrator.HANDLERS. A handler is
handler(step, context) -> dict | bool; a dict may return passed, output, exit and error, and a raised exception is
recorded as a failed step instead of crashing the run.

| Kind | Default handler |
| --- | --- |
| game.demo / game.build / game.capture | lazily imports workstream/game.py; phase1 args set the Windows Desktop preset and build/ProjectGypsy.exe output; capture produces the mp4/frame the artifacts list declares |
| check_all | subprocess: python scripts/check_all.py, cwd = project root (pack checks only; no engine dependency) |
| tests | subprocess: python -m unittest discover -s workstream/tests -v, cwd = project root |
| records | subprocess: python scripts/records_check.py --root <project root> |
| command | subprocess with an explicit argv list and cwd, shell=False; a string argv is refused |

There is no model call, no arbitrary shell and no hidden retry loop. A step that needs a failed step is skipped; an
optional step may fail without failing the slice, but a required step that depends on it is skipped and fails the
slice. Independent steps still run after a required failure so the state file records the whole attempt.

## State and artifacts

    workstream/state/slices/<slice>.json      per-step status, timings, errors, manifest SHA-256 (gitignored)
    workstream/state/slices/task-<UTC>.json   one aggregate report for a multi-slice task (gitignored)
    workstream/state/artifacts/<slice>-<runId>.json   artifact ledger: path, SHA-256, bytes (gitignored)

State files are written with a temp file plus replace, so a reader never sees a partial file. After a passing step
run, declared artifacts are hashed; a missing declared artifact turns the run into a failure and the ledger records it
as missing. run_slice returns a JSON-safe dict (slice, passed, steps, artifacts, durationSeconds, statePath, errors,
runId, manifestSha256); it never calls sys.exit.

Resume: --resume (run_slice(resume=True)) skips a step that passed in an existing state file with the same manifest
SHA-256; a changed manifest ignores the old state. --force (run_slice(force=True)) ignores existing state entirely.

## Running

    # plan only: validate and print the stable order
    python -c "import sys; sys.path.insert(0, 'workstream'); import slices; m = slices.load_all('slices'); [print(s, slices.resolve_order(d)) for s, d in m.items()]"

    # run a task with the default handlers
    python -c "import sys; sys.path.insert(0, 'workstream'); import slices, orchestrator, json; print(json.dumps(orchestrator.run_task(slices.load_all('slices'), project_root='.', state_dir='workstream/state'), indent=2))"

The `phase1` slice needs Godot 4.7.2, export templates and ffmpeg. The `quality` slice needs Python and git only:
its check step runs scripts/check_all.py (environment-dependent unit tests skip on a clean runner). Neither needs the
network. The two slices are independent manifests, but a clean-runner task can still run phase1 only after Godot is
installed.

## Tests

    python -m unittest discover -s workstream/tests -v

[workstream/tests/test_orchestrator.py](../workstream/tests/test_orchestrator.py) covers schema validation, stable
ordering, success and required-failure skipping, resume and force, artifact hashing and missing artifacts, the
multi-slice aggregate, and the command handler. It uses temporary manifests and injected fake handlers, so it passes
without Godot.