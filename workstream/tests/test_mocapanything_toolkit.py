from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

WORKSTREAM = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKSTREAM))

import toolkit  # noqa: E402

REGISTRY = toolkit.discover()
PLUGIN = REGISTRY["mocapanything"].module


def _fake_python(home: Path) -> Path:
    script = home / "fake_python.py"
    script.write_text(
        "import json, pathlib, sys\n"
        "if '-c' in sys.argv:\n"
        "    print(json.dumps({'version': '3.10.0', 'torch': '2.9.0', 'cuda': False, 'device': None}))\n"
        "    sys.exit(0)\n"
        "if 'inference/video2pose2rot.py' in sys.argv:\n"
        "    out = pathlib.Path('demo_outputs/result.bvh')\n"
        "    out.parent.mkdir(parents=True, exist_ok=True)\n"
        "    out.write_text('HIERARCHY\\nROOT Hips\\n{\\nJOINT Spine\\n{\\n}\\n}\\nMOTION\\nFrames: 3\\nFrame Time: 0.033333\\n0 0 0\\n1 2 3\\n4 5 6\\n', encoding='utf-8')\n"
        "    print('fake inference ok')\n"
        "    sys.exit(0)\n"
        "print('fake python')",
        encoding="utf-8",
    )
    return script


def _bvh(path: Path) -> None:
    path.write_text("HIERARCHY\nROOT Hips\n{\nJOINT Spine\n{\n}\n}\nMOTION\nFrames: 3\nFrame Time: 0.033333\n0 0 0\n1 2 3\n4 5 6\n", encoding="utf-8")


class RegistryTests(unittest.TestCase):
    def test_registered(self):
        self.assertIn("mocapanything", REGISTRY)
        info = REGISTRY["mocapanything"].info()
        self.assertEqual(info["id"], "mocapanything")
        self.assertEqual(info["capability"], "toolkit.mocapanything")
        self.assertEqual(toolkit.validate_plugin(PLUGIN), [])

    def test_describe(self):
        data = PLUGIN.describe()
        self.assertEqual(data["status"], "experimental")
        self.assertTrue(any("not an inference pass" in line for line in data["limits"]))


class EnvTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        (self.home / "checkpoints").mkdir()
        (self.home / "checkpoints" / "video2pos2rot_epoch60.pt").write_bytes(b"weights")
        (self.home / "demo" / "configs").mkdir(parents=True)
        (self.home / "demo" / "configs" / "demo.yaml").write_text("runtime:\n  device: cpu\n", encoding="utf-8")
        (self.home / "demo" / "data").mkdir()
        self.python = _fake_python(self.home)
        self.old_home = os.environ.get("MOCAPANYTHING_HOME")
        self.old_python = os.environ.get("MOCAPANYTHING_PYTHON")
        os.environ["MOCAPANYTHING_HOME"] = str(self.home)
        os.environ["MOCAPANYTHING_PYTHON"] = str(self.python)

    def tearDown(self):
        for key, old in (("MOCAPANYTHING_HOME", self.old_home), ("MOCAPANYTHING_PYTHON", self.old_python)):
            if old is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old
        self.tmp.cleanup()

    def test_status_is_ready_without_claiming_inference(self):
        result = PLUGIN.probe()
        self.assertTrue(result["ready"])
        self.assertTrue(result["inferenceVerified"])
        self.assertEqual(result["evidence"]["result"], "pass")
        self.assertEqual(result["pythonInfo"]["torch"], "2.9.0")

    def test_infer_and_expected_artifact(self):
        result = PLUGIN.infer("demo/configs/demo.yaml", expect="demo_outputs/result.bvh")
        self.assertTrue(result["passed"], result)
        self.assertEqual(len(result["artifacts"]), 1)
        self.assertTrue((self.home / "demo_outputs" / "result.bvh").is_file())

    def test_preexisting_expect_is_not_a_pass(self):
        expected = self.home / "demo_outputs" / "preexisting.bvh"
        expected.parent.mkdir(parents=True)
        _bvh(expected)
        result = PLUGIN.infer("demo/configs/demo.yaml", expect="demo_outputs/preexisting.bvh")
        self.assertFalse(result["passed"], result)
        self.assertFalse(result["artifacts"])
        self.assertTrue(any("not produced" in error for error in result["errors"]))

    def test_expect_traversal_is_rejected(self):
        with self.assertRaises(PLUGIN.MocapAnythingError):
            PLUGIN.infer("demo/configs/demo.yaml", expect="../outside.bvh")

    def test_config_traversal_is_rejected(self):
        with self.assertRaises(PLUGIN.MocapAnythingError):
            PLUGIN.infer("../outside.yaml")
        with self.assertRaises(PLUGIN.MocapAnythingError):
            PLUGIN.infer("demo/configs/demo.yaml; echo hi")

    def test_bvh_validation(self):
        path = self.home / "demo_outputs" / "sample.bvh"
        path.parent.mkdir(parents=True)
        _bvh(path)
        result = PLUGIN.validate_bvh(path)
        self.assertTrue(result["passed"])
        self.assertEqual(result["joints"], 1)
        self.assertEqual(result["frames"], 3)

    def test_bad_bvh_fails(self):
        path = self.home / "bad.bvh"
        path.write_text("not a bvh", encoding="utf-8")
        result = PLUGIN.validate_bvh(path)
        self.assertFalse(result["passed"])


if __name__ == "__main__":
    unittest.main()
