# Retrace - the prompt log

Retrace is ProjectGypsy's prompt log (`<PROMPT_LOG>` in the pack). Every request is recorded here in the order
it was made: its date, a one-line request, its status, and the commit or evidence it produced. The newest entry is
at the bottom and the prompt numbers are contiguous from 1.

Read it with [BuildNotes.md](BuildNotes.md), the dated versioned changelog. `python scripts/records_check.py` (run
by `python scripts/check_all.py`) fails if an entry loses its number or status, if BuildNotes is not newest-first,
if BuildNotes' `Current version:` header disagrees with its newest heading, or if a version repeats.

## How this log was started, and the one limitation in entries 1-13

This log starts on 2026-10-25 with the first Phase-1 build. Entries 1-13 are reconstructed from the session's
prompt-history summary because the earlier conversation was compacted: each request line is the summary's one-line
request, **not a verbatim quotation**, and per-prompt durations were not preserved. From entry 14 on, the request is
appended as written and the duration is recorded. Stating the gap is required by §2.1 (nothing is complete while
records disagree with the work) and §11.4; it is reported to the Lead in the bootstrap report.

Each entry has:

- **Request** - one line, quoted from the prompt or from its recorded summary.
- **Status** - Completed, In progress or Blocked. A request that changed nothing says so explicitly.
- **Version** - the BuildNotes version the change produced, or why no version belongs to it.
- **Commit/evidence** - the commit hash, or the file and observation that are the evidence.

## 1 - 2026-10-25

- Request: Create the private repository ProjectGypsy.
- Status: Completed
- Version: 2026.10.25.001
- Commit/evidence: `5ec1489` - Initial commit; `README.md` is the only tracked file.

## 2 - 2026-10-25

- Request: Copy the C7NTRY ProjectPack into this repository, apply it, and park the interface design/redesign
  material in an addendum.
- Status: Completed
- Version: 2026.10.25.002
- Commit/evidence: `6628fbe` - `ProjectPack.md`, `ProjectPack-NOTES.md`,
  `ProjectPack-ADDENDUM-Interface.md`, `AGENTS.md` and `DEFERRED.md`. The application of the pack is verified in
  the table at the end of `ProjectPack-NOTES.md`.

## 3 - 2026-10-25

- Request: Discuss the workstream application and agent architecture.
- Status: Completed - a discussion; it changed no tracked file of its own.
- Version: none of its own; the architecture was written up later in 2026.10.25.004.
- Commit/evidence: `docs/ADR-003-workstream-architecture.md`, added by `f0a8529` (2026.10.25.004).

## 4 - 2026-10-25

- Request: The engines are installed; choose one per project.
- Status: Completed - the decision mechanism was built, and the actual choice was left to the operator as recorded
  in `DEFERRED.md` PG-D3.
- Version: 2026.10.25.004 for the mechanism (engine registry, `docs/ADR-001-engines.md`); the choice itself has no
  version because it is still open.
- Commit/evidence: `docs/ADR-001-engines.md` and `workstream/gypsy.py` in `f0a8529`; PG-D3 in `DEFERRED.md`.

## 5 - 2026-10-25

- Request: Inventory the installed applications.
- Status: Completed
- Version: 2026.10.25.003
- Commit/evidence: `a4c8bc9` - `TOOL-INVENTORY.md` records versions, paths and provenance for the installed
  engines, art/audio/build tools and Python libraries.

## 6 - 2026-10-25

- Request: Install ImageMagick and the game-development tools.
- Status: Completed - a machine-level install; the repository records what was verified, not the installer run.
- Version: 2026.10.25.003
- Commit/evidence: `TOOLCHAIN.md` (commands and versions) and `TOOL-INVENTORY.md` (provenance), committed in
  `a4c8bc9`; `TOOLCHAIN.md` was added by `f0a8529` (2026.10.25.004).

## 7 - 2026-10-25

- Request: Compare open-source alternatives and consider YuE2.
- Status: Completed - an investigation; it produced records, no code.
- Version: 2026.10.25.003 (open-source replacements in `TOOL-INVENTORY.md`) and 2026.10.25.004
  (`docs/ADR-004-generative-media.md`).
- Commit/evidence: `TOOL-INVENTORY.md` in `a4c8bc9`; YuE2's Linux + 24 GB BF16 GPU requirement is registered as
  `DEFERRED.md` PG-D10 and is not claimed as installed.

## 8 - 2026-10-25

- Request: Install MusicGen.
- Status: Completed - installed and smoke-tested as a prototype path only (CC-BY-NC weights).
- Version: 2026.10.25.004 (prototype path and `tools/musicgen/`), corrected by 2026.10.25.005.
- Commit/evidence: `f0a8529` added `tools/musicgen/generate.py` and `tools/musicgen/musicgen.ps1`; `5601d96`
  fixed the MusicGen JSON validity; the non-commercial licence is recorded in `docs/ADR-004-generative-media.md`
  and `TOOLCHAIN.md`.

## 9 - 2026-10-25

- Request: Design the ADRs and the workstream.
- Status: Completed
- Version: 2026.10.25.004
- Commit/evidence: `f0a8529` - `docs/ADR-001-engines.md` through `docs/ADR-004-generative-media.md`,
  `docs/ENGINE-SMOKE.md`, `workstream/` (registry, manifests, capability schemas, 13 unit tests) and
  `tools/tool-env.ps1`.

## 10 - 2026-10-25

- Request: Write ADRs 001-007 and the golden import matrix.
- Status: Completed
- Version: 2026.10.25.004 (ADR-001 to ADR-004), 2026.10.25.006 (ADR-005 to ADR-007, golden kit, import matrix) and
  2026.10.25.007 (matrix metadata and Godot-status corrections).
- Commit/evidence: `f0a8529`, `eb8be37` and `b5ff4a1`; the matrix evidence is `docs/IMPORT-MATRIX.md`
  (Blender round-trip pass, glTF validation, Godot 4.7.2 headless import pass; Unity, UE5 and Flax recorded as
  blocked or untested, not passed).

## 11 - 2026-10-25

- Request: Explain the AAA character and art requirements.
- Status: Completed - an explanation; it changed no tracked file of its own.
- Version: none of its own; the requirements were written up in 2026.10.25.006.
- Commit/evidence: `docs/ADR-005-character-animation-automation.md`, added by `eb8be37` (2026.10.25.006); the
  honest limits and the deferred pipeline are in `DEFERRED.md` PG-D17.

## 12 - 2026-10-25

- Request: Ask about MCP and the Blender tools.
- Status: Completed - an investigation; it changed no tracked file of its own.
- Version: none of its own; the answer became the next install slice.
- Commit/evidence: the decision and its limits are `docs/ADR-008-mcp-and-free-local-tools.md`, added by
  `534d801` (2026.10.25.008); the integration is recorded in prompt 13.

## 13 - 2026-10-25

- Request: Install the MCP bridge, the Blender and Godot MCP servers, ComfyUI with SD1.5, and the Poly Haven
  downloader.
- Status: Completed - installed and smoke-tested on this machine.
- Version: 2026.10.25.008
- Commit/evidence: `534d801` - `tools/mcp/` (bridge and `servers.json`), `tools/comfyui/`,
  `tools/polyhaven/`, `docs/ADR-008-mcp-and-free-local-tools.md` and eight capability manifests. Measured
  results are recorded in `TOOLCHAIN.md` and `docs/ADR-008-mcp-and-free-local-tools.md`; nothing here is
  re-verified by this bootstrap except the capability JSON parse in `scripts/check_all.py`.

## 14 - 2026-10-25

- Request: Run the full autonomous Phase-1 build (slices, subagents, no stopping until complete).
- Status: Completed - Phase-1 slice, export, capture, workstream game adapter and records/checks are verified.
- Version: 2026.10.25.009
- Commit/evidence: `game/` and `docs/PHASE-1-EVIDENCE.md`; demo `GYPSY_DEMO_OK collected=3 frames=143`;
  `build/ProjectGypsy.exe` 109,127,680 bytes and its headless demo pass; capture 72 frames at 1280x720;
  `game verify` and `scripts/check_all.py` (6/6 PASS, 15 tests, 35 capabilities) pass.

---

## 15 - 2026-10-25

- Request: Fix the Phase-1 audit findings and re-verify the build, records and CI gate.
- Status: Completed.
- Version: 2026.10.25.010
- Commit/evidence: CI-safe test skips (simulated clean runner PASS), `game verify` now requires capture, UTF-8
  subprocess decoding, status/engine/records corrections; `scripts/check_all.py` 6/6 PASS, 15 tests local.

---

## 16 - 2026-10-25

- Request: Keep going; build the next unblocked phase (Phase-2 workstream orchestrator).
- Status: Completed.
- Version: 2026.10.25.011
- Commit/evidence: slices/phase1.json + slices/quality.json, workstream/slices.py, workstream/orchestrator.py,
  slices CLI and 39 orchestrator tests; slices run --all 6/6 steps/3 artifacts in 20.363 s; second run identical
  artifact hashes; 54 tests; scripts/check_all.py 6/6; ADR-010 and docs/PHASE-2-EVIDENCE.md.

---

Next prompt number: 17. The version list is [BuildNotes.md](BuildNotes.md); the checks are
[scripts/check_all.py](scripts/check_all.py).