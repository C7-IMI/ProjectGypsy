# Dashboard redesign — operations console

Mockups for a more intuitive, robust version of the local ProjectGypsy dashboard. **Not implemented yet.** The current
app remains design/dashboard; this is a design proposal.

## Why the current screen is hard to use

- Two board columns (Ready/Running) take half the width even when empty.
- Gates mix “untested”, “blocked” and “passing”, so the important distinction is buried.
- The default screen has no “what should I do next?” answer.
- There is no run history, no run-detail view, and no visible retry/error path.
- Few controls have a clear consequence; the current inspector is mostly passive.
- At five slices the kanban no longer scales; it will get worse with more slices.

## Proposed structure

### 1. Workspace overview — overview.png

![Overview](overview.png)

- **Next best action** at the top, with an explanation and an action.
- **Metrics** that answer “did it pass, how much is proven, what needs attention?”.
- **Pipeline strip** with one stage per slice, status, duration and artifact count.
- **Recent runs table** with scope, status, duration, start time and a way in.
- **Recent artifacts** and a **readiness checklist** fill the lower area instead of leaving dead space.
- Right rail keeps **selected artifact** and **gates**, grouped as Passing / Needs attention / Blocked.
- Gates explicitly say there is no approval queue; evidence is the review surface.

### 2. Run detail — run-detail.png

![Run detail](run-detail.png)

- Left: run metadata and ordered step timeline.
- Center: status, marker, artifact count, validator count; log with real argv; **failure playbook**; **reproduce locally**.
- Bottom: **validator evidence** table proving the marker, build, demo and PNG.
- Right: step artifacts with hashes, **retry / re-run / copy command**, and diagnostics.
- The design distinguishes “evidence is immutable” from “a retry creates a new run”.

## Design rules

1. **One primary decision per screen.** The overview's next action is the first thing to read.
2. **Never mix gate states.** Passing, needs-attention and blocked are separate groups with different treatments.
3. **Every number is actionable.** A slice, run or artifact is clickable; static metrics are avoided.
4. **Commands stay visible.** Action buttons map to explicit argv; a copy-command affordance is always nearby.
5. **Robust states are first-class:** empty, loading, stale, running, failed and blocked all get explicit UI. A failed
   step gets a retry and a log path, not a silent red badge.
6. **No fake approval.** Automated gates + evidence; no invented approval queue.
7. **Read-only evidence.** Retries create new state; old evidence is never rewritten.
8. **Scale by rows, not columns.** A runs table and a pipeline strip keep working past five slices.
9. **Responsive fallback:** below 1200 px, the right rail moves under the main column and the pipeline becomes a
   two-row grid; below 760 px, the rail collapses and runs become stacked cards.

## What implementation needs

- Backend: add API routes for run history, run detail (steps, artifacts, validators) and per-step logs, plus explicit
  retry action IDs. The current state endpoint is a good base but is snapshot-only.
- Frontend: route-level views for overview and run detail; replace the current kanban with pipeline + runs table; keep
  the existing artifact preview and command confirmation.
- Data already exists under workstream/state (task and slice state, toolpack state, artifacts); no new evidence model is
  required for the first implementation.
- Preserve localhost-only/token protections and the fixed action whitelist.

## Current data used in the mockups

5 slices (phase1, quality, toolpacks, leftbehind, mobile) · 181 tests · 46 capabilities · 2 gates needing attention
(device launch untested, UE5 hardware-blocked) · LeftBehind Unity 6 PASS.
