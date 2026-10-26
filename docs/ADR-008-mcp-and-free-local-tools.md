# ADR-008 — MCP and free local creation tools

- **Status:** accepted, 2026-10-25
- **Decision owner:** operator (accounts, licensing, hardware purchases) · **Reviewer:** Lead
- **Scope:** how MCP servers and free/no-API creation tools are used by the workstream.
- **Related:** [ADR-002](ADR-002-art-pipeline.md), [ADR-003](ADR-003-workstream-architecture.md),
  [ADR-004](ADR-004-generative-media.md), [ADR-005](ADR-005-character-animation-automation.md),
  [ADR-006](ADR-006-blender-import-matrix.md), [TOOLCHAIN.md](../TOOLCHAIN.md).

## Context

1. **MCP is a protocol, not a subscription.** Model Context Protocol servers are ordinary local processes
   (stdio/HTTP). The popular Blender integration ([ahujasid/mcp-for-blender](https://github.com/ahujasid/mcp-for-blender),
   formerly `blender-mcp`) is MIT, runs locally, and needs no account; optional premium/API providers add convenience
   but are not required for core Blender control.
2. **DSH does not consume MCP natively.** The workstream therefore uses a bridge CLI (`tools/mcp/mcp_call.py`) that
   starts a server over stdio, lists tools, or calls one. This keeps MCP usable from any agent shell without changing
   DSH itself.
3. **The no-API local stack is already strong enough to produce assets and tests**: Blender 5.2.3, ComfyUI + SD1.5,
   ImageMagick, FFmpeg, Material Maker, Poly Haven (CC0), MusicGen, Ollama/LM Studio. The hardware limits (4 GB T600)
   bound resolution and model size, not the pipeline.
4. **API/account services are useful but optional.** They should be introduced only when a concrete need outgrows the
   local stack, with key custody, cost, licensing and data-policy decisions recorded here first.

## Decision

1. **Use MCP through the local bridge**, not as a hidden requirement. Servers are configured in
   `tools/mcp/servers.json`; every call is logged and can be reproduced from the shell.
2. **Disable telemetry by default** (`DISABLE_TELEMETRY=true` for mcp-for-blender). MCP servers run with least
   privilege and localhost-only access.
3. **Prefer free/local tools first**; add API providers in a later phase only when a named capability needs them.
4. **Every generated/downloaded artefact carries provenance**: model/version, prompt/seed/params, licence, source URL,
   hash, human-review flag (ADR-002/004).
5. **MCP servers do not bypass the gates.** The output of an MCP tool is a candidate; it enters the same validators and
   review bundle as any other asset.

## Installed and tested (2026-10-25)

| Item | Status | Evidence |
| --- | --- | --- |
| **mcp-for-blender** (MIT) | addon installed and enabled in Blender 5.2.3; server configured | `uvx mcp-for-blender install-addon`; `bpy.ops.preferences.addon_enable(module='blender_mcp')` → enabled; bridge lists its tools. Tool execution requires Blender open with the addon server |
| **Godot MCP** (MIT, Coding-Solo) | built and called through the bridge | `node .../godot-mcp/build/index.js`; `get_godot_version` returned `4.7.2.stable.official.ed1daf0bf` |
| **MCP bridge** | works for list/call | `python tools/mcp/mcp_call.py list --server godot`; `call ... --tool get_godot_version` |
| **ComfyUI + SD1.5** (local, no API) | installed and generated an image | 512×512, 20 steps, 28.2 s on the T600 with `--lowvram`; output `artifacts/comfyui/*.png` + provenance sidecar |
| **Poly Haven** (CC0, public API no key) | downloader works | listed textures; downloaded `brick_wall_02` Diffuse 1k (1.03 MB), SHA-256 + CC0 record written |
| **MusicGen-small** | installed earlier, smoke-tested | see ADR-004; CC-BY-NC, prototype only |

## No-API tools and models (local)

| Need | Free/local option | State on this machine |
| --- | --- | --- |
| Image generation | **ComfyUI + SD1.5** (OpenRAIL-M) | installed; 512 px practical at 4 GB VRAM |
| Higher-quality image models | SDXL, FLUX.1 [schnell] | not installed — 8–24 GB class (PG-D21) |
| Image-to-3D | **TripoSR** (MIT code/weights) | not installed — README states ~6 GB VRAM; hardware gate (PG-D19) |
| Other local 3D | Stable Fast 3D, Hunyuan3D, TRELLIS, InstantMesh | not installed — larger VRAM/Windows toolchain risk |
| Retopology | Blender Quadriflow (built in); MeshLab | installed |
| MCP clients/servers | Blender MCP, Godot MCP (installed); Krita MCP, FreeCAD MCP (optional) | Krita/FreeCAD servers are optional and not installed |
| Asset library | **Poly Haven** (CC0), Kenney/Quaternius (CC0 packs) | Poly Haven downloader installed; packs are manual downloads |
| LLM (planning, prompts) | Ollama, LM Studio | installed (small local models) |
| Music | MusicGen-small | installed; CC-BY-NC prototype only |
| Animation | Blender/Rigify, Mixamo (free account), Cascadeur (free tier) | Blender/Rigify local; Mixamo/Cascadeur require web/account |
| Video/capture | OBS, FFmpeg, Kdenlive | installed |
| Audio editing | Audacity, LMMS | installed |

## API/account services that would help (not installed)

| Service | What it adds | Why it is optional |
| --- | --- | --- |
| **Hyper3D Rodin** | text/image → 3D model | BlenderMCP supports it with an API key; local TripoSR is the free fallback |
| **Meshy / Tripo API** | faster, higher-quality image/text → 3D | paid/API; licences vary |
| **Sketchfab** | large downloadable model library | needs API key; licence per model |
| **Stability / Scenario / Runway** | stronger image/video generation | keys, cost, and content policy |
| **Hugging Face Inference** | hosted open models | token + per-call cost; local ComfyUI covers basics |
| **OpenAI / Anthropic APIs** | stronger reasoning/vision for review | per-token cost; local models cover small tasks |
| **Mixamo** (Adobe account) | free auto-rig + animation clips | no API; manual download; licence terms |
| **Rokoko / Move.ai / DeepMotion** | mocap | hardware/subscription/API; no local mocap hardware |
| **Adobe Substance / Autodesk / Reallusion / Houdini** | industry DCC/texturing | subscriptions; Blender/Krita/Material Maker cover the current stage |
| **Unity licence / UE5 hardware** | engine builds | engine gates already recorded (ADR-001/006) |

These are **not** installed. Adding one requires the operator to approve the account, cost, data policy and licence.

## Integration

- `tools/mcp/mcp_call.py` — bridge; `servers` lists configured servers; `list` shows tools; `call` executes one with
  JSON arguments. Servers can be added in `tools/mcp/servers.json` without code.
- `tools/comfyui/start.ps1` / `stop.ps1` / `generate.py` — local image generation with provenance sidecars.
- `tools/polyhaven/polyhaven.py` — free CC0 asset search/download with SHA-256 and licence records.
- Capability manifests: `mcp.bridge`, `mcp.blender`, `mcp.godot`, `asset.polyhaven`, `gen.image.comfyui`,
  `gen.mesh.triposr` (blocked). They join the same checks as the rest.
- BlenderMCP's optional providers (Hyper3D, Sketchfab, Poly Pizza, AI 3D) are **off** unless configured with keys; its
  core is local.

## Consequences

**Positive:** no subscription is required for the core MCP/Blender/Godot path; image generation, assets, importer tests
and audits are local and reproducible; API spend is deferred until a measured gap; provenance is uniform.

**Negative:** MCP tool calls depend on the target app running (Blender open); SD1.5 at 512 px is prototype quality;
TripoSR/3D generation is gated by VRAM; MCP servers execute code and must be treated as trusted local processes;
licences (OpenRAIL-M, CC-BY-NC, model cards) still constrain shipping.

## Alternatives rejected

- **Buy a Claude/MCP subscription to get Blender control** — MCP servers are open source and local; the subscription
  adds a model, not the protocol.
- **Cloud-only generation** — keys, cost and upload policy; local stack covers the current stage.
- **GUI automation (RPA)** — brittle; the MCP/scripting APIs are the supported path.
- **Install every API provider now** — unused keys drift; add on measured need.

## Open questions

- Whether to install Krita MCP and FreeCAD MCP, and whether their socket/plugin lifecycle is reliable on this machine.
- Whether TripoSR can run at reduced settings on 4 GB VRAM or should wait for hardware (PG-D19).
- Native MCP client support in DSH (the bridge works today; a native client would remove one layer).
- Which API provider, if any, is worth paying for once the local quality ceiling is measured.
- Telemetry policy for any future MCP server: default off, documented per server.
