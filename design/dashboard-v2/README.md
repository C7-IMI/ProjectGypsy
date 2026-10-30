# Gypsy Studio operations console

The implemented operations console for the local ProjectGypsy dashboard. It is the default at `/`; the original
four-view app remains available at `/classic`.

## Why the old default screen was hard to use

- Two board columns (Ready/Running) take half the width even when empty.
- Gates mix “untested”, “blocked” and “passing”, so the important distinction is buried.
- The default screen has no “what should I do next?” answer.
- There is no run history, no run-detail view, and no visible retry/error path.
- Few controls have a clear consequence; the current inspector is mostly passive.
- At five slices the kanban no longer scales; it will get worse with more slices.

## Structure

### 1. Workspace overview — overview.png

![Overview](overview.png)

- **Next best action** at the top, with an explanation and an action.
- **Metrics** that answer “did it pass, how much is proven, what needs attention?”.
- **Pipeline strip** with one stage per slice, status, duration and artifact count.
- **Recent runs table** with scope, status, duration, start time and a way in.
- **Recent artifacts** and a **readiness checklist** fill the lower area instead of leaving dead space.
- Right rail keeps **selected artifact** and **gates**, grouped as Passing / Needs attention / Blocked.
- Gates explicitly say there is no approval queue; evidence is the review surface.

### 2. Insights — live-insights.png

![Insights](live-insights.png)

- Plain-language summary of the recorded state, with no second evidence model.
- Engine default: this checkout's Godot manifest, the LeftBehind Unity proof, and the ADR-018 default for new projects.
- Last run health, quality/gates, execution-cache hits/misses, and parallel-scheduler state.
- Cache and scheduler cards stay explicitly empty until opt-in runs record stats; hits/misses are never inferred from
  resume state.
- Next-action rows carry a real whitelisted command and/or a view link; blocked rows say "no local action" instead of
  offering a dead control.

### 3. Projects — live-projects.png

![Projects](live-projects.png)

- Read-only catalog of every `project.gypsy.json` under the checkout, via `workstream/catalog.py` `discover()`.
- Per project: name, engine and version, targets, manifest health, project path and manifest path.
- Manifest health only (schema/warnings), stated explicitly as not engine readiness, licence state or build health.
- Honest loading, empty ("no project.gypsy.json found") and error states; a failed scan never shows fake projects.
- **Scan again** re-runs the read-only scan; manifest paths and the scan root are copyable. There is no open-folder or
  editor action: the dashboard does not expose a file browser (documented in the view).
- Templates (`project.gypsy.template.json`) are never listed as projects; duplicates are flagged with both paths.

### 4. Remaining console screens — live-mission.png, live-commands.png, live-review.png, live-slices.png, live-artifacts.png

- Mission: phase ladder, machine, engine posture, grouped gates.
- Commands: the fixed whitelist with argv, run/copy and latest job output.
- Review: release readiness, evidence and checklist; no approval queue.
- Slices: table of declared slices with run/open actions.
- Artifacts: hashed artifact library with live previews.

### 5. Run detail — run-detail.png

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

## What is implemented

- Backend: `GET /api/runs` returns newest-first run summaries; `GET /api/run?id=...` returns steps, artifacts and
  validators; `/api/state` now includes `runs`. Run IDs are state paths, path-checked under `workstream/state`.
- Frontend: `/` uses `design/dashboard-v2/index.html`, `app.css` and `app.js`; overview is the default, run rows open
  the run-detail view, and the original four-view app is served at `/classic`.
- Actions: new fixed whitelist entries `leftbehind`, `leftbehind_build`, `leftbehind_demo`, `leftbehind_capture`; all UI
  actions still go through the existing confirmation and token-protected POST `/api/run`.
- Retry buttons map to real commands; no per-step argv is accepted from the browser.
- Data comes from task/slice/toolpack state; no second evidence model.
- Localhost-only and token protections remain.
- Insights tab at ?view=insights; deep links support ?view=run&id=<state path>.
- Job output streams over SSE (GET /api/logs/stream) with an automatic polling fallback (/api/job). Failures show a
  copyable command and a link to the latest run; no retry is invented per step.
- Keyboard/focus: tablist arrow-key navigation, Ctrl/⌘+K search, visible :focus-visible rings, skip link, aria-live
  job/toast regions.
- Responsive: insights and action rows reflow at 1200 px; single-column cards and compact tabs below 760 px.
- Projects tab at ?view=projects: GET /api/catalog exposes workstream/catalog.py's read-only scan; the browser cannot
  supply a scan root, so the view never becomes a filesystem browser. Refresh re-scans; no open-folder action exists.
- Projects tests cover real, empty, invalid-manifest and template-only roots, plus the endpoint's error and no-root-
  override behaviour.

## Current data

Screenshots are captured from the local checkout at capture time; they are not hand-built data. The Projects view
lists only manifests that exist on disk (currently the Godot project and LeftBehind), and it states that health is
manifest health only.

Live screenshots (1600×1000, captured by headless Chromium against the local server and real state): `live-overview.png`,
`live-insights.png`, `live-projects.png` and `live-run.png`.
