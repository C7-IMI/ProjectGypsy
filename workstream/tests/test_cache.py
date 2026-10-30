#!/usr/bin/env python3
"""Tests for the content-addressed action cache and bounded parallel scheduler (cache.py).

No network and no real tool: cache entries are seeded from temporary files, and the CLI
tests use sys.executable -c against temporary directories.
"""
from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

WORKSTREAM = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKSTREAM))

import cache  # noqa: E402
import gypsy  # noqa: E402


def write(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, bytes):
        path.write_bytes(payload)
    else:
        path.write_text(payload, encoding="utf-8")


def seed(project, state, *, input_text="v1", payload=b"artifact"):
    write(project / "src" / "in.txt", input_text)
    write(project / "out" / "a.bin", payload)
    config = cache.resolve_config(
        {"inputs": ["src/in.txt"], "artifacts": ["out/a.bin"]},
        project_root=project,
    )
    hashes = cache.input_hashes(project, config["inputs"])
    key, descriptor = cache.action_key(
        identity={"kind": "test"},
        argv=["demo"],
        cwd=str(project),
        inputs=hashes,
        artifacts=config["artifacts"],
        tool_versions={"demo": "1"},
    )
    cache_obj = cache.ActionCache(state)
    summary = cache_obj.store(
        key,
        descriptor=descriptor,
        project_root=project,
        artifacts=config["artifacts"],
        result={"exit": 0, "stdout": "seed"},
    )
    return cache_obj, key, summary


def run_cli(argv):
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = gypsy.main(argv)
    return code, stdout.getvalue(), stderr.getvalue()


class Case(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.project = self.root / "project"
        self.state = self.root / "state"
        self.project.mkdir(parents=True)


class ConfigTests(Case):
    def test_valid_config_and_resolution(self):
        value = {
            "inputs": ["src/in.txt"],
            "artifacts": ["out/a.bin"],
            "toolVersions": {"demo": "1.0"},
        }
        self.assertEqual(cache.validate_config(value), [])
        resolved = cache.resolve_config(value, project_root=self.project)
        self.assertTrue(resolved["enabled"])
        self.assertEqual(resolved["inputs"], ["src/in.txt"])
        self.assertEqual(resolved["artifacts"], ["out/a.bin"])
        self.assertEqual(resolved["toolVersions"], {"demo": "1.0"})

    def test_config_must_be_an_object(self):
        for value in (None, True, "cache", []):
            self.assertTrue(cache.validate_config(value))

    def test_unknown_key_and_enabled_type_are_rejected(self):
        errors = cache.validate_config({"inputs": [], "artifacts": [], "bogus": 1, "enabled": "yes"})
        self.assertTrue(any("unknown key" in error for error in errors), errors)
        self.assertTrue(any("enabled" in error for error in errors), errors)

    def test_inputs_and_artifacts_must_be_lists(self):
        errors = cache.validate_config({"inputs": "src/in.txt", "artifacts": "out/a.bin"})
        self.assertTrue(any("inputs" in error for error in errors), errors)
        self.assertTrue(any("artifacts" in error for error in errors), errors)

    def test_absolute_parent_glob_and_duplicate_paths_are_rejected(self):
        cases = [
            ({"inputs": [str(self.root / "x")], "artifacts": []}, "absolute"),
            ({"inputs": [], "artifacts": ["../escape.bin"]}, "escape"),
            ({"inputs": ["src/*.txt"], "artifacts": []}, "glob"),
            ({"inputs": [], "artifacts": ["out/*.bin"]}, "glob"),
            ({"inputs": ["src/in.txt", "src/in.txt"], "artifacts": []}, "repeats"),
        ]
        for value, needle in cases:
            errors = cache.validate_config(value)
            self.assertTrue(any(needle in error for error in errors), (value, errors))

    def test_tool_versions_are_checked(self):
        errors = cache.validate_config(
            {"inputs": [], "artifacts": [], "toolVersions": {"demo": ""}}
        )
        self.assertTrue(any("toolVersions" in error for error in errors), errors)
        errors = cache.validate_config(
            {"inputs": [], "artifacts": [], "toolVersions": ["demo"]}
        )
        self.assertTrue(any("toolVersions" in error for error in errors), errors)

    def test_resolve_config_raises_for_escaping_paths(self):
        with self.assertRaises(cache.CacheError):
            cache.resolve_config(
                {"inputs": ["../escape"], "artifacts": []}, project_root=self.project
            )


class KeyTests(Case):
    def _parts(self):
        write(self.project / "src" / "in.txt", "v1")
        config = cache.resolve_config(
            {"inputs": ["src/in.txt"], "artifacts": ["out/a.bin"]},
            project_root=self.project,
        )
        inputs = cache.input_hashes(self.project, config["inputs"])
        return inputs, config

    def test_same_descriptor_same_key(self):
        inputs, _ = self._parts()
        first = cache.action_key(
            identity={"a": 1}, argv=["x"], cwd=str(self.project), inputs=inputs,
            artifacts=["out/a.bin"], tool_versions={"t": "1"},
        )
        second = cache.action_key(
            identity={"a": 1}, argv=["x"], cwd=str(self.project), inputs=inputs,
            artifacts=["out/a.bin"], tool_versions={"t": "1"},
        )
        self.assertEqual(first[0], second[0])

    def test_changed_input_changes_key(self):
        inputs, _ = self._parts()
        first = cache.action_key(
            identity={"a": 1}, argv=["x"], cwd=str(self.project), inputs=inputs,
            artifacts=["out/a.bin"],
        )[0]
        write(self.project / "src" / "in.txt", "v2")
        changed = cache.input_hashes(self.project, ["src/in.txt"])
        second = cache.action_key(
            identity={"a": 1}, argv=["x"], cwd=str(self.project), inputs=changed,
            artifacts=["out/a.bin"],
        )[0]
        self.assertNotEqual(first, second)

    def test_argv_cwd_identity_tool_versions_and_artifacts_change_key(self):
        inputs, _ = self._parts()
        base = dict(
            identity={"a": 1}, argv=["x"], cwd=str(self.project), inputs=inputs,
            artifacts=["out/a.bin"], tool_versions={"t": "1"},
        )
        key = cache.action_key(**base)[0]
        variations = [
            dict(base, argv=["y"]),
            dict(base, identity={"a": 2}),
            dict(base, tool_versions={"t": "2"}),
            dict(base, artifacts=["out/b.bin"]),
            dict(base, cwd=str(self.project / "sub")),
        ]
        for variant in variations:
            self.assertNotEqual(key, cache.action_key(**variant)[0], variant)

    def test_descriptor_records_platform_and_schema(self):
        inputs, _ = self._parts()
        key, descriptor = cache.action_key(
            identity={"a": 1}, argv=["x"], cwd=str(self.project), inputs=inputs,
            artifacts=["out/a.bin"],
        )
        self.assertEqual(len(key), 64)
        self.assertEqual(descriptor["schema"], cache.KEY_SCHEMA)
        self.assertIn("system", descriptor["platform"])
        self.assertEqual(descriptor["artifacts"], ["out/a.bin"])

    def test_missing_input_is_recorded_safely(self):
        hashes = cache.input_hashes(self.project, ["src/missing.txt"])
        self.assertFalse(hashes["src/missing.txt"]["exists"])
        self.assertIsNone(hashes["src/missing.txt"]["sha256"])


class ActionCacheTests(Case):
    def test_disabled_cache_does_nothing(self):
        cache_obj = cache.ActionCache(self.state, enabled=False)
        self.assertIsNone(cache_obj.lookup("0" * 64))
        self.assertIsNone(
            cache_obj.store(
                "0" * 64, descriptor={}, project_root=self.project, artifacts=[]
            )
        )
        self.assertFalse(cache_obj.restore({"artifacts": []}, self.project)[0])
        self.assertEqual(cache_obj.counters()["stores"], 0)

    def test_store_lookup_restore_roundtrip(self):
        cache_obj, key, summary = seed(self.project, self.state)
        self.assertIsNotNone(summary)
        (self.project / "out" / "a.bin").unlink()
        entry = cache_obj.lookup(key)
        self.assertIsNotNone(entry)
        ok, restored, error = cache_obj.restore(entry, self.project)
        self.assertTrue(ok, error)
        self.assertEqual(restored, ["out/a.bin"])
        self.assertEqual((self.project / "out" / "a.bin").read_bytes(), b"artifact")
        counters = cache_obj.counters()
        self.assertEqual(counters["stores"], 1)
        self.assertEqual(counters["hits"], 1)
        self.assertEqual(counters["restores"], 1)
        self.assertEqual(cache_obj.stats()["entries"], 1)

    def test_changed_input_misses(self):
        cache_obj, key, _ = seed(self.project, self.state)
        write(self.project / "src" / "in.txt", "v2")
        changed = cache.input_hashes(self.project, ["src/in.txt"])
        new_key = cache.action_key(
            identity={"kind": "test"}, argv=["demo"], cwd=str(self.project),
            inputs=changed, artifacts=["out/a.bin"], tool_versions={"demo": "1"},
        )[0]
        self.assertNotEqual(key, new_key)
        self.assertIsNone(cache_obj.lookup(new_key))

    def test_corrupt_blob_is_a_miss(self):
        cache_obj, key, _ = seed(self.project, self.state)
        entry = cache_obj.lookup(key)
        digest = entry["artifacts"][0]["sha256"]
        (cache_obj.blobs_dir / digest).write_bytes(b"corrupt")
        self.assertIsNone(cache_obj.lookup(key))

    def test_incomplete_artifact_is_not_stored(self):
        cache_obj = cache.ActionCache(self.state)
        result = cache_obj.store(
            "0" * 64,
            descriptor={},
            project_root=self.project,
            artifacts=["out/missing.bin"],
        )
        self.assertIsNone(result)
        self.assertEqual(cache_obj.stats()["entries"], 0)

    def test_restore_rejects_an_escaping_entry_path(self):
        cache_obj, key, _ = seed(self.project, self.state)
        entry = cache_obj.lookup(key)
        blob = entry["artifacts"][0]
        (self.root / "escape.bin").unlink(missing_ok=True)
        forged = {
            "artifacts": [
                {"path": "../escape.bin", "sha256": blob["sha256"], "bytes": blob["bytes"]}
            ]
        }
        ok, restored, error = cache_obj.restore(forged, self.project)
        self.assertFalse(ok)
        self.assertTrue(error)
        self.assertFalse((self.root / "escape.bin").exists())

    def test_entries_and_clear(self):
        cache_obj, key, _ = seed(self.project, self.state)
        entries = cache_obj.entries()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["key"], key)
        cleared = cache_obj.clear()
        self.assertTrue(cleared["cleared"])
        self.assertEqual(cleared["entries"], 1)
        self.assertFalse(cache_obj.cache_dir.exists())
        self.assertEqual(cache_obj.counters()["stores"], 0)

    def test_unknown_key_counts_a_miss(self):
        cache_obj = cache.ActionCache(self.state)
        self.assertIsNone(cache_obj.lookup("f" * 64))
        self.assertEqual(cache_obj.counters()["misses"], 1)


class ParallelTests(unittest.TestCase):
    def test_worker_count_bounds(self):
        for bad in (0, -1, cache.MAX_WORKERS + 1, True, "2", None):
            with self.assertRaises(cache.CacheError):
                cache.worker_count(bad)
        self.assertEqual(cache.worker_count(1), 1)
        self.assertEqual(cache.worker_count(cache.MAX_WORKERS), cache.MAX_WORKERS)

    def test_sequential_order_and_cancellation(self):
        seen = []

        def worker(index, item):
            seen.append(item)
            return {"passed": item != 2}

        result = cache.run_parallel([1, 2, 3], worker, max_workers=1)
        self.assertEqual(seen, [1, 2])
        self.assertTrue(result["cancelled"])
        self.assertEqual(result["cancelledIndices"], [2])
        self.assertIsNone(result["results"][2])

    def test_bounded_worker_pool(self):
        lock = threading.Lock()
        active = 0
        peak = 0
        order = []

        def worker(index, item):
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
                order.append(item)
            time.sleep(0.05)
            with lock:
                active -= 1
            return {"passed": True, "item": item}

        result = cache.run_parallel(list(range(6)), worker, max_workers=2)
        self.assertLessEqual(peak, 2)
        self.assertEqual([item["item"] for item in result["results"]], list(range(6)))
        self.assertFalse(result["cancelled"])
        self.assertEqual(result["workers"], 2)

    def test_parallel_cancels_pending_after_failure(self):
        def worker(index, item):
            if item == 0:
                return {"passed": False}
            time.sleep(0.1)
            return {"passed": True}

        result = cache.run_parallel([0, 1, 2], worker, max_workers=2)
        self.assertTrue(result["cancelled"])
        self.assertFalse(result["results"][0]["passed"])
        self.assertIsNone(result["results"][2])
        self.assertIn(2, result["cancelledIndices"])

    def test_empty_items(self):
        result = cache.run_parallel([], lambda index, item: {"passed": True}, max_workers=2)
        self.assertEqual(result["results"], [])
        self.assertFalse(result["cancelled"])

    def test_parallel_preserves_order_with_variable_durations(self):
        durations = {0: 0.12, 1: 0.01, 2: 0.06}

        def worker(index, item):
            time.sleep(durations[item])
            return {"passed": True, "item": item}

        result = cache.run_parallel([0, 1, 2], worker, max_workers=3)
        self.assertEqual([item["item"] for item in result["results"]], [0, 1, 2])


class CliTests(Case):
    def test_cache_stats_list_and_clear(self):
        seed(self.project, self.state)
        code, out, err = run_cli(
            ["cache", "stats", "--state-dir", str(self.state), "--json"]
        )
        self.assertEqual(code, 0, out + err)
        stats = json.loads(out)
        self.assertEqual(stats["counters"]["stores"], 1)
        self.assertEqual(stats["entries"], 1)

        code, out, err = run_cli(
            ["cache", "list", "--state-dir", str(self.state), "--json"]
        )
        self.assertEqual(code, 0, out + err)
        self.assertEqual(len(json.loads(out)["entries"]), 1)

        code, out, err = run_cli(["cache", "clear", "--state-dir", str(self.state)])
        self.assertEqual(code, 1)
        self.assertIn("--yes", err)
        self.assertTrue((self.state / "cache").exists())

        code, out, err = run_cli(
            ["cache", "clear", "--state-dir", str(self.state), "--yes", "--json"]
        )
        self.assertEqual(code, 0, out + err)
        self.assertFalse((self.state / "cache").exists())

    def test_slices_cli_parallel_and_no_cache(self):
        manifests = self.root / "slices"
        marks = self.root / "marks"
        for slice_id in ("alpha", "beta"):
            code = (
                "from pathlib import Path\n"
                f"Path({str(marks / (slice_id + '.txt'))!r}).parent.mkdir(parents=True, exist_ok=True)\n"
                f"Path({str(marks / (slice_id + '.txt'))!r}).write_text('ran', encoding='utf-8')\n"
                "print('CLI_OK')\n"
            )
            manifest = {
                "schema": "gypsy.slice/v1",
                "id": slice_id,
                "project": ".",
                "artifacts": [],
                "steps": [
                    {
                        "id": "run",
                        "kind": "command",
                        "needs": [],
                        "required": True,
                        "timeout": 30,
                        "args": {"argv": [sys.executable, "-c", code], "cwd": "."},
                    }
                ],
            }
            write(manifests / (slice_id + ".json"), json.dumps(manifest, indent=2) + "\n")
        argv = [
            "slices", "run", "--all", "--dir", str(manifests),
            "--state-dir", str(self.state), "--parallel", "2", "--json",
        ]
        code, out, err = run_cli(argv)
        self.assertEqual(code, 0, out + err)
        data = json.loads(out)
        self.assertTrue(data["passed"], data)
        self.assertEqual(data["parallel"]["workers"], 2)
        self.assertEqual(data["sliceOrder"], ["alpha", "beta"])
        self.assertEqual([summary["status"] for summary in data["slices"]], ["passed", "passed"])
        code, out, err = run_cli(
            [
                "slices", "run", "--all", "--dir", str(manifests),
                "--state-dir", str(self.state), "--no-cache", "--json",
            ]
        )
        self.assertEqual(code, 0, out + err)
        self.assertFalse(json.loads(out)["cache"]["enabled"])

    def test_slices_cli_rejects_an_out_of_range_worker_count(self):
        manifests = self.root / "slices"
        for slice_id in ("one", "two"):
            write(
                manifests / (slice_id + ".json"),
                json.dumps(
                    {
                        "schema": "gypsy.slice/v1",
                        "id": slice_id,
                        "project": ".",
                        "artifacts": [],
                        "steps": [
                            {
                                "id": "run",
                                "kind": "command",
                                "needs": [],
                                "required": True,
                                "timeout": 5,
                                "args": {"argv": [sys.executable, "-c", "print(1)"]},
                            }
                        ],
                    }
                )
                + "\n",
            )
        code, out, err = run_cli(
            [
                "slices", "run", "--all", "--dir", str(manifests),
                "--state-dir", str(self.state), "--parallel", "9",
            ]
        )
        self.assertEqual(code, 1)
        self.assertIn("max_workers", err)

    def test_toolpacks_cli_parallel_and_no_cache(self):
        directory = self.root / "toolpacks"
        output = self.root / "tp"
        actions = []
        for action_id in ("a", "b"):
            code = (
                "from pathlib import Path\n"
                f"Path({str(output / (action_id + '.txt'))!r}).parent.mkdir(parents=True, exist_ok=True)\n"
                f"Path({str(output / (action_id + '.txt'))!r}).write_text('ran', encoding='utf-8')\n"
                "print('TP_OK')\n"
            )
            actions.append(
                {
                    "id": action_id,
                    "argv": [sys.executable, "-c", code],
                    "cwd": ".",
                    "timeout": 30,
                }
            )
        write(
            directory / "sample.json",
            json.dumps(
                {
                    "schema": "gypsy.toolpack/v1",
                    "id": "sample",
                    "name": "CLI sample",
                    "tools": ["python"],
                    "license": "MIT",
                    "actions": actions,
                }
            )
            + "\n",
        )
        code, out, err = run_cli(
            [
                "toolpacks", "run", "sample", "--dir", str(directory),
                "--state-dir", str(self.state), "--parallel", "2", "--json",
            ]
        )
        self.assertEqual(code, 0, out + err)
        data = json.loads(out)
        self.assertTrue(data["passed"], data)
        self.assertEqual(data["parallel"]["workers"], 2)
        self.assertEqual(data["actionOrder"], ["a", "b"])
        code, out, err = run_cli(
            [
                "toolpacks", "run", "sample", "--dir", str(directory),
                "--state-dir", str(self.state), "--no-cache", "--json",
            ]
        )
        self.assertEqual(code, 0, out + err)
        self.assertFalse(json.loads(out)["cache"]["enabled"])

    def test_toolpacks_cli_rejects_an_out_of_range_worker_count(self):
        directory = self.root / "toolpacks"
        write(
            directory / "sample.json",
            json.dumps(
                {
                    "schema": "gypsy.toolpack/v1",
                    "id": "sample",
                    "name": "CLI sample",
                    "tools": ["python"],
                    "license": "MIT",
                    "actions": [
                        {
                            "id": "run",
                            "argv": [sys.executable, "-c", "print(1)"],
                            "cwd": ".",
                            "timeout": 5,
                        }
                    ],
                }
            )
            + "\n",
        )
        code, out, err = run_cli(
            [
                "toolpacks", "run", "sample", "--dir", str(directory),
                "--state-dir", str(self.state), "--parallel", "0",
            ]
        )
        self.assertEqual(code, 1)
        self.assertIn("max_workers", err)


if __name__ == "__main__":
    unittest.main()
