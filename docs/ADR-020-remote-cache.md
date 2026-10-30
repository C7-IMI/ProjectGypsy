# ADR-020 — authenticated remote action cache (P1)

- **Status:** accepted, 2026-10-30.
- **Scope:** sharing the local content-addressed action cache between checkouts/machines.
- **Related:** [ADR-019](ADR-019-cache-quality.md), [IMPROVEMENT-ROADMAP.md](IMPROVEMENT-ROADMAP.md).

## Context

The local cache avoids repeated validation/build work on one checkout. P1 needs the same action results available to a
second checkout or machine without handing the server arbitrary command execution.

## Decision

1. Add a **loopback-first HTTP cache service** (workstream/remote_cache.py) with a required bearer token. Only exact
   entries and blobs are served; there is no shell, command execution, URL fetching or path browsing.
2. Bind 127.0.0.1 by default and refuse non-loopback binding. For a second machine, use an SSH tunnel or a trusted
   reverse proxy; the service itself is not exposed directly.
3. The local ActionCache remains primary. On a local miss it may fetch an entry and its verified blobs from the remote
   cache; a successful local store is pushed best-effort. Remote failures are counted and reported but never fail a
   run. Pass remote=False for local-only tests.
4. Blob ids and bodies are SHA-256 verified on both sides; bodies are bounded, Content-Length is required, and chunked
   transfer is refused. Entry ids are fixed 64-hex names in a fixed directory.
5. Enable explicitly with GYPSY_REMOTE_CACHE_URL and GYPSY_REMOTE_CACHE_TOKEN. CLI: cache serve, cache remote, and
   cache stats show remote counters. No token is printed.
6. This is not remote execution. The existing bounded worker pool remains local; remote workers are a later increment.

## Evidence

Two clean local state directories against one loopback server:

- first hero validation: local miss, remote push, **0.178 s**;
- second state directory: local miss, **remote hit, 0.0 s**, restored artifacts/hero/validation.json;
- server stats: 1 entry, 1 blob, 2 puts, 2 gets, 0 errors.

Tests cover round trip, authentication rejection, corrupt blob, missing entry, oversize payload, local-only behavior and
CLI status. Full suite at the time: 456 tests OK (3 skipped).

## Consequences

**Positive:** cache reuse across checkouts/machines; no arbitrary remote command surface; local-only remains the default.

**Limits:** no TLS (loopback/SSH-tunnel only); one bearer token, no per-user authorization; no remote artifact GC beyond
the server root; no remote execution/worker fleet yet. Remote cache is an optimization, never evidence by itself.
