# ADR-011 — Phase 3: toolpacks, validators and provenance

- **Status:** accepted, 2026-10-26 (autonomous Phase-3 build)
- **Scope:** art/audio/import toolpacks, artifact validators and provenance.
- **Related:** [ADR-002](ADR-002-art-pipeline.md) (art contract), [ADR-003](ADR-003-workstream-architecture.md)
  (phase 3), [ADR-004](ADR-004-generative-media.md) (MusicGen licensing), [ADR-008](ADR-008-mcp-and-free-local-tools.md)
  (local tools), [PHASE-3-EVIDENCE.md](PHASE-3-EVIDENCE.md).

## Context

Phase 1 proved a game slice; Phase 2 proved a manifest-driven task orchestrator. Phase 3 asks for toolpacks:
assets generated/imported with validators and provenance. The machine already has Blender 5.2.3, Godot 4.7.2,
the golden Blender kit, MusicGen-small and the glTF validator, but a shell command plus a human reading the log is
not evidence. The result needs declared artifacts, a machine check and a durable record.

## Decision

1. **A toolpack is a manifest, not a script.** toolpacks/<id>.json is a gypsy.toolpack/v1 object with declared
   tools/licence, ordered actions and validators.
2. **Actions are explicit argv, never a shell.** cwd and artifacts are repo-relative; a trailing glob is allowed;
   declared artifacts are hashed after the command.
3. **Validators fail closed.** Supported kinds: file, json (dotted equals/exists/gte), text, wav (16-bit PCM,
   duration/RMS), png (IHDR dimensions) and glb (magic/version 2). A missing artifact or a failed validator fails the
   action; a failed action stops later actions. There are no retries.
4. **Provenance is atomic and complete.** State under workstream/state/toolpacks/ records argv, cwd, exit, stdout/stderr
   clips, timing, artifact SHA-256/bytes, validator results, declared tools/licence, run id and manifest SHA-256.
5. **Two real packs prove the gate:**
   - art.import.golden — regenerates the Blender golden kit, round-trips GLB/FBX, validates glTF and imports into
     Godot with --no-doc; validators assert Godot status pass, rigged character animations >= 3 and LOD meshes >= 4.
   - audio.musicgen — local MusicGen-small 4 s menu clip; validator asserts 16-bit PCM, >= 3 s and RMS >= 0.01.
6. **Toolpacks are orchestrator steps.** The toolpack step kind runs a pack/action; slices/toolpacks.json chains the
   art import then audio generation.
7. **The CLI and orchestrator share the same runner:** toolpacks list|check|run, and slices run toolpacks.

## Acceptance criteria

| Gate | Criterion |
| --- | --- |
| Schema | strict manifests; unknown keys, duplicate actions, shell strings, escaping paths rejected |
| Execution | explicit argv, timeouts, no shell/retry; command failure is state |
| Artifacts | every declared artifact hashed; missing artifact fails |
| Validators | each kind proven by tests and real artifacts; failures fail closed |
| Provenance | atomic state carries tools/licence/argv/hashes/validators/run id |
| Real art/import | golden kit -> Godot import passes the declared JSON/text validators |
| Real audio | generated WAV passes duration/RMS validator |
| Orchestration | slices run toolpacks passes 2/2 steps |
| Tests | toolpack suite passes without Godot/network; full suite passes |

## Out of scope

Art direction, hero character authorship, style review, image-generation toolpack lifecycle (a ComfyUI server is a
separate lifecycle; the direct command is proven in ADR-008), retopo/rig automation (PG-D17) and cross-machine artifact
storage. Validators check structure and declared facts, not taste or final quality.

## Consequences

**Positive:** art/import and audio runs are declared, repeatable and hash-recorded; the same runner serves CLI and
orchestrator; missing or malformed assets fail instead of becoming a log line; the pattern extends to future
DCC/audio/import packs.

**Negative / risks:** manifests are code-adjacent and need review; wide tool licences vary (Blender GPL, MusicGen
CC-BY-NC); state is local/gitignored; validators cannot prove aesthetic quality.

## Verification

[PHASE-3-EVIDENCE.md](PHASE-3-EVIDENCE.md) records the actual toolpack and slice runs, hashes, validator details and
test counts.
