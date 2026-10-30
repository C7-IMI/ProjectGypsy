# ADR-024 — TLS remote worker with isolated jobs

- **Status:** accepted, 2026-10-30.
- **Scope:** authenticated remote execution of explicitly allowlisted read-only jobs.
- **Related:** [ADR-020](ADR-020-remote-cache.md), [IMPROVEMENT-ROADMAP.md](IMPROVEMENT-ROADMAP.md).

## Decision

1. The coordinator and worker use **TLS only** (TLS 1.2+) with certificate verification and a required bearer
   token on every endpoint. There is no plaintext fallback and no verify-false path.
2. A job is an **id pair**, not a command. Only hero.wayfarer.validate and read-only engine probes are allowlisted;
   argv, cwd, shell, env and unknown keys are rejected by both coordinator and worker.
3. The worker creates a temporary detached git worktree at HEAD, runs the allowed action with a temporary state
   directory, returns result JSON and artifact SHA-256/bytes, and removes the worktree. It never runs in the main
   checkout and has no fallback if worktree creation fails.
4. Queue states are queued, claimed, completed, failed, cancelled and expired, with idempotency, duplicate-claim
   prevention and bounded payloads.
5. This is deliberately **not** arbitrary remote command execution. The allowlist is small and read-only; artifact
   upload and durable job persistence are not implemented.

## Evidence

- Coordinator tests: 26 tests; ephemeral certs generated at test time (no key committed).
- Real loopback TLS run: https://127.0.0.1:5260, health tls=required/loopback=true, submitted job completed in
  **0.88 s**, hero.wayfarer.validate passed, artifact validation.json SHA-256 returned; wrong token 401; wrong CA
  refused; plaintext refused; main checkout/worktree list unchanged.
- Full suite at integration time: 580 tests OK (before trace integration).

## Limits

- In-memory queue only; no restart persistence, priority, worker registry or heartbeats.
- One shared bearer token; no per-worker identity, rotation or scopes.
- Worker executes committed HEAD only; allowlist intentionally minimal; no artifact upload.
- Timeout/cancellation are cooperative for in-process work; the real subprocess is bounded but a timed-out injected
  runner may finish in the background.
