# DEFERRED.md — the work deliberately not done

The register §2.28 requires: what it is, where it is, why it is deferred, what would unblock it, **what would break
if somebody fixed it casually**, and who owns the decision. Read the entry covering an area before you change that
area. An item is closed only with its evidence.

This repository is a game with rules and no product code yet. Most items below are the pack's machinery waiting for
the thing it guards to exist — they are not silent omissions, and none is claimed as built.

| ID | What is deferred | Where | Why deferred | Unblocks when | What breaks if fixed casually | Owner |
| --- | --- | --- | --- | --- | --- | --- |
| **PG-D1** | Records infrastructure: prompt log, changelog, version script, generated copies, records check, tracked hook | repository root + scripts | the pack's P1 creates them with the first build; building them now would invent the project's tooling before its engine is chosen | the first code lands, or the operator asks for the records scaffold | a half-built records guard is worse than none — the next session trusts a stale log | operator / first build |
| **PG-D2** | The one check list with a tracked pre-commit hook, a CI caller, and the coverage check | scripts + CI | there is no build, test or check to list yet | the first build and test exist | a list not wired to both callers trains everyone to ignore red | first build |
| **PG-D3** | Engine, target platforms, input methods, language and tooling | repository decision record (to be written) | the operator has not chosen them; this is a game-design decision, not a reversible technical one | the operator decides | building against an undecided engine makes every later choice a rewrite | operator |
| **PG-D4** | The game's interface design and UI/UX standard | `ProjectPack-ADDENDUM-Interface.md` | the web pack's interface rules were parked because ProjectGypsy is a game; no game-side standard exists yet. See `ProjectPack-NOTES.md` §8.1 | the operator decides whether to restore the addendum, replace it with a game-side standard, or defer further | a half-restored rule contradicts §11.1 and the parked inventory | operator |
| **PG-D5** | A docs tree with an index and a links guard | `docs/` | only README and the pack files exist; a docs tree arrives with the game's own documentation | documentation outgrows the repository root | a docs tree without its links guard rots silently | first docs change |
| **PG-D6** | A mechanised peer-project boundary guard | scripts | Part 11.5's guard needs records and tracked files to compare; neither exists yet. Until then the boundary is a discipline | PG-D1 and a code tree exist | a guard written before records exist compares nothing and reports green | first build |
| **PG-D7** | A generated contract artefact and its guide | `docs/` | no API or published interface exists; if the game never exposes one this stays closed as "not applicable" | the game exposes an API or message contract | a hand-written contract drifts from the API the moment the API exists | operator decision when an API appears |
| **PG-D8** | Rollback documents for configurable layers, and the expand-only retrofit rule's first application | `docs/` | nothing is configurable at the layer level and nothing is retrofitted yet | the first configurable layer or live data exists | a rollback document for a layer that does not exist is fiction | the change that adds it |
| **PG-D9** | Machine-level automation: scheduled tasks, boot scripts, runner shims | `scripts/` or `startup/` | nothing runs on the operator's machine as part of this project yet | something needs to run on a schedule or at boot | automation registered without its script is a machine-level orphan | the change that needs it |

## Standing note

The interface design/redesign material is **parked, not deferred work to complete**: it is complete and preserved
verbatim in `ProjectPack-ADDENDUM-Interface.md`. PG-D4 is the decision that either restores it, replaces it with a
game-side standard, or leaves it parked longer. Do not treat "parked" as "forgotten", and do not partially apply it.
