from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HERO = REPO / "scripts" / "hero" / "validate_wayfarer.py"
GLB = REPO / "assets" / "hero" / "wayfarer.glb"


class HeroAssetTests(unittest.TestCase):
    def test_validator_passes_without_blender(self):
        if not HERO.exists() or not GLB.exists():
            self.skipTest("hero asset is not present in this checkout")
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "validation.json"
            proc = subprocess.run(
                [sys.executable, str(HERO), "--json", str(report)],
                cwd=REPO,
                capture_output=True,
                text=True,
                timeout=60,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr[-2000:])
            self.assertIn("HERO_VALIDATE_OK", proc.stdout)
            data = json.loads(report.read_text(encoding="utf-8"))
            self.assertTrue(data["passed"])
            self.assertGreaterEqual(len(data["checks"]), 50)
            self.assertEqual(data["facts"]["skinning"]["joints"], 23)
            self.assertEqual(len(data["facts"]["animations"]), 3)

    def test_godot_player_keeps_collision_and_uses_hero(self):
        if not GLB.exists():
            self.skipTest("hero asset is not present in this checkout")
        player = (REPO / "game" / "scenes" / "player.tscn").read_text(encoding="utf-8")
        self.assertIn("CapsuleShape3D", player)
        self.assertIn("wayfarer", player.lower())
        self.assertIn("[node name=\"Hero\"", player)
        main = (REPO / "game" / "scripts" / "main.gd").read_text(encoding="utf-8")
        self.assertIn("GYPSY_DEMO_OK", main)


if __name__ == "__main__":
    unittest.main()
