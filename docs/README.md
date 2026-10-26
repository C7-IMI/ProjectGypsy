# docs/ — decisions and evidence

| Document | What it decides/records |
| --- | --- |
| [ADR-001-engines.md](ADR-001-engines.md) | per-project engine selection, registry, adapter contract, capability matrix, hardware gate |
| [ADR-002-art-pipeline.md](ADR-002-art-pipeline.md) | source-of-truth formats, engine-neutral export contract, validators, provenance/licensing |
| [ADR-003-workstream-architecture.md](ADR-003-workstream-architecture.md) | studio-harness architecture, contracts, phases, self-extension safety, rejected alternatives |
| [ADR-004-generative-media.md](ADR-004-generative-media.md) | YuE2 hardware block, MusicGen-small prototype fallback, cloud runbooks, image-generation route |
| [ADR-005-character-animation-automation.md](ADR-005-character-animation-automation.md) | generate/evaluate/critique/tweak loop for characters, rigs and animation; human review gates |
| [ADR-006-blender-import-matrix.md](ADR-006-blender-import-matrix.md) | Blender 5.2.3 golden-asset kit, pinned export settings, FBX quirks, per-engine import matrix |
| [ADR-007-language-boundaries.md](ADR-007-language-boundaries.md) | engine-native gameplay, Python workstream, Rust optional/not installed, C ABI boundary rules |
| [ADR-008-mcp-and-free-local-tools.md](ADR-008-mcp-and-free-local-tools.md) | MCP bridge, Blender/Godot MCP, ComfyUI+SD1.5, Poly Haven, no-API stack, API-provider list |
| [ADR-009-vertical-slice.md](ADR-009-vertical-slice.md) | Phase-1 engine choice (Godot 4.7.2 PC), slice scope, acceptance gates |
| [ADR-010-slice-orchestrator.md](ADR-010-slice-orchestrator.md) | Phase-2 slice schema, orchestrator, state, artifact ledger, multi-slice task |
| [ADR-011-toolpacks.md](ADR-011-toolpacks.md) | Phase-3 toolpacks, validators (file/json/text/wav/png/glb) and provenance |
| [ADR-012-thin-console.md](ADR-012-thin-console.md) | Phase-4 read-only terminal console (board/preview/diff), CLI parity |
| [ADR-013-phase5-mobile-live-perf.md](ADR-013-phase5-mobile-live-perf.md) | Phase-5 mobile package, live watcher, performance baseline, second-engine gate |
| [ADR-014-local-dashboard.md](ADR-014-local-dashboard.md) | local dark GUI dashboard: four views, token actions, localhost safety |
| [ENGINE-SMOKE.md](ENGINE-SMOKE.md) | Phase-0 evidence: Godot headless pass, Unity licence block, UE5 gate, Flax status |
| [IMPORT-MATRIX.md](IMPORT-MATRIX.md) | generated evidence: Blender round-trip, glTF validation, Godot import, blocked engines |
| [PHASE-1-EVIDENCE.md](PHASE-1-EVIDENCE.md) | generated evidence: headless demo, export, exported-binary demo, capture, checks |
| [PHASE-2-EVIDENCE.md](PHASE-2-EVIDENCE.md) | generated evidence: multi-slice task, hashes, reproducibility, resume, tests |
| [PHASE-3-EVIDENCE.md](PHASE-3-EVIDENCE.md) | generated evidence: golden import, MusicGen audio, validators, provenance |
| [PHASE-4-EVIDENCE.md](PHASE-4-EVIDENCE.md) | generated evidence: console board, preview, diff, no-write audit |
| [PHASE-5-EVIDENCE.md](PHASE-5-EVIDENCE.md) | generated evidence: APK package/signature, live watcher, performance, blocked second engine |
| [PHASE-6-GATE.md](PHASE-6-GATE.md) | UE5 hardware gate: blocked, no adapter claimed |
| [DASHBOARD.md](DASHBOARD.md) | launch/use guide for the local GUI dashboard and its four views |

Related: [../TOOLCHAIN.md](../TOOLCHAIN.md), [../TOOL-INVENTORY.md](../TOOL-INVENTORY.md),
[../DEFERRED.md](../DEFERRED.md), [../workstream/README.md](../workstream/README.md),
[../tools/mcp/README.md](../tools/mcp/README.md), [../tools/comfyui/README.md](../tools/comfyui/README.md),
[../assets/test/golden/generate_golden.py](../assets/test/golden/generate_golden.py),
[../scripts/import_matrix.py](../scripts/import_matrix.py).