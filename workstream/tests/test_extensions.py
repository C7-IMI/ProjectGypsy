#!/usr/bin/env python3
"""Tests for the isolated self-extension pipeline (workstream/extensions.py).

No test reaches the network or a core file. Every execution is the running Python
interpreter against a temporary extension directory. The real example extension is read
and executed because it is the committed reference; its run state lives under the ignored
extensions/.state/ directory.
"""
from __future__ import annotations

import contextlib
import copy
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

WORKSTREAM = Path(__file__).resolve().parents[1]
REPO_ROOT = WORKSTREAM.parent
EXTENSIONS_ROOT = REPO_ROOT / "extensions"
sys.path.insert(0, str(WORKSTREAM))

import extensions  # noqa: E402
import gypsy  # noqa: E402

RUN_SOURCE = """#!/usr/bin/env python3
import argparse
import os
import sys
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--action", required=True)
args = parser.parse_args()

if args.action == "hello":
    print("SAMPLE_OK")
    print("SAMPLE_CWD=" + os.getcwd())
    print("SAMPLE_ID=" + os.environ.get("GYPSY_EXTENSION_ID", ""))
    sys.exit(0)
if args.action == "fail":
    print("SAMPLE_FAIL", file=sys.stderr)
    sys.exit(3)
if args.action == "write":
    Path("dry-run-marker.txt").write_text("written", encoding="utf-8")
    print("SAMPLE_WRITE")
    sys.exit(0)
if args.action == "sleep":
    import time
    time.sleep(2)
    print("SAMPLE_SLEEP")
    sys.exit(0)
sys.exit(2)
"""


def base_capability(capability_id="extension.sample.one"):
    return {
        "schema": "gypsy.capability/v1",
        "id": capability_id,
        "layer": "extension",
        "kind": "test",
        "maturity": "experimental",
        "description": "test extension capability",
        "requires": ["python 3.14 standard library"],
        "inputs": [{"name": "action", "type": "string"}],
        "outputs": [{"name": "marker", "type": "text"}],
        "checks": ["hello passes", "fail is detected"],
        "provenance": {"record": ["extension", "treeSha256", "exit"]},
    }


def base_manifest(extension_id="sample.one"):
    return {
        "schema": "gypsy.extension/v1",
        "id": extension_id,
        "version": "1.0.0",
        "apiVersion": "1",
        "name": "Sample extension",
        "description": "A temporary test extension.",
        "license": "MIT",
        "author": "tests",
        "capability": "extension." + extension_id,
        "entrypoints": {
            "hello": {
                "description": "pass",
                "argv": ["python", "run.py", "--action", "hello"],
                "timeout": 10,
            },
            "fail": {
                "description": "fail on purpose",
                "argv": ["python", "run.py", "--action", "fail"],
                "timeout": 10,
            },
            "write": {
                "description": "write a marker if actually executed",
                "argv": ["python", "run.py", "--action", "write"],
                "timeout": 10,
            },
            "sleep": {
                "description": "sleep for the timeout test",
                "argv": ["python", "run.py", "--action", "sleep"],
                "timeout": 0.5,
            },
        },
        "tests": [
            {
                "id": "hello-passes",
                "action": "hello",
                "expectExit": 0,
                "stdoutContains": "SAMPLE_OK",
            },
            {
                "id": "fail-is-detected",
                "action": "fail",
                "expectExit": "nonzero",
                "stderrContains": "SAMPLE_FAIL",
            },
        ],
        "permissions": {"network": False, "reads": ["."], "writes": []},
    }


def run_cli(argv):
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = gypsy.main(argv)
    return code, stdout.getvalue(), stderr.getvalue()


class ExtensionTestCase(unittest.TestCase):
    def setUp(self):
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.root = Path(holder.name)

    def write_extension(
        self,
        extension_id="sample.one",
        *,
        root=None,
        manifest=None,
        capability=None,
        run_source=None,
        extra=None,
    ):
        root = Path(root) if root else self.root
        directory = root / extension_id
        directory.mkdir(parents=True, exist_ok=True)
        manifest = copy.deepcopy(manifest) if manifest is not None else base_manifest(extension_id)
        capability = (
            copy.deepcopy(capability)
            if capability is not None
            else base_capability(manifest.get("capability", "extension." + extension_id))
        )
        (directory / "extension.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n"
        )
        (directory / "capability.json").write_text(
            json.dumps(capability, indent=2) + "\n", encoding="utf-8", newline="\n"
        )
        (directory / "run.py").write_text(
            run_source if run_source is not None else RUN_SOURCE,
            encoding="utf-8",
            newline="\n",
        )
        for name, payload in (extra or {}).items():
            target = directory / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(payload, encoding="utf-8", newline="\n")
        return directory

    def register(self, extension_id="sample.one", *, root=None):
        return extensions.register(
            Path(root) if root else self.root, [extension_id], accept=True
        )


class RealExampleTests(unittest.TestCase):
    def test_example_validates(self):
        data = extensions.validate_extensions(EXTENSIONS_ROOT)
        self.assertTrue(data["passed"], data["errors"])
        self.assertEqual(data["checked"], 1)
        self.assertEqual(data["extensions"][0]["id"], "example.hello")

    def test_example_test_includes_negative_and_passes(self):
        data = extensions.test_extension(EXTENSIONS_ROOT, "example.hello")
        self.assertTrue(data["passed"], data["tests"])
        self.assertEqual(data["count"], 2)
        self.assertEqual(data["negativeTests"], 1)
        failing = [item for item in data["tests"] if item["id"] == "fail-is-detected"][0]
        self.assertEqual(failing["actualExit"], 3)
        self.assertTrue(failing["passed"])

    def test_example_lock_is_clean(self):
        lock = extensions.load_lock(EXTENSIONS_ROOT)
        entry = lock["extensions"]["example.hello"]
        self.assertTrue(entry["accepted"])
        self.assertTrue(entry["enabled"])
        extension = extensions.load_extension(EXTENSIONS_ROOT / "example.hello", root=EXTENSIONS_ROOT)
        self.assertEqual(entry["treeSha256"], extension.tree_sha256)
        status = extensions._status(extension, lock)
        self.assertEqual(status["state"], "registered")

    def test_example_list_and_show(self):
        data = extensions.list_extensions(EXTENSIONS_ROOT)
        row = [item for item in data["extensions"] if item["id"] == "example.hello"][0]
        self.assertEqual(row["status"], "registered")
        self.assertEqual(row["actions"], ["fail", "hello"])
        shown = extensions.show_extension(EXTENSIONS_ROOT, "example.hello")
        self.assertIn("hello", shown["manifest"]["entrypoints"])
        self.assertTrue(shown["files"])
        self.assertEqual(shown["errors"], [])

    def test_example_run_passes_and_fail_action_fails(self):
        passed = extensions.run_extension(EXTENSIONS_ROOT, "example.hello", "hello")
        self.assertTrue(passed["passed"], passed)
        self.assertIn("EXTENSION_HELLO_OK", passed["stdout"])
        failed = extensions.run_extension(EXTENSIONS_ROOT, "example.hello", "fail")
        self.assertFalse(failed["passed"])
        self.assertEqual(failed["exit"], 3)
        self.assertIn("EXTENSION_EXPECTED_FAILURE", failed["stderr"])

    def test_example_dry_run_executes_nothing(self):
        data = extensions.run_extension(EXTENSIONS_ROOT, "example.hello", "hello", dry_run=True)
        self.assertTrue(data["dryRun"])
        self.assertFalse(data["executed"])
        self.assertIsNone(data["passed"])
        self.assertNotIn("statePath", data)
        self.assertEqual(data["plan"]["cwd"], str((EXTENSIONS_ROOT / "example.hello").resolve()))


class SchemaTests(ExtensionTestCase):
    def test_valid_manifest_has_no_errors(self):
        directory = self.write_extension()
        self.assertEqual(
            extensions.validate_manifest(
                extensions.load_manifest(directory / "extension.json"), directory=directory
            ),
            [],
        )

    def test_wrong_schema_api_version_and_semver_are_rejected(self):
        mutate = [
            ("schema", "gypsy.extension/v2", "schema"),
            ("apiVersion", "2", "apiVersion"),
            ("version", "1.0", "version"),
            ("version", "one", "version"),
        ]
        for key, value, needle in mutate:
            manifest = base_manifest()
            manifest[key] = value
            directory = self.write_extension(manifest=manifest)
            errors = extensions.validate_manifest(manifest, directory=directory)
            self.assertTrue(any(needle in error for error in errors), (key, errors))
            with self.assertRaises(extensions.ExtensionError):
                extensions.load_extension(directory, root=self.root)

    def test_id_must_equal_directory_name(self):
        manifest = base_manifest("other.one")
        directory = self.write_extension("sample.one", manifest=manifest)
        errors = extensions.validate_manifest(manifest, directory=directory)
        self.assertTrue(any("directory name" in error for error in errors), errors)

    def test_unknown_top_level_key_is_rejected(self):
        manifest = base_manifest()
        manifest["command"] = "python run.py"
        directory = self.write_extension(manifest=manifest)
        errors = extensions.validate_manifest(manifest, directory=directory)
        self.assertTrue(any("unknown top-level key" in error for error in errors), errors)
        with self.assertRaises(extensions.ExtensionError) as raised:
            extensions.load_extension(directory, root=self.root)
        self.assertIn("unknown top-level key", str(raised.exception))

    def test_argv_must_be_an_explicit_list_not_a_shell_string(self):
        for argv, needle in (
            ("python run.py --action hello", "non-empty list"),
            ([], "non-empty list"),
            (["python", "run.py", 3], "must be a string"),
            (["python", "run.py", ""], "must not be empty"),
        ):
            manifest = base_manifest()
            manifest["entrypoints"]["hello"]["argv"] = argv
            directory = self.write_extension(manifest=manifest)
            errors = extensions.validate_manifest(manifest, directory=directory)
            self.assertTrue(any(needle in error for error in errors), (argv, errors))

    def test_shell_control_tokens_and_interpreters_are_rejected(self):
        for argv, needle in (
            (["python", "run.py", "--action", "hello;whoami"], "shell control"),
            (["python", "run.py", "--action", "hello && whoami"], "shell control"),
            (["bash", "run.sh"], "shell interpreter"),
            (["cmd.exe", "/c", "dir"], "shell interpreter"),
            (["python", "-c", "print(1)"], "interpreter options"),
            (["python", "../run.py"], "must not contain '..'"),
            (["python", "C:/Windows/system32/calc.exe"], "absolute path"),
        ):
            manifest = base_manifest()
            manifest["entrypoints"]["hello"]["argv"] = argv
            directory = self.write_extension(manifest=manifest)
            errors = extensions.validate_manifest(manifest, directory=directory)
            self.assertTrue(any(needle in error for error in errors), (argv, errors))

    def test_entrypoint_unknown_key_and_timeout_bounds(self):
        manifest = base_manifest()
        manifest["entrypoints"]["hello"]["shell"] = True
        directory = self.write_extension(manifest=manifest)
        errors = extensions.validate_manifest(manifest, directory=directory)
        self.assertTrue(any("unknown key" in error for error in errors), errors)
        for timeout in (0, -1, 301, "10", True):
            manifest = base_manifest()
            manifest["entrypoints"]["hello"]["timeout"] = timeout
            errors = extensions.validate_manifest(manifest, directory=directory)
            self.assertTrue(any("timeout" in error for error in errors), (timeout, errors))

    def test_tests_must_exist_and_include_a_negative_case(self):
        manifest = base_manifest()
        manifest["tests"] = []
        errors = extensions.validate_manifest(manifest, directory=self.write_extension(manifest=manifest))
        self.assertTrue(any("negative test" in error for error in errors), errors)
        manifest = base_manifest()
        manifest["tests"] = [test for test in manifest["tests"] if test["expectExit"] != "nonzero"]
        errors = extensions.validate_manifest(manifest, directory=self.write_extension(manifest=manifest))
        self.assertTrue(any("at least one negative" in error for error in errors), errors)

    def test_bad_test_expectations_actions_and_duplicates_are_rejected(self):
        cases = []
        manifest = base_manifest()
        manifest["tests"][0]["expectExit"] = "zero"
        cases.append((manifest, "expectExit"))
        manifest = base_manifest()
        manifest["tests"][0]["action"] = "missing"
        cases.append((manifest, "not a declared entrypoint"))
        manifest = base_manifest()
        manifest["tests"][1]["id"] = manifest["tests"][0]["id"]
        cases.append((manifest, "duplicate test id"))
        for manifest, needle in cases:
            errors = extensions.validate_manifest(manifest, directory=self.root)
            self.assertTrue(any(needle in error for error in errors), (needle, errors))

    def test_permissions_paths_stay_inside_extension(self):
        for key, value in (("writes", ["../outside"]), ("reads", ["C:/tmp"]), ("writes", ["/tmp"])):
            manifest = base_manifest()
            manifest["permissions"][key] = value
            directory = self.write_extension(manifest=manifest)
            errors = extensions.validate_manifest(manifest, directory=directory)
            self.assertTrue(errors, (key, value, errors))
        manifest = base_manifest()
        manifest["permissions"]["network"] = "yes"
        errors = extensions.validate_manifest(manifest, directory=self.write_extension(manifest=manifest))
        self.assertTrue(any("network" in error for error in errors), errors)

    def test_missing_capability_and_capability_mismatch(self):
        directory = self.write_extension()
        (directory / "capability.json").unlink()
        with self.assertRaises(extensions.ExtensionError) as raised:
            extensions.load_extension(directory, root=self.root)
        self.assertIn("capability.json is missing", str(raised.exception))

        capability = base_capability("extension.wrong")
        directory = self.write_extension(capability=capability)
        with self.assertRaises(extensions.ExtensionError) as raised:
            extensions.load_extension(directory, root=self.root)
        self.assertIn("must match manifest capability", str(raised.exception))

    def test_capability_layer_and_schema_are_checked(self):
        capability = base_capability()
        capability["layer"] = "workstream"
        errors = extensions.validate_capability(capability, expected_id="extension.sample.one")
        self.assertTrue(any("layer" in error for error in errors), errors)
        capability = base_capability()
        capability["schema"] = "gypsy.capability/v2"
        errors = extensions.validate_capability(capability, expected_id="extension.sample.one")
        self.assertTrue(any("schema" in error for error in errors), errors)
        capability = base_capability()
        del capability["provenance"]
        errors = extensions.validate_capability(capability, expected_id="extension.sample.one")
        self.assertTrue(any("provenance" in error for error in errors), errors)

    def test_symlink_is_rejected(self):
        directory = self.write_extension()
        outside = self.root / "outside.txt"
        outside.write_text("outside", encoding="utf-8")
        link = directory / "linked.txt"
        try:
            os.symlink(outside, link)
        except (OSError, NotImplementedError):
            self.skipTest("creating symlinks is not permitted on this machine")
        with self.assertRaises(extensions.ExtensionError) as raised:
            extensions.load_extension(directory, root=self.root)
        self.assertIn("symlink", str(raised.exception))


class ContainmentTests(ExtensionTestCase):
    def test_core_directories_are_rejected_as_extension_roots(self):
        for path in (REPO_ROOT, WORKSTREAM, REPO_ROOT / "docs", REPO_ROOT / "game"):
            with self.assertRaises(extensions.ExtensionError):
                extensions.ensure_root(path)
        with self.assertRaises(extensions.ExtensionError):
            extensions.ensure_root(EXTENSIONS_ROOT / "nested")

    def test_extension_cannot_live_in_workstream(self):
        with self.assertRaises(extensions.ExtensionError) as raised:
            extensions.load_extension(WORKSTREAM / "tests")
        self.assertIn("extensions/", str(raised.exception))

    def test_resolve_within_rejects_escapes(self):
        for value in ("../x", "C:/x", "/x", ".."):
            with self.assertRaises(extensions.ExtensionError):
                extensions.resolve_within(self.root, value)
        self.assertEqual(
            extensions.resolve_within(self.root, "inside/file.txt"),
            (self.root / "inside" / "file.txt").resolve(),
        )

    def test_remove_rejects_traversal_and_nested_ids(self):
        for value in ("../escape", "a/b", "C:/x"):
            with self.assertRaises(extensions.ExtensionError):
                extensions.remove(self.root, value)
        with self.assertRaises(extensions.ExtensionError):
            extensions.remove(self.root, "sample.one")

    def test_scan_tree_skips_state_and_cache_and_hashes_changes(self):
        directory = self.write_extension()
        (directory / ".state").mkdir()
        (directory / ".state" / "run.json").write_text("{}", encoding="utf-8")
        (directory / "__pycache__").mkdir()
        (directory / "__pycache__" / "run.pyc").write_bytes(b"cache")
        files, errors = extensions._scan_tree(directory)
        self.assertEqual(errors, [])
        paths = [entry["path"] for entry in files]
        self.assertNotIn(".state/run.json", paths)
        self.assertNotIn("__pycache__/run.pyc", paths)
        before = extensions.tree_hash(files)
        (directory / "run.py").write_text(RUN_SOURCE + "\n# changed\n", encoding="utf-8")
        files, errors = extensions._scan_tree(directory)
        self.assertEqual(errors, [])
        self.assertNotEqual(before, extensions.tree_hash(files))


class LifecycleTests(ExtensionTestCase):
    def test_register_requires_explicit_acceptance_and_writes_nothing(self):
        self.write_extension()
        with self.assertRaises(extensions.ExtensionError) as raised:
            extensions.register(self.root, ["sample.one"])
        self.assertIn("requires explicit review acceptance", str(raised.exception))
        self.assertFalse(extensions.lock_path(self.root).exists())

    def test_register_accept_writes_a_hashed_lock_entry(self):
        directory = self.write_extension()
        result = self.register()
        self.assertTrue(result["passed"])
        self.assertEqual(result["registered"], ["sample.one"])
        lock = extensions.load_lock(self.root)
        self.assertEqual(lock["schema"], extensions.LOCK_SCHEMA)
        entry = lock["extensions"]["sample.one"]
        self.assertTrue(entry["accepted"])
        self.assertTrue(entry["enabled"])
        self.assertEqual(entry["version"], "1.0.0")
        self.assertEqual(entry["capability"], "extension.sample.one")
        paths = [item["path"] for item in entry["files"]]
        self.assertIn("run.py", paths)
        self.assertIn("extension.json", paths)
        self.assertIn("capability.json", paths)
        self.assertEqual(entry["review"]["negativeTests"], 1)
        status = extensions._status(
            extensions.load_extension(directory, root=self.root), lock
        )
        self.assertEqual(status["state"], "registered")

    def test_register_accept_dry_run_writes_nothing(self):
        self.write_extension()
        result = extensions.register(self.root, ["sample.one"], accept=True, dry_run=True)
        self.assertTrue(result["dryRun"])
        self.assertFalse(extensions.lock_path(self.root).exists())

    def test_register_is_idempotent(self):
        self.write_extension()
        first = self.register()
        second = self.register()
        self.assertEqual(second["registered"], [])
        self.assertEqual(second["unchanged"], ["sample.one"])
        self.assertTrue(first["passed"] and second["passed"])

    def test_tamper_makes_stale_and_run_refuses_until_reload(self):
        directory = self.write_extension()
        self.register()
        (directory / "run.py").write_text(RUN_SOURCE + "\n# tampered\n", encoding="utf-8")
        rows = extensions.list_extensions(self.root)["extensions"]
        self.assertEqual(rows[0]["status"], "stale")
        with self.assertRaises(extensions.ExtensionError) as raised:
            extensions.run_extension(self.root, "sample.one", "hello")
        self.assertIn("stale", str(raised.exception))
        with self.assertRaises(extensions.ExtensionError):
            extensions.reload(self.root, ["sample.one"])
        result = extensions.reload(self.root, ["sample.one"], accept=True)
        self.assertEqual(result["registered"], ["sample.one"])
        self.assertTrue(extensions.run_extension(self.root, "sample.one", "hello")["passed"])

    def test_disable_blocks_run_and_register_reenables(self):
        self.write_extension()
        self.register()
        disabled = extensions.disable(self.root, "sample.one")
        self.assertTrue(disabled["changed"])
        self.assertEqual(
            extensions.list_extensions(self.root)["extensions"][0]["status"], "disabled"
        )
        with self.assertRaises(extensions.ExtensionError) as raised:
            extensions.run_extension(self.root, "sample.one", "hello")
        self.assertIn("disabled", str(raised.exception))
        self.register()
        self.assertTrue(extensions.run_extension(self.root, "sample.one", "hello")["passed"])

    def test_disable_dry_run_does_not_change_lock(self):
        self.write_extension()
        self.register()
        before = extensions.load_lock(self.root)["extensions"]["sample.one"]["enabled"]
        result = extensions.disable(self.root, "sample.one", dry_run=True)
        after = extensions.load_lock(self.root)["extensions"]["sample.one"]["enabled"]
        self.assertTrue(result["dryRun"])
        self.assertEqual(before, after)

    def test_remove_unregisters_without_deleting_then_deletes_on_request(self):
        directory = self.write_extension()
        self.register()
        result = extensions.remove(self.root, "sample.one")
        self.assertTrue(result["unregistered"])
        self.assertFalse(result["deletedDirectory"])
        self.assertTrue(directory.exists())
        self.assertNotIn("sample.one", extensions.load_lock(self.root)["extensions"])
        with self.assertRaises(extensions.ExtensionError) as raised:
            extensions.run_extension(self.root, "sample.one", "hello")
        self.assertIn("unregistered", str(raised.exception))
        result = extensions.remove(self.root, "sample.one", delete=True)
        self.assertTrue(result["deletedDirectory"])
        self.assertFalse(directory.exists())

    def test_remove_dry_run_does_not_delete(self):
        directory = self.write_extension()
        self.register()
        result = extensions.remove(self.root, "sample.one", delete=True, dry_run=True)
        self.assertTrue(result["dryRun"])
        self.assertTrue(directory.exists())
        self.assertIn("sample.one", extensions.load_lock(self.root)["extensions"])

    def test_orphan_lock_entry_is_reported_by_validate(self):
        directory = self.write_extension()
        self.register()
        shutil.rmtree(directory)
        data = extensions.validate_extensions(self.root)
        self.assertFalse(data["passed"])
        self.assertTrue(
            any("lockfile references missing extension" in error for error in data["errors"]),
            data["errors"],
        )

    def test_reload_requires_a_registered_extension(self):
        self.write_extension()
        with self.assertRaises(extensions.ExtensionError) as raised:
            extensions.reload(self.root, ["sample.one"], accept=True)
        self.assertIn("unregistered", str(raised.exception))

    def test_run_dry_run_is_allowed_before_registration(self):
        self.write_extension()
        data = extensions.run_extension(self.root, "sample.one", "hello", dry_run=True)
        self.assertEqual(data["status"]["state"], "unregistered")
        self.assertTrue(data["dryRun"])
        with self.assertRaises(extensions.ExtensionError):
            extensions.run_extension(self.root, "sample.one", "hello")

    def test_invalid_lockfile_is_rejected_and_reported(self):
        self.write_extension()
        (self.root / "gypsy.lock.json").write_text("{not json", encoding="utf-8")
        with self.assertRaises(extensions.ExtensionError) as raised:
            extensions.load_lock(self.root)
        self.assertIn("invalid lockfile JSON", str(raised.exception))
        data = extensions.validate_extensions(self.root)
        self.assertFalse(data["passed"])
        self.assertTrue(
            any("invalid lockfile" in error for error in data["errors"]), data["errors"]
        )

    def test_malformed_lock_entry_is_rejected(self):
        self.write_extension()
        lock = {
            "schema": extensions.LOCK_SCHEMA,
            "extensions": {"sample.one": "not-an-object"},
        }
        extensions.lock_path(self.root).write_text(
            json.dumps(lock) + "\n", encoding="utf-8", newline="\n"
        )
        with self.assertRaises(extensions.ExtensionError) as raised:
            extensions.load_lock(self.root)
        self.assertIn("lock entry", str(raised.exception))


class ExecutionTests(ExtensionTestCase):
    def test_run_uses_the_extension_directory_as_cwd_and_sets_env(self):
        directory = self.write_extension()
        self.register()
        data = extensions.run_extension(self.root, "sample.one", "hello")
        self.assertTrue(data["passed"], data)
        self.assertIn("SAMPLE_CWD=" + str(directory.resolve()), data["stdout"])
        self.assertIn("SAMPLE_ID=sample.one", data["stdout"])
        self.assertEqual(data["command"]["cwd"], str(directory.resolve()))
        self.assertFalse((directory / "__pycache__").exists())
        self.assertTrue(Path(data["statePath"]).is_file())

    def test_dry_run_executes_nothing(self):
        directory = self.write_extension()
        self.register()
        data = extensions.run_extension(self.root, "sample.one", "write", dry_run=True)
        self.assertTrue(data["dryRun"])
        self.assertFalse((directory / "dry-run-marker.txt").exists())
        self.assertFalse((self.root / ".state").exists())

    def test_timeout_is_enforced(self):
        manifest = base_manifest()
        manifest["entrypoints"]["sleep"]["timeout"] = 0.5
        self.write_extension(manifest=manifest)
        self.register()
        data = extensions.run_extension(self.root, "sample.one", "sleep")
        self.assertFalse(data["passed"])
        self.assertTrue(data["timedOut"])
        self.assertIsNone(data["exit"])
        self.assertIn("timeout", data["error"])

    def test_cli_timeout_can_shorten_but_not_extend(self):
        self.write_extension()
        self.register()
        shortened = extensions.run_extension(self.root, "sample.one", "hello", dry_run=True, timeout=0.25)
        self.assertEqual(shortened["plan"]["timeoutSeconds"], 0.25)
        extended = extensions.run_extension(self.root, "sample.one", "hello", dry_run=True, timeout=999)
        self.assertEqual(extended["plan"]["timeoutSeconds"], 10.0)
        for bad in (float("nan"), 0, -1):
            with self.assertRaises(extensions.ExtensionError):
                extensions.run_extension(
                    self.root, "sample.one", "hello", dry_run=True, timeout=bad
                )

    def test_negative_test_detects_an_unexpected_success(self):
        manifest = base_manifest()
        manifest["tests"].append(
            {"id": "wrong-expectation", "action": "fail", "expectExit": 0}
        )
        self.write_extension(manifest=manifest)
        data = extensions.test_extension(self.root, "sample.one")
        self.assertFalse(data["passed"])
        wrong = [item for item in data["tests"] if item["id"] == "wrong-expectation"][0]
        self.assertFalse(wrong["passed"])
        self.assertIn("expected exit 0, got 3", wrong["errors"][0])

    def test_declared_tests_pass_for_a_well_formed_extension(self):
        self.write_extension()
        data = extensions.test_extension(self.root, "sample.one")
        self.assertTrue(data["passed"], data)
        self.assertEqual(data["negativeTests"], 1)

    def test_execution_never_uses_a_shell(self):
        self.write_extension()
        self.register()
        completed = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="SAMPLE_OK\n", stderr=""
        )
        with mock.patch.object(extensions.subprocess, "run", return_value=completed) as patched:
            data = extensions.run_extension(self.root, "sample.one", "hello")
        self.assertTrue(data["passed"])
        args, kwargs = patched.call_args
        self.assertIsInstance(args[0], list)
        self.assertIs(kwargs["shell"], False)
        self.assertEqual(kwargs["cwd"], str((self.root / "sample.one").resolve()))
        self.assertIn("timeout", kwargs)

    def test_missing_action_is_a_named_error(self):
        self.write_extension()
        self.register()
        with self.assertRaises(extensions.ExtensionError) as raised:
            extensions.run_extension(self.root, "sample.one", "nope")
        self.assertIn("has no action", str(raised.exception))


class CliTests(ExtensionTestCase):
    def test_real_repository_list_validate_show_and_test(self):
        code, out, err = run_cli(["extension", "list", "--json"])
        self.assertEqual(code, 0, err)
        data = json.loads(out)
        self.assertIn("example.hello", [row["id"] for row in data["extensions"]])

        code, out, err = run_cli(["extension", "validate", "--json"])
        self.assertEqual(code, 0, out + err)
        self.assertTrue(json.loads(out)["passed"])

        code, out, err = run_cli(["extension", "show", "example.hello", "--json"])
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["id"], "example.hello")

        code, out, err = run_cli(["extension", "test", "example.hello", "--json"])
        self.assertEqual(code, 0, out + err)
        self.assertTrue(json.loads(out)["passed"])

    def test_cli_register_gate_and_lifecycle(self):
        directory = self.write_extension()

        code, out, err = run_cli(["extension", "validate", "--dir", str(self.root), "--json"])
        self.assertEqual(code, 0, out + err)
        self.assertTrue(json.loads(out)["passed"])

        code, out, err = run_cli(
            ["extension", "register", "sample.one", "--dir", str(self.root), "--json"]
        )
        self.assertEqual(code, 1)
        self.assertIn("requires explicit review acceptance", err)
        self.assertFalse(extensions.lock_path(self.root).exists())

        code, out, err = run_cli(
            ["extension", "register", "sample.one", "--accept", "--dir", str(self.root), "--json"]
        )
        self.assertEqual(code, 0, out + err)

        code, out, err = run_cli(
            ["extension", "run", "sample.one", "--action", "hello", "--dir", str(self.root), "--json"]
        )
        self.assertEqual(code, 0, out + err)
        self.assertTrue(json.loads(out)["passed"])

        code, out, err = run_cli(
            ["extension", "run", "sample.one", "--action", "fail", "--dir", str(self.root), "--json"]
        )
        self.assertEqual(code, 1)
        self.assertFalse(json.loads(out)["passed"])

        code, out, err = run_cli(
            ["extension", "disable", "sample.one", "--dir", str(self.root), "--json"]
        )
        self.assertEqual(code, 0, out + err)
        code, out, err = run_cli(
            ["extension", "run", "sample.one", "--action", "hello", "--dir", str(self.root)]
        )
        self.assertEqual(code, 1)
        self.assertIn("disabled", err)

        code, out, err = run_cli(
            ["extension", "reload", "sample.one", "--accept", "--dir", str(self.root), "--json"]
        )
        self.assertEqual(code, 0, out + err)
        code, out, err = run_cli(
            ["extension", "run", "sample.one", "--action", "hello", "--dir", str(self.root), "--json"]
        )
        self.assertEqual(code, 0, out + err)

        code, out, err = run_cli(
            ["extension", "remove", "sample.one", "--delete", "--dir", str(self.root), "--json"]
        )
        self.assertEqual(code, 0, out + err)
        self.assertFalse(directory.exists())

    def test_cli_validate_fails_for_an_invalid_extension(self):
        manifest = base_manifest()
        manifest["schema"] = "gypsy.extension/v2"
        self.write_extension(manifest=manifest)
        code, out, err = run_cli(["extension", "validate", "--dir", str(self.root)])
        self.assertEqual(code, 1, out + err)
        self.assertIn("FAIL sample.one", out)

    def test_cli_test_fails_when_the_negative_test_is_wrong(self):
        manifest = base_manifest()
        manifest["tests"].append(
            {"id": "wrong-expectation", "action": "fail", "expectExit": 0}
        )
        self.write_extension(manifest=manifest)
        code, out, err = run_cli(["extension", "test", "sample.one", "--dir", str(self.root)])
        self.assertEqual(code, 1, out + err)
        self.assertIn("FAIL", out)

    def test_cli_unknown_extension_ids_are_errors(self):
        commands = [
            ["extension", "show", "nope"],
            ["extension", "validate", "nope"],
            ["extension", "test", "nope"],
            ["extension", "run", "nope", "--action", "hello"],
            ["extension", "disable", "nope"],
            ["extension", "remove", "nope"],
        ]
        for argv in commands:
            code, out, err = run_cli(argv)
            self.assertEqual(code, 1, (argv, out, err))
            self.assertIn("ERROR", out + err, argv)

    def test_cli_register_refuses_invalid_extension_and_writes_no_lock(self):
        manifest = base_manifest()
        manifest["schema"] = "gypsy.extension/v2"
        self.write_extension(manifest=manifest)
        code, out, err = run_cli(
            ["extension", "register", "sample.one", "--accept", "--dir", str(self.root)]
        )
        self.assertEqual(code, 1, out + err)
        self.assertIn("cannot register invalid", err)
        self.assertFalse(extensions.lock_path(self.root).exists())

    def test_cli_run_dry_run_executes_nothing(self):
        directory = self.write_extension()
        self.register()
        code, out, err = run_cli(
            [
                "extension",
                "run",
                "sample.one",
                "--action",
                "write",
                "--dry-run",
                "--dir",
                str(self.root),
                "--json",
            ]
        )
        self.assertEqual(code, 0, out + err)
        data = json.loads(out)
        self.assertTrue(data["dryRun"])
        self.assertFalse(data["executed"])
        self.assertFalse((directory / "dry-run-marker.txt").exists())
        self.assertFalse((self.root / ".state").exists())


class CapabilityTests(unittest.TestCase):
    def test_pipeline_capability_manifest_is_valid(self):
        capabilities = gypsy.load_capabilities()
        ids = [capability.get("id") for capability in capabilities]
        self.assertIn("workstream.extension", ids)
        self.assertEqual(gypsy.validate_capabilities(capabilities), [])

    def test_example_capability_is_valid(self):
        capability = extensions.load_capability(EXTENSIONS_ROOT / "example.hello")
        self.assertEqual(
            extensions.validate_capability(
                capability, expected_id="extension.example.hello"
            ),
            [],
        )


if __name__ == "__main__":
    unittest.main()
