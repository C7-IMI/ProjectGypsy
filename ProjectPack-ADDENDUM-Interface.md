# ProjectPack — interface design and redesign addendum

**Parked 2026-10-25 by ProjectGypsy, pack revision PG-1. Not in force.**

This file holds the interface material that was removed from `ProjectPack.md` when the pack was copied into this
repository. The material is kept **verbatim**, at its original section numbers, so it can be restored without being
re-derived. Nothing in this file binds this repository while it sits here: no design language, mockup step, visual
bar, viewport measurement, browser gate or UI/UX requirement is in force.

**Why it is parked.** ProjectGypsy is a game, not a website and not a web application. The removed rules assume a
browser product with screens, routes, design tokens, mockups, viewport measurements and an operator console's visual
bar. A game's interface and UI/UX requirements are different, and no game-side interface standard has been decided
yet (see `ProjectPack-NOTES.md` §8.1 and `DEFERRED.md` PG-D4). Applying the web rules now would invent a design
language the game has not chosen. So they wait here.

**What was removed.**

| Removed from the working pack | Now in |
| --- | --- |
| Part 2, section C — "Design and interface", with §2.9, §2.10, §2.11, §2.12 | §1 below |
| Part 2, §2.35 — a user interface is verified in a browser, and the browser is installed | §2 below |
| Part 3, prompt P4 — reimagine a screen | §3 below |
| Part 3, prompt P16 — self-explanation and accessibility pass | §4 below |
| Part 9, §9.5 — the "Interface" check kinds | §5 below |
| Part 10, §10.7 — redesigning a live interface: five directions first | §6 below |
| Part 10, §10.14 — "needs to be more robust" is a redesign trigger | §7 below |
| Part 11, rule 11.1 — no interaction budget | §8 below |
| Part 11, rule 11.4 — redesigns follow the redesign playbook | §9 below |
| Part 11, rule 11.5 — explanation is a deliverable | §10 below |
| Part 11, rule 11.10 — one interface, three arrangements, named once | §11 below |
| Part 11, rule 11.11 — help stays current | §12 below |
| Part 11, rule 11.19 — the visual bar | §13 below |
| Part 11, rule 11.20 — the interface items this copy does not adopt | §14 below |
| Part 11, rule 11.23 — design reviews: A is the approved direction | §15 below |
| The "Browser verification — Chromium only" standing rule at the end of the pack | §16 below |

**One thing did not move.** §2.13 (Reversible by default) is not interface design; it stayed in the working pack,
under a section heading the working pack renamed from "C. Design and interface" to "C. Configuration and
reversibility" so the section could hold it.

Small stubs and cross-references went with the rules and are **not** reproduced here (they were pointers, not rules):
the `<DESIGN_LANGUAGE>` and `<MOCKUP_DIR>` rows of the Part 3 placeholder legend; the "Reimagine this" and
"Redesign this" rows of the how-to table; the §8.1 decision rows "What the design language is…", "How many
interfaces and themes exist…" and "How the interface's own labels are audited"; the §9.2 "token lint" check-kind
row; the two Part 4 definition-of-done lines (the "every surface" line and the design-language line); the Part 6
"a reimagine starts with a mockup" step and the "interface change (which arrangements)" frame wording; the §2.31
naming-rule reference; the P1 design-language item and its agent-file wording about reading the design language; the
P2 interface-change bullet and its "screen captured in every arrangement" evidence line; the Part 7 example 1
reference to §2.9; and the §10.2 and §10.6 browser references. Each one
is named in `ProjectPack-NOTES.md`, and each is recreatable from the restored sections and their rules.

## Restoring it

Restoring the addendum is a **deliberate change**, not a copy-paste reflex. Decide first whether the game needs the
web rules as they stand, needs a game-specific standard instead, or needs only part of them; record that decision in
`ProjectPack-NOTES.md` §8.1 and bump this pack's revision line (PG-2). Then:

1. Put each section back where it came from, at its original numbers, with two exceptions this copy created.
   §2.9–§2.12 go under Part 2 section C, before §2.13 — but the working pack renamed that section to
   "C. Configuration and reversibility" to hold §2.13, so rename it again to "C. Configuration, reversibility and
   interface" (or move §2.13) and record the rename. The Part 11 rules **cannot** go back at C7NTRY's numbers:
   this copy's Part 11 was re-authored and already uses 11.1, 11.4, 11.5, 11.10 and 11.11 for other rules — give
   them the next free numbers (11.14 onward, or a clearly labelled interface block) and record the mapping in
   `ProjectPack-NOTES.md`. The rest go as written: §2.35 after §2.32; P4 between P3 and P5; P16 between P15 and
   P17; §9.5 between §9.4 and §9.6; §10.7 between §10.6 and §10.8; §10.14 after §10.13 and before Part 11; the
   browser rule at the end.
2. Restore the stubs named above (legend rows, §8.1 rows, §9.2 row, definition-of-done line, Part 6 step, and the
   cross-references), or replace them with their game-side equivalents and say so.
3. Remove the "parked" statements added to this copy's preamble, Part 2, Part 3, §8.1, §8.2 and Part 11, and replace
   them with what is true after restoration.
4. Re-run the checks in `ProjectPack-NOTES.md` ("How this application of the pack was verified") and update it.
5. Keep this file as the record of what was parked, or delete it in the same change and say where its history went.

A game-side interface standard may replace part of this material rather than restore it. That is a legitimate
outcome: record the replacement, keep the reasoning, and do not leave a parked rule silently half-in-force.

---

## The removed material, verbatim

**1. Part 2 — the whole of section C, "Design and interface": its heading and §2.9, §2.10, §2.11, §2.12.**

## C. Design and interface

### 2.9 A reimagine starts with a mockup, and the mockup comes first
- **Trigger:** the operator says *reimagine* a screen, a dialog or a section.
- **Rule:** the first artefact is a static mockup in the project's **real** design language, with the **real**
  words, and it is looked at before any application code is written.
- **Comply:** write it to `<MOCKUP_DIR>`, render it, and **view it** — a mockup nobody looked at is a file, not a
  decision. Include **every arrangement** the screen has (every interface, every theme, every density the product
  supports), use the real tokens and the real shared components rather than approximations, and **state the register
  the design lives in before drawing** — a screenshot plus "make it better" produces something nobody asked for.
  The mockup is **not** the deliverable: the screen still gets its own arrangements, and is still verified on the
  running product. Where a variant is chosen from a set, keep the chosen ones and the rejected ones distinguished,
  and say why each was rejected.
- **Check:** the operator's review of the mockup, then the ordinary verification rules for the built screen.
- **Adapt:** the directory. Keep the ordering — layout is the cheapest thing to change in a mockup and the most
  expensive thing to change in a component tree.

### 2.10 Two interfaces, two designs
- **Trigger:** any interface change, in a product that has more than one interface, theme, or form factor.
- **Rule:** every screen is designed for each **individually**. They are two designs of the same screen, not one
  screen with a class toggled.
- **Comply:** one component, one set of handlers, one set of words, two returns — with the reason for each
  arrangement written at the top of the file. The secondary arrangement is not allowed to be a restyle of the first;
  if the two would come out identical, the feature is a shared component and belongs in the shared library — say so
  in a comment rather than leaving the reader to guess. Verify in **both**, on the running product, and capture
  both. Anything one arrangement deliberately drops belongs in the documentation, because it is a difference the
  user will notice.
- **Check:** the design-token guard, and the captures.
- **Names:** whatever the two are called, pick the names once and use them everywhere — labels, comments, variables,
  documents. Keep reading the old identifier as an alias so nobody's stored preference silently changes; never
  write the old one.

### 2.11 Explain the interface to the user
- **Trigger:** any interface change; any control that shows only an icon or is otherwise ambiguous.
- **Rule:** a control with no text of its own is labelled by **what it does**. "No label" is a legitimate answer,
  but it must be a decision rather than an oversight.
- **Comply:** a resolver that takes the label from the control's own words first, then its accessible name, then its
  title — and only for a control that shows nothing but an icon falls back to the action it performs. **Never let an
  icon's own name speak**: a picture of a key tells a user nothing. Audit it against reality: dump every icon-only
  control from the **running** product, per screen, and compare each against the resolver, so the answer is the
  label a person would actually see.
- **Check:** the audit, run against a real render. A static read of the source cannot answer what a user sees.

### 2.12 The design language is derived, not aspirational
- **Trigger:** any interface change.
- **Rule:** one document describes the tokens, the shared components and the composition rules; it is **derived
  from the code**, a change that uses a raw value instead is a defect, and where a rule in the document stops being
  true it changes in the same commit as the code that changed it.
- **Comply:** a token lint that fails on a new raw literal, with legitimate exceptions listed **in the linter beside
  their reasons**; a shared component library that is checked before inventing a component; and a definition of
  done for an interface change that names the axes to test (interface, theme, colour scheme, density — however many
  the product has).
- **Check:** the token lint, and the document's own section on how to change it.

---

**2. Part 2 — §2.35, a user interface is verified in a browser (with the browser installed rather than hoped for).**

### 2.35 A user interface is verified in a browser, and the browser is installed rather than hoped for
- **Trigger:** any change to something a person looks at.
- **Rule:** a screen is not verified by a type-check, a unit test or a build. It is verified by **loading it and
  looking at it**, and where the environment has no browser tooling, **install it** — that is a prerequisite of the
  work, not a reason to skip the verification.
- **Comply:** put a headless browser in the project's own dev dependencies so every session and every machine has
  it; drive the running application rather than a storybook or a snapshot; keep a script that visits **every
  destination the navigation offers** (derived from the rendered rail, never a list maintained by hand — a typed
  list falls behind the app and the first version of that script reported a 404 screen as healthy because a
  not-found page has a heading like any other); and assert the things a type system cannot see: that the page
  rendered, that no `undefined`, `NaN` or `[object Object]` reached the text, that nothing sits outside the box it
  belongs in, and that no page error was thrown.
- **Why this is a rule and not a preference.** Every user-visible defect this repository has found was found by a
  person looking, and **none of them was findable any other way**: a control drawn across the text it was supposed
  to sit beside; a setting mounted below the fold of a page nobody scrolls; a filter that crashed on the second
  render; a tab label reading as one word. All four typechecked, built, and passed the suite. A type system cannot
  see layout, and a unit test cannot see that a page has become unusable.
- **Check:** not a check in the commit list — it needs a running stack, a browser and seeded data, so it is run
  deliberately while changing a screen and **before claiming a screen works**. What is checked mechanically is the
  weaker half: that the browser is still a declared dependency, so the capability cannot be quietly lost.
- **Adapt:** the tool and the interactions. The requirement is that somebody or something has looked at the
  rendered page, and that the answer is a measurement rather than an assurance.

---

**3. Part 3 — prompt P4, "Reimagine a screen".**

### P4 — Reimagine a screen

```text
Reimagine <the screen or section>.

This follows the mockup-first rule:
1. Before any application code, write a static mockup to <MOCKUP_DIR>/<name>.html: **every arrangement** this
   product has, in the real design language (the actual tokens and the real shared components, no invented
   colours or spacing), with the real words.
2. Render it, look at it, and tell me what you see and what you are unsure about. Do not describe the markup.
3. Wait for my review before building. If I ask for changes, change the mockup and show it again.

When I approve it, build it: the screen keeps its own arrangements (the mockup is not the deliverable), each
arrangement is a design rather than a restyle of the other, and a piece that would be identical in both belongs
in the shared component library instead — say so in a comment if that is what you conclude.

Verify on the running application in every arrangement, and tell me which arrangement each capture shows. Update
<PRODUCT_DOCS> and the rollback document for the layer in the same commit.
```

---

**4. Part 3 — prompt P16, "Self-explanation and accessibility pass".**

### P16 — Self-explanation and accessibility pass

```text
Audit what this interface tells a user about its own controls.

1. Take the real answer, not a guess: dump every interactive control with no text of its own from the **running**
   product, per screen, and compare each one against the resolver that supplies its label.
2. The resolver's order is: the control's own words, then its accessible name, then its title — and only for a
   control that shows nothing but an icon, the action it performs. An icon's own name is never a label.
3. Report every control whose answer is "none", with what the user sees instead, and say for each whether that is a
   decision or an oversight.
4. Then check contrast and focus for anything you changed, and say which theme and colour scheme you checked.
```

---

**5. Part 9 — §9.5, the "Interface" check kinds.**

## 9.5 Interface

| Check | What it compares | Prevents | Rule |
| --- | --- | --- | --- |
| label audit | every control with no text vs the resolver that supplies its label | a user guessing at an icon | §2.11 |
| contrast | the declared colours vs the required ratio | text that cannot be read in one scheme | §2.12 |
| arrangement coverage | every screen vs the arrangements the product supports | one interface designed and the other inherited | §2.10 |
| capture freshness | the captured figure vs the running product | a figure showing a previous design | §2.3 |

---

**6. Part 10 — §10.7, redesigning a live interface: five directions first.**

## 10.7 Redesigning a live interface: five directions first

**Trigger:** the operator says "redesign <surface>", "let's redesign <surface>", or equivalent. This is a standing
instruction: the method does not have to be restated, and it applies to every named surface.

**Rule:** produce **five distinct, full-page mockup directions first**, built from the real product and real data.
Production code, routes, APIs and data do not change until the operator chooses. The mockup is not the deliverable;
the chosen screen is.

**Read before drawing.**

- Read the actual live page and every arrangement it already has: views, tabs, drawers, empty/loading/error states,
  and the narrow layout.
- Read the APIs the surface uses and the real fields they return; note permissions, role gates, tenant scoping and
  which actions are real versus unavailable.
- Read the design language and its tokens: typography, colour, spacing, surfaces, components, motion and responsive
  rules.
- Capture a **date-stamped snapshot** from the live API. The mockups use those real counts, names and states, not
  invented rows or plausible-looking placeholders.
- Keep provenance visible. If data is simulated, partial or agent-reporting, the mockup says so.
- If an action has no real contract, label it unavailable, preview or follow-on. **Never draw a working-looking
  control that does nothing.**

**Five directions, not five themes.**

- Write a one-line thesis for each direction before building it.
- Each direction answers a different question or organises the work around a different unit. A colour change, a
  denser table or the same dashboard with cards moved is not a new direction.
- The set normally covers these arrangements: decision-first landing; exception or queue view; visual gallery or
  cards; single-record dossier; and a grouped/operational view by site, tenant, team or policy.
- Mark one option **recommended**, with a short reason. The operator decides.
- A request for fewer than five is an explicit exception, not the default.

**Build the set.**

- Write it under `<MOCKUP_DIR>/<surface>-redesign/` as `option-a.png` through `option-e.png`, an `index.html`
  gallery, and a `README.md`.
- Every option is a full page at a real desktop size (normally 1440x960), readable at normal zoom, with the real
  navigation and page chrome so it is judged inside the product.
- Use real data and the repository's real design language. Do not invent a second visual language, font or colour
  system.
- Respect every role, permission, tenant/site scope and offline state. Label unavailable actions.
- Do not add a mock-only API, fake write path or mock data that leaks into production.
- Run a narrow-width sanity pass (normally 390 px) even when the delivered screenshots are desktop.
- The README records: the date and live-data snapshot; an Option | File | Direction table with the recommendation;
  what is real, intentionally unavailable or follow-on; and the line **"Mockup only; no live UI changes in this
  pass."**

**Review, then stop.**

- Present all five options together, with the recommendation, and look at every image before reporting. A mockup
  nobody viewed is a file, not a review.
- Do not change production UI, routes, APIs or data during the mockup phase. If the operator asks for changes,
  revise the mockups and show them again.
- Wait for the choice. "Here are five options" is the end of this pass, not a licence to build one unasked.

**Build what was chosen.**

- Make the selected option the default. If more than one was chosen, build the others as real switchable views in
  the operator's order.
- Keep unchosen options documented but dormant: no dead controls, no fake toggles.
- Persist the selected view under the product's own storage convention and support its deep-link convention where
  one exists.
- Implement over the existing real contracts, permissions and data. Preserve every behaviour the old surface had
  unless the chosen direction explicitly removes it.
- Mark the README **Implemented**, naming the chosen default and any switchable views.

**Verify the built screen.**

- Load every chosen/default view in a real browser against the running product; exercise the real actions and the
  empty, loading, error and unavailable states.
- Check the narrow width for overflow and unreachable controls.
- Run the repository's full check list and browser gate, and attach the summary and screenshot evidence to the
  report.
- Update the design language, API docs, build notes and prompt log in the same change. Keep the mockup folder as
  the historical record.

**Adapt:** the surface name, `<MOCKUP_DIR>`, exact viewport sizes, the product's storage/deep-link conventions and
the browser gate. The five-direction, real-data, no-production-before-choice shape does not change.

**This is not the interaction-budget or tone rule.** A project may still choose its own density, tone or
minimalism standard; that is separate from the redesign protocol. What this rule fixes is the **reviewable
protocol**: five real directions, from real data, before production.

---

**7. Part 10 — §10.14, "needs to be more robust" as a redesign trigger, with its required method.**

## 10.14 — "Needs to be more robust" is a redesign trigger

When the operator says **"needs to be more robust"** (or any paraphrase of it), it is shorthand for
**robust, detailed and visually appealing**. Treat it as a full redesign request for the named screen or
section, not a cosmetic polish. The phrase carries four requirements at once:

- **Robust** — every state is designed (empty, loading, error, partial, long content); the primary task is
  obvious; destructive and irreversible actions are guarded; data provenance, limits, permissions and
  next actions are visible where the decision is made; there are no dead controls, no silent failures,
  no clipped labels and no unlabeled icons; keyboard and screen-reader paths work.
- **Detailed** — show the facts a person needs to act: source, time, actor, state, evidence, relationship
  to the finding/application/approval, what happens next, and what will *not* happen. More detail is not
  more noise: remove duplicated explanation, routine log lines and decorative chrome before adding depth.
- **Visually appealing** — a clear hierarchy, one composition rather than a stack of cards, disciplined
  density and alignment, readable contrast, meaningful use of colour (never colour alone), and type and
  spacing that come from the design language. The screen should look intentional at 1440×960 and at
  390×844, not merely responsive.
- **Intuitive and efficient** — the user's first screenful answers "what is this, what needs me, what do
  I do next?"; frequent actions are close; advanced actions are disclosed rather than competing; the
  same object is reachable from every place it appears.

### Required method

1. **Reproduce and measure before designing.** Look at the live screen at 1440×960 and 390×844.
   Record document and panel overflow, the first screenful, the primary action, and the current
   redundancy. A screenshot is evidence; reading the source is not.
2. **State the information hierarchy.** Name the one primary task, the three facts that support it, the
   secondary tasks, and what can be deferred. Design the layout from that order.
3. **Apply the design-theory baseline** (research before the mockup; cite the sources in the plan):
   - Nielsen's ten usability heuristics — visibility of status, match to the real world, user control,
     consistency, error prevention, recognition rather than recall, flexibility and efficiency,
     aesthetic and minimalist design, error recovery, help and documentation.
   - **Recognition over recall**: persistent filters, visible context, recents and command surfaces.
   - **Progressive disclosure**: explanations, advanced filters, evidence detail and policy/limits are
     available on request rather than repeated on every row.
   - **Hick's law and Fitts's law**: fewer competing choices at the top level, larger and closer targets
     for frequent actions.
   - **Master–detail** for queue → record screens: the selected item and its proof stay beside the list.
   - **WCAG 2.2**: keyboard equivalence, visible focus, names for every control, contrast, no
     keyboard trap, status announced.
   - **Power-user efficiency**: command palette, keyboard paths, bulk actions, saved views, shareable
     URL state and bounded scrolling for long collections.
   - **Density by alignment**, not by shrinking text: consistent rows, column alignment, deliberate
     white space and no accidental "card-in-card" padding.
4. **Mockup first, in the real design language and tokens.** Design every distinct arrangement
   separately, with real labels and realistic long content, and include 1440×960 and 390×844 layouts.
   Where this repository explicitly excludes a portable design rule (for example a click budget or a
   second-design requirement), that local exception wins; this rule defines the trigger and standard,
   not a replacement for the repository's visual bar.
5. **Auto-approval.** When the operator says "auto approve" (or gives a standing instruction to proceed),
   record the design decision, implement it and do not stop for mockup approval. Auto-approval never
   applies to destructive, security, authorization or irreversible actions; those keep their existing
   confirmations and gates.
6. **Implement without widening the blast radius.** Use tokens, preserve existing contracts and state,
   keep real data and real actions, and remove only what is genuinely redundant. No mock data in a
   shipped surface, no dead controls.
7. **Verify in the running product.** Re-measure both widths; the document should not scroll by accident.
   If a long collection must scroll, bound it deliberately to its own region and say so. Check keyboard,
   focus return, empty/loading/error/partial states, long labels, a11y and the repository checks.
8. **Record and report.** BuildNotes + Retrace with the computed version, the before/after measurements,
   the design decisions and anything still deferred. A robust redesign is not finished until its
   evidence is in the records.

A response to "needs to be more robust" that only changes colours, padding or a single control has not
answered the request.

---

**8. Part 11 — 11.1 No interaction budget**

## 11.1 No interaction budget

No click-count or minimalist-interface standard is in force. A screen is judged by the pack's rules, by the visual bar
in 11.19, and by a person looking at it.

---

**9. Part 11 — 11.4 Redesigns follow the redesign playbook**

## 11.4 Redesigns follow the redesign playbook

When the operator says "redesign <surface>", follow §10.7: five distinct full-page mockup directions from real data
and the real design language, every arrangement, an explanation matrix, then stop for the choice. Production changes
only after the operator chooses.

---

**10. Part 11 — 11.5 Explanation is a deliverable**

## 11.5 Explanation is a deliverable

Every screen explains itself in the screen: a surface purpose, section sentences, and — for every setting or action —
the seven fields: function, the effect of changing it, impact including the worst case, connected applications and how,
scope and authority, prerequisites and limits, and why it exists. A build that drops descriptions is a regression.

---

**11. Part 11 — 11.10 One interface, three arrangements, named once**

## 11.10 One interface, three arrangements, named once

C7NTRY v1 has **one** interface — the operator console — with three arrangements: desktop (≥1180), rail (900–1180) and
phone (≤900/390). The names are fixed once and used everywhere in labels, code and records. There is no Classic/Modern
split in v1; adding one later is a rule change, not a preference. Every arrangement is designed individually (§2.10)
and verified on the running product.

---

**12. Part 11 — 11.11 Help stays current**

## 11.11 Help stays current

The in-app help is part of the product: every screen, setting and walkthrough is documented, and help is updated in the
same change as the feature it describes. A per-screen Help link is mounted in the product.

---

**13. Part 11 — 11.19 The visual bar**

## 11.19 The visual bar

**This product is judged on how it looks as well as on what it does.** "Functional but plain" is not a finished screen;
it is a screen one pass short. §2.12 requires a derived design language and a token lint — this rule states what that
language has to be *worth*.

| The claim | What has to be true |
| --- | --- |
| It has a point of view | Palette, type scale, spacing and motion are chosen once, recorded in `<DESIGN_LANGUAGE>`, and every screen reads as the same product. Two screens that could belong to different products is a defect. |
| It is composed, not filled | Every screen has a deliberate hierarchy: one primary action, a scan path the eye can follow, and empty space used on purpose rather than left over. |
| It is dense without being crowded | This is an operator tool, so density is the aesthetic — but density is earned by alignment and rhythm, never by shrinking type or removing labels. |
| It survives its own states | Empty, loading, error, partial and long-content states are designed rather than defaulted, and a screen is reviewed in all of them. |
| It is accessible and legible | WCAG AA contrast minimum, visible focus, no colour-only meaning, `prefers-reduced-motion` honoured, real labels instead of emoji (§2.11). |
| It is verified by looking | The §2.35 browser check is run and its captures are looked at, in every arrangement the product has (§2.10). A screen nobody has looked at is not done. |

**What this rule does not license:** decoration that costs a row; gradients, illustration or animation for their own
sake; a redesign without its states; or a handsome screen whose labels do not say what the controls do. **Check:** the
token lint (§2.12), the browser capture and review (§2.35), and the operator's own judgement — which outranks this
table.

---

**14. Part 11 — 11.20 The interface items this copy does not adopt**

## 11.20 The interface items this copy does not adopt

Because §8.2 asks a copy to be honest about what it is *not*: **§10.3** (click budgets and the tone standard for
reimagined screens) and **§10.4** (a requirement to produce a second design of the same screen) are **not in force** in
this repository and are not reproduced in this copy. The reason is the one C7NTRL 1.7 gave and it still holds: this
project imposes no interaction budget on its screens, and it has one interface rather than two. Where they would pull
against each other, 11.19 wins — a budget is a measuring tool for a screen that looks deliberate, not a substitute for
one.

---

**15. Part 11 — 11.23 Design reviews: A is the approved direction**

## 11.23 Design reviews: A is the approved direction

**Trigger:** any request to redesign or reimagine a screen, or to review design directions.

**Rule:** present the directions as **A** (the recommended one), then B, C, D as the alternatives. **A is
auto-approved and built**; the other directions are recorded as *views* — named, with the tradeoff that made A the
recommendation, and where to look — not built into the product. Do not stop to ask which option to build; the operator
has pre-approved A for every redesign. The visual bar (11.19) is what A is judged against, and the views exist so the
alternative thinking is visible rather than lost.

**What this does not license:** shipping a redesign that fails 11.19 because it was "the approved option"; silently
dropping a direction the operator asked to see; or presenting one direction as if it were the only one considered.

---

**16. The standing "Browser verification — Chromium only" rule at the end of the pack.**

## Browser verification — Chromium only (standing rule, 2026-10-25)

Every browser-based verification, mockup capture, screenshot, UI test, accessibility run or manual check in this repository uses **Chromium**, launched from `C:/Program Files/Chromium/Application/chrome.exe` (or the repository's `scripts/playwright-local.mjs`, which defaults to it and force-closes the browser tree). **Microsoft Edge and the Playwright `msedge` channel are never used for verification.** Edge's channel launcher and `browser.close()` stall on this host; a Chromium run that hangs is a harness bug to fix, not a reason to fall back to Edge.

---
