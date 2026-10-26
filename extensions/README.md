# Extensions - isolated self-extension for Gypsy Studio

This directory is the only place a Gypsy Studio extension may live. It implements the safe
self-extension contract in ADR-003: a missing capability can be added in its own directory,
with a capability manifest, a version pin, tests that prove it can fail, a dry run, an
explicit review/registration gate, and a removal path. The orchestrator core is never
modified.

## Safety model

- Isolation: one extension is one direct child directory of extensions/. The root cannot be
  workstream/ or any other core directory, and an extension id must equal its directory name.
- Declarative manifest: extension.json is validated against gypsy.extension/v1. Unknown keys
  are errors, so a manifest cannot smuggle in a command field or a shell string.
- Capability and version: capability.json is required and must be gypsy.capability/v1 with
  layer extension and the manifest's capability id. version is a semantic version pin.
- Path containment: entrypoint scripts/executables and declared read/write paths must resolve
  inside the extension directory. Absolute paths, '..' segments and symlinks are rejected.
- No shell: argv is an explicit JSON list, executed with subprocess.run(..., shell=False).
  argv[0] is python (the running interpreter) or a relative executable in the extension.
  Shell interpreter names and shell control operators in any argv token are rejected.
- Timeout: each action declares a timeout (greater than 0 and at most 300 seconds;
  default 60). The CLI can shorten it with --timeout but not extend it. A timed-out action
  is a failure.
- Dry run: extension run --action NAME --dry-run resolves and prints argv, cwd and timeout
  without executing anything. extension register --accept --dry-run shows the review without
  writing the lockfile.
- Review gate and lockfile: extension register --accept hashes every file and writes
  extensions/gypsy.lock.json. extension run refuses an unregistered, disabled, or changed
  extension. extension reload --accept is the re-review path after a change.
- Negative test: every manifest must declare a test with expectExit "nonzero".
  extension test runs the declared tests and fails if that negative test unexpectedly
  succeeds. A pipeline that cannot detect failure is not a test.
- No core modification: registration writes only the lockfile in the extension root; run
  state goes to extensions/.state/; removal with --delete is confined to the extension
  directory. Nothing writes into workstream/.

## Commands

```text
python workstream/gypsy.py extension list [--json]
python workstream/gypsy.py extension show ID [--json]
python workstream/gypsy.py extension validate [ID] [--json]
python workstream/gypsy.py extension test ID [--json]
python workstream/gypsy.py extension register [ID ...] --accept [--dry-run] [--json]
python workstream/gypsy.py extension disable ID [--dry-run] [--json]
python workstream/gypsy.py extension remove ID [--delete] [--dry-run] [--json]
python workstream/gypsy.py extension run ID --action NAME [--dry-run] [--timeout SECONDS] [--json]
python workstream/gypsy.py extension reload [ID ...] --accept [--dry-run] [--json]
```

Every command accepts --dir DIR for an out-of-checkout extension root (useful for tests).
Inside this checkout the only allowed root is extensions/.

Typical flow:

```text
python workstream/gypsy.py extension validate
python workstream/gypsy.py extension test example.hello
python workstream/gypsy.py extension register example.hello --accept
python workstream/gypsy.py extension run example.hello --action hello
python workstream/gypsy.py extension run example.hello --action fail
```

The last command exits nonzero by design: the fail action is the negative case. To turn an
extension off use disable; to unregister but keep the files use remove; to delete after
review use remove --delete.

## Manifest (gypsy.extension/v1)

```json
{
  "schema": "gypsy.extension/v1",
  "id": "example.hello",
  "version": "1.0.0",
  "apiVersion": "1",
  "name": "Example hello extension",
  "description": "one line",
  "license": "MIT",
  "author": "optional",
  "capability": "extension.example.hello",
  "entrypoints": {
    "hello": {
      "description": "print a marker",
      "argv": ["python", "run.py", "--action", "hello"],
      "timeout": 10
    }
  },
  "tests": [
    {"id": "hello-passes", "action": "hello", "expectExit": 0,
     "stdoutContains": "EXTENSION_HELLO_OK"},
    {"id": "fail-is-detected", "action": "fail", "expectExit": "nonzero",
     "stderrContains": "EXTENSION_EXPECTED_FAILURE"}
  ],
  "permissions": {"network": false, "reads": ["."], "writes": []}
}
```

The capability file is the same shape used by workstream/capabilities/:

```json
{
  "schema": "gypsy.capability/v1",
  "id": "extension.example.hello",
  "layer": "extension",
  "kind": "example",
  "maturity": "experimental",
  "description": "what the extension does",
  "requires": ["python 3.14 standard library"],
  "inputs": [],
  "outputs": [],
  "checks": [],
  "provenance": {"record": []}
}
```

## Lifecycle

- list and show are read-only; they never execute extension code.
- validate checks schema, version, apiVersion, capability, argv, path containment and tests.
- test executes the declared actions. test is an explicit execution of reviewed code too, so
  read the extension before running it.
- register --accept is the review gate. Inspect show --json (hashes, entrypoints, tests,
  declared permissions) before accepting; register --accept --dry-run prints the same review
  and writes nothing. Without --accept the command refuses, points at those review paths and
  writes no lockfile.
- run executes one fixed action. It refuses a tree whose hash differs from the lock entry.
- reload --accept updates the lock entry after a reviewed change.
- disable keeps the files and lock entry but makes run refuse.
- remove unregisters; remove --delete also deletes the extension directory.

The lockfile records id, version, capability, manifest/tree SHA-256, per-file hashes,
acceptedAt, enabled and a compact review. It is committed: it is the review record.

## What this does not do

- It is not a kernel or OS sandbox. A reviewed extension is executable code. The pipeline
  confines manifest paths, entrypoints, cwd and its own writes; it cannot stop arbitrary
  syscalls inside a process that the operating system allows. Only review and the negative
  test stand between a manifest and code execution, which is why registration is explicit.
- network and the read/write declarations are review metadata, not enforced. An extension
  must not mutate its own registered source tree during a run; write outputs below
  GYPSY_EXTENSION_STATE (extensions/.state/) or into the caller's project instead.
- A timeout terminates the direct child. A grandchild process tree is not guaranteed to be
  killed by the Python standard library here.
- No dependency installation, package manager, signing or remote registry is involved.
- Extensions are not hot-reloaded while running; reload is an explicit re-review of files.
