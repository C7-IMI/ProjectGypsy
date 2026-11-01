# MoCapAnything in Gypsy

## Status

- External repo: C:\GameTools\MocapAnything
- Python: .venv (3.10.11)
- torch: 2.9.0+cu126 (CUDA available)
- checkpoint: checkpoints\video2pos2rot_epoch60.pt (463,907,650 bytes)
- GPU: NVIDIA T600 4 GB; CUDA short clip verified
- **Inference verified:** CUDA 26 s on a 34-frame Jaguar clip, 3,851/4,096 MiB VRAM, no OOM. CPU fallback 98 s. BVH validated (34 frames/38 joints/39 channels).

## Commands

    python workstream/gypsy.py toolkit mocapanything status --json
    python workstream/gypsy.py toolkit mocapanything infer --config demo/configs/demo_zoo.yaml --expect demo_outputs/zoo/<result>.bvh
    python workstream/gypsy.py toolkit mocapanything validate --path <file>.bvh

The config must be inside the MocapAnything repo; infer does not accept arbitrary scripts or stdin.

## Intended design workflow

1. Record/reference a short video.
2. Run a MocapAnything config with a matching reference rig/species.
3. Validate the generated BVH (joints/frame count/SHA-256).
4. Import the BVH into Blender and retarget onto the Wayfarer rig.
5. Bake clips and export GLB/FBX.
6. Continue through Gypsy asset validation, import, capture and provenance.

Custom-rig support requires a base FBX plus a motion FBX and Blender preprocessing; it is upstream-tested only on
Truebones Zoo, not on the Wayfarer rig.

## Hardware reality

The local GPU has 4 GB VRAM. CPU torch is installed, but inference speed and model memory are unverified. Use
short clips first; if CPU is impractical, use the upstream HuggingFace ZeroGPU demo or a cloud GPU rather than
pretending the local machine passed.

## Licensing

MIT for code and V2 weights; demo data is research-use and carries its own terms. RMBG-1.4 (BRIA) and Truebones data
are not covered by MIT and are not redistributed by Gypsy.
