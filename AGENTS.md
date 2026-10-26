# AGENTS.md — read this first

Entry point for any model working in this repository. Read this file, then the documents it names, before acting.

## What this repository is

**ProjectGypsy** — a game. Phase 1 runs on **Godot 4.7.2, PC** ([ADR-009](./docs/ADR-009-vertical-slice.md)); other
platforms and the game's interface standard remain open (PG-D4). The engine-selection mechanism is built
([`docs/ADR-001-engines.md`](./docs/ADR-001-engines.md), `workstream/gypsy.py`); the Phase-1 choice can be overridden by
a new project manifest, but an engine change is a port, not a toggle. Do not describe ProjectGypsy as a website, a web application or a console, and do not apply web interface
rules to it.

## What governs your work

In this order:

1. **[`ProjectPack.md`](./ProjectPack.md)** — the standing rules, this copy's revision **PG-1** (base: C7NTRY's
   pack 2.5). Parts 1–10 are the portable pack and the operator's standing rules; **Part 11 is this repository's own
   overlay** — 13 rules adapted from C7NTRY's 24.
2. **[`ProjectPack-NOTES.md`](./ProjectPack-NOTES.md)** — how the pack resolves *here*: the placeholders, the §8.1
   answers, the §8.2 inventory, which rules are actually in force, the §11 mapping, and the parked interface list.
   When the pack and this repository differ, this file says how, and it is the file to correct if it is wrong.
3. **[`ProjectPack-ADDENDUM-Interface.md`](./ProjectPack-ADDENDUM-Interface.md)** — interface design/redesign
   material, **parked and not in force**. Read its first page so you know what is parked. Do not apply it, quote it as
   a requirement, or restore any of it without the recorded operator decision it asks for.
4. **[`TOOLCHAIN.md`](./TOOLCHAIN.md)** — installed engines, art/audio/build tools, paths, versions and the
   `tools/tool-env.ps1` PATH loader. Read it before claiming a tool exists.
5. **[`docs/README.md`](./docs/README.md)** — the ADRs: engines (001), art pipeline (002), workstream architecture
   (003), generative media (004), character/animation automation (005), Blender import matrix (006), language
   boundaries (007), MCP/free local tools (008), vertical slice (009), slice orchestrator (010), toolpacks (011),
   thin console (012), plus [`docs/ENGINE-SMOKE.md`](./docs/ENGINE-SMOKE.md), [`docs/IMPORT-MATRIX.md`](./docs/IMPORT-MATRIX.md),
   and the PHASE-1..4 evidence files.
6. **[`workstream/README.md`](./workstream/README.md)** — the CLI: `engines probe|smoke`, `tools probe`,
   `capabilities`, `project`, `game demo|build|capture|verify`, `slices list|plan|run|status`, `toolpacks list|check|run`,
   `console board|preview|diff`, `check`.
7. **[`DEFERRED.md`](./DEFERRED.md)** — the work deliberately not done. Read the entry covering an area before you
   change that area, and do not quietly close a deferred item by implementing it halfway.
8. **[`README.md`](./README.md)** — the repository entry point and index.

## The rules that bind every turn

- **Never claim a check you did not run.** Report exactly what was verified, by what command, and what was not
  (§1.10, P1, Part 11.2).
- **This is a game, not a web app.** No design-language, mockup-first, visual-bar, viewport, token-lint,
  accessibility-pass or browser-gate rule applies until the addendum is restored or replaced by a recorded decision
  (PG-1, Part 11.1). If a request needs interface design, say the standard is parked and treat the choice as the
  operator's — do not invent one.
- **Verify by running** the build or the test that proves the change, and read back what you captured (§2.18). If no
  build exists yet, say so rather than implying a verification. Evidence lives in `docs/ENGINE-SMOKE.md`,
  `docs/IMPORT-MATRIX.md`, and the PHASE-1..4 evidence files.
- **Record the work.** A change is not finished until its [Retrace.md](./Retrace.md) and [BuildNotes.md](./BuildNotes.md)
  entries exist, with a version from [`scripts/next-version.py`](./scripts/next-version.py) (§2.1).
  [`scripts/check_all.py`](./scripts/check_all.py) guards the records.
- **One list of checks:** [`scripts/check_all.py`](./scripts/check_all.py); the tracked pre-commit hook and the
  GitHub Actions caller both run it, and its coverage guard compares the two (§2.22–§2.23). Never keep a second list.
- **Records and peer projects are separate** (Part 11.5): C7NTRY, C7NC, C7NTAX, C7TNL, C7NTRL and the other C7-IMI
  projects are peers. A prompt asked here is logged here; nothing crosses without explicit instruction.
- **Nothing fake in the build** (Part 11.6): no dead controls, no pretend features; unavailable behaviour says so.
  An engine capability that is hardware-gated or licence-blocked is reported as such, not tested halfway
  (`engine.ue5.build` is `blocked`; Unity batchmode is blocked until activation).
- **Generated media is prototype-only until licensed.** MusicGen-small weights are CC-BY-NC 4.0; every generated
  asset needs provenance and human approval (ADR-004). Never ship it as a commercial asset.
- **Background agents are evidence only after they are read** (§10.8). A dispatch is not progress; read the status
  *and* the work before recording it.
- **Handle text carefully** (§2.32): UTF-8 without a BOM, no round-trip through PowerShell, read back what you wrote.

## First action in a new session

1. Read this file, `ProjectPack-NOTES.md` §2.31, `DEFERRED.md`, `TOOLCHAIN.md` and `docs/README.md`.
2. Check `git status` and the newest records entry — if the records do not exist yet, say so rather than pretending.
3. Run `python workstream/gypsy.py engines probe` and `python workstream/gypsy.py check` before trusting the
   environment; report what they actually print.
4. Run `python scripts/check_all.py` and `python workstream/gypsy.py slices run --all` before trusting the tree; report
   what they print. `--all` now includes the Phase-3 toolpacks slice and takes longer.
5. Ask what the session is for, then run the matching prompt from `ProjectPack.md` Part 3 — **P1** only if the
   bootstrap is incomplete, otherwise **P2** onward. Prompts P4 and P16 are parked; do not renumber the others.

## What has been built (do not overstate it)

Phase 0, 1, 2, 3 and 4 exist: engine/tool probes, hardware gates, manifests, a Godot headless smoke, a playable Godot
4.7.2 PC slice with demo/export/capture, a manifest-driven slice orchestrator with state and artifact hashes, toolpacks
with validators/provenance for Blender->Godot import and MusicGen audio, a read-only terminal console (board/preview/diff),
records and the one pack check list, the ADRs, a golden Blender import matrix, MCP/ComfyUI/Poly Haven tooling. There is
still **no hero art/character pipeline, live editing, self-extension, mobile build or performance budget**. See
`docs/PHASE-4-EVIDENCE.md` and `DEFERRED.md`.