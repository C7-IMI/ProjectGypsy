# ProjectPack — notes beside the pack

`ProjectPack.md` is the portable pack. This file is the only place the pack's placeholders, day-one decisions and
"which rules are in force" statement are resolved for **this** repository (§8.1, §8.2). The pack itself is not edited
here: the project's side lives here, and the pack's parked interface material lives in
[`ProjectPack-ADDENDUM-Interface.md`](./ProjectPack-ADDENDUM-Interface.md).

## This copy

| | |
| --- | --- |
| Held by | this repository (ProjectGypsy) |
| Base | `C7NTRY/ProjectPack.md` revision **2.5**, 2026-10-23, SHA-256 `FC5754DDCDB25535B6808042291C083B6B0BC13F27E36EC8035945AEB70ABE65` |
| This copy | revision **PG-1**, 2026-10-25 — Parts 1–10 carried, the interface design/redesign rules parked, Part 11 re-authored |
| Interface material | **parked, not in force** — `ProjectPack-ADDENDUM-Interface.md` (16 verbatim blocks) |
| Product | a **game** — not a website, not a web application; Phase-1 engine **Godot 4.7.2, PC** (ADR-009); Phase-2 orchestrator exists (ADR-010); other platforms open |
| Last applied | 2026-10-25 — the pack was copied and applied in the change that created this file |

## What was parked, and why

The operator's instruction was: copy the ProjectPack from C7NTRY, apply it, remove anything interface
design/redesign related for now, and put that material in a separate addendum to add back later. This repository is a
game, so the interface and UI/UX requirements of the web pack do not apply as written.

Every rule about how an interface is **designed or redesigned** was removed from the working pack and preserved
**verbatim** in `ProjectPack-ADDENDUM-Interface.md`: Part 2 section C and §2.9–§2.12, §2.35, prompts P4 and P16,
§9.5, §10.7, §10.14, Part 11 rules 11.1/11.4/11.5/11.10/11.11/11.19/11.20/11.23, and the "Browser verification —
Chromium only" standing rule. The addendum lists them with their original numbers and gives a restoring procedure,
including the two places a restore must not restore blindly: the Part 11 numbers (this copy re-authored Part 11 and
reuses some of C7NTRY's numbers) and the Part 2 section C heading (this copy renamed it to hold §2.13).

Pointers and stubs were removed from the pack as well (they were not rules): the `<DESIGN_LANGUAGE>` and
`<MOCKUP_DIR>` legend rows; the "Reimagine this" and "Redesign this" rows of the how-to table; three §8.1 rows; the
§9.2 token-lint row; the two Part 4 definition-of-done lines (the "every surface" line and the design-language line);
the Part 6 "a reimagine starts with a mockup" step and its frame wording; the §2.31 naming-rule reference; the P1
design-language item and its agent-file wording; the P2 interface-change bullet and the "screen captured in every
arrangement" evidence line; the Part 7 example 1 reference to §2.9; and the §10.2/§10.6 browser references. Each is replaced by a statement that says what is parked, so nothing silently
loses its rule, and each is listed here so a restore can put it back.

**Nothing else was parked.** The pack's subject is verifying claims — records, evidence, generated artefacts, gates,
hygiene — and none of that depends on the product being a website. The generic rules, the examples and the operator's
rules remain.

## §11 mapping — what C7NTRY's Part 11 became here

| C7NTRY rule | In this copy |
| --- | --- |
| 11.1 no interaction budget | **parked** (addendum) |
| 11.2 verify before reporting | carried → **11.2** |
| 11.3 work in slices and keep going | carried → **11.3** |
| 11.4 redesigns follow the redesign playbook | **parked** (addendum) |
| 11.5 explanation is a deliverable | **parked** (addendum) |
| 11.6 subagents on every prompt, cap 10 | declined — the portable §10.1 cap applies (this project: twelve) |
| 11.7 feature and integration checks across applications | declined — one application, no interop map |
| 11.8 records move with the work | carried, adapted → **11.4** (records built and guarded; PG-D1 closed) |
| 11.9 probe and discovery safety | declined — no customer infrastructure, no probes |
| 11.10 one interface, three arrangements | **parked** (addendum) |
| 11.11 help stays current | **parked** (addendum) |
| 11.12 the applications remain standalone | declined — C7NTRY's product family, not a game fact |
| 11.13 honest unavailability | carried, adapted → **11.6** (nothing fake in the build) |
| 11.14 peer projects are separate | carried → **11.5** |
| 11.15 the API document is part of the change | declined for now — no API exists; returns with one (PG-D7) |
| 11.16 every change is made ready to scale and to move | carried → **11.7** |
| 11.17 a retrofit is expand-only | carried → **11.8** (nothing retrofitted yet) |
| 11.18 the rollback documents | carried, adapted → **11.9** (no configurable layer yet, PG-D8) |
| 11.19 the visual bar | **parked** (addendum) |
| 11.20 the interface items this copy does not adopt | **parked** (addendum) |
| 11.21 keeping this overlay true | carried → **11.10** |
| 11.22 keep going: slice, delegate, one report | carried → **11.11** |
| 11.23 design reviews: A is approved | **parked** (addendum) |
| 11.24 operator's standing rules for autonomous runs | carried, adapted → **11.12** (web-console bullets removed) |

The "declined" entries are in Part 11.13 of the pack and in `DEFERRED.md` only where a mechanism is owed.

## The placeholders, resolved

| Placeholder | In this repository |
| --- | --- |
| `<PROMPT_LOG>` | [`Retrace.md`](./Retrace.md) (**PG-D1** closed) |
| `<CHANGELOG>` | [`BuildNotes.md`](./BuildNotes.md) (**PG-D1** closed) |
| version script | [`scripts/next-version.py`](./scripts/next-version.py) (**PG-D1** closed) |
| `<GUARD_LIST>` | [`scripts/check_all.py`](./scripts/check_all.py) — the pack-wide list, run by hook and CI (**PG-D2** closed) |
| `<CONTRACT_ARTEFACT>` | none yet — no published API (**PG-D7** if one appears) |
| `<CONTRACT_GUIDE>` | the same |
| `<PRODUCT_DOCS>` | [`README.md`](./README.md), [`docs/README.md`](./docs/README.md), this file, `ProjectPack.md`, `TOOLCHAIN.md` and `DEFERRED.md`; the relative-links guard runs in `scripts/check_all.py` (**PG-D5** closed) |
| `<DEFERRED_REGISTER>` | [`DEFERRED.md`](./DEFERRED.md) |
| `<HEALTH_COMMAND>` | `python workstream/gypsy.py game demo` (headless slice); `python scripts/check_all.py` for the pack checks |
| `<SWEEP_COMMAND>` | none — no test rig writes state yet |
| `<DESIGN_LANGUAGE>` | **removed from this copy** — interface material is parked (addendum, **PG-D4**) |
| `<MOCKUP_DIR>` | **removed from this copy** — parked with the design material (**PG-D4**) |

## §8.1 — the day-one decisions, answered

| The decision | This repository's answer |
| --- | --- |
| Where the prompt log and changelog live, and how the version is computed | [`Retrace.md`](./Retrace.md), [`BuildNotes.md`](./BuildNotes.md) and [`scripts/next-version.py`](./scripts/next-version.py); guarded by [`scripts/records_check.py`](./scripts/records_check.py) (**PG-D1** closed) |
| Which generated copies exist, and who regenerates them | No generated **documentation** copies; the game export (`build/`) and captures (`artifacts/`) are generated and gitignored. No contract artefact exists (PG-D7 not applicable) |
| The single check list, and how the hook and CI are kept in step | [`scripts/check_all.py`](./scripts/check_all.py) is the one list; [`.githooks/pre-commit`](./.githooks/pre-commit) and [`.github/workflows/checks.yml`](./.github/workflows/checks.yml) both run it, and its caller-coverage guard compares them (**PG-D2** closed) |
| The published contract artefact and what checks it | Not applicable yet; if the game exposes an API this becomes **PG-D7** |
| Where the product's own documentation lives, and what keeps it reachable | README, [`docs/README.md`](./docs/README.md) and the ADRs; `scripts/check_all.py` checks every relative Markdown link (**PG-D5** closed) |
| The design language, and what guards it | **Parked** — the web design rules are in the addendum and not in force (**PG-D4**). No game-side standard has been chosen; inventing one is an operator decision |
| How many interfaces and themes exist, and what they are called | Not decided; parked with the interface material. Do not claim interface facts until the game's interface standard exists |
| Whether the product runs as more than one instance, and what makes scheduled work safe | Nothing runs yet; when a server exists it answers the four questions (§2.20, Part 11.7) |
| Which bug classes this codebase actually produces | None recorded yet; the Phase-1 slice and workstream have tests but no defect history worth classifying |
| Where the scratch rigs live, and how they are reaped | None started by this repository's work |
| Whether anything commits on somebody's behalf | No. Commits are made by a person or a session; no auto-publisher exists |
| Which layers need a rollback document | None yet (**PG-D8**); `ProjectPack.md` §2.13 and Part 11.9 state what each will need |
| The token and context budget, and which loop is the expensive one | Not measured at scale; Phase 1's expensive steps are Godot export (~2.6 s), windowed capture (~4.5 s) and the test suite (~7 s). Asset builds remain future work |
| The register of deliberately deferred work | [`DEFERRED.md`](./DEFERRED.md) |
| Which artefacts are stamped, and who bumps the stamp | None — nothing is distributed |
| What is checked before a deploy, without a subscription | Nothing deployed, no templates, no infrastructure |
| What runs on the operator's machine, and how it is registered | The repo pre-commit hook is installed via `core.hooksPath=.githooks`; no scheduled tasks or services |
| Whether the parked interface rules are restored, and which ones | **No** (PG-1). The addendum is not in force until a recorded decision restores it, or replaces it with a game-side standard (**PG-D4**) |

## §2.31 — which rules are in force today (applied 2026-10-25, pack PG-1)

This repository is **a game with rules, a Phase-0/1/2/3/4/5 workstream, a playable slice, a pack-wide check list and
records**. The engine is chosen for this slice (Godot 4.7.2, PC + Android debug package); build/capture, orchestrator,
toolpacks, console, live watcher, performance baseline and Android debug package are proven; remaining work is hero asset
  authorship, self-extension, device testing and the blocked second-engine/UE5 gates.

- **In force as conduct, not mechanised:** Part 1's laws; §2.1–§2.4 records and prose (records now guarded); §2.5
  one source; §2.6 brand packet (when assets exist); §2.7 configuration declared; §2.13 reversibility; §2.14–§2.16
  permissions, sweeps and secrets; §2.17–§2.19 reproducibility, evidence and budget; §2.20 scale-and-move; §2.22–§2.30
  operations (when a build exists); §2.31 itself; §2.32 text and encoding; §2.33/§2.34 peer separation and context
  limits; Part 10 (operator's rules); Part 12; and Part 11 in this copy.
- **Mechanised today:** `python scripts/check_all.py` (records, encoding, links, capability JSON, 54 tests, hook/CI
  caller coverage), `python workstream/gypsy.py check` (engine/project manifests, hardware gate), `python
  workstream/gypsy.py game verify` (demo, export, exported-binary demo, capture) and `python workstream/gypsy.py
  slices run --all` (Phase-2 multi-slice task with artifact hashes). The pre-commit hook runs the same list. The report
  discipline in Part 11.2 remains the human half.
- **Parked — not in force:** every interface design and redesign rule, plus the browser-verification rule. The full
  list is in the addendum and in the table above. They are not to be applied, quoted as requirements, or partially
  restored without the recorded decision the addendum asks for.
- **Not triggered yet:** §2.8/§2.21 (nothing distributed or deployed), §2.25 health (nothing runs), §2.29/§2.30
  (no auto-publisher, no machine automation), §2.24/§2.26 rigs and residue (no rig), and the interface rules while
  parked.
- **Deliberately not carried:** the C7NTRY rules in the table above marked "declined".

## §8.2 — the inventory of check kinds, filled or declined

The pack-wide check list is built: `scripts/check_all.py` runs the checks below and the hook/CI call it. The table
records what is covered and what remains a manual capability.

| Check kind | Status | What compares / why not |
| --- | --- | --- |
| records | **PASS** | `scripts/records_check.py` checks `Retrace.md`/`BuildNotes.md` newest-first, header and contiguous prompts |
| newest-first / version computation | **PASS** | records check + `scripts/next-version.py` |
| encoding | **PASS** | `scripts/check_all.py` checks tracked text blobs are UTF-8 with no BOM/CR |
| documentation links | **PASS** | `scripts/check_all.py` resolves every relative Markdown link in the index |
| secret scan | not yet | no code or config yet; the first build adds the scanner before any credential exists |
| project boundary | not yet | **PG-D6**: the peer guard is a discipline until the guard exists (Part 11.5) |
| typecheck / build | **PASS (build)** | Godot export + exported-binary headless demo; no static typecheck in GDScript |
| generated artefacts | not yet | no game-art generator; MusicGen prototype outputs exist under the ADR-004 record, not a game pipeline |
| contract / curated prose | not yet | no API (**PG-D7** if one appears) |
| deploy templates, auto-publish gate, leak sweep, audit sweep, artefact stamp, health, token lint, browser check | n/a | each has no subject in this repository yet; the token-lint and browser rows are **parked** with the interface material |

## How the pack is enforced here

The pack has one enforced list, `scripts/check_all.py`, run by the tracked pre-commit hook and the CI caller:

```text
python scripts/check_all.py
python workstream/gypsy.py check
python workstream/gypsy.py game verify
```

`check_all.py` covers records, encoding, links, capability JSON, the 181 workstream tests and hook/CI caller coverage;
`gypsy check` covers engine/project manifests and the hardware gate; `game verify` covers the playable slice; `slices run
--all` covers the multi-slice task and artifact hashes; `toolpacks run` covers art/audio validation/provenance; `console`
is a read-only view of the same state.


## How this application of the pack was verified

| Claim | Observation |
| --- | --- |
| The source is C7NTRY's pack 2.5 | SHA-256 of `C7NTRY/ProjectPack.md` at copy time: `FC5754DDCDB25535B6808042291C083B6B0BC13F27E36EC8035945AEB70ABE65` |
| The parked material is verbatim, not rewritten | each of the 16 moved blocks was re-extracted from the source and found byte-for-byte inside the addendum (independent substring comparison; all 16 found) |
| The parked material is complete | the addendum carries §2.9–§2.12 (with the section C heading), §2.35, P4, P16, §9.5, §10.7, §10.14, Part 11 rules 11.1/11.4/11.5/11.10/11.11/11.19/11.20/11.23 and the browser rule |
| The working pack contains no parked rule | the pack has no §2.9–§2.12, §2.35, §9.5, §10.7, §10.14, P4, P16 or interface Part 11 rule headings; the only remaining mentions are the "parked" statements and the Part 11.13 mapping table |
| Nothing was lost from the working pack | numbered rule headings run 2.1–2.8, 2.13–2.34 (no duplicates); prompts run P1–P3, P5–P15, P17–P22 (gaps are the parked prompts, P4 and P16); Parts 1–10 and Part 12 are present |
| Every placeholder the pack still uses is resolved or explicitly deferred | the table above; the two removed placeholders (`<DESIGN_LANGUAGE>`, `<MOCKUP_DIR>`) are named in the addendum |
| Text is UTF-8 without a BOM and has no CRLF | read back with a strict decoder; no replacement characters; no BOM; 0 CR bytes |
| Links resolve | `ProjectPack.md`, `ProjectPack-NOTES.md`, `ProjectPack-ADDENDUM-Interface.md`, `DEFERRED.md` and `README.md` all exist in the repository root and the relative links in the pack target them |

## Restoring the interface material

See `ProjectPack-ADDENDUM-Interface.md` → "Restoring it". In short: decide whether the web rules, a game-side
standard or part of either is wanted; record it here under §8.1 (**PG-D4**); put the sections back with their stubs,
**renumbering the Part 11 rules** (C7NTRY's 11.1/11.4/11.5/11.10/11.11 now belong to this copy's re-authored Part 11)
and **renaming section C** (this copy holds §2.13 under it); remove the parked statements; bump this copy's revision
(PG-2); re-run the verification above. A game-side standard may replace the material instead — record that and keep
the reasoning.