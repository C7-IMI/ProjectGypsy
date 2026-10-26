from __future__ import annotations

import sys
import unittest
from pathlib import Path

WORKSTREAM = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKSTREAM))

import game  # noqa: E402
import gypsy  # noqa: E402


class GameTests(unittest.TestCase):
    def test_game_demo_contract(self):
        if not (gypsy.REPO_ROOT / "game" / "project.godot").exists():
            self.skipTest("game/ is not present")
        evidence = game.demo()
        self.assertTrue(evidence["passed"])
        self.assertEqual(evidence["collected"], 3)
        self.assertEqual(evidence["exit"], 0)
        self.assertIn("GYPSY_DEMO_OK", evidence["marker"])
