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
| Godot | 4.7.2 | `%LOCALAPPDATA%\Microsoft\WinGet\Links\godot.exe` | reference adapter; headless smoke passes; export templates missing |
| Unity | 6000.6.7f1 | `C:\Program Files\Unity 6000.6.7f1\Editor\Unity.exe` | installed; **licence not proven**, batchmode blocked |
| Unreal Engine 5 | 5.8.4 | `D:\UnrealEngine\UE_5.8\Engine\Binaries\Win64\UnrealEditor-Cmd.exe` | detected; hardware gate fails (4 GB VRAM, 52.6 GB free on D) |
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

## Machine limits to respect

- **4 GB VRAM**: no UE5 editor/Lumen work, no SDXL/FLUX local generation, MusicGen-small only for short clips.
- **D: 52.6 GB free**: UE5 projects and DDC will not fit; use C: or external NVMe.
- **Licences**: UE5 EULA/royalty; Unity activation; MusicGen weights non-commercial; ArmorPaint binary is paid.
  Never ship a generated or commercial-model asset without the record and licence in ADR-002/ADR-004.
