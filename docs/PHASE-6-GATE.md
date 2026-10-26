# PHASE-6-GATE.md — UE5 adapter gate

Recorded 2026-10-26. This is a **blocked gate**, not a build.

## Requirement

ADR-003 Phase 6 requires a gated UE5 adapter: a UE5 slice builds on a machine that meets the hardware gate.
ADR-001 sets the UE5 minimum at **8 GB VRAM** and **60 GB free on D:**.

## Actual machine

| Item | Value |
| --- | --- |
| GPU | NVIDIA T600 Laptop, **4.0 GB VRAM** |
| D: free | 60.0 GB (meets the 60 GB requirement) |
| UE5 | 5.8.4 installed at D:/UnrealEngine/UE_5.8 |
| Gate | **FAIL** — VRAM 4.0 GB < 8 GB |

The workstream engine probe reports the gate failure and never claims UE5 is buildable. No UE5 project, adapter or
build was created/attempted on this machine, because the declared gate fails before work starts.

## Unblock

- A machine with >= 8 GB VRAM (12-24 GB recommended for editor work), or
- a remote/cloud UE5 builder with the same acceptance test, and
- a recorded operator decision to spend the time/licence budget.

## What was verified

- UE5 binary/version detection and the hardware gate (probe output).
- Nothing about UE5 builds, packaging or rendering is claimed.

## Related

[ADR-001](ADR-001-engines.md), [ADR-003](ADR-003-workstream-architecture.md), [PHASE-5-EVIDENCE.md](PHASE-5-EVIDENCE.md).
