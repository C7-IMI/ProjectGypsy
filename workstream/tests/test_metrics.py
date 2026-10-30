#!/usr/bin/env python3
"""Tests for the deterministic state-derived metrics layer (workstream/metrics.py).

Every fixture is written to a temporary state directory; no repository state, Godot, network
or clock is read. Generated state documents follow the real schemas used by the orchestrator,
the toolpack runner, the cache and the quality gate.
"""
from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

WORKSTREAM = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKSTREAM))

import metrics  # noqa: E402

ISO = "2026-10-30T10:00:00+00:00"


def slice_state(
    slice_id="hero",
    passed=True,
    duration=10.0,
    finished=ISO,
    run_id="run-1",
    started=None,
):
    return {
        "schema": metrics.SLICE_STATE_SCHEMA,
        "slice": slice_id,
        "runId": run_id,
        "passed": passed,
        "durationSeconds": duration,
        "startedAt": started or finished,
        "finishedAt": finished,
        "steps": [],
        "artifacts": [],
    }


def task_state(task="task-1", passed=True, duration=20.0, finished=ISO, started=None):
    return {
        "schema": metrics.TASK_STATE_SCHEMA,
        "task": task,
        "passed": passed,
        "durationSeconds": duration,
        "startedAt": started or finished,
        "finishedAt": finished,
    }


def action_state(
    toolpack="quality.visual",
    action="gate",
    passed=True,
    duration=1.0,
    finished=ISO,
    run_id="run-1",
    use_seconds=False,
):
    document = {
        "schema": metrics.TOOLPACK_STATE_SCHEMA,
        "scope": "action",
        "toolpack": toolpack,
        "action": action,
        "runId": run_id,
        "passed": passed,
        "startedAt": finished,
        "finishedAt": finished,
    }
    if use_seconds:
        document["seconds"] = duration
    else:
        document["durationSeconds"] = duration
    return document


def run_state(toolpack="quality.visual", passed=True, duration=5.0, finished=ISO, run_id="run-1"):
    return {
        "schema": metrics.TOOLPACK_STATE_SCHEMA,
        "scope": "toolpack",
        "toolpack": toolpack,
        "runId": run_id,
        "passed": passed,
        "durationSeconds": duration,
        "startedAt": finished,
        "finishedAt": finished,
    }


def cache_stats(**overrides):
    document = {
        "schema": metrics.CACHE_STATS_SCHEMA,
        "hits": 0,
        "misses": 0,
        "stores": 0,
        "restores": 0,
        "bytesStored": 0,
        "remoteHits": 0,
        "remoteStores": 0,
        "remoteErrors": 0,
        "lastUpdated": None,
    }
    document.update(overrides)
    return document


def quality_gate(passed=True, visual=True, performance=True, generated="2026-10-30T17:00:00+00:00"):
    return {
        "schema": metrics.QUALITY_SCHEMA,
        "generated": generated,
        "passed": passed,
        "visual": {"passed": visual, "changedRatio": 0.001},
        "performance": {
            "passed": performance,
            "metrics": {"medianSeconds": 2.6, "captureGpuMsPerFrame": 0.9},
        },
    }


class MetricsCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.state = self.root / "state"

    def write(self, relative, payload, encoding="utf-8"):
        path = self.state / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(payload, (dict, list)):
            path.write_text(json.dumps(payload), encoding=encoding)
        else:
            path.write_text(str(payload), encoding=encoding)
        return path

    def collect(self):
        return metrics.collect(self.state)


class SchemaTests(MetricsCase):
    def test_empty_state_has_zero_counts_and_nulls(self):
        result = self.collect()
        self.assertEqual(result["schema"], metrics.SCHEMA)
        self.assertEqual(result["stateDir"], self.state.as_posix())
        self.assertIsNone(result["asOf"])
        self.assertEqual(result["problems"], [])
        self.assertEqual(result["tasks"]["runs"], 0)
        self.assertEqual(result["tasks"]["passed"], 0)
        self.assertEqual(result["tasks"]["failed"], 0)
        self.assertIsNone(result["tasks"]["latest"])
        self.assertEqual(result["tasks"]["durations"]["count"], 0)
        self.assertIsNone(result["tasks"]["durations"]["medianSeconds"])
        self.assertEqual(result["slices"]["runs"], 0)
        self.assertEqual(result["slices"]["bySlice"], {})
        self.assertEqual(result["toolpacks"]["actions"]["runs"], 0)
        self.assertEqual(result["toolpacks"]["runs"]["runs"], 0)
        self.assertEqual(result["cache"]["counters"]["hits"], 0)
        self.assertEqual(result["cache"]["remote"], {"hits": 0, "stores": 0, "errors": 0})
        self.assertIsNone(result["cache"]["hitRate"])
        self.assertIsNone(result["cache"]["statsPath"])
        self.assertEqual(result["quality"], {"gates": 0, "passed": 0, "failed": 0, "latest": None})
        self.assertEqual(
            result["latest"],
            {"task": None, "slice": None, "toolpack": None, "quality": None, "cache": None},
        )
        json.dumps(result)

    def test_document_shape_is_stable_and_has_no_wall_clock(self):
        result = self.collect()
        self.assertEqual(
            set(result),
            {
                "schema",
                "stateDir",
                "asOf",
                "tasks",
                "slices",
                "toolpacks",
                "cache",
                "quality",
                "latest",
                "problems",
            },
        )
        self.assertNotIn("generated", result)
        self.assertNotIn("timestamp", result)
        self.assertEqual(
            set(result["toolpacks"]), {"actions", "runs"}
        )
        self.assertEqual(
            set(result["tasks"]),
            {"runs", "passed", "failed", "durations", "latest"},
        )

    def test_state_path_that_is_a_file_is_reported(self):
        path = self.root / "state.json"
        path.write_text("{}", encoding="utf-8")
        result = metrics.collect(path)
        self.assertEqual(result["tasks"]["runs"], 0)
        self.assertEqual(len(result["problems"]), 1)
        self.assertIn("not a directory", result["problems"][0]["error"])

    def test_output_is_deterministic_across_runs(self):
        self.write("slices/hero.json", slice_state())
        self.write("slices/quality.json", slice_state("quality", passed=False, duration=4.0))
        self.write("toolpacks/a.json", action_state())
        self.write("cache/stats.json", cache_stats(hits=2, misses=3))
        first = self.collect()
        second = self.collect()
        self.assertEqual(first, second)
        self.assertEqual(json.dumps(first), json.dumps(second))


class PercentileTests(unittest.TestCase):
    def test_nearest_rank_percentile(self):
        self.assertEqual(metrics.percentile([1, 2, 3, 4], 0.95), 4)
        self.assertEqual(metrics.percentile([1, 2, 3, 4], 0.5), 2)
        self.assertEqual(metrics.percentile([5], 1.0), 5)
        self.assertIsNone(metrics.percentile([], 0.5))

    def test_duration_stats(self):
        self.assertEqual(
            metrics.duration_stats([1, 2, 3, 4]),
            {
                "count": 4,
                "medianSeconds": 2.5,
                "p95Seconds": 4,
                "minSeconds": 1,
                "maxSeconds": 4,
            },
        )
        self.assertEqual(metrics.duration_stats([2])["medianSeconds"], 2)
        self.assertEqual(
            metrics.duration_stats([]),
            {
                "count": 0,
                "medianSeconds": None,
                "p95Seconds": None,
                "minSeconds": None,
                "maxSeconds": None,
            },
        )
        self.assertEqual(metrics.duration_stats(["x", None, True, -1, 2])["count"], 1)

    def test_percentile_rejects_bad_fractions(self):
        for fraction in (0, -0.1, 1.5, True, "0.5"):
            with self.assertRaises(ValueError):
                metrics.percentile([1, 2], fraction)


class AggregationTests(MetricsCase):
    def test_mixed_task_slice_and_toolpack_counts_and_durations(self):
        self.write("slices/hero.json", slice_state("hero", True, 10.0, "2026-10-30T10:00:00+00:00"))
        self.write("slices/quality.json", slice_state("quality", False, 20.0, "2026-10-30T11:00:00+00:00"))
        self.write("slices/visual.json", slice_state("visual", True, 30.0, "2026-10-30T12:00:00+00:00"))
        self.write("slices/task-a.json", task_state("task-a", True, 5.0, "2026-10-30T13:00:00+00:00"))
        self.write("slices/task-b.json", task_state("task-b", False, 15.0, "2026-10-30T14:00:00+00:00"))
        self.write("toolpacks/a.json", action_state("alpha", "gate", True, 1.0, "2026-10-30T09:00:00+00:00"))
        self.write("toolpacks/b.json", action_state("beta", "build", False, 2.0, "2026-10-30T09:30:00+00:00"))
        self.write("toolpacks/c.json", action_state("alpha", "check", True, 3.0, "2026-10-30T09:45:00+00:00"))
        self.write("toolpacks/r1.json", run_state("alpha", True, 100.0, "2026-10-30T15:00:00+00:00"))
        self.write("toolpacks/r2.json", run_state("beta", False, 200.0, "2026-10-30T16:00:00+00:00"))
        self.write("quality/gate.json", quality_gate(generated="2026-10-30T17:00:00+00:00"))

        result = self.collect()
        self.assertEqual((result["tasks"]["runs"], result["tasks"]["passed"], result["tasks"]["failed"]), (2, 1, 1))
        self.assertEqual(result["tasks"]["durations"]["medianSeconds"], 10.0)
        self.assertEqual(result["tasks"]["durations"]["p95Seconds"], 15.0)
        self.assertEqual(result["tasks"]["latest"]["task"], "task-b")
        self.assertEqual((result["slices"]["runs"], result["slices"]["passed"], result["slices"]["failed"]), (3, 2, 1))
        self.assertEqual(result["slices"]["durations"]["medianSeconds"], 20.0)
        self.assertEqual(result["slices"]["durations"]["p95Seconds"], 30.0)
        self.assertEqual(result["slices"]["latest"]["slice"], "visual")
        actions = result["toolpacks"]["actions"]
        self.assertEqual((actions["runs"], actions["passed"], actions["failed"]), (3, 2, 1))
        self.assertEqual(actions["durations"]["medianSeconds"], 2.0)
        self.assertEqual(actions["durations"]["p95Seconds"], 3.0)
        runs = result["toolpacks"]["runs"]
        self.assertEqual((runs["runs"], runs["passed"], runs["failed"]), (2, 1, 1))
        self.assertEqual(runs["latest"]["toolpack"], "beta")
        self.assertEqual(result["latest"]["task"], "2026-10-30T14:00:00+00:00")
        self.assertEqual(result["latest"]["slice"], "2026-10-30T12:00:00+00:00")
        self.assertEqual(result["latest"]["toolpack"], "2026-10-30T16:00:00+00:00")
        self.assertEqual(result["latest"]["quality"], "2026-10-30T17:00:00+00:00")
        self.assertEqual(result["asOf"], "2026-10-30T17:00:00+00:00")
        self.assertEqual(result["problems"], [])

    def test_latest_record_fields(self):
        self.write("slices/hero.json", slice_state("hero", False, 12.5, "2026-10-30T11:00:00+00:00", run_id="abc"))
        self.write("toolpacks/a.json", action_state("alpha", "gate", True, 1.5, "2026-10-30T12:00:00+00:00", run_id="def"))
        result = self.collect()
        latest = result["slices"]["latest"]
        self.assertEqual(latest["slice"], "hero")
        self.assertEqual(latest["runId"], "abc")
        self.assertFalse(latest["passed"])
        self.assertEqual(latest["at"], "2026-10-30T11:00:00+00:00")
        self.assertEqual(latest["durationSeconds"], 12.5)
        self.assertEqual(latest["path"], "slices/hero.json")
        action = result["toolpacks"]["actions"]["latest"]
        self.assertEqual(action["toolpack"], "alpha")
        self.assertEqual(action["action"], "gate")
        self.assertEqual(action["runId"], "def")

    def test_per_slice_breakdown(self):
        self.write("slices/hero-1.json", slice_state("hero", True, 2.0, "2026-10-30T10:00:00+00:00", "r1"))
        self.write("slices/hero-2.json", slice_state("hero", False, 4.0, "2026-10-30T11:00:00+00:00", "r2"))
        self.write("slices/quality.json", slice_state("quality", True, 10.0, "2026-10-30T12:00:00+00:00"))
        result = self.collect()
        self.assertEqual(list(result["slices"]["bySlice"]), ["hero", "quality"])
        hero = result["slices"]["bySlice"]["hero"]
        self.assertEqual((hero["runs"], hero["passed"], hero["failed"]), (2, 1, 1))
        self.assertEqual(hero["durations"]["medianSeconds"], 3.0)
        self.assertEqual(hero["durations"]["p95Seconds"], 4.0)
        self.assertEqual(hero["latest"]["runId"], "r2")
        quality = result["slices"]["bySlice"]["quality"]
        self.assertEqual((quality["runs"], quality["passed"], quality["failed"]), (1, 1, 0))

    def test_per_toolpack_breakdown_for_actions_and_runs(self):
        self.write("toolpacks/a1.json", action_state("alpha", "one", True, 1.0, "2026-10-30T10:00:00+00:00"))
        self.write("toolpacks/a2.json", action_state("alpha", "two", False, 3.0, "2026-10-30T11:00:00+00:00"))
        self.write("toolpacks/b1.json", action_state("beta", "one", True, 5.0, "2026-10-30T12:00:00+00:00"))
        self.write("toolpacks/ra.json", run_state("alpha", True, 10.0, "2026-10-30T13:00:00+00:00"))
        result = self.collect()
        by_toolpack = result["toolpacks"]["actions"]["byToolpack"]
        self.assertEqual(list(by_toolpack), ["alpha", "beta"])
        self.assertEqual(by_toolpack["alpha"]["runs"], 2)
        self.assertEqual(by_toolpack["alpha"]["failed"], 1)
        self.assertEqual(by_toolpack["alpha"]["durations"]["medianSeconds"], 2.0)
        self.assertEqual(by_toolpack["beta"]["runs"], 1)
        self.assertEqual(list(result["toolpacks"]["runs"]["byToolpack"]), ["alpha"])

    def test_timestamp_fallbacks_and_missing_timestamps(self):
        self.write(
            "slices/hero.json",
            slice_state("hero", True, 1.0, "not-a-date", started="2026-10-30T08:00:00+00:00"),
        )
        self.write(
            "slices/quality.json",
            {"schema": metrics.SLICE_STATE_SCHEMA, "slice": "quality", "passed": True, "durationSeconds": 2.0},
        )
        result = self.collect()
        self.assertEqual(result["slices"]["runs"], 2)
        self.assertEqual(result["slices"]["latest"]["slice"], "hero")
        self.assertEqual(result["slices"]["latest"]["at"], "2026-10-30T08:00:00+00:00")
        self.assertEqual(result["latest"]["slice"], "2026-10-30T08:00:00+00:00")


class CacheTests(MetricsCase):
    def test_cache_counters_remote_and_hit_rate(self):
        self.write(
            "cache/stats.json",
            cache_stats(
                hits=3,
                misses=5,
                stores=2,
                restores=1,
                bytesStored=99,
                remoteHits=4,
                remoteStores=2,
                remoteErrors=7,
                lastUpdated="2026-10-30T05:44:30-05:00",
            ),
        )
        (self.state / "cache" / "entries").mkdir(parents=True)
        (self.state / "cache" / "entries" / "a.json").write_text("{}", encoding="utf-8")
        (self.state / "cache" / "entries" / "b.json").write_text("{}", encoding="utf-8")
        (self.state / "cache" / "blobs").mkdir(parents=True)
        (self.state / "cache" / "blobs" / "aaa").write_bytes(b"x")
        (self.state / "cache" / "blobs" / "bbb").write_bytes(b"y")
        result = self.collect()
        cache = result["cache"]
        self.assertEqual(cache["statsPath"], "cache/stats.json")
        self.assertEqual(
            cache["counters"],
            {"hits": 3, "misses": 5, "stores": 2, "restores": 1, "bytesStored": 99},
        )
        self.assertEqual(cache["remote"], {"hits": 4, "stores": 2, "errors": 7})
        self.assertEqual(cache["hitRate"], 0.375)
        self.assertEqual(cache["entries"], 2)
        self.assertEqual(cache["blobs"], 2)
        self.assertEqual(cache["lastUpdated"], "2026-10-30T05:44:30-05:00")
        self.assertEqual(result["latest"]["cache"], "2026-10-30T05:44:30-05:00")

    def test_missing_cache_stats_is_zero_and_not_fake(self):
        result = self.collect()
        cache = result["cache"]
        self.assertIsNone(cache["statsPath"])
        self.assertEqual(cache["counters"], {key: 0 for key in metrics.CACHE_COUNTER_KEYS})
        self.assertIsNone(cache["hitRate"])
        self.assertIsNone(cache["lastUpdated"])
        self.assertEqual(result["problems"], [])

    def test_corrupt_cache_stats_is_reported(self):
        self.write("cache/stats.json", "{not json")
        result = self.collect()
        self.assertEqual(result["cache"]["counters"]["hits"], 0)
        self.assertEqual(len(result["problems"]), 1)
        self.assertEqual(result["problems"][0]["path"], "cache/stats.json")
        self.assertIn("invalid JSON", result["problems"][0]["error"])

    def test_wrong_cache_schema_and_bad_counter_are_reported(self):
        self.write("cache/stats.json", cache_stats(hits="many"))
        result = self.collect()
        self.assertEqual(result["cache"]["counters"]["hits"], 0)
        self.assertTrue(any("invalid counter hits" in item["error"] for item in result["problems"]))
        self.write(
            "cache/stats.json",
            {"schema": "other", "hits": 1, "misses": 0, "stores": 0},
        )
        result = self.collect()
        self.assertEqual(result["cache"]["counters"]["hits"], 0)
        self.assertTrue(any("unexpected schema" in item["error"] for item in result["problems"]))


class QualityTests(MetricsCase):
    def test_quality_gate_latest_and_counts(self):
        self.write("quality/gate.json", quality_gate())
        result = self.collect()
        quality = result["quality"]
        self.assertEqual(quality["gates"], 1)
        self.assertEqual(quality["passed"], 1)
        self.assertEqual(quality["failed"], 0)
        latest = quality["latest"]
        self.assertEqual(latest["path"], "quality/gate.json")
        self.assertEqual(latest["at"], "2026-10-30T17:00:00+00:00")
        self.assertTrue(latest["visualPassed"])
        self.assertTrue(latest["performancePassed"])
        self.assertEqual(latest["changedRatio"], 0.001)
        self.assertEqual(latest["medianSeconds"], 2.6)
        self.assertEqual(latest["captureGpuMsPerFrame"], 0.9)
        self.assertEqual(result["latest"]["quality"], "2026-10-30T17:00:00+00:00")
        self.assertEqual(result["asOf"], "2026-10-30T17:00:00+00:00")

    def test_failed_quality_gate_counts_as_failed(self):
        self.write("quality/gate.json", quality_gate(passed=False, visual=False))
        result = self.collect()
        self.assertEqual(result["quality"]["gates"], 1)
        self.assertEqual(result["quality"]["passed"], 0)
        self.assertEqual(result["quality"]["failed"], 1)
        self.assertFalse(result["quality"]["latest"]["visualPassed"])

    def test_missing_quality_gate_is_zero_and_corrupt_is_reported(self):
        self.assertEqual(self.collect()["quality"]["gates"], 0)
        self.write("quality/gate.json", "{not json")
        result = self.collect()
        self.assertEqual(result["quality"]["gates"], 0)
        self.assertTrue(
            any(item["path"] == "quality/gate.json" for item in result["problems"])
        )


class CorruptionTests(MetricsCase):
    def test_bad_files_are_reported_but_valid_state_is_still_counted(self):
        self.write("slices/hero.json", slice_state("hero"))
        self.write("slices/broken.json", "{not json")
        self.write("slices/alien.json", {"schema": "gypsy.alien/v1", "passed": True})
        self.write("slices/nopass.json", {"schema": metrics.SLICE_STATE_SCHEMA, "slice": "x"})
        result = self.collect()
        self.assertEqual(result["slices"]["runs"], 1)
        paths = [item["path"] for item in result["problems"]]
        self.assertIn("slices/broken.json", paths)
        self.assertIn("slices/alien.json", paths)
        self.assertIn("slices/nopass.json", paths)
        errors = " ".join(item["error"] for item in result["problems"])
        self.assertIn("invalid JSON", errors)
        self.assertIn("unexpected schema", errors)
        self.assertIn("missing boolean passed", errors)
        self.assertEqual(result["problems"], sorted(result["problems"], key=lambda item: (item["path"], item["error"])))

    def test_toolpack_unknown_scope_and_missing_ids_are_reported(self):
        self.write("toolpacks/ok.json", action_state("alpha", "gate", True, 1.0))
        self.write(
            "toolpacks/scope.json",
            {"schema": metrics.TOOLPACK_STATE_SCHEMA, "scope": "weird", "toolpack": "x", "passed": True},
        )
        self.write(
            "toolpacks/noid.json",
            {"schema": metrics.TOOLPACK_STATE_SCHEMA, "scope": "action", "action": "a", "passed": True},
        )
        result = self.collect()
        self.assertEqual(result["toolpacks"]["actions"]["runs"], 1)
        errors = " ".join(item["error"] for item in result["problems"])
        self.assertIn("unknown toolpack state scope", errors)
        self.assertIn("missing string toolpack", errors)

    def test_invalid_duration_is_reported_and_run_is_still_counted(self):
        document = slice_state("hero")
        document["durationSeconds"] = "fast"
        self.write("slices/hero.json", document)
        result = self.collect()
        self.assertEqual(result["slices"]["runs"], 1)
        self.assertEqual(result["slices"]["durations"]["count"], 0)
        self.assertTrue(
            any("invalid durationSeconds" in item["error"] for item in result["problems"])
        )

    def test_toolpack_seconds_fallback_is_used(self):
        self.write("toolpacks/a.json", action_state("alpha", "gate", True, 1.25, use_seconds=True))
        result = self.collect()
        self.assertEqual(result["toolpacks"]["actions"]["durations"]["medianSeconds"], 1.25)
        self.assertEqual(result["toolpacks"]["actions"]["latest"]["durationSeconds"], 1.25)


class CliTests(MetricsCase):
    def test_write_metrics_is_atomic_and_repeatable(self):
        self.write("slices/hero.json", slice_state())
        document = self.collect()
        path = self.root / "out" / "metrics.json"
        first = metrics.write_metrics(path, document)
        self.assertEqual(first, path)
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), document)
        self.assertEqual([item.name for item in path.parent.iterdir() if item.name.endswith(".tmp")], [])
        payload = path.read_bytes()
        metrics.write_metrics(path, document)
        self.assertEqual(path.read_bytes(), payload)

    def test_main_prints_json_and_writes_the_same_document(self):
        self.write("slices/hero.json", slice_state())
        out = self.root / "metrics.json"
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = metrics.main(["--state-dir", str(self.state), "--write", str(out)])
        self.assertEqual(code, 0)
        parsed = json.loads(stdout.getvalue())
        self.assertEqual(parsed["schema"], metrics.SCHEMA)
        self.assertEqual(json.loads(out.read_text(encoding="utf-8")), parsed)
        self.assertIn("metrics written:", stderr.getvalue())

    def test_main_missing_state_dir_is_empty_but_succeeds(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = metrics.main(["--state-dir", str(self.root / "absent")])
        self.assertEqual(code, 0)
        parsed = json.loads(stdout.getvalue())
        self.assertEqual(parsed["slices"]["runs"], 0)
        self.assertEqual(parsed["problems"], [])

    def test_main_write_failure_returns_one(self):
        blocker = self.root / "blocked"
        blocker.write_text("not a directory", encoding="utf-8")
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = metrics.main(
                ["--state-dir", str(self.state), "--write", str(blocker / "metrics.json")]
            )
        self.assertEqual(code, 1)
        self.assertIn("ERROR: could not write metrics", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
