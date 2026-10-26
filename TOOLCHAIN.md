# TOOLCHAIN.md — how the workstream finds its tools

Last verified 2026-10-25. Full versions and provenance are in [TOOL-INVENTORY.md](TOOL-INVENTORY.md); decisions are in
[docs/ADR-001-engines.md](docs/ADR-001-engines.md) and [docs/ADR-003-workstream-architecture.md](docs/ADR-003-workstream-architecture.md).

## Load the tools into a shell

```powershell
. .\tools\tool-env.ps1          # prepends the GameTools directories to this session's PATH
```

The installer also set the **user PATH** (GameTools first), so new terminals already see the commands. A long-running
process started before the install (including the current DSH session) keeps its old PATH — refresh it or use the
script above. The manifest of record is
`%LOCALAPPDATA%\Programs\GameTools\tools.json`; override it with `GYPSY_TOOLS_MANIFEST`.

## Installed commands

| Command | Version | Purpose |
| --- | --- | --- |
| `magick` | ImageMagick 7.1.2-34 | convert, channel pack, contact sheets, validate |
| `ffmpeg` / `ffprobe` | 9.0.2 | capture, encode, frames, audio conversion |
| `cmake` / `ninja` | 4.4.4 / 1.13.2 | native builds and plugins |
| `texconv`, `texassemble`, `texdiag` | DirectXTex may2026 | BCn compression, channel assembly, diagnostics |
| `gltfpack` | 1.3 | glTF/GLB optimisation |
| `gltf-transform` | 4.5.1 | glTF inspect/validate/optimise |
| `renderdoccmd` / `qrenderdoc` | RenderDoc 1.46 | GPU frame capture and inspection |
| `tiled` | Tiled 1.12.2 | tilemaps |
| `LDtk` | LDtk 1.5.3 | 2D level editor |
| `material_maker` | Material Maker 1.8 | procedural PBR materials |
| `libresprite` | LibreSprite 1.3 | pixel art / sprite animation |
| `meshlab` | MeshLab 2025.07 | mesh cleanup, decimation, remeshing |
| `audacity` | Audacity 4.0.1 (shim) | audio editing |
| `Pixelorama.exe` | Pixelorama 1.2.3 | pixel art (launch from its folder) |

Python libraries (scipy, trimesh, pygltflib, imageio, opencv, matplotlib, numpy, Pillow) are installed in
`C:\Python\python.exe`.

## Engines

```text
python workstream/gypsy.py engines probe
```

| Engine | Version | Path | Status |
| --- | --- | --- | --- |
| Godot | 4.7.2 | `%LOCALAPPDATA%\Microsoft\WinGet\Links\godot.exe` | reference adapter; headless smoke, export, exported-binary demo and windowed capture all pass |
| Unity | 6000.6.7f1 | `C:\Program Files\Unity 6000.6.7f1\Editor\Unity.exe` | installed; **licence not proven**, batchmode blocked |
| Unreal Engine 5 | 5.8.4 | `D:\UnrealEngine\UE_5.8\Engine\Binaries\Win64\UnrealEditor-Cmd.exe` | detected; hardware gate fails (4 GB VRAM, 51.5 GB free on D) |
| Flax | 1.13 | `C:\Program Files (x86)\Flax\Flax_1.13\Binaries\Editor\Win64\Release\FlaxEditor.exe` | experimental; no headless path demonstrated |

The stale UE 5.4/4.0 registry entries are reported and ignored. Phase-0 evidence: [docs/ENGINE-SMOKE.md](docs/ENGINE-SMOKE.md).

## MusicGen (prototype music)

Installed in a Python 3.10 venv at `%LOCALAPPDATA%\Programs\GameTools\MusicGen\venv` (torch 2.11.0+cu128,
transformers 5.20.2), model cache under `...\MusicGen\hf-cache`, outputs under `...\MusicGen\outputs` or the repo's
`artifacts/musicgen/` (gitignored).

```powershell
.\tools\musicgen\musicgen.ps1 -Prompt "calm sci-fi menu loop, soft pads" -Seconds 6
```

- Measured on the T600: 6 s clip generated in ~35 s wall time; 32 kHz mono; the first float16 attempt produces NaNs,
  and the generator detects that, retries in float32, and refuses to save silence.
- **Licence: model weights CC-BY-NC 4.0 — non-commercial. Prototype only; not for shipping audio.** See
  [docs/ADR-004-generative-media.md](docs/ADR-004-generative-media.md).
- YuE2 is **not** installed: it requires Linux + Python 3.12 + a 24 GB BF16 GPU (PG-D10).

## MCP bridge (ADR-008)

MCP is a protocol, not a subscription. DSH does not speak MCP natively, so this CLI is the bridge:

~~~powershell
.\tools\mcp\mcp.ps1 servers
.\tools\mcp\mcp.ps1 list -Server blender
.\tools\mcp\mcp.ps1 list -Server godot
.\tools\mcp\mcp.ps1 call -Server godot -Tool get_godot_version -Args '{}'
~~~

- **Blender**: [mcp-for-blender](https://github.com/ahujasid/mcp-for-blender) (MIT) addon installed and enabled in
  Blender 5.2.3; its socket server runs when Blender is open. Tool calls require Blender running; optional Hyper3D/
  Sketchfab/Poly Pizza providers are off unless keys are added. Telemetry disabled in `servers.json`.
- **Godot**: [Coding-Solo/godot-mcp](https://github.com/Coding-Solo/godot-mcp) (MIT) built under
  `GameTools\Mcp\godot-mcp`; `get_godot_version` returned `4.7.2.stable.official.ed1daf0bf`.
- Other servers (Krita, FreeCAD, Unity, Unreal) are optional/planned or blocked by the engine gates; see ADR-008.

## Local generation and assets (no API)

~~~powershell
# ComfyUI + SD1.5 (installed; 4 GB T600, --lowvram)
.\tools\comfyui\start.ps1
python tools/comfyui/generate.py --prompt "stylized sword icon, game asset" --steps 20
.\tools\comfyui\stop.ps1

# Poly Haven CC0 assets (public API, no key)
python tools/polyhaven/polyhaven.py list --type textures --search brick
python tools/polyhaven/polyhaven.py download brick_wall_02 --resolution 1k --slot Diffuse --dest artifacts/polyhaven
~~~

- ComfyUI 0.42.1 portable + `v1-5-pruned-emaonly-fp16.safetensors` (2.03 GB); measured 512×512, 20 steps, 28.2 s.
  Outputs and sidecars under `artifacts/comfyui/`; SD1.5 is OpenRAIL-M (licence review before shipping).
- Poly Haven downloads write CC0 + SHA-256 provenance records; no API key.
- TripoSR (image-to-3D, MIT) is **not installed**: README states ~6 GB VRAM, above this machine (PG-D19). Use a cloud/
  API provider only on the operator's decision (ADR-008 has the list).

## Playable slice (Phase 1, ADR-009)

~~~powershell
python workstream/gypsy.py game demo      # headless: GYPSY_DEMO_OK collected=3 frames=143, exit 0
python workstream/gypsy.py game build     # exports build/ProjectGypsy.exe (109,127,680 bytes)
python workstream/gypsy.py game capture   # windowed movie -> artifacts/game/demo.mp4 + frame.png
python workstream/gypsy.py game verify    # demo + build + exported-binary demo + capture
python workstream/gypsy.py slices list|plan   # slice manifests and dependency order
python workstream/gypsy.py slices run --all   # phase1 + quality + toolpacks, one report
python workstream/gypsy.py slices status      # latest task state
python workstream/gypsy.py toolpacks list|check
python workstream/gypsy.py toolpacks run art.import.golden   # Blender->Godot import + validators
python workstream/gypsy.py toolpacks run audio.musicgen      # local MusicGen WAV + validator
~~~

- Engine: Godot 4.7.2, PC; export templates installed under `%APPDATA%\\Godot\\export_templates\\4.7.2.stable`.
- Evidence: [docs/PHASE-1-EVIDENCE.md](docs/PHASE-1-EVIDENCE.md), [docs/PHASE-2-EVIDENCE.md](docs/PHASE-2-EVIDENCE.md) and
  [docs/PHASE-3-EVIDENCE.md](docs/PHASE-3-EVIDENCE.md); state under `workstream/state/{game-*,slices,artifacts,toolpacks}/`
  (gitignored).
- `build/` and `artifacts/` are gitignored; the slice source is `game/`.

## Workstream commands

```text
python workstream/gypsy.py engines probe [--json] [--save]   # --save writes workstream/state/engines.json
python workstream/gypsy.py engines smoke godot [--json]
python workstream/gypsy.py tools probe [--json]
python workstream/gypsy.py capabilities list|check [--json]
python workstream/gypsy.py project init --path <dir> --engine <godot|unity|ue5|flax> --version <ver> --targets pc,mobile
python workstream/gypsy.py project show [--path <dir>]
python workstream/gypsy.py check [--project <dir>] [--json]
python -m unittest discover -s workstream/tests -v
```

## Golden import matrix (ADR-006)

```text
python scripts/import_matrix.py                 # regenerate the golden kit, round-trip, validate, Godot-import
python scripts/import_matrix.py --skip-generate # reuse the last generated kit
```

- Assets: `assets/test/golden/generate_golden.py` (Blender 5.2.3) → `artifacts/golden/` (gitignored):
  static+material, rigged+3 animations, morph face, LOD/collision set; GLB and FBX.
- Evidence: `docs/IMPORT-MATRIX.md`; machine-readable `workstream/state/import-matrix.json`.
- Current result: Blender round-trip pass, glTF validator no errors (one expected `NODE_SKINNED_MESH_NON_ROOT`
  warning), **Godot 4.7.2 headless import pass** (3 animations on the rigged asset, 4 LOD meshes). Unity blocked
  (no licence), UE5 blocked (hardware gate), Flax not tested — recorded, not faked.
- Add-on smoke tests (Rigify, retopo/UV/bake) are policy in ADR-006; not yet automated.

## Languages (ADR-007)

Gameplay and editor code use the engine's language (GDScript/C#/C++/Blueprints). The workstream, validators and
import harness use Python. **Rust is optional and not installed**; if a native need is proven, it may be used only
behind a versioned CLI or C ABI, never as the gameplay language. See [docs/ADR-007-language-boundaries.md](docs/ADR-007-language-boundaries.md).

## Machine limits to respect

- **4 GB VRAM**: no UE5 editor/Lumen work, no SDXL/FLUX local generation, MusicGen-small only for short clips.
- **D: 51.5 GB free**: UE5 projects and DDC will not fit; use C: or external NVMe.
- **Licences**: UE5 EULA/royalty; Unity activation; MusicGen weights non-commercial; ArmorPaint binary is paid.
  Never ship a generated or commercial-model asset without the record and licence in ADR-002/ADR-004.