from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

WORKSTREAM = Path(__file__).resolve().parents[1]
REPO_ROOT = WORKSTREAM.parent
sys.path.insert(0, str(WORKSTREAM))

import assets  # noqa: E402


def write_file(root, relative, data):
    path = Path(root) / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, str):
        data = data.encode("utf-8")
    path.write_bytes(data)
    return path


def asset_key(root, relative):
    return str((Path(root) / relative).resolve()).replace("\\", "/")


def write_registry(root, payload, relative="registry/provenance.json"):
    path = Path(root) / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, str):
        path.write_text(payload, encoding="utf-8")
    else:
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def registry_document(entries, schema=assets.PROVENANCE_SCHEMA):
    return {"schema": schema, "assets": entries}


def run_cli(*args):
    return subprocess.run(
        [sys.executable, str(WORKSTREAM / "assets.py"), *args],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )


def without_generated(payload):
    copy = json.loads(json.dumps(payload))
    copy.pop("generated", None)
    return copy


class ScanTests(unittest.TestCase):
    def test_scan_reports_fields_media_kinds_and_sorted_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_file(tmp, "images/tex.png", b"png-bytes")
            write_file(tmp, "models/hero.glb", b"glb-bytes")
            write_file(tmp, "audio/loop.wav", b"wav-bytes")
            write_file(tmp, "docs/readme.md", b"# notes\n")
            write_file(tmp, "misc/blob.xyz", b"\x00\x01\x02")
            write_file(tmp, "misc/LICENSE", b"MIT")
            payload = assets.scan([tmp])
            self.assertEqual(payload["schema"], assets.SCHEMA)
            self.assertEqual(payload["count"], 6)
            self.assertEqual(assets.validate_payload(payload), [])
            paths = [entry["path"] for entry in payload["assets"]]
            self.assertEqual(paths, sorted(paths))
            by_name = {Path(entry["path"]).name: entry for entry in payload["assets"]}
            self.assertEqual(by_name["tex.png"]["media"], "image")
            self.assertEqual(by_name["hero.glb"]["media"], "model")
            self.assertEqual(by_name["loop.wav"]["media"], "audio")
            self.assertEqual(by_name["readme.md"]["media"], "text")
            self.assertEqual(by_name["blob.xyz"]["media"], "binary")
            self.assertEqual(by_name["LICENSE"]["media"], "binary")
            entry = by_name["tex.png"]
            self.assertEqual(entry["bytes"], len(b"png-bytes"))
            self.assertEqual(entry["sha256"], hashlib.sha256(b"png-bytes").hexdigest())
            self.assertEqual(entry["root"], assets._label(Path(tmp), REPO_ROOT))
            self.assertIsNone(entry["provenance"])
            datetime.fromisoformat(entry["modified"].replace("Z", "+00:00"))
            self.assertEqual(payload["roots"][0]["found"], True)
            self.assertEqual(payload["roots"][0]["assets"], 6)
            self.assertEqual(payload["totalBytes"], sum(entry["bytes"] for entry in payload["assets"]))
            self.assertEqual(payload["counts"]["image"], 1)
            self.assertEqual(payload["counts"]["model"], 1)

    def test_media_kind_table(self):
        self.assertEqual(assets.media_kind("a.PNG"), "image")
        self.assertEqual(assets.media_kind("a.glb"), "model")
        self.assertEqual(assets.media_kind("a.FBX"), "model")
        self.assertEqual(assets.media_kind("a.wav"), "audio")
        self.assertEqual(assets.media_kind("a.md"), "text")
        self.assertEqual(assets.media_kind("a.unknown"), "binary")
        self.assertEqual(assets.media_kind("no-extension"), "binary")

    def test_ignore_rules_skip_generated_import_and_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            for relative in (
                "Library/a.png",
                "obj/b.png",
                "Build/c.png",
                "import/d.png",
                "sub/Library/e.png",
                ".git/f.png",
                ".godot/g.png",
                "node_modules/h.png",
                "Temp/i.png",
            ):
                write_file(tmp, relative, b"ignored")
            for relative in (
                "a.png.meta",
                "b.glb.import",
                "c.uid",
                "d.tmp",
                "e.bak",
                "f.swp",
                "g.log",
                ".DS_Store",
                "Thumbs.db",
                "desktop.ini",
                ".hidden.png",
                "backup~",
            ):
                write_file(tmp, relative, b"ignored")
            write_file(tmp, "keep.png", b"keep")
            write_file(tmp, "sub/keep2.txt", b"keep2")
            payload = assets.scan([tmp])
            self.assertEqual(
                sorted(entry["path"] for entry in payload["assets"]),
                sorted([asset_key(tmp, "keep.png"), asset_key(tmp, "sub/keep2.txt")]),
            )
            self.assertEqual(payload["count"], 2)
            self.assertEqual(payload["roots"][0]["ignored"], 12)
            self.assertEqual(assets.validate_payload(payload), [])

    def test_registry_sidecar_file_is_not_listed_as_an_asset(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_file(tmp, "a.png", b"a")
            sidecar = write_registry(
                tmp,
                registry_document([{"path": asset_key(tmp, "a.png"), "license": "CC0-1.0"}]),
            )
            payload = assets.scan([tmp], sidecar)
            self.assertEqual(payload["count"], 1)
            self.assertEqual(payload["assets"][0]["path"], asset_key(tmp, "a.png"))
            self.assertEqual(payload["roots"][0]["ignored"], 1)
            self.assertEqual(payload["registry"]["loaded"], True)

    def test_duplicate_content_is_grouped_and_flagged(self):
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            write_file(first, "one.bin", b"same-bytes")
            write_file(second, "two.bin", b"same-bytes")
            write_file(first, "unique.bin", b"different-bytes")
            payload = assets.scan([first, second])
            digest = hashlib.sha256(b"same-bytes").hexdigest()
            self.assertEqual(payload["duplicates"], {digest: sorted([asset_key(first, "one.bin"), asset_key(second, "two.bin")])})
            by_path = {entry["path"]: entry for entry in payload["assets"]}
            self.assertTrue(by_path[asset_key(first, "one.bin")]["duplicate"])
            self.assertTrue(by_path[asset_key(second, "two.bin")]["duplicate"])
            self.assertFalse(by_path[asset_key(first, "unique.bin")]["duplicate"])
            self.assertEqual(assets.validate_payload(payload), [])

    def test_scan_is_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_file(tmp, "b.png", b"b")
            write_file(tmp, "a.txt", b"a")
            write_file(tmp, "sub/c.glb", b"c")
            first = assets.scan([tmp])
            second = assets.scan([tmp])
            self.assertEqual(without_generated(first), without_generated(second))
            self.assertEqual(json.loads(assets.to_json(first))["assets"], json.loads(assets.to_json(second))["assets"])

    def test_empty_missing_and_file_roots(self):
        with tempfile.TemporaryDirectory() as tmp:
            empty = Path(tmp) / "empty"
            empty.mkdir()
            payload = assets.scan([empty])
            self.assertEqual(payload["count"], 0)
            self.assertEqual(payload["roots"][0]["found"], True)
            self.assertEqual(assets.validate_payload(payload), [])

            missing = Path(tmp) / "missing"
            payload = assets.scan([missing])
            self.assertEqual(payload["count"], 0)
            self.assertEqual(payload["roots"][0]["found"], False)
            self.assertEqual(payload["errors"], [])
            self.assertIn("does not exist", " ".join(payload["warnings"]))

            a_file = Path(tmp) / "not-a-root.txt"
            a_file.write_text("x", encoding="utf-8")
            payload = assets.scan([a_file])
            self.assertEqual(payload["count"], 0)
            self.assertTrue(payload["errors"])
            self.assertIn("not a directory", " ".join(payload["errors"]))
            self.assertEqual(assets.validate_payload(payload), [])

    def test_duplicate_and_overlapping_roots_count_files_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_file(tmp, "a.png", b"a")
            write_file(tmp, "sub/b.png", b"b")
            payload = assets.scan([tmp, tmp])
            self.assertEqual(payload["count"], 2)
            self.assertIn("duplicate asset root", " ".join(payload["warnings"]))
            payload = assets.scan([tmp, Path(tmp) / "sub"])
            self.assertEqual(payload["count"], 2)
            self.assertIn("overlapping asset roots", " ".join(payload["warnings"]))
            self.assertEqual(assets.validate_payload(payload), [])

    def test_modified_time_is_utc_and_matches_the_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_file(tmp, "a.png", b"a")
            stamp = 1700000000
            os.utime(path, (stamp, stamp))
            payload = assets.scan([tmp])
            expected = (
                datetime.fromtimestamp(stamp, tz=timezone.utc)
                .isoformat(timespec="seconds")
                .replace("+00:00", "Z")
            )
            self.assertEqual(payload["assets"][0]["modified"], expected)

    def test_scan_payload_is_json_safe_and_validates(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_file(tmp, "a.png", b"a")
            payload = assets.scan([tmp])
            text = assets.to_json(payload)
            self.assertEqual(json.loads(text), payload)
            self.assertEqual(assets.validate_payload(payload), [])

    def test_validate_payload_rejects_broken_payloads(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_file(tmp, "a.png", b"a")
            write_file(tmp, "b.png", b"b")
            payload = assets.scan([tmp])
            broken = json.loads(json.dumps(payload))
            broken["schema"] = "something/else"
            broken["count"] = 99
            broken["assets"][0]["media"] = "video"
            broken["assets"][0]["sha256"] = "xyz"
            broken["assets"][0]["duplicate"] = "no"
            broken["counts"] = {"image": 0}
            errors = " ".join(assets.validate_payload(broken))
            for expected in ("schema", "count", "media", "sha256", "duplicate", "counts"):
                self.assertIn(expected, errors)
            self.assertEqual(assets.validate_payload("not a dict"), ["payload must be a JSON object"])

            ordered = json.loads(json.dumps(payload))
            ordered["assets"].reverse()
            self.assertIn("sorted by path", " ".join(assets.validate_payload(ordered)))

    def test_real_checkout_scan(self):
        payload = assets.scan()
        self.assertEqual(assets.validate_payload(payload), [])
        self.assertEqual(payload["errors"], [])
        self.assertGreater(payload["count"], 10)
        self.assertGreater(payload["totalBytes"], 0)
        for report in payload["roots"]:
            self.assertTrue(report["found"], report["path"])
        paths = {entry["path"]: entry for entry in payload["assets"]}
        self.assertIn("assets/hero/wayfarer.fbx", paths)
        self.assertEqual(paths["assets/hero/wayfarer.fbx"]["media"], "model")
        self.assertIn("assets/hero/textures/wayfarer_atlas.png", paths)
        self.assertEqual(paths["assets/hero/textures/wayfarer_atlas.png"]["media"], "image")
        self.assertIsInstance(payload["duplicates"], dict)


class RegistryTests(unittest.TestCase):
    def test_provenance_is_extracted_and_gaps_are_warnings(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_file(tmp, "a.png", b"a")
            write_file(tmp, "b.wav", b"b")
            write_file(tmp, "c.glb", b"c")
            sidecar = write_registry(
                tmp,
                registry_document(
                    [
                        {
                            "path": asset_key(tmp, "a.png"),
                            "license": "CC0-1.0",
                            "source": "generated in-repo",
                            "author": "Gypsy build",
                            "approved": True,
                        },
                        {"path": asset_key(tmp, "b.wav"), "source": "recorded but no license"},
                    ]
                ),
            )
            payload = assets.scan([tmp], sidecar)
            by_name = {Path(entry["path"]).name: entry for entry in payload["assets"]}
            self.assertEqual(by_name["a.png"]["provenance"]["license"], "CC0-1.0")
            self.assertEqual(by_name["a.png"]["provenance"]["approved"], True)
            self.assertEqual(by_name["b.wav"]["provenance"]["source"], "recorded but no license")
            self.assertIn("no license", " ".join(by_name["b.wav"]["warnings"]))
            self.assertEqual(by_name["c.glb"]["provenance"], None)
            self.assertIn("no provenance entry", " ".join(by_name["c.glb"]["warnings"]))
            self.assertEqual(payload["registry"]["loaded"], True)
            self.assertEqual(payload["registry"]["entries"], 2)
            self.assertEqual(
                payload["provenance"],
                {"withProvenance": 2, "missingProvenance": 1, "missingLicense": 1},
            )
            self.assertEqual(assets.validate_payload(payload), [])

    def test_missing_registry_is_a_warning_not_a_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_file(tmp, "a.png", b"a")
            sidecar = Path(tmp) / "registry" / "does-not-exist.json"
            payload = assets.scan([tmp], sidecar)
            self.assertEqual(payload["count"], 1)
            self.assertEqual(payload["registry"]["found"], False)
            self.assertEqual(payload["registry"]["loaded"], False)
            self.assertEqual(payload["provenance"]["withProvenance"], 0)
            self.assertEqual(payload["provenance"]["missingProvenance"], 1)
            self.assertIn("no provenance registry", " ".join(payload["warnings"]))
            self.assertEqual(payload["assets"][0]["warnings"], [])
            self.assertEqual(assets.validate_payload(payload), [])

    def test_malformed_and_wrong_schema_registries_are_warnings(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_file(tmp, "a.png", b"a")
            for text in (
                "{ broken json",
                "[]",
                json.dumps({"schema": "wrong/schema", "assets": []}),
                '{"schema": "gypsy.asset-provenance/v1", "assets": [], "x": NaN}',
            ):
                sidecar = write_registry(tmp, text)
                payload = assets.scan([tmp], sidecar)
                self.assertEqual(payload["count"], 1)
                self.assertEqual(payload["registry"]["loaded"], False)
                self.assertTrue(payload["registry"]["warnings"])
                self.assertEqual(payload["provenance"]["missingProvenance"], 1)
                self.assertEqual(assets.validate_payload(payload), [])

    def test_registry_entry_errors_are_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_file(tmp, "a.png", b"a")
            sidecar = write_registry(
                tmp,
                registry_document(
                    [
                        {"path": asset_key(tmp, "a.png")},
                        {"path": asset_key(tmp, "a.png")},
                        {"path": "assets/not-scanned.png"},
                        {"path": ""},
                        "not-an-object",
                    ]
                ),
            )
            payload = assets.scan([tmp], sidecar)
            self.assertEqual(payload["count"], 1)
            self.assertEqual(payload["registry"]["entries"], 2)
            joined = " ".join(payload["registry"]["warnings"])
            self.assertIn("repeats asset path", joined)
            self.assertIn("not an asset in the scanned roots", joined)
            self.assertIn("no non-empty path", joined)
            self.assertIn("must be an object", joined)
            self.assertIn("no license", " ".join(payload["assets"][0]["warnings"]))
            self.assertEqual(assets.validate_payload(payload), [])


class StateTests(unittest.TestCase):
    def test_state_round_trip_and_refusals(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_file(tmp, "a.png", b"a")
            payload = assets.scan([tmp])
            state = Path(tmp) / "state" / "assets.json"
            saved = assets.save_state(payload, state)
            self.assertEqual(saved, state)
            self.assertTrue(state.is_file())
            self.assertEqual(assets.load_state(state), payload)
            self.assertEqual(json.loads(state.read_text(encoding="utf-8")), payload)
            self.assertFalse(list(state.parent.glob("*.tmp")))
            with self.assertRaises(assets.AssetError):
                assets.load_state(Path(tmp) / "missing.json")
            corrupt = Path(tmp) / "corrupt.json"
            corrupt.write_text("{", encoding="utf-8")
            with self.assertRaises(assets.AssetError):
                assets.load_state(corrupt)
            wrong = Path(tmp) / "wrong.json"
            wrong.write_text(json.dumps({"schema": "wrong"}), encoding="utf-8")
            with self.assertRaises(assets.AssetError):
                assets.load_state(wrong)

    def test_default_state_lives_under_state_dir(self):
        self.assertEqual(assets.DEFAULT_STATE.name, "assets.json")
        self.assertEqual(assets.DEFAULT_STATE.parent.name, "state")


class CliTests(unittest.TestCase):
    def test_cli_json_summary_and_validate(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_file(tmp, "a.png", b"a")
            result = run_cli("--root", tmp, "--json")
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["schema"], assets.SCHEMA)
            self.assertEqual(payload["count"], 1)
            ok = run_cli("--root", tmp, "--validate")
            self.assertEqual(ok.returncode, 0, ok.stderr)

            human = run_cli("--root", tmp)
            self.assertEqual(human.returncode, 0, human.stderr)
            self.assertIn("asset registry:", human.stdout)
            self.assertIn("media:", human.stdout)
            self.assertIn("provenance:", human.stdout)

    def test_cli_file_root_fails_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            a_file = Path(tmp) / "file.txt"
            a_file.write_text("x", encoding="utf-8")
            result = run_cli("--root", str(a_file), "--validate", "--json")
            self.assertEqual(result.returncode, 1)
            self.assertIn("FAIL assets", result.stderr)
            json.loads(result.stdout)

            missing = run_cli("--root", str(Path(tmp) / "missing"), "--json")
            self.assertEqual(missing.returncode, 0, missing.stderr)
            self.assertIn("does not exist", " ".join(json.loads(missing.stdout)["warnings"]))

    def test_cli_state_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_file(tmp, "a.png", b"a")
            state = Path(tmp) / "state.json"
            saved = run_cli("--root", tmp, "--save-state", str(state), "--json")
            self.assertEqual(saved.returncode, 0, saved.stderr)
            self.assertTrue(state.is_file())
            loaded = run_cli("--state", str(state), "--json")
            self.assertEqual(loaded.returncode, 0, loaded.stderr)
            self.assertEqual(json.loads(loaded.stdout)["count"], 1)


class DocumentationTests(unittest.TestCase):
    def test_registry_readme_documents_the_sidecar(self):
        readme = Path(REPO_ROOT) / "assets" / "registry" / "README.md"
        self.assertTrue(readme.is_file())
        text = readme.read_text(encoding="utf-8").lower()
        self.assertIn("gypsy.asset-provenance/v1", text)
        self.assertIn("python workstream/assets.py", text)
        self.assertIn("warning", text)
        self.assertIn("read-only", text)


if __name__ == "__main__":
    unittest.main()
