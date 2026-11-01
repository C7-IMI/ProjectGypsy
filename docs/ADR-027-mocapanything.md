# ADR-027 — MoCapAnything integration (external environment)

- **Status:** accepted, 2026-11-01.
- **Scope:** toolkit integration, not bundling the model.
- **Related:** [ADR-005](ADR-005-character-animation-automation.md), [ADR-017](ADR-017-hero-character-pipeline.md),
  [MOCAPANYTHING.md](MOCAPANYTHING.md).

## Context

MocapAnything V2 (SIGGRAPH Asia 2026) converts monocular video to BVH-ready joint rotations for arbitrary
skeletons, and supports custom rigs. The installed trial environment is separate:
C:\GameTools\MocapAnything, Python 3.10.11, CPU PyTorch 2.9.0, checkpoint 463,907,650 bytes. The GPU is a
4 GB T600; CUDA/PyTorch GPU and full demo data were not available at probe time. The reference project is MIT for
code and V2 weights; RMBG-1.4 and Truebones data have separate terms.

## Decision

1. Add a Gypsy toolkit plugin at workstream/toolkits/mocapanything.py with status, infer and validate commands.
2. Status probes the repo, Python, torch, torch.cuda, checkpoint, configs and demo-data presence. Presence is not an
   inference pass; inferenceVerified stays false until a real run succeeds.
3. Infer only runs a repository-local YAML config and returns raw stdout/stderr, exit code and an optional expected
   artifact hash. A zero exit alone is not an art-quality claim.
4. Validate parses BVH HIERARCHY/MOTION, joints, frame count/time and SHA-256.
5. No automatic retarget into Gypsy, Godot or Unity. The operator retargets BVH in Blender and then uses the existing
   hero/export/import pipeline.
6. Do not bundle weights, the repo or third-party data; keep the external environment separate.

## Evidence (at implementation time)

- Repo cloned at C:\GameTools\MocapAnything; Python 3.10.11 venv; torch 2.9.0+cpu.
- Checkpoint present: video2pos2rot_epoch60.pt, 463,907,650 bytes.
- Demo data download completed (5,293 files / 1.70 GB); GPU CUDA/PyTorch was not installed.
- Toolkit status: ready=true, inferenceVerified=false. A real inference attempt failed at CUDA preprocessing (CPU-only torch), so no inference pass is claimed.
- 7 toolkit tests (fake environment; real probe skips appropriately).

## Limits

- 4 GB VRAM is not validated for the model; the installed torch build is CPU-only.
- CPU inference may be slow; no performance claim.
- Custom-rig pipeline is validated upstream only on a Truebones Zoo rig; the Wayfarer rig is untested.
- No automatic video-to-engine retargeting; Blender is required.
- Third-party licences/data remain the operator's responsibility.
