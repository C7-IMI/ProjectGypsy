# ENGINE-SMOKE.md — Phase 0 engine evidence

Recorded 2026-10-25 on the current machine (Dell Precision 3571, i7-12800H, 64 GB RAM, NVIDIA T600 4 GB, Windows,
C: 251 GB free, D: 52.6 GB free). This is the Phase-0 gate from [ADR-003](ADR-003-workstream-architecture.md): prove
the registry and the reference adapter, and record the others honestly instead of assuming them.

## Results

| Engine | Version found | Smoke result | Evidence |
| --- | --- | --- | --- |
| **Godot** | 4.7.2 | **PASS** — headless project boots, prints the marker, exits 0 | `gypsy engines smoke godot` → exit 0, 0.209 s, marker `GYPSY_SMOKE_OK`; export templates: **none installed** |
| **Unity** | 6000.6.7f1 | **BLOCKED — licence** | no `Unity_lic.ulf`; batchmode log: `No valid Unity Editor license found. Please activate your license.` exit code 198 |
| **Unreal Engine 5** | 5.8.4 | **NOT RUN — hardware gate** | gate: 4.0 GB VRAM < 8 GB, D: 52.6 GB free < 60 GB; capability `engine.ue5.build` is `blocked` |
| **Flax** | 1.13 | **NOT RUN — experimental** | editor and `Flax.Build.exe` detected; no headless build/run path demonstrated, so no adapter claim |

Hardware gate check (same run): Godot ok, Unity ok, UE5 **fails**, Flax ok.

## Godot — the reference adapter

Command:

```text
python workstream/gypsy.py engines smoke godot
PASS godot smoke | exit 0 | 0.209s | marker=True
export templates: none installed
```

What the smoke does: creates a temporary Godot project (`project.godot`, `main.tscn`, a GDScript that prints
`GYPSY_SMOKE_OK engine=godot version=...`), runs `godot --headless --path <tmp>` with a 90 s timeout, asserts exit 0
and the marker, deletes the temp directory, and writes the evidence (exit code, duration, stdout, stderr,
export-template list) to `workstream/state/smoke-godot.json` (gitignored).

**Not proven yet:** rendering. Godot headless uses a dummy renderer, so no frame can be captured in this mode. The
visual-evidence path (windowed run + OBS, or Godot movie-maker mode) is a separate capability
(`engine.godot.capture`, maturity **planned**) and is registered as deferred work.

**Export/build** is not proven: no Godot export templates are installed. Headless export will fail until the 4.7.2
templates are installed. This is registered (PG-D14).

## Unity — installed, not pipeline-capable yet

- Editor found at `C:\Program Files\Unity 6000.6.7f1\Editor\Unity.exe`.
- No `C:\ProgramData\Unity\Unity_lic.ulf`; the licensing client reported
  `Found 0 entitlement groups and 0 free entitlements` and then `No valid Unity Editor license found`.
- The first batchmode attempt failed on an argument-quoting error in the smoke harness (project path became
  `Temp/C:/Users/...`); the second attempt used quoted `-createProject` and produced the licence verdict above. That
  first failure is recorded rather than hidden.
- Consequence: the Unity adapter is **partial**. Editor detection works; batchmode build/playmode claims are blocked
  until the operator activates a licence. Do not report a Unity build as working before that.

## Unreal Engine 5 — gated, not attempted

- Binary detected from `D:\UnrealEngine\UE_5.8\Engine\Build\Build.version` → **5.8.4**
  (`UnrealEditor-Cmd.exe` present).
- The registry also lists **UE 5.4** and **UE 4.0** entries whose directories are missing; the probe reports them as
  stale and ignores them.
- The hardware gate fails: 4 GB VRAM (declared minimum 8) and 52.6 GB free on D (declared minimum 60). No UE5 build
  was attempted; claiming one would be false. The UE5 capability is `blocked` and remains a gated/remote adapter
  ([ADR-001](ADR-001-engines.md)).

## Flax — experimental

- Editor `FlaxEditor.exe` and `Flax.Build.exe` exist under `C:\Program Files (x86)\Flax\Flax_1.13`.
- No demonstrated headless build/run path on this machine, so the adapter stays **experimental**; no smoke test is
  claimed.

## Commands used

```text
python workstream/gypsy.py engines probe
python workstream/gypsy.py engines smoke godot
python workstream/gypsy.py capabilities check
python workstream/gypsy.py check
python -m unittest discover -s workstream/tests -v
```

Unity batchmode was invoked directly with:

```text
Unity.exe -batchmode -quit -nographics -logFile <log> -createProject <temp dir>
```

and the licence error above was read from that log.

## What Phase 0 does and does not prove

**Proven:** engine discovery by binary probe; Godot headless project boot; hardware gate; stale-registry rejection;
Unity licence absence; capability/project manifests and their checks.

**Not proven:** rendered capture for any engine; Godot export; Unity batchmode; UE5 build; Flax build; playtest
automation. Those are Phase 1+ work, written down in [DEFERRED.md](../DEFERRED.md) instead of assumed.
