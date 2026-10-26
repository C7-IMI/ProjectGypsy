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
| Product | a **game** — not a website, not a web application; engine and platforms not chosen yet (`DEFERRED.md` PG-D3) |
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
arrangement" evidence line; the Part 7 example 1 reference to §2.9; the §8.2 sentence that says what is parked; and
the §10.2/§10.6 browser references. Each is replaced by a statement that says what is parked, so nothing silently
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
| 11.8 records move with the work | carried, adapted → **11.4** (records not built yet, PG-D1) |
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
| `<PROMPT_LOG>` | not created yet — **PG-D1** |
| `<CHANGELOG>` | not created yet — **PG-D1** |
| version script | none yet — **PG-D1** |
| `<GUARD_LIST>` | none yet — **PG-D2** (there is no build or test to list) |
| `<CONTRACT_ARTEFACT>` | none yet — no published API (**PG-D7** if one appears) |
| `<CONTRACT_GUIDE>` | the same |
| `<PRODUCT_DOCS>` | [`README.md`](./README.md), this file, `ProjectPack.md` and `DEFERRED.md`; no docs tree yet (**PG-D5**) |
| `<DEFERRED_REGISTER>` | [`DEFERRED.md`](./DEFERRED.md) |
| `<HEALTH_COMMAND>` | none — nothing runs yet (engine decision **PG-D3**) |
| `<SWEEP_COMMAND>` | none — no test rig writes state yet |
| `<DESIGN_LANGUAGE>` | **removed from this copy** — interface material is parked (addendum, **PG-D4**) |
| `<MOCKUP_DIR>` | **removed from this copy** — parked with the design material (**PG-D4**) |

## §8.1 — the day-one decisions, answered

| The decision | This repository's answer |
| --- | --- |
| Where the prompt log and changelog live, and how the version is computed | Not built yet (**PG-D1**). The intended home is the C7NTRY pattern: a prompt log, a changelog and a script-computed version, guard-checked; the first build bootstraps it |
| Which generated copies exist, and who regenerates them | None — nothing generated yet |
| The single check list, and how the hook and CI are kept in step | None yet (**PG-D2**); there is nothing to run. The first code creates the list, the tracked hook and the CI caller together |
| The published contract artefact and what checks it | Not applicable yet; if the game exposes an API this becomes **PG-D7** |
| Where the product's own documentation lives, and what keeps it reachable | README and these pack files today. A docs tree and a links guard arrive with the first docs (**PG-D5**) |
| The design language, and what guards it | **Parked** — the web design rules are in the addendum and not in force (**PG-D4**). No game-side standard has been chosen; inventing one is an operator decision |
| How many interfaces and themes exist, and what they are called | Not decided; parked with the interface material. Do not claim interface facts until the game's interface standard exists |
| Whether the product runs as more than one instance, and what makes scheduled work safe | Nothing runs yet; when a server exists it answers the four questions (§2.20, Part 11.7) |
| Which bug classes this codebase actually produces | None recorded — no code exists |
| Where the scratch rigs live, and how they are reaped | None started by this repository's work |
| Whether anything commits on somebody's behalf | No. Commits are made by a person or a session; no auto-publisher exists |
| Which layers need a rollback document | None yet (**PG-D8**); `ProjectPack.md` §2.13 and Part 11.9 state what each will need |
| The token and context budget, and which loop is the expensive one | Not measured; the repository is small. The expensive loop will be asset builds and play-test runs once an engine exists |
| The register of deliberately deferred work | [`DEFERRED.md`](./DEFERRED.md) |
| Which artefacts are stamped, and who bumps the stamp | None — nothing is distributed |
| What is checked before a deploy, without a subscription | Nothing deployed, no templates, no infrastructure |
| What runs on the operator's machine, and how it is registered | Nothing yet — no hooks, tasks or services installed |
| Whether the parked interface rules are restored, and which ones | **No** (PG-1). The addendum is not in force until a recorded decision restores it, or replaces it with a game-side standard (**PG-D4**) |

## §2.31 — which rules are in force today (applied 2026-10-25, pack PG-1)

This repository is **a game with rules and no product code yet**: no engine, no build, no test, no check list, no
records infrastructure. That state is why most of the pack is conduct rather than mechanism here.

- **In force as conduct, not mechanised:** Part 1's laws; §2.1–§2.4 records and prose (the mechanism is PG-D1); §2.5
  one source; §2.6 brand packet (when assets exist); §2.7 configuration declared; §2.13 reversibility; §2.14–§2.16
  permissions, sweeps and secrets; §2.17–§2.19 reproducibility, evidence and budget; §2.20 scale-and-move; §2.22–§2.30
  operations (when a build exists); §2.31 itself; §2.32 text and encoding; §2.33/§2.34 peer separation and context
  limits; Part 10 (operator's rules); Part 12; and Part 11 in this copy.
- **Mechanised today:** nothing. There is no script that enforces a pack rule; the only enforcement is the report
  discipline in Part 11.2 and the review of the change that added this file.
- **Parked — not in force:** every interface design and redesign rule, plus the browser-verification rule. The full
  list is in the addendum and in the table above. They are not to be applied, quoted as requirements, or partially
  restored without the recorded decision the addendum asks for.
- **Not triggered yet:** §2.8/§2.21 (nothing distributed or deployed), §2.25 health (nothing runs), §2.29/§2.30
  (no auto-publisher, no machine automation), §2.24/§2.26 rigs and residue (no rig), and the interface rules while
  parked.
- **Deliberately not carried:** the C7NTRY rules in the table above marked "declined".

## §8.2 — the inventory of check kinds, filled or declined

No check exists yet. The table names the first ones the build should produce; the pack's §9 list is the full menu.

| Check kind | Status | What compares / why not |
| --- | --- | --- |
| records | not yet | **PG-D1**: the prompt log, changelog and generated copies need the first records files |
| newest-first / version computation | not yet | same (**PG-D1**) |
| encoding | not yet | the first build adds the guard; the pack files are UTF-8 without BOM (checked) |
| documentation links | not yet | **PG-D5**: README and the pack files are the only docs; a links guard comes with the docs tree |
| secret scan | not yet | no code or config yet; the first build adds the scanner before any credential exists |
| project boundary | not yet | **PG-D6**: the peer guard is a discipline until the guard exists (Part 11.5) |
| typecheck / build | not yet | no engine or code (**PG-D3**) |
| generated artefacts | not yet | no generator |
| contract / curated prose | not yet | no API (**PG-D7** if one appears) |
| deploy templates, auto-publish gate, leak sweep, audit sweep, artefact stamp, health, token lint, browser check | n/a | each has no subject in this repository yet; the token-lint and browser rows are **parked** with the interface material |

## How the pack is enforced here

There is no enforcement mechanism yet — no `scripts/checks.mjs`, no hook, no CI. What exists is the discipline:
Part 11.2 (verify before reporting), §2.28 (the register), and honest reporting of what is not built. The first code
creates the one check list and both callers (§2.22–§2.23) together, not one at a time.

```text
git status                     # the only "check" this repository currently has
```

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
