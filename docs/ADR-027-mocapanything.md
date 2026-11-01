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

## Evidence (verified 2026-11-01)

- Repo at C:\GameTools\MocapAnything; Python 3.10.11 venv; **torch 2.9.0+cu126**; CUDA true; device NVIDIA T600 Laptop GPU.
- Checkpoint: video2pos2rot_epoch60.pt, 463,907,650 bytes; demo data 5,293 files / 1.70 GB.
- **CUDA short clip:** Jaguar#Jaguar-Run_y60, 34 frames, 720x720@30; inference 26 s, total 35 s, upstream success
  1 / fail 0; nvidia-smi 3,851/4,096 MiB, 100% GPU, no OOM.
- **CPU fallback:** same clip, inference 98 s, total 106 s, success 1 / fail 0, GPU idle.
- **BVH:** 46,286 B; CUDA SHA-256 8526f277...367628; CPU 8b37e909...39a900; Gypsy validate passed=true,
  34 frames, 38 joints, 39 channels, frameTime 0.033333. GT 46,256 B / 5791a87c...fc44c77.
- Upstream log MPJPE: CUDA 0.034979/0.055443; CPU 0.034973/0.055443 (not independently benchmarked).
- A first attempt failed on cp1252 printing an arrow; UTF-8 rerun passed. `torch.utils.serialization` did not reproduce
  in fresh processes; it was a process imported while uv replaced torch files.
- 9 toolkit tests (fake environment; live probe only when installed).

## Limits

- One short zoo clip with a GT reference; no retarget/custom-rig/Blender render.
- CUDA vs CPU BVH bytes differ due floating point; counts/validation match.
- No performance claim beyond the observed 26 s CUDA / 98 s CPU clip; no full-demo benchmark.
- Custom-rig pipeline is validated upstream only on a Truebones Zoo rig; the Wayfarer rig is untested.
- No automatic video-to-engine retargeting; Blender is required.
- Third-party licences/data remain the operator's responsibility.
