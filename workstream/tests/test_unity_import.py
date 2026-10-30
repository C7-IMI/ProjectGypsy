from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
EDITOR_SCRIPT = REPO / "unity" / "LeftBehind" / "Assets" / "Editor" / "HeroImportProof.cs"
WRAPPER = REPO / "scripts" / "unity_hero_import.ps1"
REPORT = REPO / "artifacts" / "unity-hero-import" / "hero-import-report.json"
EXPECTED_CAPE_BONES = ["cape_a", "cape_b", "cape_c"]
EXPECTED_CLIPS = ["idle", "run", "reach"]
EXPECTED_MATERIALS = ["Wayfarer_Cloth", "Wayfarer_Leather", "Wayfarer_Skin", "Wayfarer_Accent"]


class UnityHeroImportTests(unittest.TestCase):
    """Static contract for the Unity hero import proof, plus the real report when present.

    The live Unity batchmode run is opt-in (GYPSY_RUN_UNITY_IMPORT=1) because it needs the
    editor licence and takes tens of seconds; scripts/unity_hero_import.ps1 runs it explicitly.
    """

    def test_editor_script_exists_and_asserts_the_contract(self):
        self.assertTrue(EDITOR_SCRIPT.is_file(), str(EDITOR_SCRIPT))
        text = EDITOR_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("HeroImportProof", text)
        for token in ("cape_a", "cape_b", "cape_c", "Smile", "idle", "run", "reach",
                      "ExtractTextures", "globalScale", "EditorApplication.Exit",
                      "ModelImporterAnimationType.Generic", "importBlendShapes"):
            self.assertIn(token, text)

    def test_wrapper_invokes_batchmode_import(self):
        self.assertTrue(WRAPPER.is_file(), str(WRAPPER))
        text = WRAPPER.read_text(encoding="utf-8")
        for token in ("-batchmode", "-nographics", "-quit", "-executeMethod",
                      "HeroImportProof.Run", "-heroFbx", "-heroReport", "-logFile"):
            self.assertIn(token, text)

    def test_report_when_present_matches_expected_hero_contract(self):
        if not REPORT.is_file():
            self.skipTest("no Unity hero import report in this checkout; run scripts/unity_hero_import.ps1")
        text = REPORT.read_text(encoding="utf-8")
        self.assertNotIn("﻿", text)
        report = json.loads(text)
        self.assertEqual(report["schema"], "gypsy.unity.hero-import/v1")
        self.assertIn("unityVersion", report)
        self.assertTrue(report["passed"], json.dumps(report.get("errors"))[:2000])
        model = report["model"]
        self.assertEqual(model["boneCount"], 23)
        for bone in EXPECTED_CAPE_BONES:
            self.assertIn(bone, model["bones"])
        self.assertEqual(model["missingCapeBones"], [])
        self.assertTrue(any("Smile".lower() in shape.lower() for shape in model["blendShapes"]),
                        model["blendShapes"])
        clip_names = [clip["name"].lower() for clip in model["clips"]]
        for expected in EXPECTED_CLIPS:
            self.assertTrue(any(expected in name for name in clip_names), clip_names)
        material_names = [name.lower() for name in model["materials"]]
        for expected in EXPECTED_MATERIALS:
            self.assertTrue(any(expected.lower() in name for name in material_names), material_names)
        texture_names = [texture["name"].lower() for texture in model["textures"]]
        self.assertTrue(any("wayfarer_atlas" in name for name in texture_names), texture_names)
        self.assertTrue(any("wayfarer_normal" in name for name in texture_names), texture_names)
        self.assertGreaterEqual(model["triangleCount"], 500)
        self.assertGreaterEqual(model["heightMeters"], 1.7)
        self.assertLessEqual(model["heightMeters"], 2.1)
        self.assertLessEqual(abs(model["bounds"]["minY"]), 0.15)
        for check in report["checks"]:
            self.assertTrue(check["passed"], check)

    @unittest.skipUnless(os.environ.get("GYPSY_RUN_UNITY_IMPORT") == "1",
                         "set GYPSY_RUN_UNITY_IMPORT=1 to run the real Unity batchmode import")
    def test_live_unity_batchmode_import(self):
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-File", str(WRAPPER)],
            cwd=REPO,
            capture_output=True,
            text=True,
            timeout=900,
        )
        self.assertEqual(proc.returncode, 0,
                         "stdout:\n" + proc.stdout[-4000:] + "\nstderr:\n" + proc.stderr[-4000:])
        self.assertIn("UNITY_HERO_IMPORT_OK", proc.stdout)


if __name__ == "__main__":
    unittest.main()
