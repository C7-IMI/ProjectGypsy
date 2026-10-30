#!/usr/bin/env python3
"""Tests for local HMAC provenance and the deterministic SBOM (workstream/provenance.py).

All keys are fixed test bytes; no real key, repository state, network or clock is used.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

WORKSTREAM = Path(__file__).resolve().parents[1]
REPO_ROOT = WORKSTREAM.parent
sys.path.insert(0, str(WORKSTREAM))

import provenance  # noqa: E402

KEY = b"k" * 32
OTHER_KEY = b"z" * 32
TIMESTAMP = "2026-10-30T12:00:00+00:00"


def write_json(root, relative, payload):
    path = Path(root) / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


class KeyTests(unittest.TestCase):
    def test_ensure_key_generates_once_in_gitignored_state_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state"
            first = provenance.ensure_key(state, env={})
            self.assertEqual(len(first), 32)
            path = provenance.key_path(state)
            self.assertTrue(path.is_file())
            self.assertEqual(path.read_text(encoding="utf-8").strip(), first.hex())
            second = provenance.ensure_key(state, env={})
            self.assertEqual(first, second)
            self.assertTrue(provenance.key_fingerprint(first).startswith("sha256:"))

    def test_env_key_wins_and_creates_no_key_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state"
            key = provenance.ensure_key(state, env={"GYPSY_PROVENANCE_KEY": KEY.hex()})
            self.assertEqual(key, KEY)
            self.assertFalse(provenance.key_path(state).exists())
            with self.assertRaises(provenance.ProvenanceError):
                provenance.ensure_key(state, env={"GYPSY_PROVENANCE_KEY": "secret-not-hex"})

    def test_corrupt_key_file_is_not_silently_replaced(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state"
            path = provenance.key_path(state)
            path.parent.mkdir(parents=True)
            path.write_text("not-a-key", encoding="utf-8")
            with self.assertRaises(provenance.ProvenanceError):
                provenance.ensure_key(state, env={})
            self.assertEqual(path.read_text(encoding="utf-8"), "not-a-key")

    def test_key_validation_and_fingerprint(self):
        with self.assertRaises(provenance.ProvenanceError):
            provenance.key_fingerprint(b"short")
        with self.assertRaises(provenance.ProvenanceError):
            provenance.key_fingerprint("zz")
        self.assertEqual(provenance.key_fingerprint(KEY), provenance.key_fingerprint(KEY.hex()))
        self.assertNotEqual(provenance.key_fingerprint(KEY), provenance.key_fingerprint(OTHER_KEY))


class ProvenanceCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.project = self.root / "project"
        self.project.mkdir()
        self.state = self.root / "state"
        (self.project / "a.bin").write_bytes(b"alpha")
        (self.project / "dir").mkdir()
        (self.project / "dir" / "b.bin").write_bytes(b"beta")

    def sign(self, files=("a.bin", "dir/b.bin"), **overrides):
        options = {
            "state_dir": self.state,
            "project_root": self.project,
            "project": {"name": "ProjectX", "manifest": "game/project.gypsy.json"},
            "engine": {"id": "godot", "version": "4.7.2", "adapter": "godot-4"},
            "tools": [{"name": "Godot", "version": "4.7.2"}],
            "key": KEY,
            "timestamp": TIMESTAMP,
        }
        options.update(overrides)
        return provenance.create_provenance(list(files), **options)


class SignVerifyTests(ProvenanceCase):
    def test_sign_verify_round_trip(self):
        document = self.sign()
        self.assertEqual(document["schema"], provenance.PROVENANCE_SCHEMA)
        self.assertEqual(document["canonicalization"], provenance.CANONICALIZATION)
        self.assertEqual(document["subject"]["project"], {"name": "ProjectX", "manifest": "game/project.gypsy.json"})
        self.assertEqual(document["subject"]["engine"]["version"], "4.7.2")
        self.assertEqual(
            [item["path"] for item in document["subject"]["artifacts"]], ["a.bin", "dir/b.bin"]
        )
        self.assertEqual(document["subject"]["artifacts"][0]["bytes"], 5)
        self.assertEqual(document["signer"]["algorithm"], "hmac-sha256")
        self.assertEqual(document["signer"]["keyFingerprint"], provenance.key_fingerprint(KEY))
        json.dumps(document, allow_nan=False)
        result = provenance.verify_provenance(document, project_root=self.project, key=KEY)
        self.assertTrue(result["passed"])
        self.assertTrue(result["signatureValid"])
        self.assertEqual(result["errors"], [])
        self.assertEqual([item["path"] for item in result["artifacts"]], ["a.bin", "dir/b.bin"])

    def test_artifacts_are_deduplicated_and_sorted(self):
        document = self.sign(files=["dir/b.bin", "a.bin", "a.bin"])
        self.assertEqual(
            [item["path"] for item in document["subject"]["artifacts"]], ["a.bin", "dir/b.bin"]
        )

    def test_canonical_payload_is_order_independent_and_excludes_signature(self):
        document = self.sign()
        first = provenance.canonical_payload(document)
        reordered = dict(reversed(list(document.items())))
        self.assertEqual(first, provenance.canonical_payload(reordered))
        self.assertNotIn(b"signature", first)
        self.assertIn(b"canonicalization", first)
        changed = dict(document)
        changed["createdAt"] = "2026-10-30T13:00:00+00:00"
        self.assertNotEqual(first, provenance.canonical_payload(changed))

    def test_signing_requires_real_repo_relative_artifacts(self):
        with self.assertRaises(provenance.ProvenanceError):
            self.sign(files=["missing.bin"])
        with self.assertRaises(provenance.ProvenanceError):
            self.sign(files=["../escape.bin"])
        with self.assertRaises(provenance.ProvenanceError):
            self.sign(files=[str(self.project / "a.bin")])
        with self.assertRaises(provenance.ProvenanceError):
            self.sign(files=[])
        with self.assertRaises(provenance.ProvenanceError):
            self.sign(timestamp="not-a-timestamp")

    def test_tampered_payload_fails(self):
        document = self.sign()
        document["subject"]["artifacts"][0]["sha256"] = "0" * 64
        result = provenance.verify_provenance(document, project_root=self.project, key=KEY)
        self.assertFalse(result["passed"])
        self.assertFalse(result["signatureValid"])
        self.assertTrue(any("signature mismatch" in item for item in result["errors"]))

    def test_tampered_signature_fails(self):
        document = self.sign()
        document["signature"] = "0" * 64
        result = provenance.verify_provenance(document, project_root=self.project, key=KEY)
        self.assertFalse(result["passed"])
        self.assertFalse(result["signatureValid"])

    def test_wrong_key_fails_with_fingerprint_mismatch(self):
        document = self.sign()
        result = provenance.verify_provenance(document, project_root=self.project, key=OTHER_KEY)
        self.assertFalse(result["passed"])
        self.assertFalse(result["signatureValid"])
        self.assertNotEqual(result["keyFingerprint"], result["expectedFingerprint"])
        self.assertTrue(any("wrong key" in item for item in result["errors"]))

    def test_missing_artifact_is_detected_after_signing(self):
        document = self.sign()
        (self.project / "a.bin").unlink()
        result = provenance.verify_provenance(document, project_root=self.project, key=KEY)
        self.assertTrue(result["signatureValid"])
        self.assertFalse(result["passed"])
        self.assertTrue(any("artifact missing: a.bin" in item for item in result["errors"]))
        self.assertFalse(result["artifacts"][0]["exists"])

    def test_changed_artifact_hash_and_size_are_detected(self):
        document = self.sign()
        (self.project / "a.bin").write_bytes(b"tampered payload")
        result = provenance.verify_provenance(document, project_root=self.project, key=KEY)
        self.assertTrue(result["signatureValid"])
        self.assertFalse(result["passed"])
        self.assertTrue(any("hash mismatch" in item for item in result["errors"]))
        self.assertTrue(any("size mismatch" in item for item in result["errors"]))

    def test_malformed_payloads_fail_without_raising(self):
        document = self.sign()
        cases = [None, "text", {}, dict(document, schema="other/v1")]
        no_signature = dict(document)
        del no_signature["signature"]
        cases.append(no_signature)
        cases.append(dict(document, canonicalization="other"))
        bad_artifacts = dict(document)
        bad_artifacts["subject"] = {"artifacts": [{"path": "../x", "sha256": "x", "bytes": -1}]}
        cases.append(bad_artifacts)
        for case in cases:
            result = provenance.verify_provenance(case, project_root=self.project, key=KEY)
            self.assertFalse(result["passed"], case)
            self.assertFalse(result["signatureValid"], case)
            self.assertTrue(result["errors"], case)

    def test_verification_without_a_key_fails_clearly(self):
        document = self.sign()
        result = provenance.verify_provenance(document, project_root=self.project, state_dir=self.state, env={})
        self.assertFalse(result["passed"])
        self.assertFalse(result["signatureValid"])
        self.assertTrue(any("no provenance key" in item for item in result["errors"]))

    def test_environment_key_can_verify(self):
        document = self.sign()
        result = provenance.verify_provenance(
            document, project_root=self.project, env={"GYPSY_PROVENANCE_KEY": KEY.hex()}
        )
        self.assertTrue(result["passed"])

    def test_write_read_provenance_is_atomic(self):
        document = self.sign()
        path = provenance.write_provenance(self.root / "out" / "provenance.json", document)
        self.assertEqual(provenance.read_provenance(path), document)
        self.assertEqual([item.name for item in path.parent.iterdir() if item.name.endswith(".tmp")], [])
        (self.root / "out" / "bad.json").write_text("{not json", encoding="utf-8")
        with self.assertRaises(provenance.ProvenanceError):
            provenance.read_provenance(self.root / "out" / "bad.json")
        with self.assertRaises(provenance.ProvenanceError):
            provenance.write_provenance(self.root / "out" / "wrong.json", {"schema": "other"})

    def test_secret_key_is_never_in_the_document_or_errors(self):
        document = self.sign()
        text = json.dumps(document)
        self.assertNotIn(KEY.hex(), text.lower())
        self.assertNotIn(KEY.hex(), str(document))
        with self.assertRaises(provenance.ProvenanceError) as caught:
            provenance.ensure_key(self.state, env={"GYPSY_PROVENANCE_KEY": "leaky-secret-value"})
        self.assertNotIn("leaky-secret-value", str(caught.exception))


class SbomTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def build_project(self):
        write_json(self.root, "game/project.gypsy.json", {
            "schema": provenance.PROJECT_SCHEMA,
            "name": "ProjectX",
            "engine": {"id": "godot", "version": "4.7.2", "adapter": "godot-4"},
            "targets": ["pc", "mobile"],
        })
        write_json(self.root, "workstream/capabilities/a.json", {
            "schema": provenance.CAPABILITY_SCHEMA,
            "id": "cap.a",
            "layer": "art",
            "kind": "export",
            "maturity": "stable",
            "tool": "blender",
            "engine": "godot",
            "requires": ["blender.installed", "cap.b"],
        })
        write_json(self.root, "workstream/capabilities/b.json", {
            "schema": provenance.CAPABILITY_SCHEMA,
            "id": "cap.b",
            "layer": "game",
            "kind": "check",
            "maturity": "stable",
        })
        write_json(self.root, "toolpacks/p.json", {
            "schema": provenance.TOOLPACK_SCHEMA,
            "id": "pack.p",
            "name": "Pack P",
            "tools": ["Blender 5.2.3", {"name": "Python", "version": "3.14"}],
            "license": "MIT",
            "actions": [{"id": "build"}, {"id": "check"}],
        })

    def test_empty_root_produces_an_empty_stable_sbom(self):
        sbom = provenance.build_sbom(self.root)
        self.assertEqual(sbom["schema"], provenance.SBOM_SCHEMA)
        self.assertEqual(sbom["components"], [])
        self.assertEqual(sbom["relationships"], [])
        self.assertEqual(sbom["counts"], {"components": 0, "relationships": 0, "byType": {}})
        self.assertEqual(sbom["problems"], [])
        json.dumps(sbom)

    def test_synthetic_repository_components_and_relationships(self):
        self.build_project()
        sbom = provenance.build_sbom(self.root)
        self.assertEqual(sbom["problems"], [])
        refs = {component["bomRef"] for component in sbom["components"]}
        self.assertTrue({
            "project:ProjectX",
            "engine:godot:4.7.2",
            "target:pc",
            "target:mobile",
            "capability:cap.a",
            "capability:cap.b",
            "toolpack:pack.p",
            "tool:blender",
            "tool:Blender 5.2.3",
            "tool:Python@3.14",
            "requirement:blender.installed",
        }.issubset(refs))
        relations = {(item["from"], item["type"], item["to"]) for item in sbom["relationships"]}
        self.assertIn(("project:ProjectX", "uses", "engine:godot:4.7.2"), relations)
        self.assertIn(("project:ProjectX", "targets", "target:pc"), relations)
        self.assertIn(("capability:cap.a", "uses", "tool:blender"), relations)
        self.assertIn(("capability:cap.a", "uses", "engine:godot:4.7.2"), relations)
        self.assertIn(("capability:cap.a", "requires", "requirement:blender.installed"), relations)
        self.assertIn(("capability:cap.a", "requires", "capability:cap.b"), relations)
        self.assertIn(("toolpack:pack.p", "uses", "tool:Blender 5.2.3"), relations)
        self.assertIn(("toolpack:pack.p", "uses", "tool:Python@3.14"), relations)
        self.assertEqual(sbom["components"], sorted(sbom["components"], key=lambda item: (item["type"], item["bomRef"])))
        self.assertEqual(sbom["relationships"], sorted(sbom["relationships"], key=lambda item: (item["from"], item["type"], item["to"])))
        self.assertEqual(sbom["counts"]["components"], len(sbom["components"]))
        python = next(item for item in sbom["components"] if item["bomRef"] == "tool:Python@3.14")
        self.assertEqual(python["version"], "3.14")
        pack = next(item for item in sbom["components"] if item["bomRef"] == "toolpack:pack.p")
        self.assertEqual(pack["properties"]["actions"], ["build", "check"])

    def test_sbom_is_deterministic(self):
        self.build_project()
        first = provenance.build_sbom(self.root)
        second = provenance.build_sbom(self.root)
        self.assertEqual(first, second)
        self.assertEqual(json.dumps(first), json.dumps(second))

    def test_corrupt_and_wrong_schema_inputs_become_problems(self):
        self.build_project()
        (self.root / "workstream" / "capabilities" / "broken.json").write_text("{not json", encoding="utf-8")
        write_json(self.root, "workstream/capabilities/alien.json", {"schema": "gypsy.alien/v1", "id": "x"})
        sbom = provenance.build_sbom(self.root)
        self.assertIn("capability:cap.a", {item["bomRef"] for item in sbom["components"]})
        paths = [item["path"] for item in sbom["problems"]]
        self.assertIn("workstream/capabilities/broken.json", paths)
        self.assertIn("workstream/capabilities/alien.json", paths)
        self.assertEqual(sbom["problems"], sorted(sbom["problems"], key=lambda item: (item["path"], item["error"])))

    def test_write_read_sbom_is_atomic(self):
        self.build_project()
        sbom = provenance.build_sbom(self.root)
        path = provenance.write_sbom(self.root / "out" / "sbom.json", sbom)
        self.assertEqual(provenance.read_sbom(path), sbom)
        self.assertEqual([item.name for item in path.parent.iterdir() if item.name.endswith(".tmp")], [])
        with self.assertRaises(provenance.ProvenanceError):
            provenance.write_sbom(self.root / "out" / "wrong.json", {"schema": "other"})

    def test_real_checkout_sbom_has_components_and_no_problems(self):
        sbom = provenance.build_sbom(REPO_ROOT)
        self.assertEqual(sbom["schema"], provenance.SBOM_SCHEMA)
        self.assertEqual(sbom["problems"], [])
        refs = {component["bomRef"] for component in sbom["components"]}
        self.assertIn("project:ProjectGypsy", refs)
        self.assertIn("project:LeftBehind", refs)
        self.assertIn("engine:godot:4.7.2", refs)
        self.assertGreaterEqual(sbom["counts"]["byType"].get("capability", 0), 50)
        self.assertGreaterEqual(sbom["counts"]["byType"].get("toolpack", 0), 6)
        self.assertGreater(sbom["counts"]["relationships"], 0)
        second = provenance.build_sbom(REPO_ROOT)
        self.assertEqual(sbom, second)


if __name__ == "__main__":
    unittest.main()
