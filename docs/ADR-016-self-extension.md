# ADR-016 — Safe self-extension pipeline

- **Status:** accepted, 2026-10-26; self-extension pipeline built and tested at the Python-pipeline level.
- **Decision owner:** operator; implemented autonomously as the missing PG-D15 work.
- **Scope:** adding a new Gypsy capability in an isolated extension directory without modifying the core.
- **Related:** [ADR-003](ADR-003-workstream-architecture.md) (safe self-extension contract), [extensions/README.md](../extensions/README.md),
  [workstream/extensions.py](../workstream/extensions.py), [DEFERRED.md](../DEFERRED.md).

## Context

ADR-003 says a missing capability may be proposed or generated in an isolated directory, with a capability manifest and
version pin, tests that prove failure, a dry run, an explicit review gate, a lockfile and a removal path. The core must
not self-modify. Before this change, Gypsy had no implementation of that contract: PG-D15 listed self-extension as
deferred, and toolkit plugins were first-party only.

The risk is obvious: a self-modifying harness that can run arbitrary code and rewrite its own core is both unsafe and
unreviewable. The useful version is narrower: a reviewed, declarative extension directory that the core can discover,
validate, hash, enable/disable and execute without changing core files.

## Decision

1. **One extension is one direct child directory of extensions/.** Extension ids equal directory names. The extension
   root may be the checkout's extensions/ or a caller-supplied out-of-checkout root for tests; core directories
   (workstream/, game/, etc.) are rejected.
2. **Declarative manifest gypsy.extension/v1.** It pins a semantic version, apiVersion, id, license, capability id,
   fixed argv entrypoints and tests. Unknown keys are errors; a manifest cannot smuggle in a shell string or command.
3. **Capability manifest required.** The extension's own gypsy.capability/v1 file must match the manifest's capability id
   and layer extension.
4. **No shell and path containment.** argv is an explicit list run with shell=False; python entrypoints must name a
   relative .py file inside the extension; relative executables must stay inside; absolute paths, .., symlinks and
   shell interpreters/operators are rejected. Timeouts are bounded.
5. **Dry-run everywhere it matters.** run, register, disable and remove support --dry-run; register --accept --dry-run
   shows the review without writing the lock.
6. **Explicit review/register gate and lockfile.** Registration requires --accept, hashes the whole extension tree
   into extensions/gypsy.lock.json and is the activation record. run refuses unregistered, disabled or changed
   extensions; reload --accept re-reviews a change; disable/remove are reversible paths.
7. **Negative tests are mandatory.** Each manifest declares a test with expectExit "nonzero"; extension test fails if
   that negative case unexpectedly succeeds. A pipeline that cannot detect failure is not evidence.
8. **No core self-modification.** The pipeline writes only the lockfile and ignored extensions/.state/ evidence; it
   does not edit workstream/. The core was extended once by a normal reviewed code change (the extension module and
   CLI wiring), not by itself at runtime.
9. **CLI:** gypsy extension list|show|validate|test|register|disable|remove|run|reload, backed by
   workstream/extensions.py and the safe example in extensions/example.hello/.
10. **Limits are documented, not hidden.** This is a Python-level safety pipeline, not an OS sandbox. Reviewed extension
    code runs with the user's rights; network and read/write declarations are review metadata, not enforcement.
    Timeouts kill the direct child only.

## Evidence

- python -m unittest workstream.tests.test_extensions: **55 tests, OK** (one symlink test skipped — Windows account
  cannot create symlinks).
- Full suite at the time of this decision: **270 tests, OK (2 skipped)**; scripts/check_all.py **6/6 PASS**;
  **49 capability manifests**.
- Real flow: list → validate → test (pass + intentional fail detected) → register without --accept refused →
  register --accept → run hello PASS → run fail exit 1/action exit 3 by design → dry-run executes nothing.
- Lifecycle: register → disable → run refused → reload → run passes → remove --delete confines deletion to the
  extension directory. A tampered negative expectation makes extension test exit 1. See
  [extensions/README.md](../extensions/README.md) for the full commands.

## Consequences

**Positive:** a new tool/capability can be proposed without editing the orchestrator; review sees hashes, argv, cwd,
timeout and declared permissions; failure detection is part of the contract; registration is reversible.

**Negative / risks:** reviewed extensions are executable code; this is not a sandbox. A malicious or careless extension
can still do what the operating system allows. Dependency installation, signing and remote registries are out of scope.
Hot reload while running is not claimed; reload is an explicit re-review of files.

## Non-goals

OS-level sandboxing, network enforcement, dependency installation, remote registries, automatic code generation,
self-modifying core, extension marketplace.
