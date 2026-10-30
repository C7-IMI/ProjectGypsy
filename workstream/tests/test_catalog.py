from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

WORKSTREAM = Path(__file__).resolve().parents[1]
REPO_ROOT = WORKSTREAM.parent
sys.path.insert(0, str(WORKSTREAM))

import catalog  # noqa: E402

TEMPLATES = REPO_ROOT / "templates"


def manifest(name="Demo", engine="godot", version="4.7.2", targets=("pc",), **overrides):
    data = {
        "schema": catalog.PROJECT_SCHEMA,
        "name": name,
        "engine": {
            "id": engine,
            "version": version,
            "adapter": "godot-4" if engine == "godot" else "unity-6",
        },
        "targets": list(targets),
        "paths": {"game": "game", "artifacts": "artifacts"},
        "created": "2026-10-30T00:00:00-05:00",
    }
    data.update(overrides)
    return data


def write_project(root, relative, payload):
    folder = Path(root) / relative
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / catalog.MANIFEST_NAME
    if isinstance(payload, str):
        path.write_text(payload, encoding="utf-8")
    else:
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def paths_of(payload):
    return [entry["path"] for entry in payload["projects"]]


def run_cli(*args):
    return subprocess.run(
        [sys.executable, str(WORKSTREAM / "catalog.py"), *args],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )


class DiscoveryTests(unittest.TestCase):
    def test_discovers_the_checkout_projects(self):
        payload = catalog.discover()
        self.assertEqual(payload["schema"], catalog.SCHEMA)
        self.assertEqual(payload["count"], len(payload["projects"]))
        found = {entry["path"]: entry for entry in payload["projects"]}
        self.assertIn("game", found)
        self.assertIn("unity/LeftBehind", found)
        self.assertEqual(found["game"]["engine"], "godot")
        self.assertEqual(found["unity/LeftBehind"]["engine"], "unity")
        for relative in ("game", "unity/LeftBehind"):
            entry = found[relative]
            self.assertEqual(entry["health"], "ok", entry["errors"])
            self.assertIsInstance(entry["targets"], list)
            self.assertTrue(entry["targets"])
            self.assertIsInstance(entry["path"], str)
        self.assertEqual(payload["duplicates"], {})
        self.assertEqual(catalog.validate_catalog(payload), [])

    def test_temp_root_is_sorted_and_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_project(tmp, "zeta", manifest(name="Zeta"))
            write_project(tmp, "alpha/nested", manifest(name="Nested"))
            payload = catalog.discover(tmp)
            self.assertEqual(paths_of(payload), ["alpha/nested", "zeta"])
            self.assertEqual(payload["count"], 2)
            self.assertEqual(payload["counts"], {"ok": 2, "warning": 0, "invalid": 0})
            for entry in payload["projects"]:
                for field in catalog.REQUIRED_ENTRY_FIELDS:
                    self.assertIn(field, entry)
                self.assertIsInstance(entry["engine"], str)
                self.assertIsInstance(entry["manifest"], str)
                self.assertEqual(entry["duplicate"], False)

    def test_scanned_payload_is_json_safe(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_project(tmp, "demo", manifest())
            payload = catalog.discover(tmp)
            text = catalog.to_json(payload)
            self.assertEqual(json.loads(text), payload)
            self.assertIsInstance(json.loads(text)["projects"][0]["path"], str)

    def test_root_can_be_one_project_directory(self):
        payload = catalog.discover(REPO_ROOT / "game")
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["projects"][0]["path"], ".")
        self.assertEqual(payload["projects"][0]["engine"], "godot")
        self.assertEqual(catalog.validate_catalog(payload), [])

    def test_prunes_generated_and_hidden_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            for relative in (
                ".git/ghost",
                "node_modules/pkg",
                "Library/cache",
                "artifacts/old",
                "build/export",
                "Temp/scratch",
            ):
                write_project(tmp, relative, manifest(name=relative))
            write_project(tmp, "real", manifest(name="Real"))
            payload = catalog.discover(tmp)
            self.assertEqual(paths_of(payload), ["real"])

    def test_missing_manifest_is_not_invented(self):
        with tempfile.TemporaryDirectory() as tmp:
            lookalike = Path(tmp) / "lookalike"
            lookalike.mkdir()
            (lookalike / "project.godot").write_text("config_version=5\n", encoding="utf-8")
            (lookalike / "project.gypsy.txt").write_text("{}", encoding="utf-8")
            payload = catalog.discover(tmp)
            self.assertEqual(payload["count"], 0)
            self.assertEqual(payload["projects"], [])
            with self.assertRaises(catalog.CatalogError):
                catalog.load_manifest(lookalike / catalog.MANIFEST_NAME)

    def test_malformed_manifests_are_reported_not_fatal(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_project(tmp, "broken", "{ this is not json")
            write_project(tmp, "empty", {})
            write_project(tmp, "good", manifest(name="Good"))
            payload = catalog.discover(tmp)
            self.assertEqual(payload["count"], 3)
            entries = {entry["path"]: entry for entry in payload["projects"]}
            self.assertEqual(entries["broken"]["health"], "invalid")
            self.assertIn("invalid JSON", " ".join(entries["broken"]["errors"]))
            self.assertEqual(entries["empty"]["health"], "invalid")
            self.assertIn("schema", " ".join(entries["empty"]["errors"]))
            self.assertEqual(entries["good"]["health"], "ok")
            self.assertEqual(catalog.validate_catalog(payload), [])

    def test_unknown_engine_is_invalid(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_project(tmp, "odd", manifest(name="Odd", engine="cryengine"))
            payload = catalog.discover(tmp)
            entry = payload["projects"][0]
            self.assertEqual(entry["health"], "invalid")
            self.assertIn("not a known engine", " ".join(entry["errors"]))

    def test_duplicate_names_are_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_project(tmp, "one", manifest(name="Demo"))
            write_project(tmp, "two", manifest(name="Demo"))
            write_project(tmp, "three", manifest(name="demo"))
            write_project(tmp, "four", manifest(name="Unique"))
            payload = catalog.discover(tmp)
            self.assertEqual(payload["duplicates"], {"Demo": ["one", "three", "two"]})
            entries = {entry["path"]: entry for entry in payload["projects"]}
            for relative in ("one", "two", "three"):
                self.assertTrue(entries[relative]["duplicate"])
                self.assertEqual(entries[relative]["health"], "warning")
                self.assertIn("duplicate project name", " ".join(entries[relative]["warnings"]))
            self.assertFalse(entries["four"]["duplicate"])
            self.assertEqual(entries["four"]["health"], "ok")
            self.assertEqual(catalog.validate_catalog(payload), [])

    def test_bad_root_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing"
            with self.assertRaises(catalog.CatalogError):
                catalog.discover(missing)
            a_file = Path(tmp) / "file.txt"
            a_file.write_text("x", encoding="utf-8")
            with self.assertRaises(catalog.CatalogError):
                catalog.discover(a_file)


class ManifestTests(unittest.TestCase):
    def test_checkout_manifests_validate(self):
        for relative in ("game/project.gypsy.json", "unity/LeftBehind/project.gypsy.json"):
            data = catalog.load_manifest(REPO_ROOT / relative)
            self.assertEqual(catalog.validate_manifest(data), [], relative)
            self.assertEqual(catalog.manifest_warnings(data), [], relative)

    def test_validate_manifest_reports_each_problem(self):
        broken = {
            "schema": "wrong",
            "name": "",
            "engine": {"id": "cryengine", "version": "", "adapter": ""},
            "targets": [],
            "paths": {"game": 1},
        }
        errors = " ".join(catalog.validate_manifest(broken))
        for expected in (
            "schema must be",
            "name must be",
            "engine.id",
            "engine.version",
            "engine.adapter",
            "targets must be",
            "paths.",
            "game",
        ):
            self.assertIn(expected, errors)
        self.assertEqual(catalog.validate_manifest("not a dict"), ["manifest must be a JSON object"])

    def test_manifest_warnings_report_optional_fields(self):
        data = manifest()
        data.pop("created")
        data["paths"] = {"game": "game"}
        warnings = " ".join(catalog.manifest_warnings(data))
        self.assertIn("created", warnings)
        self.assertIn("paths.artifacts", warnings)
        self.assertEqual(catalog.validate_manifest(data), [])

    def test_load_manifest_rejects_missing_invalid_and_non_object(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(catalog.CatalogError):
                catalog.load_manifest(Path(tmp) / "missing.json")
            invalid = Path(tmp) / "invalid.json"
            invalid.write_text("{", encoding="utf-8")
            with self.assertRaises(catalog.CatalogError):
                catalog.load_manifest(invalid)
            array = Path(tmp) / "array.json"
            array.write_text("[1, 2]", encoding="utf-8")
            with self.assertRaises(catalog.CatalogError):
                catalog.load_manifest(array)


class PayloadTests(unittest.TestCase):
    def test_validate_catalog_rejects_unsafe_payloads(self):
        self.assertNotEqual(catalog.validate_catalog({}), [])
        with tempfile.TemporaryDirectory() as tmp:
            write_project(tmp, "demo", manifest())
            payload = catalog.discover(tmp)
            self.assertEqual(catalog.validate_catalog(payload), [])
            broken = json.loads(json.dumps(payload))
            broken["projects"][0]["health"] = "excellent"
            broken["projects"][0]["path"] = 7
            broken["projects"][0]["duplicate"] = "no"
            broken["count"] = 99
            broken["counts"] = {"ok": 0, "warning": 0, "invalid": 0}
            errors = " ".join(catalog.validate_catalog(broken))
            self.assertIn("health", errors)
            self.assertIn("path", errors)
            self.assertIn("duplicate", errors)
            self.assertIn("count", errors)
            with self.assertRaises(catalog.CatalogError):
                catalog.to_json(broken)

    def test_health_problems_reports_invalid_and_duplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_project(tmp, "bad", "{")
            write_project(tmp, "a", manifest(name="Same"))
            write_project(tmp, "b", manifest(name="Same"))
            payload = catalog.discover(tmp)
            problems = " ".join(catalog.health_problems(payload))
            self.assertIn("invalid", problems)
            self.assertIn("duplicate project name", problems)
            clean = catalog.discover(str(REPO_ROOT / "game"))
            self.assertEqual(catalog.health_problems(clean), [])


class StateTests(unittest.TestCase):
    def test_state_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_project(tmp, "demo", manifest())
            payload = catalog.discover(tmp)
            state = Path(tmp) / "state" / "catalog.json"
            saved = catalog.save_state(payload, state)
            self.assertEqual(saved, state)
            self.assertTrue(state.is_file())
            loaded = catalog.load_state(state)
            self.assertEqual(loaded, payload)
            self.assertEqual(json.loads(state.read_text(encoding="utf-8")), payload)
            self.assertFalse(list(state.parent.glob("*.tmp")))

    def test_state_refuses_missing_corrupt_and_wrong_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(catalog.CatalogError):
                catalog.load_state(Path(tmp) / "missing.json")
            corrupt = Path(tmp) / "corrupt.json"
            corrupt.write_text("{", encoding="utf-8")
            with self.assertRaises(catalog.CatalogError):
                catalog.load_state(corrupt)
            wrong = Path(tmp) / "wrong.json"
            wrong.write_text(json.dumps({"schema": "something/else"}), encoding="utf-8")
            with self.assertRaises(catalog.CatalogError):
                catalog.load_state(wrong)

    def test_default_state_lives_under_state_dir(self):
        self.assertEqual(catalog.DEFAULT_STATE.name, "catalog.json")
        self.assertEqual(catalog.DEFAULT_STATE.parent.name, "state")


class CliTests(unittest.TestCase):
    def test_cli_json_and_validate(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_project(tmp, "good", manifest(name="Good"))
            result = run_cli("--root", tmp, "--json")
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["schema"], catalog.SCHEMA)
            self.assertEqual(payload["count"], 1)
            ok = run_cli("--root", tmp, "--validate")
            self.assertEqual(ok.returncode, 0, ok.stderr)

            write_project(tmp, "bad", "{")
            bad = run_cli("--root", tmp, "--validate", "--json")
            self.assertEqual(bad.returncode, 1)
            self.assertIn("FAIL catalog", bad.stderr)
            json.loads(bad.stdout)

    def test_cli_human_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_project(tmp, "demo", manifest(name="Demo"))
            result = run_cli("--root", tmp)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("project catalog:", result.stdout)
            self.assertIn("Demo", result.stdout)
            self.assertIn("demo", result.stdout)

    def test_cli_refuses_a_missing_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run_cli("--root", str(Path(tmp) / "missing"))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("catalog: FAIL", result.stderr)


class TemplateTests(unittest.TestCase):
    TEMPLATES = {"unity-project": "unity", "godot-project": "godot"}

    def test_templates_exist_with_instructions_and_agents_block(self):
        for folder, engine in self.TEMPLATES.items():
            base = TEMPLATES / folder
            self.assertTrue(base.is_dir(), folder)
            readme = (base / "README.md").read_text(encoding="utf-8")
            agents = (base / "AGENTS.gypsy.md").read_text(encoding="utf-8")
            template = json.loads((base / "project.gypsy.template.json").read_text(encoding="utf-8"))
            self.assertIn("project init", readme.lower())
            self.assertIn("recommended slices and toolpacks", readme.lower())
            self.assertIn("<GYPSY_HOME>", agents)
            self.assertIn(engine, agents.lower())
            self.assertEqual(template["schema"], catalog.PROJECT_SCHEMA)
            self.assertEqual(template["engine"]["id"], engine)
            self.assertEqual(catalog.validate_manifest(template), [])
            self.assertNotEqual(
                (base / "project.gypsy.template.json").name, catalog.MANIFEST_NAME
            )

    def test_templates_are_never_catalogued(self):
        self.assertEqual(catalog.discover(TEMPLATES)["count"], 0)
        checkout = catalog.discover()
        self.assertFalse([path for path in paths_of(checkout) if path.startswith("templates")])

    def test_templates_index_lists_both_golden_paths(self):
        index = (TEMPLATES / "README.md").read_text(encoding="utf-8")
        self.assertIn("unity-project", index)
        self.assertIn("godot-project", index)


if __name__ == "__main__":
    unittest.main()
