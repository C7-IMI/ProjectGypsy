#!/usr/bin/env python3
"""Local HMAC integrity provenance and a deterministic SBOM for Gypsy Studio.

Two independent, local tools:

1. Artifact provenance (schema gypsy.provenance/v1). A document binds declared artifacts
   (repo-relative path, SHA-256, byte size) plus project/engine/tool metadata and a timestamp
   to an HMAC-SHA256 signature. The signing key is 32 random bytes generated once at
   <state_dir>/keys/provenance.key (gitignored because workstream/state/ is gitignored) or
   supplied by the GYPSY_PROVENANCE_KEY environment variable (64 hex characters). The key is
   never written into a provenance document and is never printed. Documents carry a
   non-secret signer key fingerprint (SHA-256 over a domain separator plus the key) and the
   canonicalisation identifier; canonical_payload(document) is the exact signed byte string:
   JSON with sorted keys, compact separators, UTF-8 and the top-level signature removed.

   This is symmetric HMAC integrity, not PKI. There is no certificate, no public key, no
   external identity, no non-repudiation and no third-party attestation: anyone who can read
   the key can sign. It proves that a payload and its artifacts have not changed since a
   holder of this local key signed them, and that the verifier holds the matching key.
   verify detects signature tampering, a different key, missing artifacts and artifact
   hash/size changes.

2. SBOM (schema gypsy.sbom/v1). A deterministic inventory built from the repository's
   project manifests (*/project.gypsy.json), capability manifests
   (workstream/capabilities/*.json) and toolpack manifests (toolpacks/*.json). Components are
   projects, engines, targets, capabilities, toolpacks, declared tools and capability
   requirement tokens; relationships connect them (uses, targets, requires). Components and
   relationships are sorted, file digests are recorded, and corrupt inputs become problems
   instead of invented entries. There is no clock and no network in the SBOM.

Public API (CLI-free):

    PROVENANCE_SCHEMA, SBOM_SCHEMA, CANONICALIZATION, KEY_ENV
    ProvenanceError
    canonical_payload(document) -> bytes
    key_fingerprint(key) -> str
    key_path(state_dir=DEFAULT_STATE_DIR) -> Path
    ensure_key(state_dir=DEFAULT_STATE_DIR, *, env=None) -> bytes
    create_provenance(artifacts, *, state_dir=..., project_root=".", project=None,
                      engine=None, tools=None, key=None, env=None, timestamp=None) -> dict
    verify_provenance(document, *, project_root=".", state_dir=None, key=None,
                      env=None) -> dict
    read_provenance(path) -> dict
    write_provenance(path, document) -> Path
    build_sbom(project_root=".") -> dict
    read_sbom(path) -> dict
    write_sbom(path, sbom) -> Path
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import tempfile
from datetime import datetime, timezone
from pathlib import Path

PROVENANCE_SCHEMA = "gypsy.provenance/v1"
SBOM_SCHEMA = "gypsy.sbom/v1"
PROJECT_SCHEMA = "gypsy.project/v1"
CAPABILITY_SCHEMA = "gypsy.capability/v1"
TOOLPACK_SCHEMA = "gypsy.toolpack/v1"
CANONICALIZATION = "json-canonical/v1"
SIGNATURE_ALGORITHM = "hmac-sha256"
KEY_ENV = "GYPSY_PROVENANCE_KEY"
DEFAULT_STATE_DIR = "workstream/state"
KEY_DIR = "keys"
KEY_FILE = "provenance.key"
KEY_BYTES = 32
HEX64 = re.compile(r"^[0-9a-f]{64}$")
FINGERPRINT_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
EXCLUDED_SBOM_DIRS = frozenset(
    {
        ".git",
        ".godot",
        "__pycache__",
        "artifacts",
        "build",
        "cache",
        "logs",
        "node_modules",
        "state",
    }
)


class ProvenanceError(ValueError):
    """A provenance/SBOM input, key, document or write is invalid."""


# -- small helpers -----------------------------------------------------------


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _parse_iso(value):
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment


def _json_safe(value, label):
    try:
        text = json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ProvenanceError(f"{label} must be JSON-safe: {exc}") from None
    return json.loads(text)


def _atomic_write_text(path, text) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(
        prefix="." + path.stem + "-", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except BaseException:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise
    return path


def _atomic_write_json(path, document) -> Path:
    text = json.dumps(document, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    return _atomic_write_text(path, text)


def _read_json_document(path, label):
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        raise ProvenanceError(f"{label} unreadable: {exc}") from None
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProvenanceError(f"{label} is not valid JSON: {exc}") from None
    if not isinstance(data, dict):
        raise ProvenanceError(f"{label} must be a JSON object")
    return data


def _relative_path(value, label):
    if isinstance(value, Path):
        value = value.as_posix()
    if not isinstance(value, str) or not value.strip():
        raise ProvenanceError(f"{label} must be a non-empty repo-relative path")
    path = Path(value)
    if path.is_absolute() or path.anchor:
        raise ProvenanceError(f"{label} must be repo-relative: {value!r}")
    if ".." in path.parts:
        raise ProvenanceError(f"{label} must not escape the project root: {value!r}")
    return path.as_posix()


def _hash_file(path):
    digest = hashlib.sha256()
    size = 0
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


# -- key handling ------------------------------------------------------------


def key_path(state_dir=DEFAULT_STATE_DIR) -> Path:
    """Path of the local provenance key: <state_dir>/keys/provenance.key (gitignored state)."""
    return Path(state_dir) / KEY_DIR / KEY_FILE


def _decode_key(value) -> bytes:
    if not isinstance(value, str):
        raise ProvenanceError("provenance key must be a 64-character hexadecimal string")
    text = value.strip()
    if not re.fullmatch(r"[0-9a-fA-F]{64}", text):
        raise ProvenanceError(
            "provenance key must be 64 hexadecimal characters (32 bytes); the value was not echoed"
        )
    return bytes.fromhex(text)


def _validate_key(key) -> bytes:
    if isinstance(key, str):
        return _decode_key(key)
    if not isinstance(key, (bytes, bytearray)):
        raise ProvenanceError("provenance key must be bytes or a 64-character hexadecimal string")
    key = bytes(key)
    if len(key) < KEY_BYTES:
        raise ProvenanceError(f"provenance key must be at least {KEY_BYTES} bytes; the value was not echoed")
    return key


def key_fingerprint(key) -> str:
    """A non-secret key identifier: sha256 over a domain separator plus the key."""
    key = _validate_key(key)
    digest = hashlib.sha256(b"gypsy.provenance.keyid/v1\x00" + key).hexdigest()
    return "sha256:" + digest


def _read_key_file(path):
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise ProvenanceError(f"provenance key file unreadable: {path}: {exc}") from None
    return _decode_key(text)


def _generate_key(path):
    path = Path(path)
    key = secrets.token_bytes(KEY_BYTES)
    _atomic_write_text(path, key.hex() + "\n")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass  # best effort on platforms without POSIX modes
    return key


def ensure_key(state_dir=DEFAULT_STATE_DIR, *, env=None) -> bytes:
    """Return the explicit env key, or read/create <state_dir>/keys/provenance.key.

    An explicitly supplied env mapping (or the real environment) wins over a key file,
    including an empty mapping (which falls through to the file/generation path). The key
    value is never written to stdout/stderr by this module.
    """
    env_map = os.environ if env is None else env
    if KEY_ENV in env_map:
        value = env_map.get(KEY_ENV)
        return _decode_key(value)
    path = key_path(state_dir)
    if path.is_file():
        return _read_key_file(path)
    return _generate_key(path)


def _resolve_key(state_dir, *, key=None, env=None, create):
    if key is not None:
        return _validate_key(key)
    env_map = os.environ if env is None else env
    if KEY_ENV in env_map:
        value = env_map.get(KEY_ENV)
        return _decode_key(value)
    directory = Path(state_dir) if state_dir is not None else Path(DEFAULT_STATE_DIR)
    path = key_path(directory)
    if path.is_file():
        return _read_key_file(path)
    if create:
        return _generate_key(path)
    raise ProvenanceError(
        f"no provenance key at {path}; sign first or set {KEY_ENV} (the key is never printed)"
    )


# -- canonicalisation and signing -------------------------------------------


def canonical_payload(document) -> bytes:
    """The exact signed bytes: top-level signature removed, JSON sorted/compact, UTF-8."""
    if not isinstance(document, dict):
        raise ProvenanceError("provenance document must be a JSON object")
    payload = {key: value for key, value in document.items() if key != "signature"}
    try:
        return json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ProvenanceError(f"provenance payload must be JSON-safe: {exc}") from None


def create_provenance(
    artifacts,
    *,
    state_dir=DEFAULT_STATE_DIR,
    project_root=".",
    project=None,
    engine=None,
    tools=None,
    key=None,
    env=None,
    timestamp=None,
) -> dict:
    """Hash declared artifacts and sign their provenance with HMAC-SHA256.

    artifacts is an iterable of repo-relative paths (a single string/Path is accepted). Every
    file must exist and stay inside project_root; a missing or escaping path is an error, so
    no signature can claim an artifact that was not observed. project/engine/tools are JSON
    metadata copied into the signed subject; timestamp defaults to the current UTC time and is
    explicit for deterministic tests/evidence.
    """
    root = Path(project_root)
    if isinstance(artifacts, (str, Path)):
        artifacts = [artifacts]
    if not isinstance(artifacts, (list, tuple)) and not hasattr(artifacts, "__iter__"):
        raise ProvenanceError("artifacts must be an iterable of repo-relative paths")
    entries = {}
    for value in artifacts:
        relative = _relative_path(value, "artifact path")
        if relative in entries:
            continue
        path = root / relative
        if not path.is_file():
            raise ProvenanceError(f"artifact not found: {relative}")
        digest, size = _hash_file(path)
        entries[relative] = {"path": relative, "sha256": digest, "bytes": size}
    if not entries:
        raise ProvenanceError("at least one declared artifact is required")
    if timestamp is None:
        timestamp = _utc_now_iso()
    elif not isinstance(timestamp, str) or _parse_iso(timestamp) is None:
        raise ProvenanceError("timestamp must be an ISO-8601 date-time string")
    key_bytes = _resolve_key(state_dir, key=key, env=env, create=True)
    payload = {
        "schema": PROVENANCE_SCHEMA,
        "kind": "artifact-provenance",
        "canonicalization": CANONICALIZATION,
        "createdAt": timestamp,
        "subject": {
            "artifacts": [entries[name] for name in sorted(entries)],
            "project": _json_safe(project, "project") if project is not None else None,
            "engine": _json_safe(engine, "engine") if engine is not None else None,
            "tools": _json_safe(tools, "tools") if tools is not None else None,
        },
        "signer": {
            "algorithm": SIGNATURE_ALGORITHM,
            "keyFingerprint": key_fingerprint(key_bytes),
        },
    }
    signature = hmac.new(key_bytes, canonical_payload(payload), hashlib.sha256).hexdigest()
    document = dict(payload)
    document["signature"] = signature
    return document


def _verify_failure(errors, key_fingerprint_value=None):
    return {
        "schema": PROVENANCE_SCHEMA,
        "kind": "artifact-provenance-verification",
        "passed": False,
        "signatureValid": False,
        "keyFingerprint": key_fingerprint_value,
        "expectedFingerprint": None,
        "artifacts": [],
        "errors": list(errors),
    }


def _artifact_entry_error(entry, index):
    if not isinstance(entry, dict):
        return f"subject.artifacts[{index}] must be an object"
    try:
        _relative_path(entry.get("path"), f"subject.artifacts[{index}].path")
    except ProvenanceError as exc:
        return str(exc)
    digest = entry.get("sha256")
    if not isinstance(digest, str) or not HEX64.match(digest):
        return f"subject.artifacts[{index}].sha256 must be 64 lowercase hexadecimal characters"
    size = entry.get("bytes")
    if isinstance(size, bool) or not isinstance(size, int) or size < 0:
        return f"subject.artifacts[{index}].bytes must be a non-negative integer"
    return None


def verify_provenance(
    document,
    *,
    project_root=".",
    state_dir=None,
    key=None,
    env=None,
) -> dict:
    """Verify a provenance document and its artifacts; returns a JSON-safe result dict.

    Detects a malformed payload, a tampered payload/signature, a different key, a missing
    artifact and an artifact whose hash or size changed. This is HMAC integrity with a local
    shared secret; it is not PKI and makes no identity or non-repudiation claim.
    """
    if not isinstance(document, dict):
        return _verify_failure(["document must be a JSON object"])
    fingerprint = document.get("signer", {}).get("keyFingerprint") if isinstance(document.get("signer"), dict) else None
    errors = []
    if document.get("schema") != PROVENANCE_SCHEMA:
        errors.append(f"unexpected schema {document.get('schema')!r}")
    if document.get("canonicalization") != CANONICALIZATION:
        errors.append(
            f"unexpected canonicalization {document.get('canonicalization')!r}; expected {CANONICALIZATION!r}"
        )
    if _parse_iso(document.get("createdAt")) is None:
        errors.append("createdAt must be an ISO-8601 date-time string")
    signer = document.get("signer")
    if not isinstance(signer, dict):
        errors.append("signer must be an object")
    else:
        if signer.get("algorithm") != SIGNATURE_ALGORITHM:
            errors.append(f"signer.algorithm must be {SIGNATURE_ALGORITHM!r}")
        signer_fingerprint = signer.get("keyFingerprint")
        if not isinstance(signer_fingerprint, str) or not FINGERPRINT_RE.match(signer_fingerprint):
            errors.append("signer.keyFingerprint must be sha256:<64 lowercase hex>")
        else:
            fingerprint = signer_fingerprint
    signature = document.get("signature")
    if not isinstance(signature, str) or not HEX64.match(signature):
        errors.append("signature must be 64 lowercase hexadecimal characters")
    subject = document.get("subject")
    artifacts = None
    if not isinstance(subject, dict):
        errors.append("subject must be an object")
    else:
        artifacts = subject.get("artifacts")
        if not isinstance(artifacts, list) or not artifacts:
            errors.append("subject.artifacts must be a non-empty list")
            artifacts = None
        else:
            for index, entry in enumerate(artifacts):
                message = _artifact_entry_error(entry, index)
                if message:
                    errors.append(message)
    if errors:
        result = _verify_failure(errors, fingerprint)
        return result

    try:
        key_bytes = _resolve_key(state_dir, key=key, env=env, create=False)
        expected_fingerprint = key_fingerprint(key_bytes)
    except ProvenanceError as exc:
        key_bytes = None
        expected_fingerprint = None
        errors.append(str(exc))

    signature_valid = False
    if key_bytes is not None:
        if fingerprint != expected_fingerprint:
            errors.append(
                "wrong key: the document signer fingerprint does not match the verifying key"
            )
        else:
            expected_signature = hmac.new(
                key_bytes, canonical_payload(document), hashlib.sha256
            ).hexdigest()
            signature_valid = hmac.compare_digest(signature, expected_signature)
            if not signature_valid:
                errors.append(
                    "signature mismatch: the signed payload or the signature was tampered with"
                )

    root = Path(project_root)
    artifact_results = []
    for entry in artifacts:
        relative = entry["path"]
        path = root / relative
        exists = path.is_file()
        actual_sha = None
        actual_bytes = None
        if exists:
            try:
                actual_sha, actual_bytes = _hash_file(path)
            except OSError as exc:
                errors.append(f"artifact unreadable: {relative}: {exc}")
        else:
            errors.append(f"artifact missing: {relative}")
        sha_matches = bool(exists and actual_sha == entry["sha256"])
        bytes_matches = bool(exists and actual_bytes == entry["bytes"])
        if exists and not sha_matches:
            errors.append(f"artifact hash mismatch: {relative}")
        if exists and not bytes_matches:
            errors.append(f"artifact size mismatch: {relative}")
        artifact_results.append(
            {
                "path": relative,
                "exists": exists,
                "sha256": actual_sha,
                "expectedSha256": entry["sha256"],
                "sha256Matches": sha_matches,
                "bytes": actual_bytes,
                "expectedBytes": entry["bytes"],
                "bytesMatches": bytes_matches,
            }
        )
    passed = bool(signature_valid and not errors)
    return {
        "schema": PROVENANCE_SCHEMA,
        "kind": "artifact-provenance-verification",
        "passed": passed,
        "signatureValid": signature_valid,
        "keyFingerprint": fingerprint,
        "expectedFingerprint": expected_fingerprint,
        "artifacts": artifact_results,
        "errors": errors,
    }


def read_provenance(path) -> dict:
    """Read a provenance JSON document without verifying it (call verify_provenance after)."""
    document = _read_json_document(path, "provenance document")
    if document.get("schema") != PROVENANCE_SCHEMA:
        raise ProvenanceError(
            f"unexpected schema {document.get('schema')!r}; expected {PROVENANCE_SCHEMA!r}"
        )
    return document


def write_provenance(path, document) -> Path:
    """Atomically write a provenance document; returns the path."""
    if not isinstance(document, dict) or document.get("schema") != PROVENANCE_SCHEMA:
        raise ProvenanceError(f"provenance document must use schema {PROVENANCE_SCHEMA!r}")
    return _atomic_write_json(path, document)


# -- SBOM --------------------------------------------------------------------


def _sbom_problem(problems, path, message):
    problems.append({"path": path, "error": message})


def _read_manifest(path, relative, schema, problems):
    try:
        raw = path.read_bytes()
    except OSError as exc:
        _sbom_problem(problems, relative, f"unreadable: {exc}")
        return None, None
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        _sbom_problem(problems, relative, f"not valid UTF-8: {exc}")
        return None, None
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        _sbom_problem(problems, relative, f"invalid JSON: {exc}")
        return None, None
    if not isinstance(data, dict):
        _sbom_problem(problems, relative, "not a JSON object")
        return None, None
    if data.get("schema") != schema:
        _sbom_problem(
            problems, relative, f"unexpected schema {data.get('schema')!r}; expected {schema!r}"
        )
        return None, None
    return data, hashlib.sha256(raw).hexdigest()


def _relative(path, root):
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _project_manifests(root):
    found = []
    for current, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(
            name
            for name in dirnames
            if name not in EXCLUDED_SBOM_DIRS and not name.startswith(".")
        )
        if "project.gypsy.json" in filenames:
            found.append(Path(current) / "project.gypsy.json")
    return sorted(found, key=lambda path: _relative(path, root))


def _new_component(ref, kind, name, version, source, properties):
    return {
        "bomRef": ref,
        "type": kind,
        "name": name,
        "version": version,
        "sources": [source] if source else [],
        "properties": dict(properties or {}),
    }


def _add_component(components, ref, kind, name, version=None, source=None, properties=None):
    if ref in components:
        component = components[ref]
        if source and source not in component["sources"]:
            component["sources"].append(source)
            component["sources"].sort()
        for key, value in (properties or {}).items():
            component["properties"].setdefault(key, value)
        return component
    component = _new_component(ref, kind, name, version, source, properties)
    components[ref] = component
    return component


def _tool_descriptor(declared, source, problems):
    if isinstance(declared, str):
        text = declared.strip()
        if not text:
            _sbom_problem(problems, source, "blank declared tool")
            return None
        return {"bomRef": "tool:" + text, "name": text, "version": None}
    if isinstance(declared, dict):
        name = declared.get("name", declared.get("id"))
        if not isinstance(name, str) or not name.strip():
            name = json.dumps(declared, sort_keys=True, ensure_ascii=False)
        version = declared.get("version")
        version = version if isinstance(version, str) and version else None
        ref = "tool:" + name + (("@" + version) if version else "")
        return {"bomRef": ref, "name": name, "version": version}
    _sbom_problem(problems, source, f"declared tool must be a string or object, not {type(declared).__name__}")
    return None


def build_sbom(project_root=".") -> dict:
    """Build a deterministic SBOM from project, capability and toolpack manifests.

    Corrupt or wrong-schema files are listed under problems and skipped; they never become
    invented components. There is no clock, no network and no signature in an SBOM.
    """
    root = Path(project_root)
    problems = []
    components = {}
    relationships = set()
    engine_refs = {}
    capability_ids = set()
    toolpack_ids = set()

    if not root.is_dir():
        _sbom_problem(problems, root.as_posix(), "project root is not a directory")

    # Projects and their engines/targets.
    for path in _project_manifests(root) if root.is_dir() else []:
        relative = _relative(path, root)
        data, digest = _read_manifest(path, relative, PROJECT_SCHEMA, problems)
        if data is None:
            continue
        name = data.get("name")
        if not isinstance(name, str) or not name.strip():
            name = path.parent.name or "project"
        ref = "project:" + name
        if ref in components:
            ref = ref + "@" + relative
        targets = [item for item in (data.get("targets") or []) if isinstance(item, str) and item]
        engine = data.get("engine")
        if not isinstance(engine, dict):
            engine = None
        properties = {
            "schema": data.get("schema"),
            "manifestSha256": digest,
            "targets": sorted(targets),
        }
        if engine is not None:
            properties["engine"] = engine
        _add_component(components, ref, "project", name, None, relative, properties)
        if engine is not None:
            engine_id = engine.get("id")
            engine_id = engine_id if isinstance(engine_id, str) and engine_id else "unknown"
            version = engine.get("version")
            version = version if isinstance(version, str) and version else None
            engine_ref = f"engine:{engine_id}:{version or 'unknown'}"
            _add_component(
                components,
                engine_ref,
                "engine",
                engine_id,
                version,
                relative,
                {"adapter": engine.get("adapter"), "manifestSha256": digest},
            )
            engine_refs.setdefault(engine_id, set()).add(engine_ref)
            relationships.add((ref, "uses", engine_ref))
        for target in sorted(set(targets)):
            target_ref = "target:" + target
            _add_component(components, target_ref, "target", target, None, relative, {})
            relationships.add((ref, "targets", target_ref))

    # Capability components and relationships.
    capability_records = []
    capability_dir = root / "workstream" / "capabilities"
    paths = sorted(capability_dir.glob("*.json")) if capability_dir.is_dir() else []
    for path in paths:
        relative = _relative(path, root)
        data, digest = _read_manifest(path, relative, CAPABILITY_SCHEMA, problems)
        if data is None:
            continue
        capability_id = data.get("id")
        if not isinstance(capability_id, str) or not capability_id:
            _sbom_problem(problems, relative, "missing string id")
            continue
        if capability_id in capability_ids:
            _sbom_problem(problems, relative, f"duplicate capability id {capability_id!r}")
            continue
        capability_ids.add(capability_id)
        capability_records.append((capability_id, relative, data, digest))
    for capability_id, relative, data, digest in capability_records:
        ref = "capability:" + capability_id
        properties = {"schema": data.get("schema"), "manifestSha256": digest}
        for key in ("layer", "kind", "maturity"):
            if isinstance(data.get(key), str):
                properties[key] = data[key]
        _add_component(components, ref, "capability", capability_id, None, relative, properties)
        tool = data.get("tool")
        if isinstance(tool, str) and tool:
            tool_ref = "tool:" + tool
            _add_component(components, tool_ref, "tool", tool, None, relative, {})
            relationships.add((ref, "uses", tool_ref))
        engine = data.get("engine")
        if isinstance(engine, str) and engine:
            matching = sorted(engine_refs.get(engine, set()))
            if not matching:
                engine_ref = "engine:" + engine
                _add_component(
                    components, engine_ref, "engine", engine, None, relative, {"declaredBy": "capability"}
                )
                engine_refs.setdefault(engine, set()).add(engine_ref)
                matching = [engine_ref]
            for engine_ref in matching:
                relationships.add((ref, "uses", engine_ref))
        requires = data.get("requires")
        if isinstance(requires, list):
            for token in sorted({item for item in requires if isinstance(item, str) and item}):
                if token in capability_ids:
                    relationships.add((ref, "requires", "capability:" + token))
                else:
                    requirement_ref = "requirement:" + token
                    _add_component(components, requirement_ref, "requirement", token, None, relative, {})
                    relationships.add((ref, "requires", requirement_ref))
        elif requires is not None:
            _sbom_problem(problems, relative, "requires must be a list")

    # Toolpack components and their declared tools.
    toolpack_dir = root / "toolpacks"
    paths = sorted(toolpack_dir.glob("*.json")) if toolpack_dir.is_dir() else []
    for path in paths:
        relative = _relative(path, root)
        data, digest = _read_manifest(path, relative, TOOLPACK_SCHEMA, problems)
        if data is None:
            continue
        toolpack_id = data.get("id")
        if not isinstance(toolpack_id, str) or not toolpack_id:
            _sbom_problem(problems, relative, "missing string id")
            continue
        if toolpack_id in toolpack_ids:
            _sbom_problem(problems, relative, f"duplicate toolpack id {toolpack_id!r}")
            continue
        toolpack_ids.add(toolpack_id)
        ref = "toolpack:" + toolpack_id
        actions = data.get("actions")
        action_ids = sorted(
            action.get("id")
            for action in actions
            if isinstance(action, dict) and isinstance(action.get("id"), str)
        ) if isinstance(actions, list) else []
        properties = {
            "schema": data.get("schema"),
            "manifestSha256": digest,
            "actions": action_ids,
        }
        if isinstance(data.get("license"), str):
            properties["license"] = data["license"]
        _add_component(components, ref, "toolpack", toolpack_id, None, relative, properties)
        tools = data.get("tools")
        if not isinstance(tools, list):
            _sbom_problem(problems, relative, "tools must be a list")
            continue
        for declared in tools:
            descriptor = _tool_descriptor(declared, relative, problems)
            if descriptor is None:
                continue
            _add_component(
                components,
                descriptor["bomRef"],
                "tool",
                descriptor["name"],
                descriptor["version"],
                relative,
                {},
            )
            relationships.add((ref, "uses", descriptor["bomRef"]))

    component_list = sorted(
        components.values(), key=lambda component: (component["type"], component["bomRef"])
    )
    relationship_list = [
        {"from": source, "type": relation, "to": target}
        for source, relation, target in sorted(relationships)
    ]
    by_type = {}
    for component in component_list:
        by_type[component["type"]] = by_type.get(component["type"], 0) + 1
    unique_problems = []
    seen = set()
    for problem in sorted(
        problems, key=lambda item: (str(item.get("path")), str(item.get("error")))
    ):
        key = (problem.get("path"), problem.get("error"))
        if key not in seen:
            seen.add(key)
            unique_problems.append(problem)
    return {
        "schema": SBOM_SCHEMA,
        "kind": "sbom",
        "root": root.as_posix(),
        "components": component_list,
        "relationships": relationship_list,
        "counts": {
            "components": len(component_list),
            "relationships": len(relationship_list),
            "byType": {key: by_type[key] for key in sorted(by_type)},
        },
        "problems": unique_problems,
    }


def read_sbom(path) -> dict:
    """Read an SBOM document; raises ProvenanceError for unreadable or wrong-schema files."""
    document = _read_json_document(path, "SBOM document")
    if document.get("schema") != SBOM_SCHEMA:
        raise ProvenanceError(
            f"unexpected schema {document.get('schema')!r}; expected {SBOM_SCHEMA!r}"
        )
    return document


def write_sbom(path, sbom) -> Path:
    """Atomically write an SBOM document; returns the path."""
    if not isinstance(sbom, dict) or sbom.get("schema") != SBOM_SCHEMA:
        raise ProvenanceError(f"SBOM document must use schema {SBOM_SCHEMA!r}")
    return _atomic_write_json(path, sbom)
