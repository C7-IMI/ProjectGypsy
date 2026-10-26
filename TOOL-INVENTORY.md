# TOOL-INVENTORY.md — installed tooling for the ProjectGypsy workstream

Recorded 2026-10-25. Inventory of what this machine has, what was installed for game development, what each
open-source tool replaces, and what is blocked by hardware. Paths and versions below were verified by running the
binaries, not read from the registry.

## Machine and its limits

| | |
| --- | --- |
| Machine | Dell Precision 3571 laptop — i7-12800H (14C/20T), 64 GB RAM |
| GPU | NVIDIA T600 Laptop, **4 GB VRAM** (+ Intel Iris Xe) |
| Disk | C: **256 GB free** · D: **52.6 GB free** (UE 5.8 is installed on D) |
| OS | Windows, managed work machine (SentinelOne/Intune/ConnectWise present) |

Consequences: Godot, Unity, Blender, Krita, Inkscape and the tools below are comfortable. **UE5 with Nanite/Lumen is
not** — 4 GB VRAM is below a practical editor minimum and D: is nearly full. Local generative models are limited to
small checkpoints (a 7B+ music model such as YuE2 is out of reach; see below).

## Installed by this change (portable, user scope, no admin required)

Installed under `%LOCALAPPDATA%\Programs\GameTools` with a manifest at `%LOCALAPPDATA%\Programs\GameTools\tools.json`.
The user PATH was updated (GameTools entries first); **new terminals** pick it up. Existing long-running processes
need a restart or a PATH refresh.

| Tool | Version | Path | Open source | Use |
| --- | --- | --- | --- | --- |
| ImageMagick | 7.1.2-34 (Q16-HDRI x64) | `GameTools\ImageMagick\7.1.2-34` | yes (ImageMagick licence) | batch convert, channel packing, texture validation, contact sheets |
| FFmpeg | 9.0.2 essentials | `GameTools\ffmpeg\...\bin` | yes (LGPL/GPL build) | capture/encode, frame extraction, GIFs, audio conversion |
| RenderDoc | 1.46 | `GameTools\RenderDoc\1.46\...` | yes (MIT) | GPU frame capture and graphics debugging (D3D/Vulkan) |
| Tiled | 1.12.2 | `GameTools\Tiled\1.12.2\PFiles\Tiled` | yes (GPL) | tilemap and level editing |
| LDtk | 1.5.3 | `GameTools\LDtk\1.5.3\app` | yes (MIT) | modern 2D level editor |
| Material Maker | 1.8 | `GameTools\MaterialMaker\1.8\...` | yes (MIT) | **procedural PBR material authoring — open-source Substance Designer alternative** |
| Pixelorama | 1.2.3 | `GameTools\Pixelorama\...` | yes (MIT) | pixel art + frame animation |
| LibreSprite | 1.3 | `GameTools\LibreSprite\1.3` | yes (GPL) | **open-source Aseprite alternative** |
| Audacity | 4.0.1 | `GameTools\Audacity\4.0.1\...\bin` | yes (GPL) | audio editing; `audacity` shim launches `Audacity4.exe` |
| MeshLab | 2025.07 | `GameTools\MeshLab\2025.07` | yes (GPL) | mesh cleanup, decimation, remeshing, inspection |
| CMake | 4.4.4 | `GameTools\CMake\4.4.4\...\bin` | yes (BSD) | native plugin / build toolchain |
| Ninja | 1.13.2 | `GameTools\Ninja\1.13.2` | yes (Apache-2.0) | fast build backend |
| DirectXTex (`texconv`, `texassemble`, `texdiag`) | may2026 | `GameTools\DirectXTex\may2026` | yes (MIT) | BCn texture compression, channel assembly, texture diagnostics |
| gltfpack | 1.3 | `GameTools\gltfpack\1.3` | yes (MIT) | glTF/GLB optimisation and mesh compression |
| glTF-Transform | 4.5.1 | `%APPDATA%\npm` | yes (MIT) | glTF inspect/validate/optimise CLI |

Python libraries installed into `C:\Python\python.exe`: `scipy`, `trimesh`, `pygltflib`, `imageio`,
`imageio-ffmpeg`, `opencv-python-headless`, `matplotlib` (Pillow and NumPy were already present).

## Already present and useful

| Tool | Version | Role |
| --- | --- | --- |
| Blender | 5.2.3 LTS (Python 3.13.13) | 3D assets, sculpt, rig, animation, texture bake, glTF/FBX/USD export (headless verified) |
| Krita | 5.3.4.1 | painting, concept art, texture layers (limited headless scripting) |
| Inkscape | 1.4.4 | vector art, icons, patterns; strong CLI export |
| GIMP | 3.2.6 | raster fallback and format bridge |
| Upscayl | 2.15.0 | AI upscaling of concepts/textures (AGPL; provenance required) |
| Topaz Gigapixel / Photo / Video AI | 7.1.4 / 3.2.0 / 7.1.1 | paid upscalers; source/concept only, never to fake resolution |
| Godot | 4.7.2 | engine — headless build/run (best agent loop) |
| Unity | 6000.6.7f1 | engine — mobile strength; batchmode needs licence check |
| Unreal Engine | 5.8.4 (5.4 registry entry is stale) | engine — limited by 4 GB VRAM and free disk |
| Flax | 1.13 | engine — experimental |
| OBS Studio | 32.2.2 | playtest/demo capture |
| ScreenToGif / Greenshot | 2.43.2 / 1.3.328 | bug clips and screenshots |
| Kdenlive / Shotcut / OpenShot / HandBrake | current | trailer and capture processing |
| LMMS | 1.2.2 | music/SFX production |
| MusicGen-small (venv) | torch 2.11.0+cu128 / transformers 5.20.2 | local prototype music generation; **CC-BY-NC weights, non-commercial** (ADR-004) |
| Ollama / LM Studio | 0.40.11 / current | local LLMs (small models practical on 4 GB VRAM) |
| Docker Desktop, VirtualBox, WSL | current | tool isolation / build sandboxes |
| Git + Git LFS, GitHub CLI/Desktop | current | version control, binary assets |
| Android Studio | 2025.2 | Android build/emulator (iOS export impossible on Windows) |
| NVIDIA Nsight Systems/Compute, CUDA 13.x | current | GPU profiling |
| HWiNFO, GPU-Z, System Informer, WizTree/SpaceSniffer | current | performance and disk telemetry |

## Hosted libraries fetched on demand (not installed)

Recorded 2026-10-26.

| Library | What it provides | Licence | How it is reached |
| --- | --- | --- | --- |
| ActionForge animation library | humanoid rig `rig-human.glb` and CC0 animation clips — a browser-based Mixamo alternative | animation library **CC0** (no attribution required); ActionForge application code **(c) CGstuff** | `python workstream/gypsy.py toolkit actionforge fetch --project <dir> --clips <ids> --rig`; nothing is installed, network is used only by `probe`/`fetch`, and each fetch writes SHA-256 provenance + `NOTICE.md` in the project ([ADR-015](docs/ADR-015-actionforge-toolkit.md)) |

## Open-source replacements for the commercial gaps

| Commercial tool | Open-source replacement | Status |
| --- | --- | --- |
| Substance Designer | **Material Maker** | installed |
| Substance Painter | **ArmorPaint** (GPL, source) plus Krita/Blender texture paint | no free Windows binary in its releases; build from source or buy the binary. Krita/Blender cover painting now |
| Quixel / Megascans | **Material Maker**, **Blender** procedural materials, **Poly Haven** (CC0 assets, web) | partial; asset library is a web service, not installed |
| ZBrush | **Blender sculpt** + **MeshLab** for decimation/remesh/cleanup | installed |
| Maya | **Blender** | installed |
| Houdini | **Blender geometry nodes** (no full open-source equivalent) | partial; no simulation/FX replacement installed |
| Photoshop | **GIMP** and **Krita** | installed |
| Illustrator | **Inkscape** | installed |
| Aseprite | **LibreSprite**, **Pixelorama** | installed |
| Spine / Rive | **Godot built-in 2D skeletal animation** (no equivalent open-source editor installed) | partial; paid tools remain the practical route for advanced rigs |
| Audacity / Reaper | **Audacity** (installed); **Ardour** is the open-source DAW alternative if needed | installed |
| FMOD / Wwise | Godot audio; **SoLoud** (zlib) as an embeddable engine | not installed — middleware needs accounts/licences; decide when audio integration starts |
| YuE2 (music generation) | **cannot run on this hardware** — see below | blocked |
| MusicGen-small | **installed** as the local prototype fallback; CC-BY-NC weights, non-commercial | installed (prototype only) |
| Local image generation (SD/ComfyUI) | ComfyUI (MIT) is the open-source route, but 4 GB VRAM is the limit | not installed; cloud generation + provenance is the practical path now |

## Blocked by hardware: YuE2

`https://github.com/multimodal-art-projection/YuE` (YuE2) states the requirement in its README: **Linux, Python 3.12,
and an NVIDIA GPU with BF16 support and 24 GB VRAM**, producing 48 kHz stereo audio. This machine has Windows and a
4 GB T600 (no BF16 class of Ampere+ support), so a local install would be a multi-gigabyte download that cannot run.

Practical routes, in order: (1) the free hosted demo the project links; (2) the official ComfyUI YuE2 workflow on a
cloud GPU with 24 GB+; (3) a rented GPU instance (RunPod/Lambda/AWS) with the repository's `examples/generate.py`.
Downloading YuE2 weights (7B stage + 1.5B stage + vocoder) is only worth doing once one of those paths exists.

**Local fallback installed:** MusicGen-small (below) generates short instrumental clips on the T600 for prototyping.
It is not a YuE2 substitute (no vocals, 32 kHz, lower quality) and its weights are CC-BY-NC 4.0 — prototype only.

## MusicGen-small (local prototype music)

- Venv: `%LOCALAPPDATA%\Programs\GameTools\MusicGen\venv` (Python 3.10, torch 2.11.0+cu128, transformers 5.20.2).
- Model cache: `...\MusicGen\hf-cache`; outputs: `...\MusicGen\outputs` or `artifacts/musicgen/` (gitignored).
- Use: `tools/musicgen/musicgen.ps1 -Prompt "calm menu loop" -Seconds 6`, or `python tools/musicgen/generate.py ...`.
- Measured on the T600: 6 s clip, 32 kHz mono, RMS 0.146, peak 0.427, 35.5 s wall time. float16 produced NaNs on this
  GPU; the generator detects that, retries float32, and refuses to save silence.
- **Licence: weights CC-BY-NC 4.0 (non-commercial). Prototype only; not for shipping audio.** See
  `docs/ADR-004-generative-media.md`.

## Not installed, deliberately

- **ArmorPaint** binary (paid; source is GPL) — Krita/Blender cover painting.
- **Spine/Rive** (paid/account) — Godot's Skeleton2D/AnimationPlayer covers basic 2D rigs.
- **FMOD/Wwise** (account/licence) — deferred until audio integration.
- **YuE2 weights** — hardware gate (Linux/Python 3.12/24 GB BF16); MusicGen-small is the installed prototype fallback.
- **ComfyUI/SD models** — 4 GB VRAM; use cloud generation with asset provenance.
- **Substance/Quixel/Adobe CC/Houdini/Maya/ZBrush** — paid; see the replacement table.
- Hardware: **external NVMe** (D: has 52.6 GB free) and a **stronger GPU/eGPU or desktop** are the only real fixes for
  UE5 + AAA look and heavy local generative work. No software install substitutes for them.

## MCP and local generation (ADR-008)

| Item | Version | Notes |
| --- | --- | --- |
| ComfyUI portable | 0.42.1 (nvidia) | local image generation; `--lowvram` on the 4 GB T600 |
| SD1.5 checkpoint | `v1-5-pruned-emaonly-fp16.safetensors` | 2.03 GB; OpenRAIL-M; licence review before shipping |
| mcp-for-blender | 2.2.4 (server), addon protocol 15 | MIT; addon enabled in Blender 5.2.3; Blender must be open for tool calls; telemetry off |
| godot-mcp | build from Coding-Solo/godot-mcp | MIT; `get_godot_version` returns 4.7.2 through the bridge |
| MCP bridge | `tools/mcp/mcp_call.py` | stdio list/call; DSH integration path |
| Poly Haven downloader | `tools/polyhaven/polyhaven.py` | CC0 assets, no API key, SHA-256 records |
| TripoSR | **not installed** | MIT but ~6 GB VRAM (PG-D19) |


## Mobile toolchain (Phase 5)

| Item | Version | Notes |
| --- | --- | --- |
| OpenJDK | 17.0.20.1 (Temurin portable) | `GameTools/Java/jdk17`; Android export only |
| Android SDK | platform-tools + platforms;android-35 + build-tools 35.0.0 | `GameTools/AndroidSdk`; aapt2/apksigner verified |
| Debug keystore | local | `%APPDATA%/Godot/keystores/debug.keystore`; debug signing only |
| Android export | arm64-v8a debug APK | 28,305,095 bytes; signature verified; no device launch |

## Verification performed

| Claim | Observation |
| --- | --- |
| ImageMagick works | `magick -version` → 7.1.2-34 Q16-HDRI; `magick -size 16x16 gradient:red-blue test.png` → 16x16 PNG; converted to WebP |
| FFmpeg works | `ffmpeg -version` → 9.0.2-essentials; generated a 1 s 320x240 H.264 MP4; `ffprobe` reported duration 1.000000; extracted a frame |
| Build tools work | `cmake --version` → 4.4.4; `ninja --version` → 1.13.2 |
| glTF tooling works | `gltf-transform --version` → 4.5.1; `gltfpack` runs |
| MusicGen works | `facebook/musicgen-small` generated a 5.94 s clip at 32 kHz on CUDA; RMS 0.146, peak 0.427; fp16 NaN detected and retried in fp32; metadata sidecar written |
| Unity licence and UE5 gates | Unity batchmode: exit 0, entitlements resolved, `GYPSY_UNITY_SMOKE_OK` in 50.891 s (2026-10-26); UE5 hardware gate fails (4 GB VRAM, 60 GB free) — see `docs/ENGINE-SMOKE.md` |
| ComfyUI works | 512×512 SD1.5, 20 steps, seed 42 → PNG (304 KB, mean 0.526) in 28.2 s on the T600 with `--lowvram`; provenance sidecar written |
| MCP bridge works | `tools/mcp/mcp_call.py list --server godot` lists tools; `get_godot_version` returned `4.7.2.stable.official.ed1daf0bf`; Blender server lists tools with the addon installed |
| Android APK works | `scripts/build_android.ps1` produced a 28,305,095-byte signed arm64 debug APK; aapt2 package com.c7imi.projectgypsy; apksigner cert SHA-256 140c76ff... |
| Performance baseline | `game bench --runs 3`: median 2.605 s, p95 2.605 s, GPU 0.56 ms/frame, budgets pass |
| Live watcher | `live.py --once --command demo`: 2.726 s, exit 0; 34 tests |
| Poly Haven works | downloaded `brick_wall_02` Diffuse 1k (1,032,279 bytes, SHA-256 recorded, CC0) |
| Python tooling works | imports of scipy, trimesh, pygltflib, imageio, cv2, matplotlib all succeed under `C:\Python\python.exe` |
| All new commands resolve | `Get-Command magick,ffmpeg,ffprobe,cmake,ninja,gltfpack,gltf-transform,texconv,renderdoccmd,tiled,material_maker,LDtk,libresprite,meshlab,audacity` all found on the refreshed user PATH |
| No admin needed | everything is portable under the user profile; no elevation was used |
| Nothing left running | installation was scripted; no installer or GUI was launched and left open; test artifacts were deleted |

## Where things live

- Tools: `%LOCALAPPDATA%\Programs\GameTools`
- Manifest: `%LOCALAPPDATA%\Programs\GameTools\tools.json`
- Installer cache: `%LOCALAPPDATA%\Programs\GameTools\_downloads` (can be deleted; ~1 GB)
- PATH: user environment variable, GameTools directories first