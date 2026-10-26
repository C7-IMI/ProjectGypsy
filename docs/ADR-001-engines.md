# ADR-001 — Engine selection and adapter architecture

- **Status:** accepted, 2026-10-25
- **Scope:** how the ProjectGypsy workstream chooses, pins and drives a game engine.
- **Related:** `docs/ADR-003-workstream-architecture.md`, `docs/ADR-002-art-pipeline.md`, `TOOLCHAIN.md`,
  `TOOL-INVENTORY.md`, `DEFERRED.md` PG-D3/PG-D11.

## Context

Four engines are installed on this machine: **Unreal Engine 5.8.4** (`D:\UnrealEngine\UE_5.8`), **Unity 6000.6.7f1**
(`C:\Program Files\Unity 6000.6.7f1`), **Godot 4.7.2** (WinGet links) and **Flax 1.13**
(`C:\Program Files (x86)\Flax\Flax_1.13`). The registry also lists a UE **5.4** install that no longer exists — a
stale entry. The operator wants to be able to choose which engine a game is developed in, rather than have one
hard-coded.

The machine is a Dell Precision 3571: i7-12800H, 64 GB RAM, **NVIDIA T600 Laptop with 4 GB VRAM**, C: 256 GB free,
D: 52.6 GB free (UE 5.8 lives on D). That hardware is comfortable for Godot and Unity, and below a practical UE5
editor/cook minimum. Engine choice is therefore both a product decision and a hardware decision.

## Decision

1. **Engine choice is a per-project property, not a workstream setting.** One project = one engine + one pinned
   engine version + one adapter. A project manifest (`project.gypsy.json`) records it:
   `engine.id`, `engine.version`, `engine.adapter`, `targets`, `paths`, and the operator decisions that led there.
2. **Detection is by probing binaries, never by trusting the registry.** The workstream's engine registry validates
   the executable, reads its version, and reports unusable/stale entries as unusable. UE 5.4 and Flax's "1.0"
   uninstall metadata both demonstrate why.
3. **Every engine is driven through one adapter contract:** `createProject`, `importAsset`, `build`, `run`,
   `capture`, `exportTarget`, `launchEditor`, `reload`, `readDiagnostics`. An adapter declares what it supports and
   at what maturity; it never silently falls back to a different engine.
4. **Engines are never switched inside a project.** A change of engine is a **port**: a new project manifest, a
   migration plan, asset re-import, and acceptance tests. It is not a settings toggle.
5. **Maturity is honest.** The workstream ships adapters in this order: **Godot (stable), Unity (partial until
   licensing is proven), UE5 (gated: look-dev/from a stronger machine), Flax (experimental)**. A capability that is
   not implemented is reported as unavailable, not faked.
6. **The hardware gate runs before project creation.** The workstream checks VRAM, RAM and free disk against the
   selected adapter's minimums and requires an explicit override to continue below them.
7. **Selection surfaces:** CLI (`gypsy engines probe`, `gypsy project init --engine ...`) and later a thin console.
   No global "current engine" state; every command resolves the manifest of the project it is run against.

## Detected installations at decision time

| Engine | Version | Binary | Notes |
| --- | --- | --- | --- |
| Godot | 4.7.2 stable | `%LOCALAPPDATA%\Microsoft\WinGet\Links\godot.exe` | console twin available; lowest friction, MIT |
| Unity | 6000.6.7f1 | `C:\Program Files\Unity 6000.6.7f1\Editor\Unity.exe` | standalone install, no Unity Hub config found; licence state must be proven for batchmode |
| Unreal | 5.8.4 | `D:\UnrealEngine\UE_5.8\Engine\Binaries\Win64\UnrealEditor-Cmd.exe` | 5.4 registry entry stale; 4 GB VRAM / 52.6 GB free on D are gates |
| Flax | 1.13 | `C:\Program Files (x86)\Flax\Flax_1.13\Binaries\Editor\Win64\Release\FlaxEditor.exe` | editor present; automation surface least documented |

## Capability matrix (declared, to be proven adapter by adapter)

| Capability | Godot 4.7 | Unity 6 | UE 5.8 | Flax 1.13 |
| --- | --- | --- | --- | --- |
| Project creation from template | native/CLI | batchmode / Hub | uproject template | manual/CLI |
| Headless logic run | **strong** | strong (batchmode) | possible | limited |
| Headless build/export | **strong** (export templates) | strong | possible, heavy (UAT/BuildCookRun) | documented less |
| Scripted asset import | strong | strong (Editor C#) | strong (Python editor) | medium |
| Scripted playtest + metrics | strong | strong (PlayMode tests) | automation framework | limited |
| Rendered capture (visual evidence) | windowed/movie mode (headless has no renderer) | windowed/batch graphics | editor/MRQ with GPU | windowed |
| Live reload / remote inspect | remote debugger | domain reload | Live Coding (C++) | limited |
| Mobile export | good | **strong** | possible, heavy | limited |
| Disk / VRAM cost | low | medium | **very high** | low/medium |
| Licence | MIT | activation required | EULA, 5% royalty | MIT |

"Rendered capture is a known gap for every headless path" — Phase 0 proves headless logic on Godot; the capture
gate is an explicit follow-up, not assumed.

## Per-engine gates

- **Godot:** export templates must be installed before a build/export claim; headless has no renderer, so visual
  capture uses a windowed run (OBS) or movie-maker mode. This is the reference adapter.
- **Unity:** batchmode needs a valid licence (`Unity_lic.ulf` or Hub-managed activation). If licensing cannot be
  proven, Unity is "installed, not pipeline-capable" and the adapter stays partial.
- **UE5:** requires VS toolchain (present), large free disk and a GPU the editor can live with. On this machine the
  adapter is **gated**: it may build small C++/blueprint projects but is not the primary engine. The stale 5.4 entry
  is ignored.
- **Flax:** experimental; no adapter claim until a headless build/run path is demonstrated.

## Consequences

**Positive:** the operator can choose per game; the pipeline code stays engine-neutral; the hardware gate prevents
slow disappointments; a past project keeps its pinned engine version.

**Negative / costs:** four adapters is four times the maintenance; the capability matrix is a support burden; the
engine-neutral asset contract (ADR-002) needs per-engine import profiles; a true port remains expensive.

## Alternatives rejected

- **Hard-code one engine** — contradicts the operator's requirement and the hardware reality.
- **An engine-agnostic scene IR** (export the game from a neutral format into each engine) — a research project; the
  engines' own scene/asset models are the product. Rejected for now.
- **Choose UE5 only because it is "AAA"** — hardware cannot carry it today; AAA is content/pipeline/team, not an
  engine name.
- **Use the registry to find engines** — proved wrong on this machine (UE 5.4, Flax 1.0).
- **Auto-select an engine when none is specified** — hides an irreversible decision; project creation requires it.

## Implementation

- `workstream/gypsy.py engines probe` — validates binaries, versions, export templates, Unity licence, hardware gate,
  and writes `workstream/state/engines.json`.
- `workstream/gypsy.py project init --engine <id> --version <ver> --targets pc|mobile --path <dir>` — writes the
  pinned project manifest and refuses conflicting/overlapping choices.
- `workstream/capabilities/engine.*.json` — the declared capability records this ADR describes.
- Phase 0 reference: `docs/ENGINE-SMOKE.md` records the Godot headless smoke test and the other engines' honest
  status.

**Amendment 2026-10-25:** under the operator's full-autonomy instruction, the Phase-1 slice chooses **Godot 4.7.2,
PC target** (ADR-009, `game/project.gypsy.json`). This is a recorded per-project choice, not a change to the mechanism;
other engines remain adapters and a port is not a toggle.

## Open questions

- **Resolved for Phase 1:** Godot 4.7.2, PC (ADR-009). The mechanism still allows another project/port; mobile vs PC
  and any later engine change remain operator decisions.
- PC or mobile first? Mobile changes the engine ranking and the verification matrix.
- Does the operator want the workstream to support engine **ports** as a first-class workflow, or only per-project
  choice? (Assumed per-project choice first.)