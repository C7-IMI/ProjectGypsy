#!/usr/bin/env python3
"""Tests for the Phase-5 live-iteration watcher (workstream/live.py).

Everything runs against temporary files with an injected fake clock/sleep and a fake runner.
No Godot, no network, no shell, no real sleeping and no writes outside the temporary directory.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

WORKSTREAM = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKSTREAM))

import live  # noqa: E402


class FakeClock:
    """Deterministic now/sleep pair. Each sleep advances the clock and runs one queued action."""

    def __init__(self):
        self.time = 1000.0
        self.actions = []
        self.sleeps = []

    def add(self, action):
        self.actions.append(action)
        return action

    def now(self):
        return self.time

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.time += seconds
        if self.actions:
            self.actions.pop(0)()


class Recorder:
    """Fake runner: counts calls, optionally returns queued results or raises."""

    def __init__(self, results=None, error=None):
        self.calls = 0
        self.results = list(results or [])
        self.error = error

    def __call__(self):
        self.calls += 1
        if self.error is not None:
            raise self.error
        if self.results:
            return self.results.pop(0)
        return {"passed": True, "call": self.calls}


def write_file(path, text="data", mtime=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


@contextlib.contextmanager
def working_directory(path):
    previous = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.tmp = Path(self._temp.name)

    def test_snapshot_records_only_files_sorted_with_mtime_and_size(self):
        first = write_file(self.tmp / "b.txt", "bbb")
        second = write_file(self.tmp / "nested" / "a.txt", "a")
        data = live.snapshot([str(self.tmp)])
        self.assertEqual(list(data), sorted([str(first), str(second)]))
        self.assertEqual(data[str(first)]["size"], 3)
        self.assertEqual(data[str(second)]["size"], 1)
        self.assertIsInstance(data[str(first)]["mtime"], float)
        self.assertIsInstance(data[str(first)]["size"], int)

    def test_snapshot_accepts_a_single_file_or_pathlike(self):
        target = write_file(self.tmp / "one.txt", "x")
        self.assertEqual(list(live.snapshot(str(target))), [str(target)])
        self.assertEqual(list(live.snapshot(Path(target))), [str(target)])

    def test_snapshot_of_missing_paths_is_empty(self):
        self.assertEqual(live.snapshot([str(self.tmp / "nope")]), {})
        self.assertEqual(live.snapshot([str(self.tmp / "nope" / "deeper")]), {})

    def test_snapshot_merges_overlapping_paths(self):
        target = write_file(self.tmp / "game" / "data.txt", "x")
        data = live.snapshot([str(self.tmp), str(target)])
        self.assertEqual(list(data), [str(target)])

    def test_snapshot_relative_paths_stay_relative(self):
        with working_directory(self.tmp):
            write_file(self.tmp / "game" / "data.txt", "x")
            data = live.snapshot(["game"])
        self.assertEqual(list(data), [os.path.join("game", "data.txt")])

    def test_snapshot_empty_directory_is_empty(self):
        empty = self.tmp / "empty"
        empty.mkdir()
        self.assertEqual(live.snapshot([str(empty)]), {})


class ChangedPathsTests(unittest.TestCase):
    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.tmp = Path(self._temp.name)

    def test_reports_added_modified_and_deleted_sorted(self):
        before = {
            "b": {"mtime": 1.0, "size": 1},
            "d": {"mtime": 1.0, "size": 1},
        }
        after = {
            "a": {"mtime": 1.0, "size": 1},
            "b": {"mtime": 2.0, "size": 1},
            "c": {"mtime": 1.0, "size": 1},
        }
        self.assertEqual(live.changed_paths(before, after), ["a", "b", "c", "d"])

    def test_identical_snapshots_have_no_changes(self):
        before = {"a": {"mtime": 1.0, "size": 1}}
        self.assertEqual(live.changed_paths(before, dict(before)), [])

    def test_mtime_only_change_on_disk_is_detected(self):
        target = write_file(self.tmp / "a.txt", "same-size")
        before = live.snapshot([str(self.tmp)])
        os.utime(target, (before[str(target)]["mtime"] + 5, before[str(target)]["mtime"] + 5))
        after = live.snapshot([str(self.tmp)])
        self.assertEqual(live.changed_paths(before, after), [str(target)])

    def test_size_change_with_same_mtime_is_detected(self):
        before = {"a": {"mtime": 1.0, "size": 1}}
        after = {"a": {"mtime": 1.0, "size": 2}}
        self.assertEqual(live.changed_paths(before, after), ["a"])


class WatchTests(unittest.TestCase):
    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.tmp = Path(self._temp.name)
        self.clock = FakeClock()
        self.recorder = Recorder()
        self.target = self.tmp / "a.txt"

    def watch(self, paths=None, **overrides):
        options = {
            "runner": self.recorder,
            "iterations": 1,
            "interval": 0.01,
            "sleep": self.clock.sleep,
            "now": self.clock.now,
        }
        options.update(overrides)
        return live.watch(paths if paths is not None else [str(self.tmp)], **options)

    def test_zero_iterations_returns_immediately_without_sleeping(self):
        summary = self.watch(iterations=0)
        self.assertEqual(summary["iterations"], 0)
        self.assertEqual(summary["runs"], 0)
        self.assertEqual(summary["changes"], [])
        self.assertEqual(self.clock.sleeps, [])
        self.assertEqual(self.recorder.calls, 0)

    def test_iterations_limit_runs_once_per_settled_change(self):
        self.clock.add(lambda: write_file(self.target, "1"))
        self.clock.add(lambda: write_file(self.target, "22"))
        summary = self.watch(iterations=2)
        self.assertEqual(
            set(summary), {"iterations", "runs", "changes", "runnerResults", "errors"}
        )
        self.assertEqual(summary["iterations"], 2)
        self.assertEqual(summary["runs"], 2)
        self.assertEqual(len(summary["changes"]), 2)
        self.assertEqual(self.recorder.calls, 2)
        self.assertEqual(summary["errors"], [])
        self.assertEqual(len(self.clock.sleeps), 2)
        json.dumps(summary)  # the summary must be JSON-safe

    def test_single_path_string_is_accepted(self):
        write_file(self.target, "start")
        self.clock.add(lambda: write_file(self.target, "a longer body"))
        summary = self.watch(paths=str(self.tmp))
        self.assertEqual(summary["iterations"], 1)
        self.assertEqual(self.recorder.calls, 1)

    def test_deleted_file_is_a_change(self):
        write_file(self.target, "x")
        self.clock.add(self.target.unlink)
        summary = self.watch()
        self.assertEqual(summary["changes"][0]["paths"], [str(self.target)])
        self.assertEqual(self.recorder.calls, 1)

    def test_debounce_waits_for_stability_then_runs_once(self):
        write_file(self.target, "0")
        self.clock.add(lambda: write_file(self.target, "11"))
        self.clock.add(lambda: write_file(self.target, "333"))
        summary = self.watch(debounce=0.1, interval=0.05)
        self.assertEqual(summary["iterations"], 1)
        self.assertEqual(self.recorder.calls, 1)
        self.assertEqual(summary["changes"][0]["paths"], [str(self.target)])
        # one poll to see the change plus three debounce polls (0.05, 0.10 stable, 0.15 cap)
        self.assertEqual(len(self.clock.sleeps), 4)

    def test_runner_exception_is_recorded_not_fatal(self):
        self.recorder = Recorder(error=ValueError("boom"))
        self.clock.add(lambda: write_file(self.target, "1"))
        self.clock.add(lambda: write_file(self.target, "22"))
        summary = self.watch(iterations=2)
        self.assertEqual(summary["iterations"], 2)
        self.assertEqual(summary["runs"], 2)
        self.assertEqual(len(summary["errors"]), 2)
        self.assertEqual(summary["errors"][0]["type"], "ValueError")
        self.assertEqual(summary["errors"][0]["error"], "boom")
        self.assertEqual(summary["runnerResults"], [])

    def test_runner_result_is_coerced_to_json_safe(self):
        self.recorder = Recorder(results=[object()])
        self.clock.add(lambda: write_file(self.target, "1"))
        summary = self.watch()
        self.assertIsInstance(summary["runnerResults"][0], str)
        json.dumps(summary)

    def test_on_event_receives_the_settled_change(self):
        events = []
        self.clock.add(lambda: write_file(self.target, "1"))
        summary = self.watch(on_event=events.append)
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(
            set(event), {"iteration", "paths", "result", "error", "seconds"}
        )
        self.assertEqual(event["iteration"], 1)
        self.assertEqual(event["paths"], [str(self.target)])
        self.assertEqual(event["result"], {"passed": True, "call": 1})
        self.assertIsNone(event["error"])
        self.assertGreaterEqual(event["seconds"], 0.0)
        self.assertEqual(summary["runs"], 1)

    def test_on_event_exception_is_recorded_not_fatal(self):
        def broken(event):
            raise RuntimeError("bad listener")

        self.clock.add(lambda: write_file(self.target, "1"))
        summary = self.watch(on_event=broken)
        self.assertEqual(summary["runs"], 1)
        self.assertEqual(summary["errors"][0]["type"], "on_event")
        self.assertEqual(summary["errors"][0]["error"], "bad listener")

    def test_a_failed_result_is_data_not_a_watch_error(self):
        self.recorder = Recorder(results=[{"passed": False}])
        self.clock.add(lambda: write_file(self.target, "1"))
        summary = self.watch()
        self.assertEqual(summary["errors"], [])
        self.assertEqual(summary["runnerResults"], [{"passed": False}])

    def test_sleep_receives_the_interval(self):
        self.clock.add(lambda: write_file(self.target, "1"))
        self.watch(interval=0.25)
        self.assertEqual(self.clock.sleeps, [0.25])

    def test_rejects_invalid_arguments(self):
        invalid = [
            ("empty paths", lambda: live.watch([], runner=self.recorder)),
            ("negative interval", lambda: live.watch([str(self.tmp)], runner=self.recorder, interval=-1)),
            ("negative debounce", lambda: live.watch([str(self.tmp)], runner=self.recorder, debounce=-1)),
            ("negative iterations", lambda: live.watch([str(self.tmp)], runner=self.recorder, iterations=-1)),
        ]
        for label, call in invalid:
            with self.subTest(label=label):
                with self.assertRaises(ValueError):
                    call()
        with self.assertRaises(TypeError):
            live.watch([str(self.tmp)], runner=None)


class MainTests(unittest.TestCase):
    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.tmp = Path(self._temp.name)
        self.clock = FakeClock()
        self.recorder = Recorder()
        self.target = self.tmp / "a.txt"

    def run_main(self, argv, **overrides):
        options = {
            "runner": self.recorder,
            "sleep": self.clock.sleep,
            "now": self.clock.now,
        }
        options.update(overrides)
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = live.main(argv, **options)
        return code, buffer.getvalue()

    def test_once_runs_the_injected_runner_and_exits_zero(self):
        code, output = self.run_main(["--once", "--paths", str(self.tmp)])
        self.assertEqual(code, 0)
        self.assertEqual(self.recorder.calls, 1)
        self.assertIn("[live] run 1 (once): ok", output)

    def test_once_does_not_require_watched_paths_to_exist(self):
        code, output = self.run_main(["--once", "--paths", str(self.tmp / "missing")])
        self.assertEqual(code, 0)
        self.assertIn("run 1 (once): ok", output)
        self.assertEqual(self.clock.sleeps, [])

    def test_once_failed_result_exits_one(self):
        self.recorder = Recorder(results=[{"passed": False}])
        code, output = self.run_main(["--once", "--paths", str(self.tmp)])
        self.assertEqual(code, 1)
        self.assertIn("run 1 (once): FAIL", output)

    def test_once_runner_exception_exits_one(self):
        self.recorder = Recorder(error=RuntimeError("boom"))
        code, output = self.run_main(["--once", "--paths", str(self.tmp)])
        self.assertEqual(code, 1)
        self.assertIn("error: RuntimeError: boom", output)

    def test_once_ctrl_c_exits_zero(self):
        class Interrupting:
            def __call__(self):
                raise KeyboardInterrupt

        code, output = self.run_main(
            ["--once", "--paths", str(self.tmp)], runner=Interrupting()
        )
        self.assertEqual(code, 0)
        self.assertIn("stopped (interrupted)", output)

    def test_watch_prints_change_and_run_lines(self):
        self.clock.add(lambda: write_file(self.target, "1"))
        code, output = self.run_main(
            ["--paths", str(self.tmp), "--iterations", "1", "--interval", "0.01"]
        )
        self.assertEqual(code, 0)
        self.assertIn("[live] change 1: 1 path(s): " + str(self.target), output)
        self.assertIn("[live] run 1: ok", output)
        self.assertIn(
            "[live] done: 1 change(s), 1 run(s), 0 error(s)", output
        )

    def test_watch_failed_result_exits_one(self):
        self.recorder = Recorder(results=[{"passed": False}])
        self.clock.add(lambda: write_file(self.target, "1"))
        code, output = self.run_main(
            ["--paths", str(self.tmp), "--iterations", "1", "--interval", "0.01"]
        )
        self.assertEqual(code, 1)
        self.assertIn("[live] run 1: FAIL", output)

    def test_watch_runner_error_exits_one(self):
        self.recorder = Recorder(error=RuntimeError("boom"))
        self.clock.add(lambda: write_file(self.target, "1"))
        code, output = self.run_main(
            ["--paths", str(self.tmp), "--iterations", "1", "--interval", "0.01"]
        )
        self.assertEqual(code, 1)
        self.assertIn("[live] run 1: error: RuntimeError: boom", output)
        self.assertIn("1 error(s)", output)

    def test_ctrl_c_during_watch_exits_zero(self):
        def interrupt(seconds):
            raise KeyboardInterrupt

        code, output = self.run_main(
            ["--paths", str(self.tmp), "--iterations", "1", "--interval", "0.01"],
            sleep=interrupt,
        )
        self.assertEqual(code, 0)
        self.assertIn("stopped (interrupted)", output)
        self.assertEqual(self.recorder.calls, 0)

    def test_command_runner_maps_to_lazy_game_functions(self):
        calls = []
        fake = types.ModuleType("game")
        fake.demo = lambda: calls.append("demo") or {"passed": True}
        fake.verify = lambda: calls.append("verify") or {"passed": True}
        with mock.patch.dict(sys.modules, {"game": fake}):
            code, output = self.run_main(
                ["--once", "--paths", str(self.tmp), "--command", "verify"],
                runner=None,
            )
        self.assertEqual(code, 0)
        self.assertEqual(calls, ["verify"])
        self.assertIn("run 1 (once): ok", output)

    def test_command_runner_rejects_unknown_command(self):
        with self.assertRaises(ValueError):
            live._command_runner("bogus")

    def test_invalid_cli_values_are_rejected(self):
        argv_sets = [
            ["--once", "--interval", "0"],
            ["--once", "--debounce", "-0.1"],
            ["--once", "--iterations", "-1"],
            ["--once", "--command", "bogus"],
        ]
        for argv in argv_sets:
            with self.subTest(argv=argv):
                with contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit) as raised:
                        live.main(["--paths", str(self.tmp)] + argv, runner=self.recorder)
                self.assertNotEqual(raised.exception.code, 0)


if __name__ == "__main__":
    unittest.main()
