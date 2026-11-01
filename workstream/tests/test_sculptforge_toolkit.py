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
PLUGIN = REGISTRY["sculptforge"].module


def _fake_cli(project: Path, bridge: Path) -> Path:
    script = project / "fake_sculptforge.py"
    script.write_text(
        "import json, os, pathlib, sys\n"
        "args = sys.argv[1:]\n"
        "if '--help' in args:\n"
        "    print('SculptForge fake 0.0.0')\n"
        "    sys.exit(0)\n"
        "sets = {}\n"
        "for index, value in enumerate(args):\n"
        "    if value == '--set':\n"
        "        name, _, payload = args[index + 1].partition('=')\n"
        "        sets[name] = payload\n"
        "script = args[args.index('-c') + 1]\n"
        "out = pathlib.Path(sets['OUT']) if 'OUT' in sets else pathlib.Path('unused')\n"
        "if 'export_lods' in script:\n"
        "    levels = int(sets['LEVELS'])\n"
        "    for level in range(levels + 1):\n"
        "        (out.parent / (out.stem + '_LOD' + str(level) + '.glb')).write_bytes(b'glTF')\n"
        "elif 'export_glb' in script or 'export_fbx' in script or 'export_usd' in script:\n"
        "    out.parent.mkdir(parents=True, exist_ok=True)\n"
        "    out.write_bytes(b'output')\n"
        "if 'blender_send' in script:\n"
        "    folder = pathlib.Path(os.environ['SCULPTFORGE_BLENDER_EXCHANGE']) / 'to_blender'\n"
        "    folder.mkdir(parents=True, exist_ok=True)\n"
        "    (folder / 'manifest.json').write_text(json.dumps({'schema': 'sculptforge-bridge', 'revision': 1}), encoding='utf-8')\n"
        "if 'blender_receive' in script:\n"
        "    out.parent.mkdir(parents=True, exist_ok=True)\n"
        "    out.write_bytes(b'received')\n",
        encoding="utf-8",
    )
    return script


class RegistryTests(unittest.TestCase):
    def test_registered_and_capability(self):
        self.assertIn("sculptforge", REGISTRY)
        info = REGISTRY["sculptforge"].info()
        self.assertEqual(info["id"], "sculptforge")
        self.assertEqual(info["capability"], "toolkit.sculptforge")
        self.assertEqual(toolkit.validate_plugin(PLUGIN), [])

    def test_describe_is_honest(self):
        data = PLUGIN.describe()
        self.assertEqual(data["status"], "partial")
        self.assertIn("not redistributed", data["license"])
        self.assertTrue(any("no GUI automation" in line for line in data["limits"]))


class FakeCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.bridge = self.root / "bridge"
        self.bridge.mkdir()
        self.input = self.root / "assets" / "hero.glb"
        self.input.parent.mkdir(parents=True)
        self.input.write_bytes(b"glTF")
        self.fake = _fake_cli(self.root, self.bridge)
        self.old_cli = os.environ.get("SCULPTFORGE_CLI")
        self.old_bridge = os.environ.get("SCULPTFORGE_BLENDER_EXCHANGE")
        os.environ["SCULPTFORGE_CLI"] = str(self.fake)
        os.environ["SCULPTFORGE_BLENDER_EXCHANGE"] = str(self.bridge)

    def tearDown(self):
        if self.old_cli is None:
            os.environ.pop("SCULPTFORGE_CLI", None)
        else:
            os.environ["SCULPTFORGE_CLI"] = self.old_cli
        if self.old_bridge is None:
            os.environ.pop("SCULPTFORGE_BLENDER_EXCHANGE", None)
        else:
            os.environ["SCULPTFORGE_BLENDER_EXCHANGE"] = self.old_bridge
        self.tmp.cleanup()

    def test_probe(self):
        data = PLUGIN.probe()
        self.assertTrue(data["installed"])
        self.assertTrue(data["helpOk"])
        self.assertEqual(data["exchange"], str(self.bridge))

    def test_lods_and_convert(self):
        result = PLUGIN.lods(self.root, "assets/hero.glb", "artifacts/hero.glb", levels=2, ratio=0.5)
        self.assertTrue(result["passed"], result)
        self.assertEqual(len(result["artifacts"]), 3)
        self.assertTrue((self.root / "artifacts" / "hero_LOD0.glb").is_file())
        converted = PLUGIN.convert(self.root, "assets/hero.glb", "artifacts/hero.glb", format="glb")
        self.assertTrue(converted["passed"], converted)

    def test_existing_output_requires_force(self):
        (self.root / "artifacts").mkdir()
        (self.root / "artifacts" / "hero_LOD0.glb").write_bytes(b"x")
        with self.assertRaises(PLUGIN.SculptForgeError):
            PLUGIN.lods(self.root, "assets/hero.glb", "artifacts/hero.glb", levels=1)
        self.assertTrue(PLUGIN.lods(self.root, "assets/hero.glb", "artifacts/hero.glb", levels=1, force=True)["passed"])

    def test_path_traversal_is_rejected(self):
        with self.assertRaises(PLUGIN.SculptForgeError):
            PLUGIN.lods(self.root, "../outside.glb", "artifacts/hero.glb")
        with self.assertRaises(PLUGIN.SculptForgeError):
            PLUGIN.lods(self.root, "assets/hero.glb", "../outside.glb")
        with self.assertRaises(PLUGIN.SculptForgeError):
            PLUGIN.lods(self.root, "assets/hero.glb", "artifacts/hero.glb;rm -rf /")

    def test_bridge_send_and_receive(self):
        sent = PLUGIN.bridge_send(self.root, "assets/hero.glb")
        self.assertTrue(sent["passed"], sent)
        self.assertTrue(sent["manifestChanged"])
        received = PLUGIN.bridge_receive(self.root, "artifacts/received.glb")
        self.assertTrue(received["passed"], received)


@unittest.skipUnless(PLUGIN._cli_path().is_file(), "SculptForge CLI is not installed")
class LiveProbeTests(unittest.TestCase):
    def test_live_probe_reports_install_and_bridge(self):
        data = PLUGIN.probe()
        self.assertTrue(data["installed"])
        self.assertTrue(data["helpOk"])
        self.assertIsNotNone(data["version"])


if __name__ == "__main__":
    unittest.main()
