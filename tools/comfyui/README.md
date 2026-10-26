# ComfyUI (local SD1.5)

Portable ComfyUI in `%LOCALAPPDATA%\\Programs\\GameTools\\ComfyUI\\portable`, checkpoint
`v1-5-pruned-emaonly-fp16.safetensors` in `ComfyUI\\models\\checkpoints`. No cloud API.

~~~powershell
.\tools\comfyui\start.ps1
python tools/comfyui/generate.py --prompt "stylized fantasy sword icon, game asset, clean background" --steps 20
.\tools\comfyui\stop.ps1
~~~

- Server: http://127.0.0.1:8188, `--lowvram` for the 4 GB T600.
- Outputs: `artifacts/comfyui/` (gitignored) with a provenance sidecar; SD1.5 is OpenRAIL-M and needs
  licence review before commercial use. See ADR-008.
