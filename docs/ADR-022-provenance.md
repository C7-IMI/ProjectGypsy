# ADR-022 — Signed artifact provenance and SBOM

- **Status:** accepted, 2026-10-30.
- **Scope:** local integrity provenance for declared artifacts and a deterministic SBOM.
- **Related:** [ADR-021](ADR-021-assets-metrics.md), [IMPROVEMENT-ROADMAP.md](IMPROVEMENT-ROADMAP.md).

## Decision

1. Workstream/provenance.py hashes declared artifacts (path, SHA-256, bytes), records project/engine/tool metadata,
   timestamp and signer fingerprint, and signs a canonical JSON payload with **HMAC-SHA256**. The key is 32 random
   bytes generated once at workstream/state/keys/provenance.key (state is gitignored) or supplied by
   GYPSY_PROVENANCE_KEY. The key is never written to the payload or printed.
2. Verification fails on signature tampering, wrong key, missing artifacts, changed artifact hashes, malformed payload,
   escaping paths or schema mismatch. It reports a non-secret key fingerprint and artifact results.
3. The SBOM (gypsy.sbom/v1) is built deterministically from project manifests, capability manifests, toolpacks and
   declared tools, with components and relationships sorted; corrupt manifests are problems, not invented components.
4. This is **local symmetric integrity, not PKI**: no certificate, no public key, no identity proof, no timestamp
   authority. Anyone holding the key can sign; it proves a payload has not changed since a holder signed it.
5. CLI: provenance sign, provenance verify, provenance sbom. Dashboard: /api/provenance and Insights Provenance card.

## Evidence

- Signed artifacts: artifacts/game/frame.png, assets/hero/wayfarer.glb, build/ProjectGypsy.exe.
  Verification PASS signatureValid=True, 3 artifacts, key fingerprint sha256:11232c0e...
- SBOM: 152 components, 155 relationships, written under workstream/state/provenance/sbom.json (gitignored).
- Tests: provenance module tests pass; full suite at integration time 529+ tests; dashboard API/UI tests pass.
- The key and generated provenance/SBOM state are gitignored; no secret is committed.

## Limits

- HMAC is not code signing/PKI and does not prove who signed; it proves key possession and tamper detection.
- No timestamp authority, revocation, key rotation UI or hardware-backed key.
- SBOM is manifest/tooling-level, not a full package-manager dependency graph or licence legal review.
- Artifacts must exist locally to sign/verify; remote provenance transport is not implemented.
- Dashboard summarizes the latest local state; absence shows an honest empty state.
