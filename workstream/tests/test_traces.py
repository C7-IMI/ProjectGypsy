from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

WORKSTREAM = Path(__file__).resolve().parents[1]
REPO_ROOT = WORKSTREAM.parent
sys.path.insert(0, str(WORKSTREAM))

import traces  # noqa: E402

T0 = "2026-10-30T12:00:00+00:00"
T5 = "2026-10-30T12:00:05+00:00"
T10 = "2026-10-30T12:00:10+00:00"


def write_state(state_dir, relative, payload):
    path = Path(state_dir) / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, str):
        path.write_text(payload, encoding="utf-8")
    else:
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def step_doc(step_id="build", status="passed", seconds=5.0, cached=False, error=None, output="MARKER\n"):
    return {
        "id": step_id,
        "kind": "command",
        "status": status,
        "required": True,
        "attempted": True,
        "cached": cached,
        "seconds": seconds,
        "startedAt": T0,
        "finishedAt": T5,
        "output": output,
        "error": error,
        "exit": 0 if status == "passed" else 1,
    }


def slice_doc(slice_name="demo", run_id="20261030T120000Z-abc123", passed=True, project=".", steps=None, **extra):
    steps = steps if steps is not None else [step_doc()]
    data = {
        "schema": traces.SLICE_SCHEMA,
        "slice": slice_name,
        "project": project,
        "runId": run_id,
        "manifestSha256": "a" * 64,
        "startedAt": T0,
        "finishedAt": T10,
        "durationSeconds": 10.0,
        "passed": passed,
        "timeoutScale": 1.0,
        "resumed": False,
        "stepOrder": [step["id"] for step in steps],
        "steps": steps,
        "artifacts": [],
        "ledgerPath": "C:\\checkout\\workstream\\state\\artifacts\\demo-run.json",
        "cache": {"enabled": True, "configuredSteps": 0, "hits": 0, "misses": 0, "stores": 0},
        "errors": [],
    }
    data.update(extra)
    return data


def task_doc(name="task-20261030T120000Z", slices=None, artifacts=None, passed=True, **extra):
    slices = slices if slices is not None else []
    data = {
        "schema": traces.TASK_SCHEMA,
        "task": name,
        "startedAt": T0,
        "finishedAt": T10,
        "durationSeconds": 10.0,
        "passed": passed,
        "sliceOrder": [summary["slice"] for summary in slices],
        "slices": slices,
        "steps": {"total": 2, "passed": 2, "failed": 0, "skipped": 0},
        "artifacts": artifacts or [],
        "parallel": {"requestedWorkers": 1, "workers": 1, "cancelled": False, "log": []},
        "cache": {"enabled": True, "hits": 0, "misses": 0, "stores": 0, "restores": 0, "bytesStored": 0},
        "errors": [],
    }
    data.update(extra)
    return data


def action_doc(toolpack="leftbehind.unity", action="demo", run_id="R2", passed=True, **extra):
    data = {
        "schema": traces.TOOLPACK_SCHEMA,
        "scope": "action",
        "toolpack": toolpack,
        "toolpackName": "LeftBehind Unity 6 Windows player",
        "action": action,
        "runId": run_id,
        "manifestSha256": "b" * 64,
        "startedAt": T0,
        "finishedAt": T5,
        "durationSeconds": 5.0,
        "passed": passed,
        "timedOut": False,
        "seconds": 5.0,
        "timeoutSeconds": 180.0,
        "command": {"argv": ["powershell", "-File", "scripts/run.ps1", "-Mode", action], "cwd": "."},
        "exit": 0 if passed else 1,
        "stdout": "MARKER_OK\n",
        "stderr": "",
        "artifacts": [{"path": "artifacts/player.log", "bytes": 100, "sha256": "c" * 64, "exists": True}],
        "validators": [{"id": "marker", "kind": "text", "passed": passed, "error": None}],
        "license": "test licence",
        "tools": ["Unity 6000.6.7f1"],
        "errors": [] if passed else ["marker missing"],
    }
    data.update(extra)
    return data


def toolpack_run_doc(toolpack="leftbehind.unity", run_id="R1", actions=None, passed=True, **extra):
    actions = actions if actions is not None else [
        {
            "action": "build",
            "status": "passed",
            "passed": True,
            "exit": 0,
            "seconds": 4.0,
            "timedOut": False,
            "statePath": "C:\\checkout\\workstream\\state\\toolpacks\\leftbehind.unity-build-R1.json",
            "artifacts": 1,
            "validators": 1,
            "label": None,
            "errors": [],
            "cache": {"enabled": True, "hits": 1, "misses": 0, "stores": 0},
        }
    ]
    data = {
        "schema": traces.TOOLPACK_SCHEMA,
        "scope": "toolpack",
        "toolpack": toolpack,
        "toolpackName": "LeftBehind Unity 6 Windows player",
        "runId": run_id,
        "manifestSha256": "d" * 64,
        "startedAt": T0,
        "finishedAt": T10,
        "durationSeconds": 10.0,
        "passed": passed,
        "actionOrder": [action["action"] for action in actions],
        "actions": actions,
        "artifacts": [{"action": "build", "path": "build/app.exe", "bytes": 100, "sha256": "e" * 64, "exists": True}],
        "validators": [{"action": "build", "id": "exe", "kind": "file", "passed": passed}],
        "parallel": {"requestedWorkers": 1, "workers": 1, "cancelled": False, "log": []},
        "cache": {"enabled": True, "hits": 1, "misses": 0, "stores": 0, "restores": 0, "bytesStored": 0},
        "license": "test licence",
        "tools": ["Unity 6000.6.7f1"],
        "errors": [] if passed else ["action failed"],
    }
    data.update(extra)
    return data


def collect_with(tmp, files):
    state = Path(tmp) / "state"
    (state / "slices").mkdir(parents=True)
    (state / "toolpacks").mkdir(parents=True)
    for relative, payload in files.items():
        write_state(state, relative, payload)
    return state, traces.collect(state)


def run_cli(*args):
    return subprocess.run(
        [sys.executable, str(WORKSTREAM / "traces.py"), *args],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=180,
    )


def without_generated(payload):
    copy = json.loads(json.dumps(payload))
    copy.pop("generated", None)
    return copy


class EmptyStateTests(unittest.TestCase):
    def test_empty_state_dir_is_valid_and_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state"
            (state / "slices").mkdir(parents=True)
            (state / "toolpacks").mkdir(parents=True)
            payload = traces.collect(state)
            self.assertEqual(payload["counts"]["traces"], 0)
            self.assertEqual(payload["counts"]["spans"], 0)
            self.assertEqual(payload["traces"], [])
            self.assertEqual(traces.validate(payload), [])
            self.assertEqual(traces.problems(payload), [])
            self.assertEqual(payload["source"]["live"], False)

    def test_missing_state_dir_is_a_problem_trace(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload = traces.collect(Path(tmp) / "missing")
            self.assertEqual(payload["counts"]["traces"], 1)
            self.assertEqual(payload["counts"]["problemTraces"], 1)
            trace = payload["traces"][0]
            self.assertEqual(trace["kind"], "problem")
            self.assertEqual(trace["status"], "error")
            self.assertEqual(trace["spans"][0]["kind"], "problem")
            self.assertIn("not found", trace["spans"][0]["attributes"]["error"])
            self.assertEqual(traces.validate(payload), [])
            self.assertTrue(traces.problems(payload))

    def test_missing_subdirectory_is_a_warning_not_a_problem(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state"
            (state / "slices").mkdir(parents=True)
            payload = traces.collect(state)
            self.assertEqual(payload["counts"]["traces"], 0)
            self.assertEqual(payload["counts"]["problemTraces"], 0)
            self.assertTrue(any("toolpacks" in warning for warning in payload["warnings"]))
            self.assertEqual(traces.problems(payload), [])


class HierarchyTests(unittest.TestCase):
    def test_slice_trace_hierarchy_timings_and_cache(self):
        steps = [
            step_doc("check", cached=True),
            step_doc("tests", seconds=3.25),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            _state, payload = collect_with(tmp, {"slices/demo.json": slice_doc(steps=steps)})
            self.assertEqual(payload["counts"]["traces"], 1)
            trace = payload["traces"][0]
            self.assertEqual(trace["kind"], "slice")
            self.assertEqual(trace["status"], "ok")
            self.assertEqual(trace["startTime"], "2026-10-30T12:00:00Z")
            self.assertEqual(trace["endTime"], "2026-10-30T12:00:10Z")
            self.assertEqual(trace["durationSeconds"], 10.0)
            self.assertEqual(len(trace["spans"]), 3)
            root, check, tests = trace["spans"]
            self.assertEqual(root["kind"], "run")
            self.assertIsNone(root["parentSpanId"])
            self.assertEqual(check["parentSpanId"], root["spanId"])
            self.assertEqual(check["name"], "step check")
            self.assertEqual(check["kind"], "step")
            self.assertEqual(check["durationSeconds"], 5.0)
            self.assertTrue(check["attributes"]["cacheHit"])
            self.assertEqual(check["attributes"]["outputBytes"], len("MARKER\n"))
            self.assertEqual(tests["durationSeconds"], 3.25)
            self.assertFalse(tests["attributes"]["cacheHit"])
            self.assertEqual(root["attributes"]["engine"], None)
            self.assertEqual(traces.validate(payload), [])

    def test_task_trace_uses_recorded_summaries_without_inventing_times(self):
        summaries = [
            {
                "slice": "alpha",
                "status": "passed",
                "passed": True,
                "statePath": "C:\\checkout\\workstream\\state\\slices\\alpha.json",
                "steps": {"total": 2, "passed": 2, "failed": 0, "skipped": 0},
                "artifacts": 1,
                "durationSeconds": 6.5,
                "errors": [],
                "cache": {"enabled": True, "hits": 1, "misses": 0, "stores": 0},
            },
            {
                "slice": "beta",
                "status": "failed",
                "passed": False,
                "statePath": "C:\\checkout\\workstream\\state\\slices\\beta.json",
                "steps": {"total": 1, "passed": 0, "failed": 1, "skipped": 0},
                "artifacts": 0,
                "durationSeconds": 3.5,
                "errors": ["beta broke"],
                "cache": None,
            },
        ]
        artifacts = [
            {"slice": "alpha", "path": "artifacts/alpha.png", "bytes": 10, "sha256": "f" * 64, "exists": True},
            {"slice": "beta", "path": "artifacts/beta.png", "bytes": 20, "sha256": "0" * 64, "exists": True},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            _state, payload = collect_with(
                tmp, {"slices/task-T.json": task_doc(slices=summaries, artifacts=artifacts)}
            )
            trace = payload["traces"][0]
            self.assertEqual(trace["kind"], "task")
            self.assertEqual(len(trace["spans"]), 3)
            root, alpha, beta = trace["spans"]
            self.assertEqual(root["attributes"]["sliceCount"], 2)
            self.assertEqual(alpha["name"], "slice alpha")
            self.assertEqual(alpha["parentSpanId"], root["spanId"])
            self.assertIsNone(alpha["startTime"])
            self.assertIsNone(alpha["endTime"])
            self.assertEqual(alpha["durationSeconds"], 6.5)
            self.assertFalse(alpha["attributes"]["timingRecorded"])
            self.assertEqual([item["path"] for item in alpha["attributes"]["artifacts"]], ["artifacts/alpha.png"])
            self.assertEqual(beta["status"], "error")
            self.assertEqual(beta["attributes"]["errors"], ["beta broke"])
            self.assertEqual(traces.validate(payload), [])

    def test_toolpack_run_dedupes_referenced_action_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state"
            (state / "slices").mkdir(parents=True)
            (state / "toolpacks").mkdir(parents=True)
            run = toolpack_run_doc()
            write_state(state, "toolpacks/leftbehind.unity-R1.json", run)
            write_state(state, "toolpacks/leftbehind.unity-build-R1.json", action_doc(action="build", run_id="R1"))
            write_state(state, "toolpacks/leftbehind.unity-demo-R2.json", action_doc(action="demo", run_id="R2"))
            payload = traces.collect(state)
            self.assertEqual(payload["counts"]["traces"], 2)
            kinds = sorted(trace["kind"] for trace in payload["traces"])
            self.assertEqual(kinds, ["toolpack", "toolpack-action"])
            run_trace = next(trace for trace in payload["traces"] if trace["kind"] == "toolpack")
            self.assertEqual(len(run_trace["spans"]), 2)
            action = run_trace["spans"][1]
            self.assertEqual(action["name"], "action build")
            self.assertEqual(action["status"], "ok")
            self.assertEqual(action["durationSeconds"], 4.0)
            self.assertEqual(action["attributes"]["cache"]["hits"], 1)
            standalone = next(trace for trace in payload["traces"] if trace["kind"] == "toolpack-action")
            root = standalone["spans"][0]
            self.assertEqual(root["attributes"]["action"], "demo")
            self.assertEqual(root["attributes"]["argv"][0], "powershell")
            self.assertIn("MARKER_OK", root["attributes"]["stdoutTail"] or "")
            self.assertEqual(traces.validate(payload), [])

    def test_failed_runs_and_steps_are_errors(self):
        steps = [step_doc("check", status="failed", error="exit 1", output="")]
        with tempfile.TemporaryDirectory() as tmp:
            _state, payload = collect_with(
                tmp,
                {
                    "slices/demo.json": slice_doc(passed=False, steps=steps, errors=["demo failed"]),
                    "toolpacks/bad-R3.json": toolpack_run_doc(run_id="R3", passed=False, actions=[]),
                },
            )
            self.assertEqual(payload["counts"]["errorTraces"], 2)
            slice_trace = next(trace for trace in payload["traces"] if trace["kind"] == "slice")
            self.assertEqual(slice_trace["status"], "error")
            self.assertEqual(slice_trace["spans"][1]["status"], "error")
            self.assertEqual(slice_trace["spans"][1]["attributes"]["error"], "exit 1")
            toolpack_trace = next(trace for trace in payload["traces"] if trace["kind"] == "toolpack")
            self.assertEqual(toolpack_trace["status"], "error")
            self.assertEqual(traces.validate(payload), [])

    def test_missing_timings_are_null_not_invented(self):
        steps = [step_doc("check")]
        for field in ("startedAt", "finishedAt"):
            steps[0].pop(field)
        data = slice_doc(steps=steps)
        for field in ("startedAt", "finishedAt", "durationSeconds"):
            data.pop(field)
        with tempfile.TemporaryDirectory() as tmp:
            _state, payload = collect_with(tmp, {"slices/demo.json": data})
            trace = payload["traces"][0]
            root = trace["spans"][0]
            self.assertIsNone(root["startTime"])
            self.assertIsNone(root["endTime"])
            self.assertIsNone(root["durationSeconds"])
            step = trace["spans"][1]
            self.assertIsNone(step["startTime"])
            self.assertEqual(step["durationSeconds"], 5.0)
            self.assertTrue(step["attributes"]["timingRecorded"])
            self.assertEqual(traces.validate(payload), [])

    def test_canonical_order_and_deterministic_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state"
            (state / "slices").mkdir(parents=True)
            (state / "toolpacks").mkdir(parents=True)
            later = slice_doc(run_id="LATER")
            later["startedAt"] = "2026-10-30T13:00:00+00:00"
            later["finishedAt"] = "2026-10-30T13:00:10+00:00"
            write_state(state, "slices/later.json", later)
            earlier = slice_doc(steps=[step_doc("b"), step_doc("a")], run_id="EARLIER")
            write_state(state, "slices/earlier.json", earlier)
            first = traces.collect(state)
            second = traces.collect(state)
            self.assertEqual(without_generated(first), without_generated(second))
            starts = [trace["startTime"] or "" for trace in first["traces"]]
            self.assertEqual(starts, sorted(starts))
            step_names = [span["name"] for span in first["traces"][0]["spans"]]
            self.assertEqual(step_names, ["run demo", "step b", "step a"])
            self.assertEqual(traces.validate(first), [])

    def test_ids_are_stable_across_state_directory_copies(self):
        with tempfile.TemporaryDirectory() as first_tmp, tempfile.TemporaryDirectory() as second_tmp:
            first_state = Path(first_tmp) / "state"
            (first_state / "slices").mkdir(parents=True)
            (first_state / "toolpacks").mkdir(parents=True)
            write_state(first_state, "slices/demo.json", slice_doc())
            second_state = Path(second_tmp) / "state"
            shutil.copytree(first_state, second_state)
            first = traces.collect(first_state)
            second = traces.collect(second_state)
            self.assertEqual(first["traces"], second["traces"])
            trace_id = first["traces"][0]["traceId"]
            self.assertRegex(trace_id, r"^[0-9a-f]{32}$")
            for span in first["traces"][0]["spans"]:
                self.assertRegex(span["spanId"], r"^[0-9a-f]{16}$")
            total_ids = [trace["traceId"] for trace in first["traces"]] + [
                span["spanId"] for trace in first["traces"] for span in trace["spans"]
            ]
            self.assertEqual(len(total_ids), len(set(total_ids)))

    def test_engine_attribute_comes_from_the_project_manifest_or_is_null(self):
        manifest = REPO_ROOT / "game" / "project.gypsy.json"
        with tempfile.TemporaryDirectory() as tmp:
            _state, payload = collect_with(
                tmp, {"slices/demo.json": slice_doc(project="game")}
            )
            root = payload["traces"][0]["spans"][0]
            if manifest.is_file():
                manifest_data = json.loads(manifest.read_text(encoding="utf-8"))
                self.assertEqual(root["attributes"]["engine"], manifest_data["engine"]["id"])
                self.assertEqual(root["attributes"]["engineSource"], "project.gypsy.json")
            else:
                self.assertIsNone(root["attributes"]["engine"])
                self.assertIsNone(root["attributes"]["engineSource"])

        with tempfile.TemporaryDirectory() as tmp:
            _state, payload = collect_with(tmp, {"slices/demo.json": slice_doc(project=".")})
            root = payload["traces"][0]["spans"][0]
            self.assertIsNone(root["attributes"]["engine"])
            self.assertIsNone(root["attributes"]["engineSource"])


class ProblemStateTests(unittest.TestCase):
    def test_corrupt_unexpected_and_non_object_states_become_problem_traces(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state"
            (state / "slices").mkdir(parents=True)
            (state / "toolpacks").mkdir(parents=True)
            write_state(state, "slices/good.json", slice_doc())
            write_state(state, "slices/broken.json", "{ not json")
            write_state(state, "slices/array.json", "[]")
            write_state(state, "slices/wrong-schema.json", {"schema": "something/else"})
            write_state(state, "toolpacks/bad-scope.json", {"schema": traces.TOOLPACK_SCHEMA, "scope": "mystery"})
            write_state(state, "toolpacks/bad-schema.json", {"schema": "unknown", "scope": "toolpack"})
            payload = traces.collect(state)
            self.assertEqual(payload["counts"]["problemTraces"], 5)
            self.assertEqual(payload["counts"]["traces"], 6)
            self.assertEqual([trace["kind"] for trace in payload["traces"]].count("slice"), 1)
            for trace in payload["traces"]:
                if trace["kind"] != "problem":
                    continue
                self.assertEqual(trace["status"], "error")
                self.assertEqual(trace["spans"][0]["kind"], "problem")
                self.assertTrue(trace["spans"][0]["attributes"]["error"])
            self.assertEqual(traces.validate(payload), [])
            self.assertTrue(traces.problems(payload))

    def test_non_json_files_are_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state"
            (state / "slices").mkdir(parents=True)
            (state / "toolpacks").mkdir(parents=True)
            (state / "slices" / "notes.txt").write_text("not state", encoding="utf-8")
            payload = traces.collect(state)
            self.assertEqual(payload["counts"]["traces"], 0)
            self.assertEqual(payload["counts"]["problemTraces"], 0)


class PayloadTests(unittest.TestCase):
    def sample(self):
        with tempfile.TemporaryDirectory() as tmp:
            _state, payload = collect_with(
                tmp,
                {
                    "slices/demo.json": slice_doc(),
                    "toolpacks/run-R1.json": toolpack_run_doc(actions=[]),
                },
            )
            return payload

    def test_validate_accepts_collected_payloads(self):
        payload = self.sample()
        self.assertEqual(traces.validate(payload), [])
        self.assertEqual(traces.problems(payload), [])
        self.assertEqual(json.loads(traces.to_json(payload)), payload)

    def test_validate_rejects_broken_payloads(self):
        payload = self.sample()
        broken = json.loads(json.dumps(payload))
        broken["schema"] = "wrong"
        broken["source"]["live"] = True
        broken["traces"][0]["traceId"] = "abc"
        broken["traces"][0]["spans"][0]["kind"] = "run"
        broken["traces"][0]["spans"][1]["parentSpanId"] = "0" * 16
        broken["counts"]["traces"] = 99
        errors = " ".join(traces.validate(broken))
        for expected in ("schema", "source.live", "traceId", "parent span must appear", "counts"):
            self.assertIn(expected, errors)
        self.assertEqual(traces.validate("not a dict"), ["payload must be a JSON object"])

        reordered = json.loads(json.dumps(payload))
        reordered["traces"].reverse()
        if len(reordered["traces"]) > 1:
            self.assertIn("sorted", " ".join(traces.validate(reordered)))

    def test_to_otel_is_local_and_maps_ids_and_status(self):
        payload = self.sample()
        otel = traces.to_otel(payload)
        self.assertIs(otel["_local"], True)
        self.assertIn("Not live instrumentation", otel["_note"])
        spans = otel["resourceSpans"][0]["scopeSpans"][0]["spans"]
        self.assertEqual(len(spans), payload["counts"]["spans"])
        payload_spans = [span for trace in payload["traces"] for span in trace["spans"]]
        self.assertEqual([span["spanId"] for span in spans], [span["spanId"] for span in payload_spans])
        codes = {span["spanId"]: span["status"]["code"] for span in spans}
        for span in payload_spans:
            expected = {"ok": 1, "error": 2}.get(span["status"], 0)
            self.assertEqual(codes[span["spanId"]], expected)
        self.assertIn("startTimeUnixNano", spans[1])
        self.assertTrue(all(isinstance(item["value"]["intValue"], str) for span in spans for item in span["attributes"] if "intValue" in item["value"]))
        self.assertEqual(traces.validate(payload), [])


class RealStateTests(unittest.TestCase):
    def test_real_state_collects_a_valid_hierarchy(self):
        payload = traces.collect()
        self.assertEqual(traces.validate(payload), [])
        self.assertEqual(traces.problems(payload), [])
        self.assertGreater(payload["counts"]["traces"], 0)
        self.assertGreater(payload["counts"]["spans"], 0)
        self.assertEqual(payload["counts"]["problemTraces"], 0)
        self.assertGreater(payload["counts"]["byKind"]["task"], 0)
        self.assertGreater(payload["counts"]["byKind"]["slice"], 0)
        self.assertGreater(payload["counts"]["byKind"]["toolpack"], 0)
        second = traces.collect()
        self.assertEqual(without_generated(payload), without_generated(second))
        otel = traces.to_otel(payload)
        self.assertIs(otel["_local"], True)
        self.assertEqual(
            len(otel["resourceSpans"][0]["scopeSpans"][0]["spans"]),
            payload["counts"]["spans"],
        )


class CliTests(unittest.TestCase):
    def test_cli_json_validate_and_human(self):
        result = run_cli("--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["schema"], traces.SCHEMA)
        self.assertEqual(traces.validate(payload), [])
        valid = run_cli("--validate")
        self.assertEqual(valid.returncode, 0, valid.stderr)
        human = run_cli()
        self.assertEqual(human.returncode, 0, human.stderr)
        self.assertIn("local trace:", human.stdout)
        self.assertIn("Not live instrumentation", human.stdout)

    def test_cli_problem_state_fails_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state"
            (state / "slices").mkdir(parents=True)
            (state / "toolpacks").mkdir(parents=True)
            (state / "slices" / "bad.json").write_text("{", encoding="utf-8")
            result = run_cli("--state-dir", str(state), "--validate")
            self.assertEqual(result.returncode, 1)
            self.assertIn("FAIL traces", result.stderr)

    def test_cli_otel_export(self):
        result = run_cli("--otel")
        self.assertEqual(result.returncode, 0, result.stderr)
        otel = json.loads(result.stdout)
        self.assertIs(otel["_local"], True)
        self.assertIn("resourceSpans", otel)
        self.assertTrue(otel["resourceSpans"][0]["scopeSpans"][0]["spans"])

    def test_cli_rejects_json_and_otel_together(self):
        result = run_cli("--json", "--otel")
        self.assertEqual(result.returncode, 2)


if __name__ == "__main__":
    unittest.main()
