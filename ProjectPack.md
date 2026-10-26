# ProjectPack

**A portable set of standing rules, prompts and checks for AI-assisted software work.**

Drop this into any repository. It applies to any language, any framework and any model, and it names none of them:
where a rule needs a file it says what *kind* of file it needs, and the placeholder in angle brackets is for you to
fill in. There is no product name anywhere in this document, on purpose — a rule that only makes sense inside one
codebase is not a rule, it is a memory of one.

Two audiences, one document:

- **The person directing the work** uses it as a menu. "Run a security sweep", "write the records", "check for
  leaks" all mean what the sections below say, without re-explaining the definition each time.
- **The model doing the work** uses it as instructions. Part 2 is written as rules with a trigger and a check,
  Part 3 is copy-paste prompts, Part 4 is the checklist that decides whether a piece of work is finished, and
  Part 6 is how to run the whole thing.

**Revision:** 2.5 · 2026-10-23 · *the portable body; a copy keeps this line as it was taken, and if it differs from
the source line the copy is behind — see §8.2.* **This copy:** ProjectGypsy, revision **PG-1**, 2026-10-25.

**This copy is ProjectGypsy's.** It was taken from **C7NTRY's `ProjectPack.md` revision 2.5** (2026-10-23, SHA-256
`FC5754DDCDB25535B6808042291C083B6B0BC13F27E36EC8035945AEB70ABE65`), which is itself a merge of four repositories'
standing rules — Parts 1–9 are the portable pack at revision 1.7, Part 10 is the operator's standing rules, and
C7NTRY's Part 11 was its own overlay. Parts 1–10 are the pack as it was taken, with one deliberate exception:
**every rule about how an interface is designed or redesigned has been removed from the working pack.**

**Why that exception.** This repository is a **game**, not a website or a web application. The removed rules assume
a browser product with screens, routes, design tokens, mockups, viewport measurements, a visual bar and a
browser-verification gate — a design system for an operator console. A game's interface and UI/UX requirements are
different, and no game-side interface standard has been decided yet. So those rules are **parked, not in force**:
they are preserved **verbatim** in
[`ProjectPack-ADDENDUM-Interface.md`](./ProjectPack-ADDENDUM-Interface.md), which says exactly what was removed and
how to restore it. Nothing in this pack imposes a design language, a mockup step, a visual bar, a viewport
measurement or a browser gate until the addendum is deliberately restored by a recorded decision.

**What else changed in this copy.** Part 11 has been re-authored for this repository (C7NTRY's Part 11 says of
itself that it is not portable); the mapping from C7NTRY's rules is in
[`ProjectPack-NOTES.md`](./ProjectPack-NOTES.md). The header tables, the placeholder legend, the §8.1 decisions, the
§8.2 inventory and the cross-references that pointed at the parked rules were edited to match. No portable rule
outside the interface material was rewritten.

**Revision history.** The base pack's history is C7NTRY's (1.0 → 2.5). **PG-1** (2026-10-25) is this copy: the
interface design and redesign rules are parked in the addendum, Part 11 is re-authored for a game repository, and
the pack is applied here for the first time.

**The rule of the pack itself:** when a rule here stops being true for the project it is being used on, it changes
in the same commit as the code that changed it. A rule nobody can point at in the code is a wish.

---

## How to use this pack

| If the request is… | Read | Then run |
| --- | --- | --- |
| Anything, on a project that has never used the pack | Part 2, Part 8 | **P1** (bootstrap), then **P2** |
| Any ordinary change | Part 1, §2.1–2.4 | **P2** |
| "Fix this bug" | §2.8, §1.3 | **P3** |
| "Reimagine this" / "Redesign this" | — | **parked** — this is a game; see the interface addendum |
| "Run a security sweep" | §2.15, Part 5 | **P5** |
| "Check for leaks" / a long session of headless or background work | §2.24 | **P6** |
| "Is it done?" / before reporting | Part 4 | **P7** |
| A release | §2.1, §2.18 | **P8** |
| Handing work to a reviewer | §2.27 | **P9** |
| A review round to answer | §2.27 | **P10** |
| A logo, icon, or any generated asset packet | §2.6, §2.7 | **P11** |
| Anything touching permissions, secrets, or scheduled work | §2.14, §2.16, §2.20 | **P12**, **P13** |
| A slow loop, a huge log, a context filling up | §2.19 | **P15** |
| Infrastructure, image, or deploy workflow | §2.21 | **P17** |
| After any change to a running service | §2.25 | **P18** |
| After anything that wrote to a database, session store or filesystem | §2.26 | **P19** |
| Something found and deliberately not fixed | §2.28 | **P20** |
| A distributable artefact — an installer, a package, a client | §2.8 | **P21** |

**The one habit that makes the rest work:** nothing is reported as done on the strength of having written it. Every
claim in a report is attached to an observation — a command that ran, a number that was measured, a screen that was
captured. §1.1 is the law; everything else in the pack is its machinery.

---

# Part 1 — The laws

These generate every rule in Part 2. If a rule there ever seems arbitrary, it is one of these applied to a
particular kind of work.

1. **A claim and a fact must be compared, or the claim is a guess.** Every statement — in code, a comment, a
   document, a commit message, a report — is a claim about something. If nothing compares it with the thing it
   describes, it will drift, silently, and in the direction that looks finished. Prefer a mechanism that compares
   them over care.
2. **Two places that must agree need a mechanism making them agree.** Two lists, two counts, two copies of a
   version, a document and the routes it describes, an asset and the code that draws it. If nothing fails when they
   part, they will part. Where you cannot remove the second place, make the check **exact** — a byte comparison, a
   set comparison, a parse — not a likeliness.
3. **Verify by running, never by reading.** A change is understood when it has been executed and observed, not when
   the diff looks right. Reproduce the symptom before you fix it, and reproduce its absence afterwards.
4. **One source for everything generated.** Every derived artefact — an asset, a stylesheet, a types file, a spec, a
   fallback copy — comes from one source, by a script, and the script fails loudly when the input it expects is not
   there. Anything hand-maintained in two places is a future inconsistency with a delay fuse.
5. **A check that cannot fail is not a check.** Measure the check before trusting it: break the thing on purpose and
   confirm it goes red. A test that passes on the wrong input, a comparison that is always equal, a probe that
   reads a value it never staged — each is worse than no check, because it is reported as evidence.
6. **The measurement decides, not the impression.** When something looks wrong or looks fixed, measure it: pixel by
   pixel, byte by byte, row by row, count by count. And then check *what* you measured: a correct figure about the
   wrong region is the most convincing wrong answer there is.
7. **Prose is part of the change.** Documentation, the product's own help text, the API guide, the changelog and the
   prompt log ship in the same commit as the code. They are not follow-ups; a follow-up is a drift with a nicer
   name.
8. **Every change states what it does about more than one process.** Replica safety, shared state, secret storage,
   outbound calls. A change that is merely correct can still be a deployment defect.
9. **Leave nothing behind.** No leaked process, no temp file, no residue in a database or a session store, no
   half-written record, no marker left set, no commented-out code, no debug print. Clean up in the same task, and
   check that you did.
10. **Report evidence, and report the parts that failed.** A report says what was run, what it printed, what was
    assumed, and what remains unverified. A confident summary of unverified work is the most expensive thing a
    model produces.
11. **Context and time are budgeted.** Every loop has a cost, and the cheapest loop that proves the change is the
    one to run. Filter what you print, cap what you log, do not rewrite what has not changed, cache the expensive
    step — and write down what invalidates the cache, because an uninvalidatable cache is a trap wearing a
    speed-up's clothes.
12. **A gate that nobody can fail is decoration.** Where a rule matters, there is something that fails — and where
    it genuinely cannot be enforced, the exception is written down beside it, with the reason. An undocumented
    exception is how a codebase learns to ignore red.

---

# Part 2 — The standing rules

Each rule: **trigger** (when it applies), **the rule**, **comply** (what doing it well looks like), **check** (what
tells you it still holds), and **adapt** (what changes on a new project). Rules are grouped; the numbers are for
reference, not order.

**Parked in this copy:** the interface design and redesign rules — §2.9–§2.12 and §2.35 in this part, plus P4, P16,
§9.5, §10.7, §10.14 and the interface rules of Part 11 — are held verbatim in
[`ProjectPack-ADDENDUM-Interface.md`](./ProjectPack-ADDENDUM-Interface.md) and are **not in force**. They assume a
web product's screens, design language, mockups and browser; this repository is a game, whose interface and UI/UX
requirements have not been decided yet. Nothing here should be claimed against them.

## A. The record

### 2.1 Records — every prompt, every change
- **Trigger:** every request, including questions, investigations, and requests that change nothing.
- **Rule:** every prompt is logged verbatim, in order, with a status and the change it produced; every completed
  change gets a dated, versioned changelog entry. Nothing is complete while these disagree with the code.
- **Comply:** a **prompt log** (`<PROMPT_LOG>`) that appends the next number, quotes the prompt exactly as written,
  and records status, duration and the version it produced — including prompts that changed nothing, which say so
  explicitly. A **changelog** (`<CHANGELOG>`) whose version comes from a script rather than a guess, with its
  generated copies written by another script. A third check that the source, the generated copies and the
  machine-readable copy all agree, and that the newest entry is first.
- **Check:** a records guard that fails when they disagree or when a version exists in one and not the others.
- **Adapt:** the file names and the fallback destinations. **The shape is what to keep** — log, changelog,
  generated copies, one guard. Get the version from a script on the first day, or the numbering is a guess forever.

### 2.2 The published contract is part of the change
- **Trigger:** any change to an interface others depend on — a route, a message, a schema, a CLI flag, a permission,
  an auth requirement, a request or response shape.
- **Rule:** the generated specification **and** the written guide change in the same commit as the interface.
- **Comply:** regenerate the spec, then run the check that fails when the document is behind the implementation,
  when it documents something that no longer exists, or when a curated human-written entry names something that was
  renamed. Prose a parser cannot invent — a summary, an example, a note about behaviour — lives beside the spec in a
  curated file keyed by the operation's identity.
- **Check:** a contract guard. Run it after any interface change, alongside whatever checks the routes themselves.
- **Adapt:** whatever serves the role — OpenAPI, protobuf, GraphQL, a typed client, a message schema. The rule is
  that the document is generated from the implementation **and checked against it**, never written alongside.

### 2.3 The product's own documentation is part of the change
- **Trigger:** any feature added, changed or removed; any flag, environment variable, default or user-visible limit.
- **Rule:** the documentation the user reads changes in the same commit.
- **Comply:** update the feature's walkthrough or add one; add its rows to the index, which is where people look for
  something they cannot name; update the configuration reference if a setting is involved; add a FAQ entry if a user
  would plausibly ask about it. Where the walkthrough has figures, capture them from the running product — **and
  read the captured file back**, because a screenshot tool can paint a stale frame — with a caption that says what
  to notice rather than naming the picture.
- **Check:** a links guard: every documented link resolves to a real destination, and every walkthrough is reachable
  from the index and the documentation's home.
- **Adapt:** the documentation surface. If the product has none, this rule creates one. If it is an external site,
  the rule is still about making the update *part of the same commit* rather than a separate ticket.

### 2.4 Prose inside the artefact counts as prose
- **Trigger:** any change that leaves a heading, a note, a row of a table, a comment or a summary describing
  something that has moved.
- **Rule:** a stale sentence inside the product is a defect of the same kind as a stale copy of the code, and it is
  found the same way — by comparing, or by building the sentence **from the value** instead of repeating it.
- **Comply:** prefer generated text to repeated text (a note that reads the constant, a table that reads the
  configuration); where it must be written, re-read it as part of the change. A heading is a claim like any other.
- **Check:** the same guards as §2.1–2.3 cover the parts that are structured; the rest is a habit of reading what
  you touched.

## B. One source, and everything derived

### 2.5 One source for anything that exists twice
- **Trigger:** any asset, spec, list, count, stylesheet or type that exists in more than one place.
- **Rule:** one source, one generator, one staleness check. Never hand-edit a generated file.
- **Comply:** put the definition in a module both the runtime and the generator read; have the generator write every
  derived file; give it a **`--check` mode that writes nothing and names every file that is not what the source
  would produce**; wire that into the same check list as everything else. When the derived artefact is visual,
  generate it from the **same numbers** the drawing uses — an asset rasterised from a description that differs from
  the one being drawn can arrive wrong in exactly one place.
- **Check:** the generator's `--check`, run wherever the other checks run. A stale derived artefact usually still
  *looks* correct, which is why this is a byte comparison and not a review.
- **Adapt:** nothing. This transfers whole, and it is the highest-value rule in the pack.

### 2.6 The brand and asset packet
- **Trigger:** any identity asset — a logo, an icon, a favicon, a letterhead, a document mark, a watermark.
- **Rule:** the mark is drawn from one source, and every size, mask, flat, and download is generated from it. Never
  ship a mark that is a crop of a raster.
- **Comply:** a vector or geometric source; generated masks, so one layer can paint in the active theme's ink while
  the brand colour is overprinted, rather than a flat image on a plate; **knock-outs as real holes** rather than a
  shape filled with an assumed background colour, so the mark works on any surface without a second asset;
  downloads offered as the vector plus the flats; and a README recording what each asset is **and which attempts
  were rejected and why** — the rejections are what stop the next person redoing them.
- **Check:** the generated-asset check (§2.5), plus a measurement of the rendered result (§1.6).
- **Adapt:** the directory. Keep the "everything generated, knock-outs are holes, rejections documented" shape.

### 2.7 Declare configuration before reading it
- **Trigger:** any new setting, flag, environment variable or default.
- **Rule:** a read of configuration names a field that is **declared** somewhere — with its type, its default, and
  whether it is secret — and a secret field is withheld from reads.
- **Comply:** declare the field, then read it; let a guard fail on an undeclared read; document the flag or default
  in the user-facing reference in the same commit (§2.3). Never scatter string literals for configuration names.
- **Check:** a config-reads guard.
- **Adapt:** the registry mechanism. The failure this prevents is universal: a setting a screen reports and the code
  ignores.

### 2.8 Anything you ship is stamped, and the stamp is checked
- **Trigger:** a distributable artefact — an installer, a package, a client, a plugin, an add-in.
- **Rule:** the artefact carries an identity and a hash of what it was built from, and a check fails when the
  payload changed without the identity changing.
- **Comply:** a record file holding the version and the payload hash; a script that bumps it rather than a person;
  a check that fails when the hash moved and the version did not; the artefact built from that record. **Serve the
  artefact from the product itself** rather than from a third party's public URLs, so distribution does not depend
  on somebody else's hosting — which is also what stops an unrelated change (a host renaming a path, a repository
  changing visibility) from breaking a user's install.
- **Check:** the artefact guard, proved to fail before it is trusted (§1.5).
- **Adapt:** the record's contents and where the artefact is served from.

## C. Configuration and reversibility

### 2.13 Reversible by default
- **Trigger:** any change to a layer the product can be configured around — an interface, a palette, a navigation
  mode, a subsystem.
- **Rule:** the layer's document states how to turn it off, and the document says how the change is verified.
- **Comply:** a rollback document per layer at a known location, kept true as the layer changes. Where the reversal
  is mechanical, ship it as a **script** with a selector, a dry run and a direction (`-Enable` to put it back), plus
  a restart option so the change is visible after it runs. It is also the test of whether the author understood the
  change: if it cannot be turned off, the design is not finished.

## D. Authorization and secrets

### 2.14 A permission authorises something, or says that it does not
- **Trigger:** any change to a permission, a role, or a guard on an interface.
- **Rule:** every permission is read by something, or its register row states that it is not. A permission offered
  to a person and read by nothing is a claim the product does not honour.
- **Comply:** guard the operation by the key named after it; make the **screen's own gate ask for the same key the
  operation asks for** (two places that must agree — §1.2); when retiring a key, remember it is a data migration
  against grants somebody may have made deliberately; and when you change what an operation requires, **preserve
  access** by migrating the stored grants rather than silently widening or narrowing them.
- **Check:** enforcement and label guards (every permission is read by something or says it is not; no two keys in a
  group read identically), and a navigation check that every row asks for the permission its destination requires.
- **Top tier:** if the product has a super-admin, state it as a **mechanism** rather than folk memory — it holds
  every permission by definition, and a gate that refuses it is a defect. Careful: a stored role row that omits the
  always-granted keys is normal, so compare the **effective** set and not the stored list, or a tool will report
  permissions missing that are not.

### 2.15 A security sweep means a defined scope, not a feeling
- **Trigger:** the operator says *run a security sweep*, and before any go-live.
- **Rule** (the standing definition, in four parts):
  1. Check the **bug classes this codebase has actually produced findings in**, deliberately, and the dependency
     vulnerability database.
  2. Fix what is found, unless the fix would break the application.
  3. Plan, fix and verify against the migration-readiness questions (§2.20) at the same time.
  4. Write the sweep up as a document a reviewer can reply to, and update the documents that describe the risks.
- **Comply:** run the dependency audit **including development dependencies**, and say for each finding whether it
  **ships** — a dev dependency that never enters the runtime image is a different size of problem. For every finding
  you do not fix, state why, with the evidence: "no patch published" is an answer; a patch range that excludes every
  published version is the evidence for it. Then sweep the bug classes rather than reading generally. **Build the
  class table from the project's own history** — for a codebase that has been swept before, the recurring shapes are
  knowable, and they are what a sweep should start from rather than a scanner's opinion. Four shapes that recur
  widely, as a starting table:
  | Class | What it is |
  | --- | --- |
  | A permission granted and read by nothing | authorization that authorises nothing |
  | A setting a screen reports but the code ignores | a claim the runtime does not honour |
  | A warning written to a channel nobody reads | a signal with no reader |
  | A flag honoured on one path and not its sibling | the same value treated two ways |
- **Check:** the written sweep, plus whichever guard covers each class.
- **Adapt:** the class table — it is the part that is specific to a codebase, and the part that makes a sweep better
  than a scan.

### 2.16 Secrets discipline
- **Trigger:** any credential, key, token or environment file.
- **Rule:** nothing secret in the repository, ever — and the checks that look for it must not be quietly weakened.
- **Comply:** a secret scanner over the working tree **and the history**; a **credential gate** on any automated
  push that refuses a token instead of committing it, **with a test proving it refuses a token and does not refuse a
  harmless fixture** — a gate that refuses everything is as broken as one that refuses nothing; secret fields
  withheld from configuration reads (§2.7); secrets read from a managed store through an identity rather than a
  static credential (§2.20).
- **Check:** the secret-scan job, and the credential gate's own test. Where a gate's test only applies on one
  platform, have it **report that it does not apply** elsewhere rather than failing for a reason nobody can act on.

## E. Correctness and verification

### 2.17 A bug is reproduced before it is fixed
- **Trigger:** any report of something not working.
- **Rule:** reproduce it first. Do not fix a bug you have not seen.
- **Comply:** produce the reproduction, show it, then state the cause in one sentence before changing anything. Fix
  the cause, not the symptom. Afterwards, reproduce the **absence** — and check the neighbouring paths the fix could
  have broken. Fix bugs your change causes; report unrelated pre-existing problems rather than fixing them (§2.28).
- **The visual case, which is where this rule is most often skipped:** measure rather than describe — the pixel, the
  colour, the gap, the row, the count. And **when the report comes with a screenshot and your own capture disagrees
  with it, measure both before deciding which is wrong**: a stale screen and a wrong file look identical in a
  conversation, and they have different fixes. Worked example in Part 7, case 2.

### 2.18 Verification is evidence
- **Trigger:** before reporting anything as done, fixed or working.
- **Rule:** produce the observation. Every claim in the report is attached to something that was run.
- **Comply:** run the product rather than reading the diff; capture the screen; read the value back; run the guard;
  execute the migration against a scratch database; boot the surface with the slow part delayed when the question is
  about what paints **first**. When you write a probe, **first confirm the probe can fail** (§1.5) — and when a
  measurement disagrees with your impression, believe the measurement and then check the measurement's own
  assumptions: its grid, its coordinate space, which element it read, whether it staged its input, and whether the
  region it measured is the region in question (§1.6).
- **Check:** Part 4's checklist, and the project's check list.

### 2.19 The token and context budget is a design constraint
- **Trigger:** any change; and whenever a loop is slow, a log is huge, or the context keeps filling up.
- **Rule:** spend context deliberately — the smallest output that answers the question, the cheapest loop that
  proves the change.
- **Comply:** filter noisy tool output to what changed rather than printing everything; cap and rotate logs; write a
  file only when its content changed; cache an expensive preparation step keyed by a hash of its input **and write
  down what invalidates it** — a cache nobody can invalidate is a trap that looks like a speed-up, and the classic
  instance is a preparation step skipped because an input hash was stale, so a schema change never reached the
  database; memoise the expensive part of a model prompt, truncate the large field, make the model overridable;
  pause polling while the view is not visible. Make each optimisation **individually revertible** with a marker
  comment and a one-line revert instruction, so one can be rolled back without disturbing the others.
- **Check:** measured, with before-and-after figures and a revert per option. A budget that is not measured is a
  preference.
- **Adapt:** the specific optimisations. The principle is that context and time are budgeted, the optimisations are
  separable, and every cache has its invalidation written down.

### 2.20 Every change is made ready to scale and to move
- **Trigger:** every change, as a standing constraint rather than a project.
- **Rule:** state what the change does about **four questions**, or say plainly that it does nothing and why:
  1. **Will it run on more than one instance?** Anything scheduled, repeated or polling either takes a **claim or
     lease** — one instance at a time, with a takeover when an owner dies — or is **provably idempotent**. Work that
     runs per replica provisions twice, bills twice, or mails twice.
  2. **Where does its state live?** In the database or a shared store, never in a process-local map. An in-memory
     registry, challenge store or session map is a blocker before more than one instance, and is worth naming as one
     when you find it.
  3. **Where do its secrets live?** A managed secret store read through an identity — never a static credential, a
     committed environment file, or a secret in code — and per environment, never shared.
  4. **What does it call, and how does it leave?** Every outbound call goes through the one egress path, which
     applies its rules to the URL **and to every address it resolves to**. In a cloud deployment a new destination
     is also a network change, so it is a change to two things.
- **Check:** the change's own statement, plus a guard where the mechanism is checkable. A guard whose subject is
  unrecoverable — data encrypted under a key that must not change — is worth building first, because its failure is
  silent and its loss is permanent.

### 2.21 Check what can be checked before you deploy
- **Trigger:** any change to infrastructure, a container image, or a deploy workflow.
- **Rule:** what cannot be exercised without a subscription is still checked as far as it can be — and the
  workflow's own shell is **executed**, not read.
- **Comply:** validate templates with the real tool (the same check the cloud CLI performs), and **print how to
  install that tool when it is missing** rather than failing obscurely; run a preflight that reports the environment
  facts, including whether every value the templates read is exported by the script that invokes them; and run the
  deploy workflow's shell through a shell. That last one exists because a comment placed **between the
  backslash-continued arguments of a command ends the chain**: the next line is swallowed and the invocation arrives
  silently truncated — a command missing its registry and identity, which nothing could see by reading.
- **Check:** the preflight, the template validation, and the workflow-shell check.
- **Adapt:** the tool names. Keep the three-way split — template, workflow, environment contract — because each
  fails differently.

## F. Operations

### 2.22 One list of checks, and every caller reads it
- **Trigger:** after any change; and whenever a check is added.
- **Rule:** one file names every check; the pre-commit hook and CI both run it; a third check fails when the two
  lists diverge in either direction.
- **Comply:** add the check to the list, to the runner's script entry, to CI, and to the coverage map — in the same
  commit. Mark each as blocking or **reported**, and say why. A check that is red for a reason that is not any
  committer's is reported rather than enforced; a check that needs a tool the machine may not have is **skipped**
  rather than failed, because a machine without the tool has been told nothing.
- **Check:** the coverage guard.

### 2.23 A hook is a convenience; the gate is CI
- **Trigger:** adding a check, or relying on one to run.
- **Rule:** hooks live **in the repository** — tracked, versioned, installed by the ordinary install step — and are
  never the only enforcement; a hook can be bypassed with a flag and does not exist on a machine where nobody
  installed anything.
- **Comply:** a tracked hooks directory the install script points git at, with the installer's own failures silent
  on purpose (it also runs when the package is consumed as a dependency); the same list run by a CI job that has no
  bypass; the list itself living in one file that both callers read (§2.22). Have the hook do the regeneration that
  must never be stale — and **stage the regenerated file**, so a commit cannot carry a stale copy.
- **Check:** the coverage guard, and the CI job.

### 2.24 Leave nothing running
- **Trigger:** after any headless browser, dev server, watcher, container or long-running process; and whenever a
  session has been long or busy.
- **Rule:** a resource you started is a resource you stop, and you verify it before finishing.
- **Comply:** give every rig one job, and make it kill exactly what it started, identified by an **exact marker**
  (a profile directory, an explicit name, a container label). Refuse to touch anything you did not create — another
  session's browser or port is not yours to kill. Provide a **leak report as a command**, so a leak is found by
  running something rather than by the owner opening a task manager. **Never terminate by process name**: kill by
  the specific identifier you created.
- **Check:** the leak report, run as the last step, with its line in the summary.
- **Adapt:** a resource leak is universal and the numbers are not small — a handful of forgotten browser instances
  is tens of processes and tens of gigabytes. If more than one session will use the rig, put the rig in the
  repository rather than in a session folder.

### 2.25 A health check after the change
- **Trigger:** any change to a running service.
- **Rule:** there is one command that answers "is the system well?", and it is run after the change rather than
  reasoned about.
- **Comply:** a verification script that exercises the service's own health path and prints what it found; run it as
  the last step, and put its output in the report. If no such command exists for the surface you changed, write the
  smallest one that answers the question — it is cheaper than the next debugging session.

### 2.26 Test rigs clean up after themselves
- **Trigger:** anything that writes to a database, a session store or the filesystem in order to test.
- **Rule:** a probe that leaves residue corrupts the next run, and the sweeper is part of the rig rather than an
  afterthought.
- **Comply:** sweep **by command**, with a dry run and an apply mode; clean up in a `finally` where you can, and
  know what a hard kill leaves behind — a `finally` does not run on a forced termination, which is exactly why a
  sweeper exists as well as a cleanup.

### 2.27 Reviews are answered in writing
- **Trigger:** a review round from a person or another model.
- **Rule:** answer each point in a document, with its **premises checked** and its proposed fix **tested** before it
  is adopted.
- **Comply:** a finding can be right about the symptom and wrong about the cause, and a reviewer's proposed fix can
  be impossible in the platform — say so, and name the reason (a template language with no hash function, an API
  that returns nothing useful in the environment that matters, a permission the platform does not grant). Say which
  points you confirmed, which you adjusted and why, and which you are declining and why, quoting the evidence for
  anything you assert. Where the review asks something you cannot answer from the machine you are on, say so and
  record it as **open** rather than guessing. Number the paragraphs so the next round can reply to them.
- **Check:** the reviewer's next round; the documents are the artefact.

### 2.28 A register of the work you deliberately did not do
- **Trigger:** finding something and choosing not to fix it.
- **Rule:** it goes in a register — what it is, where it is, why you did not fix it, what would break if somebody
  fixed it casually, and whether the decision belongs to the operator.
- **Comply:** one document (`<DEFERRED_REGISTER>`), read before changing the area it covers and updated when an item
  is done or its reason changes. **Not** a code comment, and not only a line in your summary: if it is not in the
  register, the next person will re-find it or, worse, half-fix it.

### 2.29 The auto-publisher does not publish surprises
- **Trigger:** a machine or script that commits and pushes on your behalf.
- **Rule:** it must not publish work that is merely **quiet**. A builder that is reading, thinking or running a
  verification writes nothing for minutes at a time and looks exactly like one that is finished.
- **Comply:** a **hold marker** for multi-step work, removed when the work is committed; a **size refusal** above a
  number it can name — files **and** inserted lines, because a rename is many files and a generated file is many
  lines; refusals that instruct the **right** remedy and leave the tree in a state the operator can see; a marker
  file recording how long it has been held, because "nothing has been pushed for six hours" should be a file you
  find rather than an inference you make; and a **credential gate** so it refuses a token rather than committing it
  (§2.16).
- **And the opposite mistake to avoid:** do not make it refuse code without a records update. That rule reads well
  and measures badly — most commits carry no records — and it is a proxy anyway, since records can be written
  before the work is finished, at which point a half-built change looks complete.

### 2.30 Machine-level automation belongs in the repository
- **Trigger:** anything that runs on a schedule, or at boot, on somebody's machine.
- **Rule:** the script, its registration and its runner shim are committed, and the reason for each is written
  beside it. Machine state is neither a gate nor documentation.
- **Comply:** registration scripts for each scheduled task; a console-less runner where the scheduler would
  otherwise flash a window — **with a comment saying why**, because "a hidden shell" looks like a mistake to the
  next reader; and an operator-facing note for the manual steps.

### 2.33 A peer project is separate unless someone says otherwise
- **Trigger:** more than one project in the same organisation, account or workspace — especially when the same
  person or the same model works on both.
- **Rule:** a prompt, a change or a record belongs to the project it was asked in. Nothing crosses — not a file, not
  an entry, not a cross-reference — unless the person directing the work says to cross explicitly.
- **Comply:** state the boundary where the next session will read it *before* it starts, in the instructions file
  rather than in a log, because a log is read after the fact. If a request turns out to concern the other project,
  say so and let that project's session do it: **reaching across to do it "because it is quick" is the crossing.**
  Where a session genuinely has to touch both, have been told to, each repository records only its own side.
- **Check:** this is a claim of the kind that never holds on its own — *"the two logs do not mix"* — so compare the
  facts with a script. Read each record file as **blocks** and fail on any block that names the peer without
  carrying an explicit marker; fail on any tracked file holding a path into the peer's directory or its remote. Make
  the marker the *only* exemption, so a note about the separation is allowed and is visible to a grep, and a note
  that has crossed is not.
- **Two consequences worth expecting.** Two sessions appending to one record file will collide on **prompt numbers**
  as well as on content, because both count from the same last entry — so a number collision is a symptom of a
  crossing rather than a separate fault. And a peer repository needs the *mirror* of the check, which is work for a
  session standing there; installing it from here would be the thing the rule forbids, so record it as outstanding
  instead.

### 2.32 Text, quoting and the shell
- **Trigger:** any file written — and especially any file written *through a shell*.
- **Rule:** never round-trip text through a tool that may reinterpret it, and never let a byte-order mark decide
  whether a script parses.
- **Comply:** read and write text with the language's own file APIs wherever you can; keep scripts ASCII, or make
  the encoding explicit; and when a shell must be involved, **check what it wrote rather than what you asked for**.
  The failures are silent and all of them are real: a redirection that writes a different encoding; an explicit
  "as UTF-8" that adds a byte-order mark; a script with no mark and non-ASCII content that **fails to parse**
  because the interpreter reads one of its characters as a quote; a here-string piped through a shell that mangles
  the very punctuation the script matches on — so a `replace` looking for an em dash silently matches nothing and
  the script never does the edit it was written to do. Where a mark is deliberate, say so in the file and add a
  check that fails **by name** when it is missing.
- **Check:** an encoding guard over the tree that fails on double-encoded text, plus reading the file back after
  writing it.
- **Adapt:** the tooling. The trap is not specific to any platform: shell quoting is a transformation, and the
  output of a transformation has to be inspected.

### 2.34 Context is a budget, and running out of it is a state to be handled
- **Trigger:** any session long enough that the conversation, rather than the work, becomes the constraint.
- **Rule:** a session that is about to reach its context limit **secures what it has before it continues**, and the
  securing is a commit, a record and a written handover — never a hope that the next turn will fit. Work that has been
  thought through but not yet written down is the only irreplaceable thing in a session, and it is lost silently:
  there is no error, no failing check and no half-written file, only work that a later reader cannot tell was ever
  done.
- **Comply:** in this order, stopping at the first step that is enough — **commit** what is finished and verified,
  with its record entry, so that the repository is the memory rather than the conversation; **write the remaining
  design into a file in the repository** rather than into a message (the register, the decision draft, the deferred
  list), because a decision that exists only in a transcript is a decision the next session will make again and make
  differently; then **compact the conversation or start a new session**, and have the new one read the records before
  it writes anything. A change that is half-built is worse than one not started: the tree either compiles or it does
  not, and nobody reading it can tell an abandoned edit from a finished one.
- **Check:** the records themselves. A session that ends with an uncommitted tree, or with its plan in a chat message,
  fails this rule in a way a records guard cannot see — which is why the guard here is the commit rather than a
  script. The one mechanical part is that the handover has to name the *next* thing, in the order it should be done.
- **Adapt:** the mechanism. Some environments compact a conversation, some open a new one, some keep a scratch file
  outside the repository; the requirement is only that the next reader can reconstruct the work without the previous
  reader's conversation.

### 2.31 Say which of these applies, or say none does
- **Trigger:** every change.
- **Rule:** the record rules (§2.1–2.3) and the four questions (§2.20) are answered explicitly. A change that
  touches none of them says so in one line, and that line is cheap.

---

# Part 3 — The prompt pack

Copy a prompt, replace the `<…>` markers, send it. Each is written to be self-contained: a model that has never
seen this document should be able to follow the prompt alone, and a model that has read it will recognise the rules
behind each step.

**Two prompts are parked in this copy.** **P4** (reimagine a screen) and **P16** (self-explanation and accessibility
pass) are held in the interface addendum and are not in force. Prompt numbers are stable identifiers rather than
positions, so the list has gaps where they were removed; do not renumber the remaining prompts.

**Placeholder legend** — substitute your project's own names once, then reuse:

| Placeholder | What it is |
| --- | --- |
| `<PROMPT_LOG>` | the file every prompt is appended to |
| `<CHANGELOG>` | the dated, versioned changelog |
| `<GUARD_LIST>` | the one file naming every check |
| `<CONTRACT_ARTEFACT>` | the generated interface specification |
| `<CONTRACT_GUIDE>` | the written guide for whoever integrates |
| `<PRODUCT_DOCS>` | the product's own documentation source |
| `<DEFERRED_REGISTER>` | the register of work deliberately not done |
| `<HEALTH_COMMAND>` | the command that answers "is this well?" |
| `<SWEEP_COMMAND>` | the command that clears test residue |

### P1 — Bootstrap a project (run once, first)

```text
Set up the working rules for this project before any feature work. Create and commit:

1. A prompt log at <PROMPT_LOG>. Number every prompt from 1, quote it verbatim, and record status, duration and
   the change it produced — including prompts that change nothing.
2. A changelog at <CHANGELOG>, dated and versioned, with generated copies at <path A> and <path B>. Write
   <version script> to compute the next version, <generator script> to write the copies, and <records check> to
   fail when the three disagree or the newest entry is not first.
3. A check list: <GUARD_LIST> naming every check, with a script entry per check, a pre-commit hook that runs the
   list, a CI job that runs the same list, and <coverage check> that fails when the hook's list and CI's list
   differ in either direction. Hooks live in the repository (a tracked directory the install step points git
   at), never in a machine's own config.
4. A rollback document per configurable layer, stating how to turn it off.
5. A register of deferred work at <DEFERRED_REGISTER>.
6. The agent instruction file (whatever this project's models read first — AGENTS.md, CLAUDE.md, a
   copilot-instructions file), telling a model to read this pack and the check list before reporting anything
   finished.

Then run the whole check list and show me the output. Report what is already green, what is reported rather than
enforced and why, and anything you had to assume. Tell me which of the rules in this prompt the project cannot
support yet, and what it would take.

The interface design material in `ProjectPack-ADDENDUM-Interface.md` is parked: do not create its design-language or
mockup scaffolding as part of this bootstrap unless the operator says to restore it.
```

### P2 — Implement a feature

```text
Implement <the feature>.

Before you write anything, state in one line each:
- whether this changes something a player will see or hear (and so has to be looked at running),
- whether it changes a published contract (and so needs <CONTRACT_ARTEFACT> and <CONTRACT_GUIDE>),
- whether it adds or changes a setting, flag or default (and so needs <PRODUCT_DOCS>),
- which generated artefacts are affected (and so which generator must be re-run),
- whether it changes what a permission requires,
- and what it does about more than one process: replica safety, where state lives, where secrets live, what it
  calls and how it leaves.
Say "none" and why for any that do not apply.

Do the work in the smallest complete steps, and verify each by running the system rather than reading the diff.

When you are done:
- Record it: <PROMPT_LOG>, <CHANGELOG> with a script-computed version, regenerated copies.
- Run the check list and paste the summary line.
- Show me the evidence: command output, measured values, and a capture of what changed while it ran.
- Tell me what you assumed, what you could not verify and why, and anything you found and deliberately did not fix.
```

### P3 — Fix a bug

```text
Fix: <the symptom, and how to reproduce it>.

1. Reproduce it first, and show me the reproduction. If you cannot reproduce it, say so and stop — do not fix a
   bug you have not seen.
2. Find the cause, not the symptom, and tell me the cause in one sentence before changing anything.
3. Fix it with the smallest complete change. Fix bugs your change causes; report unrelated pre-existing problems
   instead of fixing them.
4. Reproduce the *absence* of the symptom, and check the neighbouring paths your change could have broken.
5. Record it, and run the check list.

If the symptom is visual, measure it — the pixel, the colour, the gap, the row, the count — rather than
describing it. If the report came with a screenshot and your own capture disagrees, measure both before deciding
which one is wrong: a stale screen and a wrong file look identical in a conversation.
```

### P5 — Run a security sweep

```text
Run a security sweep. This has a standing definition; follow it exactly.

1. Dependencies: run the audit including development dependencies. For every finding, state whether it *ships* —
   does it reach the runtime image or the deployed artefact? For every finding you do not fix, say why, with the
   evidence (a patch range that excludes every published version is evidence; "no patch" is not). Fix what has a
   patch, and test the fix rather than reasoning about it, especially if it is a major-version override.
2. Bug classes: sweep the classes this codebase has actually produced findings in — not a general reading. Start
   from the register of past findings and name the classes; then check each deliberately and report the result for
   each, including "none found". If there is no such history yet, start from these four and add to them:
   a permission granted and read by nothing; a setting a screen reports but the code ignores; a warning written to
   a channel nobody reads; a flag honoured on one path and not its sibling.
3. Stay ready to scale and move: for anything you find, answer the four questions — multi-instance safety, where
   state lives, where secrets live, what it calls and how it leaves.
4. Write it up as a document with a section per area, a table of findings with a severity, what you did about each,
   and the parts you did not check — so a reviewer can reply to specific paragraphs.

Report the raw numbers, the commands you ran, and anything you could not check from this machine and why.
```

### P6 — Check for leaks

```text
Check for leaked resources and clean up anything you started.

- Report every <browser/server/container/watcher> instance you or a previous session started, by its exact
  identifier (its profile directory, its explicit name, its label), with its memory or resource use.
- Kill only what belongs to this project's work, by that exact identifier. Never kill by process name, and never
  touch something you did not create — another session's is not yours.
- Leave the tree and the session clean: no temp files, no running background command, no hold marker left set, no
  residue in a database or session store.
- When I say **"clean up after yourself"**, extend this audit to every active session on the machine: clean only
  orphaned resources whose owning session has ended, leave active servers, watchers, tests and another session's work
  alone, and report what was left with its exact identifier.
- Finish by running the leak report again and telling me the count is zero.
```

### P7 — Verify a change before reporting it done

```text
Verify <the change> and give me evidence, not assurance.

For each claim you intend to make, produce the observation:
- It runs: the command, and its output.
- It is correct: the measured value, not an impression — a count, a byte size, a pixel, a row, a response body.
- It did not break its neighbours: the checks that cover what you touched.
- The check list, with its summary line.

Then tell me plainly:
- what you assumed,
- what you could not verify and why,
- what you did not do that I might expect (unfixed unrelated problems, deferred work, unproven paths),
- and what the weakest part of this change is.
A short report with those four lines is worth more than a long confident one without them.
```

### P8 — Record and release

```text
Record and release this change.

1. Append the prompt to <PROMPT_LOG>, verbatim, with the next number.
2. Add a changelog entry to <CHANGELOG>: get the version from <version script> — do not guess it — and write
   concise bullets in the house style (New / Update / Fix), with verification where relevant.
3. Regenerate the fallbacks. Do not edit a generated file by hand.
4. Run the records check and the check list; paste both summary lines.
5. Commit with a message that says what changed and why, and push.
6. Confirm after pushing that the newest entry is first in the changelog source *and* in both generated copies,
   and that the three agree.
```

### P9 — Hand the change to a reviewer

```text
Write a hand-off for this change, for a reviewer who has the repository but not this conversation.

Include: the commit range; what the change is for; the design it follows and the alternatives you rejected, one
line each; every file that matters and why; the evidence (commands, output, measurements, captures); the
assumptions you made; the parts you know are weak or unverified; anything you deliberately did not do; and the
questions you would most like answered. Number your paragraphs so the reply can reference them.
```

### P10 — Answer a review round

```text
Answer this review, point by point, in <a numbered document>.

For each point:
- Verify its premise before you accept or reject it. A finding can be right about the symptom and wrong about the
  cause, and a proposed fix can be impossible in this platform — if it is, name the reason and say what the
  consequence would be if it were attempted.
- Say which you confirmed, which you adjusted and why, and which you are declining and why.
- Quote the evidence for anything you assert.

Then state plainly what you have not addressed, what remains unproven from this machine, and any question you
cannot answer without resources you do not have — record those as open rather than guessing at them.
```

### P11 — Build a brand or asset packet

```text
Build the identity assets for <the project>, from one source.

- The source is vector or geometric and it is the only place the mark exists. Every size, mask, flat, favicon and
  download is generated from it by a script with a `--check` mode.
- The mark must work on light and dark without a second asset: paint one layer with the inherited ink and
  overprint the brand colour, and make any knock-out a **real hole** rather than a shape filled with an assumed
  background.
- Generate the raster from the same geometry the vector is written from, so the two cannot disagree about the
  shape.
- Add a download surface offering the vector and the flats, and a README recording what each asset is and which
  attempts were rejected and why.
- Wire the staleness check into the check list, and verify by measuring the rendered result rather than looking
  at it.
```

### P12 — Scale-and-move readiness review

```text
Review this change against the four questions, and answer each in writing:

1. Will it run on more than one instance? If it schedules, repeats or polls anything, it must take a claim and
   release it (with a takeover path when an owner dies) or be provably idempotent. Name which, and where.
2. Where does its state live? If it is in a process-local map, it does not survive a second instance. Say what you
   moved, or why it is safe.
3. Where do its secrets live? No static credential, no committed environment file, no secret in code. Say how the
   secret reaches the process.
4. What does it call, and how does it leave? Every outbound call goes through the one egress path, which checks the
   destination *and every address it resolves to*. A new destination in a cloud deployment is also a network
   change — say so.

If a question does not apply, say "none" and why. Then state the two things that are easy to get wrong: whether
this is exercisable in the pre-production environment, and whether it assumes two independently deployable halves
where the product ships as one.
```

### P13 — Change a permission or a gate

```text
Change <the permission or gate>.

- Every permission either is read by something or its register row says it is not — check which this is, and do not
  leave a key that authorises nothing without saying so.
- Make the screen's gate ask for the same key the operation asks for. Two places that must agree need a mechanism,
  so add or extend the check that fails when they stop agreeing.
- If you change what an operation requires, preserve access: migrate the stored grants rather than silently widening
  or narrowing them, and test the migration on a scratch database.
- If a top tier holds every permission by definition, verify with the **effective** set, not the stored row — a
  stored row that omits always-granted keys is normal, and a tool that reports it as a defect is wrong.
- Update the permission register, the documentation, and any picker that offers the key, in the same commit.
```

### P14 — Investigate unexpected behaviour

```text
Investigate: <what happened, and what you expected>.

- Do not change anything yet. Establish what is true: reproduce it, measure it, and find the smallest case that
  shows it.
- Distinguish the explanations that would look the same from outside — a stale screen versus a wrong file, a
  cached asset versus a broken build, a permission refusing a request versus a feature reading the wrong key. Say
  which candidates your evidence rules out and which remain.
- Tell me the cause, the evidence, and what you would change; then wait for me to agree before changing it.
```

### P15 — Token and context budget pass

```text
Make this loop cheaper without making it weaker. Say what you measure first, and give me the numbers before and
after.

Candidates, in the order worth trying:
- Tool output: print only what changed, not the whole tree.
- Logs: cap and rotate; name the cap, where the rotation happens, and prove it ran.
- Writes: do not rewrite a file whose content has not changed.
- Preparation steps: cache them behind a hash of their input — and write down what invalidates that hash, because a
  cache nobody can invalidate is a trap that looks like a speed-up.
- Model calls: memoise the stable part of the prompt, truncate the large field, make the model overridable.
- Polling: stop while the view is not visible.

Requirements for each one: a marker comment at the change, a one-line revert instruction, and the ability to be
rolled back on its own without touching the others. Report any optimisation whose invalidation is not obvious, and
anything you decided not to do and why.
```

### P17 — Pre-deploy preflight

```text
Before this can be deployed, check what can be checked without a subscription, and report each result:

1. Templates: validate them with the real tool (the same check the cloud CLI runs). If the tool is not installed,
   say how to install it rather than reporting a failure nobody can act on.
2. Environment contract: every value the templates read must be exported by the script that invokes them. Name each
   one and how it is supplied.
3. The workflow's own shell: run it through a shell rather than reading it. A comment inside a backslash-continued
   command chain silently truncates the invocation, and reading does not find that.
4. The image: how it is built, what it is tagged with, and how it reaches each environment.
5. Say plainly what could not be checked from this machine and why.
```

### P18 — Post-change health check

```text
Run the health check for this service after the change: <HEALTH_COMMAND>.

Report its output verbatim, and tell me which of its checks are the ones that would actually fail if this change
were wrong — a health check that passes for the wrong reason is worth less than no check. If there is no such
command for this surface yet, write the smallest one that answers "is this well?" for the thing you changed.
```

### P19 — Sweep test residue

```text
Clean up after the testing this session did.

- Sweep residue by command, with a dry run first and the applied result after: <SWEEP_COMMAND>.
- Say what the rig leaves behind and what it cannot clean: cleanup in a `finally` does not run when a process is
  killed outright, which is why the sweeper exists as well.
- Then confirm nothing was created outside the sweep: no leftover rows, sessions, files, containers, or processes
  (see P6 for the process half).
- Tell me what you deliberately left, and why it is safe.
```

### P20 — Register the work you did not do

```text
Register the things you found and chose not to fix, in <DEFERRED_REGISTER>.

For each: what it is, where it is, why you did not fix it, what would break if somebody fixed it casually, and
whether the decision belongs to me. Nothing here belongs in a code comment or in your summary alone — if it is not
in the register, the next person will re-find it or, worse, half-fix it.
```

### P21 — Ship a stampable artefact

```text
Build the distributable artefact for <the thing> so that a change to it cannot ship under an old identity.

- The artefact carries an identity and a hash of what it was built from. Bump the identity with a script, never by
  hand.
- Add or extend the check that fails when the payload changed and the identity did not, and show me it failing
  before it passes.
- Serve the artefact from the product itself rather than from a third party's public URLs, and tell me which URL a
  user actually downloads from.
- Tell me how a stale artefact would present itself to a user, so I know what to look for if it happens.
```

### P22 — Make a hosting or account decision

```text
Answer this question with an audit rather than an opinion: <the decision, e.g. "would making this repository
private affect anything?">

- Enumerate every category of thing that could depend on the current setting: build and deploy authentication,
  anything that fetches over the network anonymously, distribution of what users download, checks that only exist
  on one host, the runtime's own calls, documentation links, and any feature whose availability depends on the
  setting.
- Read each one rather than reasoning about it, and report what you read and what it said.
- State the things that **do** change, including account-level consequences (a plan requirement, a metered quota,
  a protection rule that stops being available).
- Check the current state through whatever API answers for it, and say what you found — including anything that
  contradicts what the project's own documents claim, because that is a defect either way.
- If it is safe, make the change, then verify it **independently of the call that made it** — the setting read back,
  an anonymous read refused, and the normal workflow still working.
- Write it up, and list the things the audit turned up that need a decision from me.
```

---

# Part 4 — The definition of done

A model should be able to answer **yes** to every line that applies, and say why for every line that does not.

- [ ] The change is the smallest complete thing that answers the request; nothing unrelated was altered.
- [ ] It was **run**, not merely written — and the original symptom, if there was one, is gone.
- [ ] Every platform, input method and configuration the product supports was considered for it.
- [ ] The generated things were regenerated from their source, and the staleness check passes.
- [ ] A changed interface means the contract artefact and its guide agree with the implementation.
- [ ] The product's own documentation is updated in the same commit, with its figures captured from the running
      product.
- [ ] The permission register says what is true: read by something, or explicitly not.
- [ ] The four questions are answered — multi-instance safety, where state lives, where secrets live, what it calls
      and how it leaves — or answered with "none" and why.
- [ ] The check list passes, and its summary line is in the report.
- [ ] Every check added or changed was **shown to fail** before it was trusted.
- [ ] The prompt is logged and the changelog entry exists, with a script-computed version.
- [ ] The rollback document for any touched layer still tells the truth.
- [ ] Anything shipped carries the identity of what it was built from, and the stamp check passes.
- [ ] Test residue was swept, and the sweep was reported.
- [ ] Everything found and not fixed is in the register.
- [ ] Any cache added says what invalidates it.
- [ ] Nothing is left running, staged, or half-written.
- [ ] The report contains: what was run, what it printed, what was assumed, what is unverified, what was
      deliberately not done, and the weakest part of the change.

---

# Part 5 — The failure catalogue

Part 2's rules are reactions to these shapes. Recognising a shape is much faster than re-deriving the rule, and
this is the part of the pack worth reading twice.

| # | The shape | What it looks like | The rule |
| --- | --- | --- | --- |
| 1 | **A claim and a fact never compared** | A document says something is gated and it is not. A screen reports a setting the runtime ignores. A comment describes behaviour that changed. | §1.1, and every prose rule |
| 2 | **Two places that must agree, no mechanism** | Two colour lists. A screen testing one key while the operation tests another. A document naming a destination that was renamed. | §1.2, §2.2, §2.3, §2.14 |
| 3 | **A check that cannot fail** | A probe fetching with caching disabled and then asserting the cache. A "many-case" rig that ran one case because the data structure parsed as a single object. A linter matching nothing. | §1.5 |
| 4 | **A correct answer from a wrong measurement** | Measuring space to the right of a letter without deciding where the letter ends, so the "clear width" included an open aperture. A sampling grid one cell wider than the shape. A gap check comparing against a whole row rather than the shape's own pixels. | §1.6, §2.18 |
| 5 | **A generated file written by hand** | A generated copy edited directly; an asset rebuilt from changed input without the generator; a stylesheet with a rule the generator would not produce. | §1.4, §2.5 |
| 6 | **The file written is not the file intended** | An encoding that silently changes the bytes; a script that fails to parse because of its own byte-order mark; a text-writing call with an argument validated after the file was opened, truncating it; a find-and-replace that mangles the function it was installing a check into; a shell that mangles the punctuation a script matches on, so the edit silently never happens. | §2.32, and *check what was written, not what was asked for* |
| 7 | **A rule written twice** | A number in prose and in a constant. A heading describing a previous round. A count in a document. | §1.2, §1.4, §2.4 |
| 8 | **Work that looks finished because it is quiet** | An auto-publisher committing a half-built refactor. A "test" command that runs builds and exits zero. | §2.29 |
| 9 | **The wrong environment hides the failure** | A guard reading a secret through a path production closes, so it fails open exactly where it matters. A fix verified only where things already worked. A check that needs a tool the machine lacks, reported as a failure. | §2.20, §2.18 |
| 10 | **Resources left behind** | Forgotten headless browsers numbering dozens of processes. A temp file in the repository. A hold marker still set. Rows left in a database by a probe. | §2.24, §2.26, §1.9 |
| 11 | **The report outran the work** | "Fixed and verified" with no command, no measurement, and no mention of the paths not checked. | §1.10, Part 4 |
| 12 | **A stale claim inside the artefact** | A page's own heading, a row's own note, a review document describing an earlier design, a file's own comment asserting the opposite of its code. | §1.1, §2.4 |
| 13 | **A cache nobody can invalidate** | A preparation step skipped because an input hash was stale, so a schema change never reached the database. | §2.19 |
| 14 | **A gate that exists only on one machine** | A hook in a machine's own config directory, ending in a success exit so it could not fail anything, that nobody cloning the repository got. | §2.23, §2.30 |
| 15 | **A gate whose test cannot fail** | A credential gate with no test, which turned out to have several defects, one visible only by running it. | §2.16, §1.5 |
| 16 | **An artefact shipped under an old identity** | An installer whose payload changed and whose version did not, so a user reinstalls and gets the old behaviour. | §2.8 |
| 17 | **Residue that corrupts the next run** | Sessions, rows or files a probe left behind; a cleanup that could not run because the process was killed. | §2.26 |
| 18 | **A promise in a header with nothing behind it** | A workflow comment saying production needs an approval, in a repository with no such environment configured. | §1.12, §2.21 — reading is what should have found it |
| 19 | **A finding accepted on its authority** | A review's diagnosis adopted because it was confident, when its premise was never checked — or its fix rejected as impossible without saying which platform fact makes it so. | §2.27 |
| 20 | **Two projects bleeding into each other** | A session standing in one repository logs the other project's prompt, versions its change, or numbers its entries — so one prompt acquires two accounts and two logs start to disagree about the same work. | §2.33, §1.2 |

---

# Part 6 — How to run the pack as a model

Read this part at the start of a task, and again before reporting.

1. **Classify the request** with the table at the top, and read the rules it points at.
2. **State the frame in one line each** before working: what a player will see or hear, contract change (which
   artefact and guide), settings change (which documentation), generated artefacts (which generator), permission
   change, and the four questions — and *none* where none applies. This takes seconds and prevents most of Part 5.
3. **A bug is reproduced first.** Do not fix what you have not seen fail.
4. **Measure, do not glance.** For anything visual or countable, produce the number — and check what the number is
   *of*.
5. **Prove new checks by breaking the thing.** A check that has never been red is an assumption.
6. **Verify by running**, in every configuration the product has, and capture the evidence as you go rather than
   reconstructing it at the end.
7. **Record** before you commit: prompt log, changelog, regenerated copies, check list.
8. **Report** with Part 4's last line: what ran, what it printed, what you assumed, what is unverified, what you did
   not do — plus the weakest part of the change.
9. **Clean up** — processes, files, markers, residue — and say that you did.

**Tone to use in reports:** plain, specific, and honest about uncertainty. Numbers rather than adjectives — "the
closest approach is 2.25 units, measured with a distance transform" rather than "looks clean". If a previous claim
of yours turned out to be wrong, say which claim and what the measurement showed; that is worth more to the person
directing the work than a silent correction.

**Two habits worth naming on their own, because they are the ones that get skipped:**

- **Before reporting a fix, ask what would be different if the fix had not worked.** If nothing would be different,
  you have not verified anything.
- **When someone reports the same defect twice, change your method, not the patch.** Two rounds of the same
  complaint means the first diagnosis was wrong about something — usually about *which* thing is broken.

---

# Part 7 — Worked examples

Anonymised, because the shape is the point and the product is not. Each is a real sequence of the kind this pack
exists to catch, with the rules that would have shortened it.

### 1. One requirement that decided a whole design

*"Make it rotate, and make sure two places that show it can never disagree."* The second clause was the design
constraint: one of the two places renders **before** the application's code is available, and the platform's
security policy forbade the obvious workaround (an inline script). So the decision had to be made by a file that
runs before the first paint, and recorded somewhere both surfaces read.

That moved the choice from *"pick one at random when the app loads"* to *"derive it from something every window
already agrees on"* — a value derived from the date — and it also fixed a second problem nobody had raised: two
windows open at once would otherwise have shown two different marks. Storage was left for a **pin** only, so the
state that could go stale was one value a person sets deliberately.

**Rules:** §1.3 (state the frame before designing), §1.2 (two places need a mechanism), §2.5 (source and
generation), §2.1 (the record).

### 2. The defect reported four times

A visual defect was reported with a screenshot, fixed, reported again, "fixed" again, and so on. Every round
inspected the asset and adjusted it. The round that resolved it did something the others had not: it **measured the
reporter's own image** rather than the project's asset — finding an enclosed region by filling from the border and
counting — and measured the mark **as it appeared on the page**, which showed it drawn far larger than the size
that page asks for.

Two faults were hiding behind one complaint. The asset had a counter that was closed by its tracing step; and the
*client* was painting an image it had decoded before the rebuild, because a URL that has not changed is never
re-fetched by anything. So the asset was redrawn **and** the caching was made to revalidate rebuilt assets — and
then the reporter's screenshot was measured again.

**Rules:** §1.6, §2.17 (measure both when the captures disagree), §1.2 (the client and the file), Part 5 shape 12.

### 3. A guard that failed open in the one environment that mattered

A guard compared a stored value with a value about to be written, and refused when they differed. It read the stored
value through a call that goes through a **data plane** which production deliberately closes. So in production the
read failed, the comparison was skipped, and a changed value was written silently — and the data encrypted under the
old one became unreadable. The guard protected the development environment and failed open in the only one where the
loss was permanent.

The replacement changed the **question**: not *"is it the same value"* but *"is there a value at all"*, asked twice
through channels that stay reachable, with the two answers reconciled explicitly — present wins, absence requires a
call that actually answered, and unknown means *leave it alone*. Two actions, and a deliberate decision to have no
refusal. A test rig was written with a case **for the old fail-open state**.

**Rules:** §1.5, §2.20 (the guard whose subject is unrecoverable comes first), Part 5 shapes 9 and 3.

### 4. Authorization that authorised nothing

A sweep found a set of operations asking for an unrelated permission, while the key named after each area was
offered to administrators and **read by nothing at all**. Fixing it meant preserving access rather than narrowing or
widening it: a data migration appended the missing key to the stored grants, proved against a scratch database, and
was applied.

Then the same sweep found **screens whose own gate disagreed with the operation they load** — a page testing one key
while the endpoint it calls tests another. Both were corrected to the operation's key.

**Rules:** §2.14, §2.15, §1.2.

### 5. A probe that could not fail

A test for stale caching fetched the asset with caching disabled and then asserted the cache was fresh. It passed —
and would have passed with the fix reverted, because the thing under test was never staged: the worker was not yet
controlling the page and the asset had never been cached. The rewrite **staged the cache, asserted it held the old
bytes, and failed loudly if it did not**, then asserted the new behaviour.

**Rules:** §1.5, Part 6 step 6.

### 6. Many cases that ran as one

A test rig with a dozen cases reported that most of them passed. The data format had parsed as a single object, so
what the rig treated as "the arguments for this case" was **every case's arguments joined together** — one case,
many times the input. The fix was to emit one explicit statement per case rather than a structure the runner had to
interpret.

**Rules:** §1.5, Part 5 shape 4, §2.18 (measure the rig, not just its subject).

### 7. The measurement that was right about the wrong thing

Fitting a shape inside a letter required the space inside it. A flood-fill search reported a clear width. The figure
was measured correctly and was wrong: the search treated the letter's **open aperture** as part of its interior, so
it measured the room *beside* the letter rather than the counter *inside* it. Capped at the letter's own edge, the
figure was a fifth smaller — and that difference was exactly the margin reported as missing.

**Rules:** §1.6, Part 5 shape 4. The lesson is not "measure" but "check what the measurement is *of*".

### 8. The file written was not the file intended

A text-writing call took a newline argument that is validated **after** the file is opened for writing, and
truncated a module to zero bytes. The same session lost a second file to a routine find-and-replace that mangled
the function it was installing a check into. Both were caught only because the next step read the file back.

**Rules:** §2.32, Part 5 shape 6, Part 6 step 1.

### 9. The exception that has to stay red

One check was red on the main branch for a payload change that was nobody's: the artefact's hash had moved and the
version was not bumped, by whoever did it. Enforcing it would have meant stamping the current release number onto
somebody else's artefact. So it is run, printed and **reported**, with the reasoning recorded where the check lives.
A check with an exception is fine; a check with an **undocumented** exception is how a codebase learns to ignore
red.

**Rules:** §2.22, §2.8, §1.12.

### 10. The audit that became a document

Asked whether a hosting change would affect the deployment plan, the useful answer was not "no" but a list of what
was checked and what did not depend on it: the pipeline's authentication (a federated credential's subject contains
no visibility), the container build (local context), the templates (local files), how users download what the
product ships (served by the product), the checks (command-line tools, no host-specific service), and the absence of
any anonymous fetch anywhere. Writing it down turned a yes/no question into a document that also recorded three
corrections the audit had found — including a promise in a workflow's own comment with nothing behind it.

**Rules:** §1.10, §1.12, Part 5 shape 18.

---

# Part 8 — Adopting the pack

## 8.1 The decisions to make on day one

Nothing in Part 1, Part 4, Part 5 or Part 6 changes between projects. What changes is **where each rule lives**.
Decide these before feature work, and write the answers down — `P1` walks a model through creating the files.

| Decide | Why it matters | What a good answer looks like |
| --- | --- | --- |
| Where the prompt log and changelog live, and how the version is computed | §2.1 — a guessed version is a broken record within a month | two documents and a script that computes the next version |
| Which generated copies exist, and who regenerates them | §2.1, §2.5 | at least one machine-readable copy, written by a script, checked |
| What the single check list is, and how the hook and CI are kept in step | §2.22 — three hand-written lists diverge | one file, a hook and a CI job that both read it, a coverage check |
| What the published contract artefact is, and what checks it | §2.2 | a generated spec plus a guard comparing it with the implementation |
| Where the product's own documentation lives, and what keeps it reachable | §2.3 | a docs source plus a links guard |
| Whether the product runs as more than one instance, and what makes scheduled work safe | §2.20 | a claim/lease mechanism, or a stated reason it is unnecessary |
| Which bug classes this codebase actually produces | §2.15 — specific, not general | a table grown from the project's own finding history |
| Where the scratch rigs live, and how they are reaped | §2.24 | a rig per job that kills exactly what it started |
| Whether anything commits on somebody's behalf | §2.29 | a hold marker, a size refusal, a credential gate |
| Which layers need a rollback document | §2.13 | one per configurable layer, kept true |
| What the token and context budget is, and which loop is the expensive one | §2.19 — and every cache needs its invalidation written down | before-and-after figures, a revert per optimisation |
| What the register of deliberately deferred work is | §2.28 | one document, read before changing the area it covers |
| Which artefacts are stamped, and who bumps the stamp | §2.8 | a record file, a scripted bump, a guard |
| What is checked before a deploy, without a subscription | §2.21 | template, workflow and environment contract, each checked |
| What runs on the operator's machine, and how it is registered | §2.30 | registration scripts, committed, with reasons |
| Whether the parked interface rules are restored, and which ones | the addendum is not in force until a recorded decision restores it (PG-1) | a decision in the notes, the sections put back in one change, and the revision line bumped |

## 8.2 The inventory of checks to produce

Part 9 is the complete list of check *kinds* this pack assumes, with what each compares and which rule it serves. A
new project should end up with its own version of that table — some rows filled, some explicitly declined with a
reason — and it is the fastest way to see which of these rules a project has actually taken on.

The interface rows of §9.5 are parked with the rest of the interface material.

**Keep the pack generic.** If you want a mapping from the placeholders in this document to your project's real
paths, put it in your own file beside the pack (`<PROJECT>-PROJECTPACK-NOTES.md` or similar), not in the pack itself.
A pack with one project's paths in it stops being portable the day that project is renamed.

**And if the pack ends up copied into more than one repository, the pack's own law applies to the pack.** Two copies
of one document with nothing comparing them will drift, and it happens fast: a second repository took a copy of this
pack and it was out of date within the hour, because the original gained two rules in between.

The minimal mechanism is the **revision line at the top of this document**: a copy keeps that line as it was taken,
so comparing a copy's line with the source's is a one-line check that says whether the copy is behind. That makes
drift *findable* rather than impossible, which is honest about what a copied document can do — the stronger version
is that something runs the comparison, and a project that keeps the pack in two repositories should do that instead
of trusting the line to be read.

**One more thing a copy should say:** which project's rules it is *not*. The pack is generic, so a copy in a second
repository looks exactly like the original — and the two projects may have fewer rules than the pack describes,
because each is where the pack's `P1` will be run separately. Say which half is aspirational there.

**And this copy says it:** its interface design and redesign rules are parked in
[`ProjectPack-ADDENDUM-Interface.md`](./ProjectPack-ADDENDUM-Interface.md), and
[`ProjectPack-NOTES.md`](./ProjectPack-NOTES.md) lists every parked rule and every C7NTRY rule this repository does
not carry. Those are the halves that are aspirational here.

---

# Part 9 — Appendix: the complete inventory of check kinds

Read this as a menu. Each row is a **comparison** that can be mechanised, what breaks when nobody makes it, and the
rule it serves. A project does not need every row, but it should be able to say for each one whether it has it and
why not.

## 9.1 The record and the prose

| Check | What it compares | Prevents | Rule |
| --- | --- | --- | --- |
| records | the changelog, its generated copies, and the prompt log | a version, a date or an entry that exists in one place only; a stale fallback | §2.1 |
| project boundary | each record block vs the peer project's name, and every tracked file vs the peer's path and remote | one project's prompt, entry or file landing in another's records | §2.33 |
| newest-first | the order of entries in all three | a changelog whose top entry is not the newest | §2.1 |
| contract | the generated specification vs the implementation | a document that is behind the code, or describes something removed | §2.2 |
| curated prose | human-written notes vs the operations they describe | prose attached to something that was renamed away | §2.2 |
| documentation links | every link in the product's docs vs the real destinations | a help page pointing at a route that no longer exists | §2.3 |
| index completeness | every walkthrough vs the index | help that exists and cannot be found | §2.3 |
| deferred register | an item marked done vs whether it is | a register that has drifted from the code | §2.28 |

## 9.2 Generated artefacts

| Check | What it compares | Prevents | Rule |
| --- | --- | --- | --- |
| generator `--check` | every generated file vs what the source would write, byte for byte | a stale asset, stylesheet, spec or fallback that still *looks* right | §2.5 |
| source lists | a list repeated in a file that runs before the build vs the generated one | two lists of the same thing drifting apart | §2.5, §1.2 |
| artefact stamp | the payload hash vs the declared identity | shipping a changed artefact under an old version | §2.8 |
| config reads | every configuration read vs the declared fields | a setting read by name and declared nowhere | §2.7 |

## 9.3 Authorization

| Check | What it compares | Prevents | Rule |
| --- | --- | --- | --- |
| enforcement | every permission vs something that reads it, or a row saying not | a key that authorises nothing | §2.14 |
| labels | every permission in a group vs the others in it | two keys that read identically to an administrator | §2.14 |
| screen gates | every screen's guard vs its operation's guard | a page that tests a different key than the thing it loads | §2.14, §1.2 |
| navigation | every navigation row vs its destination's requirement | a row that shows something the destination refuses | §2.14 |
| route guards | every authenticated route vs a guard or a documented exemption | an endpoint with no authorization at all | §2.14 |
| top-tier holds everything | the **effective** permission set of the top tier vs "everything" | a gate that refuses the one role that cannot be refused | §2.14 |

## 9.4 Correctness and the workspace

| Check | What it compares | Prevents | Rule |
| --- | --- | --- | --- |
| typecheck / compile | the source vs the language's rules | a build that cannot build | §1.3 |
| migration drift | the migration set vs the declared schema | a datamodel and a database that can differ with every check green | §2.20 |
| encoding | the bytes of every file vs what they claim to be | text written twice-encoded that still parses for some readers | §2.32 |
| dependency baseline | the dependency tree vs the accepted advisory list | a new advisory arriving unnoticed | §2.15 |
| secret scan | the working tree and the history vs known secret shapes | a credential committed | §2.16 |
| image/config scan | the built artefact and its configuration vs known misconfigurations | a container that runs as a privileged user, or a service exposed by default | §2.21 |
| template validation | the infrastructure templates vs the real tool | a deployment that fails at deploy time rather than at review time | §2.21 |
| workflow shell | the deploy workflow's shell **executed** by a shell | a command silently truncated by a comment in a continuation chain | §2.21 |
| environment contract | every value the templates read vs whoever exports it | a deploy that works from one shell and not another | §2.21 |
| hook/CI coverage | the hook's list vs CI's list | two lists of checks that have already diverged | §2.22 |
| test runner reality | what the test command **actually** runs vs what its name claims | a command that prints a passing task count made entirely of builds | Part 5 shape 8 |

## 9.6 Operations and hygiene

| Check | What it compares | Prevents | Rule |
| --- | --- | --- | --- |
| credential gate | a push's contents vs what must never be committed, with a test that it refuses one and accepts a fixture | an automated push committing a credential | §2.16 |
| auto-publish gate | the tree's state and size vs what may be published unattended | a machine publishing unfinished work | §2.29 |
| leak report | running processes/resources vs the ones this work created | tens of processes and tens of gigabytes left behind | §2.24 |
| residue sweep | a database, session store or filesystem vs its clean state | a probe corrupting the next run | §2.26 |
| health check | the running service vs "well" | discovering a broken deploy from a user | §2.25 |
| audit sweep tooling | the reported findings of a sweep vs a written, reviewable record | a sweep that is a feeling rather than a scope | §2.15 |

## 9.7 The things that are not checks, and still count

- **The leak report is a command** — so a leak is found by running something rather than by the owner noticing.
- **The health command is named for the moment it exists for** — so nobody has to work out what to run after a
  change.
- **The sweeper is part of the rig** — because a cleanup in a `finally` does not survive a forced termination.
- **The register is read before the area is changed** — a register nobody reads is a diary.
- **The exception is written where the check lives** — a reported check and a skipped check both need their reason
  beside them, or the next person will treat red as normal.

---

# Part 10 — The operator's standing rules

Rules added to this copy after it was taken, because the operator asked for behaviour that outlives the
conversation it was asked in. They are written to be portable like the rest of the pack: the *shape* is the rule,
and a project fills in its own names.

**Every rule added from here on goes into this part, in the same change in which it is first stated** — a rule that
lives only in the file where it bites is a rule the next session finds by accident, and a rule that lives only in a
conversation is not a rule at all.

## 10.1 Which subagents, in what order, and how many

- **DeepSeek models only, and the model is named on every dispatch.** The flash model first; the pro model for
  genuinely complex work, or wherever the session judges it the better instrument. What the rule fixes is the
  **order**, not the ceiling: most delegated work is search, transcription and verification, and the expensive model
  is spent on the task that deserves it. Leaving the model unset is not neutral — it hands the choice to the
  runtime, and the runtime's default is not the operator's choice.
- **A hard cap on concurrent agents** (this project: **twelve**). The cap is about the machine as much as the
  budget: agents run beside a live stack on a shared machine, and a hundred parallel workers produce a hundred
  half-verified results.
- **The ordinary rules still decide *whether* to dispatch.** A subagent is for work that needs its own context; a
  dispatched agent is not evidence that work is happening (read its status *and* the work it has done); and its
  report is a claim verified from the tree.

## 10.2 Working continuously, and the one report

- **"Keep going until it is all done, however many passes" is a shape, not encouragement.** Make pass after pass —
  dispatch the next batch, integrate it, verify it on the running product, record it, commit it — and do not end
  the turn while work remains. Do not stop to report progress; do not ask whether to continue; do not treat a
  finished batch as a finished task.
- **One report, at the end.** It states what is finished, what was verified and how, and what is not done with the
  reason. A mid-way progress report is noise to an operator who asked for the whole thing, and it spends the
  context the remaining work needs.
- **Continuity never suspends verification.** A batch still gets its records, its check list, and a look at the
  running build before it is called done. "Keep going" is never a reason to skip the check — it is the reason the
  check has to be cheap enough to run on every pass.

## 10.5 An attached image has a name: `(pi)`, `(pi2)`, …

A person directing the work types **`(pi)`** instead of "pasted image", and numbers them when a prompt carries more
than one: `(pi)` is the first attachment, `(pi2)` the second, `(pi3)` the third. The point is speed — the operator
should not spell out four words to point at a picture — and the cost of the shorthand falls on the model, which
must do the resolving.

- **Read the attachment before acting.** A prompt whose request is "fix this `(pi)`" keeps its subject in the
  picture. Answering from the surrounding prose is answering a different question, and describing the picture from
  expectation rather than from a look is the same error with more confidence behind it.
- **The number counts the prompt's own attachments, in the order they arrived.** When a number names nothing that
  was attached, say which one was read and ask which was meant — never guess, and never silently treat a missing
  image as an absent one.
- **The shorthand survives into the record; the entry resolves it.** A prompt log quotes what was said, `(pi)` and
  all, and the entry says in its own words what the picture showed, so that a later reader without the image still
  knows what the work was about. "See attached" is not a record.

The convention lives in this part rather than in a session because the *shape* is the rule: any operator pointing at
a screenshot in a hurry is doing the same thing, in any project, whatever the shorthand is called.

## 10.6 Work in slices, and do not stop between them

- **Trigger:** any task larger than one comfortable sitting — a build plan, a multi-part feature, a migration, a
  long verification loop.
- **Rule:** cut the work into **slices** that each end in something observable — a file written, a check run, an
  entry recorded, a commit — and run one slice at a time. A slice is sized by *what must be held in mind*, not by
  how much it changes: read what this slice needs, write it, verify it, record it, commit it, then take the next
  slice's context from the repository rather than from the conversation.
- **The slice list is the memory.** Write the ordered list into the repository before the first slice — a plan, a
  register, a draft entry. A list that lives only in the conversation is re-derived, differently, by the next pass;
  a list in the tree survives a compaction, an interruption and a different model.
- **Continue without asking.** When a slice ends and another remains, start the next one. The plan in the
  repository is the permission to continue; stopping to ask "shall I go on?" spends the context the remaining
  slices need and produces the mid-way report §10.2 already forbids. One report, at the end.
- **Carry only the next slice.** Everything behind it is read back from the repository, which is why the records
  (§2.1) and the plan matter more than a good memory.
- **A slice that runs out mid-way was cut too large.** Cut the next one smaller; do not open a new conversation to
  escape the bound, and do not compress the work to fit by skipping its check.
- **Verification per slice, the whole suite at the end.** Each slice runs the check that proves *it*; the last
  slice runs the full list, including whatever verification the change's surface needs.
- **Why this is a rule and not a working style.** Context is a budget (§2.34), and a session that ends mid-task
  loses exactly the part that was thought through but not written down. Slicing moves each decision into the tree
  as it is made, so a long job survives the limit that will arrive, whatever its size.
- **What this does not license:** stopping after each slice to report; calling a slice done without its check;
  letting one slice touch files another owns (slices are sequential unless they are provably disjoint); or using a
  slice boundary to defer a decision the slice needed to make.

## 10.8 Background agents are evidence only after they are read

- **A dispatched agent is not evidence that work is happening.** Read its status **and** the work it has done before
  treating it as in flight; never report it as "still running" without having read it.
- **A failed agent with zero completed tool calls never began.** A healthy agent reports `running` or `idle` **and** a
  non-zero tool-call count. Do not judge by turn count alone: a working first turn can still report zero turns with
  tool calls already behind it.
- **If an agent type will not start, use one that does and name it.** Treat "this type cannot start here" as a local
  fact to verify, not a rule to assume; say which type was used instead.
- **An agent's report is a claim, not a result.** Verify the slice from the tree — run the tests, run the probe, read
  the file — before recording it or calling it done. A report that was not checked is a second thing that might be
  wrong.

---

## 10.9 Reuse the rig, and clean up the whole machine when asked

- **Reuse before creating.** One browser profile/context is the default for related checks; one teammate is the
  default for related work. A new browser or teammate is added when it buys isolation or parallelism, not because
  launching one is easy. Reuse the running stack rather than starting a second one.
- **The creator closes it.** Put browser/context shutdown in a `finally`, delete only the temp files and profiles the
  rig created, stop the processes it started, and say what was closed. A test that exits without closing its browser
  has leaked regardless of whether the command returned zero.
- **"Clean up after yourself" is a machine-wide sweep, not a session-only one.** Inventory this session's agents, jobs
  and terminals, then inspect the machine's process trees and exact resource markers as well. Classify clearly:
  a resource is *active* while a live session, job, listener, watcher or parent process owns it; it is *orphaned* when
  that owner has ended and no live process depends on it.
- **Clean orphaned resources; leave active work.** Remove orphaned browser trees, crash-handler children and stale
  profile directories that no live process references. Do **not** kill active dev servers, API servers, watchers,
  tests, build jobs, containers, another session's browser or another session's port merely because they are heavy,
  old or parentless; parentless application servers and watchers may be intentional. Report every active resource
  left behind with its exact identifier and why it was left.
- **Never terminate by process name.** Kill by the exact PID/process tree/profile directory you have proved orphaned,
  and remove only paths you have checked. Verify after the sweep, and report reclaimed memory/disk as well as the
  active resources that remain.
- **When the resource is ambiguous, leave it and say so.** The operator's request to clean the estate overrides the
  caution about touching only your own session's resources; it does not override the caution about interrupting
  active work.

## 10.10 AI-facing control planes are read-first and confirmation-gated

- Named operations only; no raw shell, SQL, device command or "do anything" endpoint.
- Read tools execute under the person's permissions and tenant; per-tool policy is server-enforced and session-managed.
- Writes are previews with a single-use, expiring human confirmation; the model cannot approve its own proposal.
- Tokens are opaque/encrypted, not replayable as REST tokens; federation forwards the user's assertion, never a supertoken.
- Capability metadata carries domain, kind, permission and confirmation; unproven vendor commands are unavailable, and
  recovery is observed state after the action.

## 10.11 Demo data survives a reseed

- The seed and its sample-clone scripts are the source; a local database is not.
- Run the full reset including derived tenants after changing sample data, update expected counts/tests, and stop
  writers before resetting.
- Preserve existing vendor families; a mixed estate including storage, wireless, edge and controller roles is the point.

## 10.12 Migrations belong to the application's own database

- A migration targets the application's own DATABASE_ADMIN_URL, not a peer app's database.
- Apply additive migrations before the code that reads them; record the target and names; ask if ambiguous.

## 10.13 A client or UI claim is only made after loading it

- A protocol test is not a client flow. Load the real client/browser, read the result back, and state what was not run.

# Part 11 — Repository standing rules

**This part is not portable.** Parts 1–9 are the pack and Part 10 is the operator's standing rules; this part is
ProjectGypsy's own rulebook. It started from C7NTRY's 24-rule Part 11 — the copy this pack came from — and every
rule was carried, adapted, parked in the interface addendum, or declined with a reason; the mapping is in
[`ProjectPack-NOTES.md`](./ProjectPack-NOTES.md). **Where this part and a portable rule differ, this part wins.**

## 11.1 This repository is a game, and its interface rules are parked

ProjectGypsy is a game. It is not a website and not a web application. The interface design and redesign rules of
this pack — §2.9–§2.12 and §2.35, prompts P4 and P16, §9.5, §10.7, §10.14, Part 11's interface rules and the browser
verification rule — are held in [`ProjectPack-ADDENDUM-Interface.md`](./ProjectPack-ADDENDUM-Interface.md) and are
**not in force**. No design language, mockup-first step, visual bar, viewport measurement, token lint, accessibility
pass or browser gate is claimed here until the addendum is deliberately restored by a recorded decision. Do not
invent a game-specific design standard to replace them; that is the operator's decision.

## 11.2 Verify before reporting

Nothing is reported as done on the strength of having written it. Every claim carries the command, measurement or
observation behind it. Verify by running the build or the test that proves the change, and read back what you
captured. A claim about something a player sees or hears is made only after seeing or hearing it run (§10.13).

## 11.3 Work in slices and keep going

Cut long work into observable slices, write the slice list into the repository, verify and commit each slice, then
continue without stopping to ask. Carry only the next slice in context; read the rest from the tree (§10.6).

## 11.4 Records move with the work

Every change updates the prompt log and the changelog in the same commit, with the version computed rather than
typed, and a prompt that changes nothing is still logged and says so (§2.1). The records files and the version
script do not exist in this repository yet; until they do, the rule binds the conduct and the missing mechanism is
registered in `DEFERRED.md` — it is not a reason to omit recording what was done in the change's own report.

## 11.5 Peer projects are separate

C7NTRY, C7NC, C7NTAX, C7TNL, C7NTRL and the other C7-IMI projects are peers: their own repositories, records and
sessions. A prompt asked here lands here, is logged here and versioned here; nothing is written into a peer's tree
and nothing of a peer's is written here. Work on a peer is done by a session standing in that peer's repository.
Crossing happens only on explicit instruction, and even then each repository records only its own side. The guard
that compares records and tracked paths against the peer list is **not built yet**; until it is, the boundary is a
discipline and is not claimed as mechanised.

## 11.6 Nothing fake in the build

No dead or fake behaviour: an action without a real implementation is absent, or visibly unavailable with its
reason. A demo that pretends a feature exists is a defect, not a demo.

## 11.7 Every change is made ready to scale and to move

Every change answers the four questions, or says plainly that it does nothing for them and why (§2.20): more than
one instance (a claim/lease, or provably idempotent), where state lives (never a process-local map), where secrets
live (a managed store, never code or a committed environment file), and what it calls and how it leaves (one egress
path). A game client and any server it talks to are separate deployment surfaces once they exist; say which one a
change touches.

## 11.8 A retrofit of something that already works is expand-only

When changing a working system: no destructive change to live data; new behaviour arrives as an additive field, a
sidecar table or a view; and a retrofit edits what a write stores rather than what an existing reader parses. Not
triggered yet — this repository has nothing retrofitted.

## 11.9 The rollback documents

Every configurable layer — a graphics mode, a difficulty mode, a feature flag, a server setting — gets a document
at a known location stating how to turn it off and how the change is verified, kept true as the layer changes
(§2.13). Where the reversal is mechanical, ship it as a script with a selector, a dry run and a direction. None
exists yet.

## 11.10 Keeping this overlay true

This part changes in the same commit as the work that changes a rule. A rule that lives only in a conversation is a
rule half the sessions will miss. When the source pack moves, compare its revision line against the one in this
copy's header (§8.2), take its generic changes into Parts 1–10, re-check the parked list in
`ProjectPack-NOTES.md`, and keep this part. The interface addendum is re-checked the same way; it does not drift
silently into force.

## 11.11 Keep going: slice, delegate, one report

**Trigger:** any instruction with several parts, any "build it all" request, and the operator saying "keep going",
"don't stop to report", "as many passes as it takes", or "until it is done".

**Rule:** work continuously until the *whole* instruction is satisfied. Do not stop between slices to report
progress; a slice boundary is a place to save state, not a place to ask permission. The full rule is §10.6 and
Part 12; this section makes it a repository rule.

## 11.12 The operator's standing rules for autonomous runs

Carried from the source copy, minus the bullets that describe a web console:

- **Build to completion.** The measure is the instruction satisfied in the tree, not a report about it. Empty the
  buildable remainder; when something cannot be finished here, name the exact external input that blocks it.
- **Full autonomy for buildable work.** If it needs no external account, credential, subscription or target, build
  it, verify it and record it without asking. If it does, say exactly which input is missing — never fake a
  completion.
- **Recommendations become decisions.** When the operator says "use your recommendations" or "you decide", choose,
  record the choice as a written decision, and proceed.
- **Verify the rendered output, not the intent.** After a scripted change, run the build and look at the result —
  the thing on screen and the thing in the log, measured rather than described.
- **Machine hygiene.** Reuse the rig before launching another; the creator closes what it opened; never kill another
  session's active work; never terminate by process name (§10.9).
- **Records and one report.** Each slice carries its records entry and checks; the operator receives one
  consolidated account of what shipped, what was verified, what was chosen for them, and what remains.

**What this does not license:** fabricating an external completion; turning autonomy into unbounded scope; skipping
verification because the demo looked fine; leaving a background job unobserved; or reporting a check that was not
run.

## 11.13 The C7NTRY rules this copy does not carry

C7NTRY's Part 11 also had rules for facts this repository does not have, or that are parked with the interface
material. They are **declined** or **parked**, not forgotten, and `ProjectPack-NOTES.md` records each with its
reason:

| C7NTRY rule | Why it is not carried |
| --- | --- |
| 11.7 feature and integration checks across applications | there is one application here, and no interop map |
| 11.9 probe and discovery safety against customer infrastructure | this repository has no customer infrastructure and sends no probes |
| 11.12 the applications remain standalone | C7NTRY's product family; this repository is a game, not a member of that deployment |
| 11.15 the API document is part of the change | no API is published yet; the rule returns as soon as one is |
| 11.10 one interface, three arrangements; 11.11 help stays current; 11.19 visual bar; 11.23 design reviews | interface design material — **parked** in the addendum, not declined |
| 11.1 no interaction budget; 11.4 redesign playbook; 11.5 explanation in the screen; 11.20 interface items not adopted | interface design material — **parked** in the addendum |

The parked rules in the addendum become binding again only if it is restored.

---

## Part 12 — Build to completion in slices (operator rule, applied 2026-10-23)

This rule applies in addition to every other rule in this pack. The operator granted full approval for the build
cycle that added it.

1. **Build in slices sized for one agent and one context.** Write the slice list into the repository, check items off
   as they land, and keep going until the list is clear.
2. **Use your recommendations.** When a decision is needed, make the recommended choice, record the decision and the
   reason in the repository, and proceed. Do not stop to ask.
3. **Use subagents on every slice.** Disjoint write scopes, DeepSeek models only, the model named in the dispatch,
   agents never commit; the Lead integrates, verifies and writes the records.
4. **Install whatever you need and elevate when necessary.** Full approval is granted for this build cycle: install
   dependencies, restart services, and request elevation when the sandbox denies an operation the work requires.
5. **Do not stop to say what is next or what you plan to do next.** Keep working. One report at the end.
6. **Clear and check off every list item and build task.** A task is deferred only with a written reason, an owner
   and the condition that would unblock it — never silently dropped.
