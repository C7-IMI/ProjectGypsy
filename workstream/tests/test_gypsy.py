from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

WORKSTREAM = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKSTREAM))

import gypsy  # noqa: E402


class CapabilityTests(unittest.TestCase):
    def test_capabilities_load_and_validate(self):
        capabilities = gypsy.load_capabilities()
        self.assertGreaterEqual(len(capabilities), 10)
        self.assertEqual(gypsy.validate_capabilities(capabilities), [])
        ids = [cap["id"] for cap in capabilities]
        self.assertEqual(len(ids), len(set(ids)))

    def test_engine_capabilities_reference_known_engines(self):
        for cap in gypsy.load_capabilities():
            if cap["layer"] == "engine":
                self.assertIn(cap["engine"], gypsy.ENGINE_NAMES)


class EngineTests(unittest.TestCase):
    def test_probe_finds_installed_engines(self):
        probe = gypsy.probe_engines()
        self.assertIn("godot", probe["engines"])
        self.assertTrue(probe["engines"]["godot"]["installed"])
        self.assertTrue(probe["engines"]["godot"]["usable"])
        self.assertEqual(probe["engines"]["godot"]["version"], "4.7.2")
        self.assertTrue(probe["engines"]["ue5"]["installed"])
        self.assertIsNotNone(probe["machine"]["ram_gb"])
        self.assertIn("C", probe["machine"]["disks"])

    def test_ue5_is_hardware_gated_on_this_machine(self):
        probe = gypsy.probe_engines()
        gate = probe["engines"]["ue5"]["gate"]
        self.assertFalse(gate["ok"])
        self.assertTrue(any("VRAM" in reason or "free space" in reason for reason in gate["reasons"]))

    def test_stale_registry_entries_are_reported(self):
        probe = gypsy.probe_engines()
        self.assertIsInstance(probe["staleRegistry"], list)

    def test_godot_headless_smoke(self):
        record = gypsy.detect_godot()
        if not record.get("usable"):
            self.skipTest("Godot not usable")
        evidence = gypsy.smoke_godot()
        self.assertTrue(evidence["passed"])
        self.assertIn("GYPSY_SMOKE_OK", evidence["stdout"] + evidence["stderr"])
        self.assertEqual(evidence["exit"], 0)


class ToolTests(unittest.TestCase):
    def test_tools_manifest(self):
        data = gypsy.load_tools()
        self.assertTrue(data["exists"], data["errors"])
        self.assertGreater(len(data["tools"]), 5)
        self.assertEqual(data["missing"], [])


class ProjectTests(unittest.TestCase):
    def test_init_show_and_overwrite_protection(self):
        version = gypsy.detect_godot()["version"]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "demo"
            result = gypsy.init_project(path, "godot", version, ["pc"])
            manifest_path = path / "project.gypsy.json"
            self.assertTrue(manifest_path.exists())
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["schema"], "gypsy.project/v1")
            self.assertEqual(manifest["engine"]["id"], "godot")
            self.assertEqual(manifest["targets"], ["pc"])
            shown = gypsy.show_project(path)
            self.assertEqual(shown["engine"]["version"], version)
            with self.assertRaises(gypsy.GypsyError):
                gypsy.init_project(path, "godot", version, ["pc"])
            gypsy.init_project(path, "godot", version, ["pc"], force=True)

    def test_unknown_engine_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(gypsy.GypsyError):
                gypsy.init_project(Path(tmp) / "demo", "cryengine", "1.0", ["pc"])

    def test_version_mismatch_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(gypsy.GypsyError):
                gypsy.init_project(Path(tmp) / "demo", "godot", "0.0.0", ["pc"])

    def test_unity_licence_gate(self):
        probe = gypsy.probe_engines()
        record = probe["engines"]["unity"]
        if not record.get("installed"):
            self.skipTest("Unity not installed")
        if (record.get("licence") or {}).get("proven"):
            self.skipTest("Unity licence is proven on this machine")
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(gypsy.GypsyError):
                gypsy.init_project(Path(tmp) / "demo", "unity", record.get("version"), ["pc"])

    def test_version_matching(self):
        self.assertTrue(gypsy.version_matches("4.7.2", "4.7.2"))
        self.assertTrue(gypsy.version_matches("5.8", "5.8.0"))
        self.assertFalse(gypsy.version_matches("4.6", "4.7.2"))


class CheckTests(unittest.TestCase):
    def test_check_all_passes(self):
        result = gypsy.check_all()
        self.assertTrue(result["passed"], result["errors"])
        self.assertGreater(result["capabilities"], 10)
