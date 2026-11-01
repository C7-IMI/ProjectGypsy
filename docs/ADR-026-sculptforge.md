# ADR-026 — SculptForge in the design/toolkit pipeline

- **Status:** accepted, 2026-10-31.
- **Scope:** integrate the installed SculptForge CLI and its Blender bridge as a Gypsy toolkit.
- **Related:** [ADR-015](ADR-015-actionforge-toolkit.md), [ADR-017](ADR-017-hero-character-pipeline.md),
  [ART-DIRECTION.md](ART-DIRECTION.md), [SCULPTFORGE.md](SCULPTFORGE.md).

## Context

SculptForge 0.9.6 is installed at C:\Program Files\SculptForge. It provides a headless CLI
(sculptforge-cli), a Blender 4.2+ bridge extension (sculptforge_bridge), file-exchange bridge folders, and
headless commands including open, export_lods, export_glb/fbx/usd, blender_send and blender_receive. The Blender
exchange is folder-based, not a live socket.

## Decision

1. Add a Gypsy toolkit plugin at workstream/toolkits/sculptforge.py with status, lods, convert, bridge-send and
   bridge-receive commands, a capability manifest, ADR and workflow guide.
2. Status locates the CLI, Blender add-on, exchange folder, app path and heartbeat; missing pieces are reported.
3. Commands use fixed CLI templates and project-confined input/output paths. Values containing script metacharacters
   are refused. No arbitrary argv, shell, cwd or env is accepted.
4. LOD output is validated for every requested level and each artifact is SHA-256 hashed. Convert output and bridge
   receive output are validated. Bridge send requires the exchange manifest to be created/changed; a missing heartbeat
   is reported, not treated as a pass.
5. SculptForge remains GPL-3.0-or-later and external; Gypsy does not redistribute it. The GUI and Blender must be run
   by the operator for interactive bridge work.

## Evidence

- Real probe: CLI installed (0.9.6), help OK, Blender bridge add-on found, exchange folder exists, app path recorded,
  no live heartbeat at probe time.
- Real headless LODs from assets/hero/wayfarer.glb: LOD0 46,208 B, LOD1 26,340 B, LOD2 15,748 B, LOD3 10,360 B,
  all written under artifacts/sculptforge with SHA-256 hashes.
- Real bridge-send created to_blender/manifest.json and r1_000.GoZ through the exchange folder.
- 8 toolkit tests (fake CLI for deterministic command/path tests; live probe test skips when SculptForge is absent).

## Limits

- Bridge send/receive is a file handoff; live SculptForge/Blender GUI automation is not attempted.
- Bridge receive requires Blender to have sent a mesh; no such inbound exchange was available during this pass.
- No sculpt/retopo quality claim; SculptForge is an authoring tool, not a validator of art quality.
- Only fixed templates/paths are exposed; the full SculptForge command surface is not exposed.
