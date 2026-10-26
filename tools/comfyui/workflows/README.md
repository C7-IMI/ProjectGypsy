# ComfyUI workflows

## projectgypsy-sd15-basic.json

A minimal SD1.5 workflow that uses the checkpoint actually installed on this machine:

    v1-5-pruned-emaonly-fp16.safetensors

It has no Qwen/Z-Image/AuraFlow dependencies and no missing models. Verified in ComfyUI 0.42.1 on 2026-10-26:
loaded into the UI with no errors, and the same graph executed through /prompt to a 512x512 PNG.

### Import

1. Open http://127.0.0.1:8188/
2. Drag projectgypsy-sd15-basic.json onto the canvas, or use Workflow -> Open.
3. Press Run.

If the checkpoint dropdown is empty, confirm the file is in:

    %LOCALAPPDATA%/Programs/GameTools/ComfyUI/portable/ComfyUI_windows_portable/ComfyUI/models/checkpoints/

### Graph

    CheckpointLoaderSimple
      MODEL -> KSampler
      CLIP  -> positive CLIPTextEncode
      CLIP  -> negative CLIPTextEncode
      VAE   -> VAEDecode
    EmptyLatentImage 512x512 -> KSampler -> VAEDecode -> SaveImage

Defaults: seed 42, 20 steps, CFG 7.0, euler/normal, denoise 1.0.

### Verify without the UI

    python tools/comfyui/verify_workflow.py

The verifier validates node/link types, checks the checkpoint against /object_info, converts the UI graph to the ComfyUI
API prompt, runs it, and writes a PNG + provenance sidecar under artifacts/comfyui/.

### Limits

- SD1.5 output is 512px prototype quality; OpenRAIL-M licence review is still required before shipping.
- The 4 GB T600 uses --lowvram; expect roughly 30 s per 512x512/20-step image.
- This is a portrait/sword test prompt; edit the positive/negative text for real work.
