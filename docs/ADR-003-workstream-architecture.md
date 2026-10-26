# ADR-003 — Workstream architecture: a studio harness, not an IDE

- **Status:** accepted, 2026-10-25
- **Scope:** how the ProjectGypsy application/agent is structured to develop a game end to end.
- **Related:** `docs/ADR-001-engines.md`, `docs/ADR-002-art-pipeline.md`, `docs/ADR-004-generative-media.md`,
  `ProjectPack.md`, `TOOLCHAIN.md`.

## Context

The goal is an application/agent that can take a game from idea to running demos using many tools: engines, Blender,
Krita/Inkscape, material authoring, audio, capture, profiling and generators. The candidate shapes were an IDE, a
workflow engine that connects tools, or an agent that calls tools.

Rebuilding an IDE is years of work with no leverage: the engines already have editors, importers and build systems.
The hard part is **orchestration plus verification**: deciding what to do, calling deterministic tools, running the
result, and proving it works. The pack's rule applies directly — a claim is not done until something ran.

## Decision

Build a **studio harness** with six layers. The interface (a console) is a thin skin added later.

1. **Orchestrator** — turns an intent into a task/slice list, runs it, persists state, retries, enforces budgets and
   approvals. Durable state lives in the repository (`workstream/state/`, the slice list, artifacts), never only in
   a conversation.
2. **Capability bus** — every tool or engine operation is a versioned capability manifest with inputs, outputs, cost,
   reversibility, requirements and acceptance checks. Tools are invoked as deterministic CLIs; GUI-only tools are
   driven through their scripting API or are explicitly human steps.
3. **Engine adapters** — the ADR-001 contract. One project, one pinned engine and adapter.
4. **Art/audio toolpacks** — Blender/Inkscape/Krita/Material Maker/Audacity/ImageMagick/FFmpeg adapters that produce
   engine-neutral artifacts with provenance (ADR-002).
5. **Verification harness** — the non-negotiable layer: boot the build, run a scripted demo/playtest, capture output
   (frames, logs, metrics), compare against acceptance criteria, and attach the evidence to the artifact.
6. **Records and artifact store** — content-addressed outputs with source hashes, tool versions, seeds/parameters,
   licence/provenance, and a changelog/prompt log. Derived artifacts are never hand-edited.

**Deterministic pipeline mode and agent mode share the same capabilities.** Fixed sequences (build → run → capture →
gate) run without a model; the agent is used for planning, tool choice, failure recovery and novel composition. The
deterministic path is what CI and trust rest on.

**Not decisions:** no custom scene format, no in-game editor, no IDE, no self-modifying core, no GUI automation as
the primary path.

## Contracts

- **Project manifest** (`project.gypsy.json`): engine id/version/adapter, targets, paths, decisions.
- **Capability manifest** (`workstream/capabilities/*.json`): `id`, `layer`, `kind`, `maturity` (`stable`, `partial`,
  `experimental`, `planned` for declared-but-not-implemented, `blocked`), `requires`,
  `inputs`, `outputs`, `checks`, `provenance`. Validated by `gypsy capabilities check`.
- **Artifact record**: hash, path, source inputs + hashes, tool id/version, command, seed/parameters, licence,
  producing run and timestamp. Stored as JSONL under `artifacts/` (not committed; the record is).
- **Slice list**: ordered work items in the repository; each ends in something observable (file, build, capture,
  recorded entry, commit). One report at the end (pack §10.6/Part 12).
- **Acceptance test**: what "working" means for the slice, in machine-checkable terms (exit code, marker in stdout,
  frame count, perf budget, screenshot diff).

## Repository layout

```
ProjectPack.md / ProjectPack-NOTES.md / AGENTS.md   the rules
TOOLCHAIN.md                                        installed tools, paths and commands
workstream/gypsy.py                                 CLI: engines/tools/capabilities/project/check
workstream/capabilities/                            capability manifests
workstream/state/                                   runtime state (gitignored)
workstream/tests/                                   unit tests for the harness
docs/ADR-*.md                                       decisions (this file and siblings)
game/                                               the game project (engine-specific)
artifacts/                                          generated outputs (gitignored)
tools/                                              helper scripts (PATH loader)
```

The workstream app is kept as a separate component from the game project so tool code and game content can move at
different speeds. If it grows beyond this repository, it moves to its own repository with the capability manifests as
the contract.

## Self-extension: the safe version

When a capability is missing, the agent may **propose or generate a new adapter/tool** in an isolated directory, with:
- a capability manifest and a version pin,
- tests that prove it can fail (not just pass),
- a dry-run mode and an explicit reversible action,
- a review/approval gate before registration,
- a lockfile update, and a removal path.

The orchestrator core is not self-modified. Arbitrary dependency installation and destructive actions require
explicit approval. Generated code is evidence only after it is read and run.

## Live editing and demos

- **Playable demo is the primary milestone:** headless boot → scripted input replay → capture + metrics → pass/fail.
- **Fast iteration loop** (agent edits source/data, hot-reload, demo resumes from checkpoint, remote inspector) comes
  before any in-game editor.
- **In-game live editing** is a later phase and essentially a second product; it is not assumed.

## Phases and gates

| Phase | Deliverable | Gate |
| --- | --- | --- |
| 0 | Engine registry, project manifest, capability manifests, Godot headless smoke | `gypsy check` passes; Godot prints the smoke marker; other engines' status recorded |
| 1 | First vertical slice on the chosen engine: one scene, one mechanic, one map, scripted demo | builds, runs, captures evidence from a clean checkout |
| 2 | Orchestrator + slice state + artifact provenance + verifier | a multi-slice task runs unattended with one report and reproducible artifacts |
| 3 | Toolpacks (art/audio/import) and engine import profiles | assets generated/imported with validators and provenance |
| 4 | Thin console (task board, preview, diffs, approvals) | the console adds no capability the CLI lacks |
| 5 | Live iteration, mobile export, second engine adapter | same slice runs on two engines; mobile gate passes |
| 6 | Gated UE5 adapter (hardware/remote) | UE5 slice builds on a machine that meets the gate |

## What is not built yet

Orchestrator state machine, artifact store writes, capture harness, engine adapters beyond detection, console,
self-extension pipeline, live reload. They are registered as deferred work rather than pretended. Phase 0 is the
current boundary.

## Alternatives rejected

- **An IDE** — the engines own editing; value is orchestration and evidence.
- **GUI automation (RPA) of Blender/Krita** — brittle; use scripting APIs and deterministic tools.
- **One giant agent prompt** — no durable state, no reproducibility, no gates.
- **A closed toolchain** — capability manifests keep tools replaceable and allow open-source substitutions.
- **Self-modifying core** — unbounded risk for no product gain.

## Open questions

- Which engine first? (ADR-001 / PG-D3; recommendation: Godot for the proof, Unity if mobile.)
- Where does the artifact store live long-term (local vs server) once assets grow?
- How much of the art pipeline is human-finish vs agent-driven? (ADR-002.)
- Which generation providers are acceptable and under what licence policy? (ADR-004.)
