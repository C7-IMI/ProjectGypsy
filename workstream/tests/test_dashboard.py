from __future__ import annotations

import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

WORKSTREAM = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKSTREAM))

import dashboard  # noqa: E402
import gypsy  # noqa: E402


class StateTests(unittest.TestCase):
    def test_collect_state_shape(self):
        state = dashboard.collect_state()
        for key in ("generated", "branch", "head", "clean", "slices", "artifacts", "gates", "phases", "metrics", "commands", "runs"):
            self.assertIn(key, state)
        self.assertEqual(len(state["slices"]), state["metrics"]["slicesTotal"])
        self.assertGreaterEqual(state["metrics"]["capabilities"], 40)
        self.assertIsInstance(state["commands"], list)
        self.assertIn("run_all", [item["id"] for item in state["commands"]])
        self.assertIn("leftbehind", [item["id"] for item in state["commands"]])
        self.assertIsInstance(state["runs"], list)

    def test_commands_are_fixed_argv_lists(self):
        for action, command in dashboard.COMMANDS.items():
            self.assertIsInstance(command["argv"], list)
            self.assertTrue(command["argv"])
            self.assertTrue(all(isinstance(item, str) for item in command["argv"]), action)
            self.assertNotIn("|", command["argv"], action)

    def test_safe_artifact_rejects_traversal(self):
        self.assertIsNone(dashboard._safe_artifact("../../Windows/win.ini"))
        self.assertIsNone(dashboard._safe_artifact("does/not/exist.txt"))
        if (Path(dashboard.REPO_ROOT) / "artifacts" / "game" / "frame.png").exists():
            self.assertIsNotNone(dashboard._safe_artifact("artifacts/game/frame.png"))

    def test_artifact_entry_has_live_metadata(self):
        if not (Path(dashboard.REPO_ROOT) / "artifacts" / "game" / "frame.png").exists():
            self.skipTest("artifact not present in this checkout")
        entry = dashboard._artifact_entry(Path("artifacts/game/frame.png"))
        self.assertTrue(entry["exists"])
        self.assertEqual(entry["kind"], "png")
        self.assertGreater(entry["bytes"], 0)
        self.assertIn("/api/artifact", entry["preview"])


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), dashboard.Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = "http://127.0.0.1:" + str(cls.server.server_address[1])

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def get(self, path):
        with urllib.request.urlopen(self.base + path, timeout=10) as response:
            return response.status, response.read()

    def post(self, path, payload, token=None):
        request = urllib.request.Request(
            self.base + path,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", **({"X-Gypsy-Token": token} if token else {})},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read()

    def test_index_and_assets(self):
        status, body = self.get("/")
        self.assertEqual(status, 200)
        text = body.decode("utf-8")
        self.assertIn("Overview", text)
        self.assertIn("Run detail", text)
        self.assertIn("Mission", text)
        self.assertIn("Commands", text)
        self.assertIn("Review", text)
        self.assertIn("Slices", text)
        self.assertIn("Artifacts", text)
        self.assertIn("Classic views", text)
        self.assertIn("gypsy-token", text)
        self.assertNotIn("__TOKEN__", text)
        status, js = self.get("/app.js")
        self.assertEqual(status, 200)
        self.assertIn(b"renderOverview", js)
        self.assertIn(b"renderRun", js)
        self.assertIn(b"renderMission", js)
        self.assertIn(b"renderCommands", js)
        self.assertIn(b"renderReview", js)
        self.assertIn(b"renderSlices", js)
        self.assertIn(b"renderArtifacts", js)
        status, classic = self.get("/classic")
        self.assertEqual(status, 200)
        classic_text = classic.decode("utf-8")
        self.assertIn("Studio Board", classic_text)
        self.assertIn("/classic/app.js", classic_text)

    def test_state_endpoint(self):
        status, body = self.get("/api/state")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertGreaterEqual(data["metrics"]["capabilities"], 40)

    def test_run_history_endpoint(self):
        status, body = self.get("/api/runs")
        self.assertEqual(status, 200)
        runs = json.loads(body)["runs"]
        if not runs:
            self.skipTest("no run state in this checkout")
        status, body = self.get("/api/run?id=" + urllib.parse.quote(runs[0]["id"], safe=""))
        self.assertEqual(status, 200)
        detail = json.loads(body)
        self.assertIn("steps", detail)
        self.assertIn("artifacts", detail)
        with self.assertRaises(urllib.error.HTTPError) as missing:
            self.get("/api/run?id=not-a-run")
        self.assertEqual(missing.exception.code, 404)

    def test_run_requires_token_and_known_action(self):
        status, _ = self.post("/api/run", {"action": "live_once"})
        self.assertEqual(status, 403)
        if not gypsy.detect_godot().get("usable"):
            self.skipTest("Godot is not installed on this clean runner")
        status, _ = self.post("/api/run", {"action": "live_once"}, dashboard.TOKEN)
        self.assertEqual(status, 202)
        # The job above is a real whitelisted command; wait for it to finish so no run leaks.
        import time
        for _ in range(120):
            with urllib.request.urlopen(self.base + "/api/job", timeout=10) as response:
                job = json.loads(response.read())
            if job.get("status") != "running":
                break
            time.sleep(0.5)
        self.assertIn(job.get("status"), {"passed", "failed"})

    def test_unknown_action_is_400(self):
        status, _ = self.post("/api/run", {"action": "arbitrary_shell"}, dashboard.TOKEN)
        self.assertEqual(status, 400)

    def test_artifact_raw(self):
        if not (Path(dashboard.REPO_ROOT) / "artifacts" / "game" / "frame.png").exists():
            self.skipTest("artifact not present in this checkout")
        status, body = self.get("/api/artifact?raw=1&path=artifacts/game/frame.png")
        self.assertEqual(status, 200)
        self.assertTrue(body.startswith(b"\x89PNG"))


# -- Phase-4 dashboard upgrade: insights, cache, scheduler, SSE, remediation -


def write_json_file(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def task_state(**overrides):
    payload = {
        "schema": "gypsy.task-state/v1",
        "task": "task-test",
        "passed": True,
        "durationSeconds": 2.0,
        "startedAt": "2026-10-30T00:00:00+00:00",
        "slices": [],
        "steps": {"total": 0, "passed": 0, "failed": 0, "skipped": 0},
        "artifacts": [],
    }
    payload.update(overrides)
    return payload


def slice_state(slice_id, *, passed=True, steps=None, artifacts=None):
    return {
        "schema": "gypsy.slice-state/v1",
        "slice": slice_id,
        "passed": passed,
        "durationSeconds": 1.0,
        "steps": steps or [{"id": "demo", "kind": "game.demo", "status": "passed", "seconds": 1.0}],
        "artifacts": artifacts or [],
        "errors": [],
    }


class InsightStateTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.state = Path(self._tmp.name) / "state"
        self.state.mkdir(parents=True)

    def collect(self):
        with mock.patch.object(dashboard, "STATE", self.state):
            return dashboard.collect_state()

    def test_empty_state_is_honest_and_actionable(self):
        data = self.collect()
        insights = data["insights"]
        self.assertEqual(data["slices"], [])
        self.assertFalse(insights["cache"]["available"])
        self.assertIsNone(insights["cache"]["hits"])
        self.assertTrue(insights["cache"]["emptyReason"])
        self.assertFalse(insights["scheduler"]["available"])
        self.assertTrue(insights["scheduler"]["emptyReason"])
        self.assertFalse(insights["lastRun"]["available"])
        self.assertTrue(insights["lastRun"]["emptyReason"])
        ids = [item["id"] for item in insights["nextActions"]]
        self.assertIn("no-run", ids)
        for action in insights["nextActions"]:
            self.assertTrue(action["title"])
            if action["action"] is not None:
                self.assertIn(action["action"], dashboard.COMMANDS)
            self.assertTrue(action["command"] or action["view"])
        # nothing is inferred from a missing cache or scheduler
        self.assertEqual(insights["cache"]["lookedFor"], list(dashboard.CACHE_STATS_PATHS))

    def test_engine_insight_uses_manifests_and_documented_default(self):
        data = dashboard.collect_state()
        engine = data["insights"]["engine"]
        self.assertEqual(engine["current"]["engine"], "godot")
        self.assertEqual(engine["current"]["version"], "4.7.2")
        self.assertEqual(engine["second"]["engine"], "unity")
        self.assertEqual(engine["second"]["version"], "6000.6.7f1")
        self.assertEqual(engine["default"]["engine"], "unity")
        self.assertEqual(engine["default"]["version"], "6000.6.7f1")
        self.assertIn("ADR-018", engine["default"]["source"])
        self.assertTrue(engine["facts"])

    def test_cache_stats_fixture(self):
        write_json_file(self.state / "cache" / "stats.json", {
            "hits": 7,
            "misses": 3,
            "entries": 2,
            "savedSeconds": 12.5,
        })
        cache = self.collect()["insights"]["cache"]
        self.assertTrue(cache["available"])
        self.assertEqual(cache["hits"], 7)
        self.assertEqual(cache["misses"], 3)
        self.assertAlmostEqual(cache["hitRate"], 0.7, places=4)
        self.assertEqual(cache["entries"], 2)
        self.assertIn("70% hit rate", cache["summary"])
        self.assertIn("cache/stats.json", cache["source"].replace("\\", "/"))

    def test_cache_from_explicit_step_markers(self):
        write_json_file(self.state / "slices" / "phase1.json", slice_state("phase1", steps=[
            {"id": "demo", "status": "passed", "cache": "hit"},
            {"id": "build", "status": "passed", "cache": "miss"},
        ]))
        cache = self.collect()["insights"]["cache"]
        self.assertTrue(cache["available"])
        self.assertEqual(cache["hits"], 1)
        self.assertEqual(cache["misses"], 1)
        self.assertIn("explicit cache fields", cache["source"])

    def test_resume_cached_field_is_not_reported_as_action_cache(self):
        write_json_file(self.state / "slices" / "phase1.json", slice_state("phase1", steps=[
            {"id": "demo", "status": "passed", "cached": True},
        ]))
        cache = self.collect()["insights"]["cache"]
        self.assertFalse(cache["available"])
        self.assertIsNone(cache["hits"])

    def test_scheduler_state_fixture(self):
        write_json_file(self.state / "slices" / "task-20261030T000000Z.json", task_state(
            scheduler={"mode": "parallel", "workers": 4, "queueSeconds": 1.5, "cancelled": 1},
        ))
        scheduler = self.collect()["insights"]["scheduler"]
        self.assertTrue(scheduler["available"])
        self.assertEqual(scheduler["mode"], "parallel")
        self.assertEqual(scheduler["workers"], 4)
        self.assertEqual(scheduler["queueSeconds"], 1.5)
        self.assertEqual(scheduler["cancelled"], 1)
        self.assertIn("4 workers", scheduler["summary"])

    def test_quality_insight_counts_recorded_gates(self):
        # Gate/test evidence lives in the real checkout state; do not patch STATE here.
        quality = dashboard.collect_state()["insights"]["quality"]
        self.assertGreater(quality["passing"], 0)
        self.assertIn("gates pass", quality["summary"])
        self.assertIsNotNone(quality["tests"])
        self.assertGreaterEqual(quality["capabilities"], 40)


class RunRemediationTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.state = Path(self._tmp.name) / "state"
        self.state.mkdir(parents=True)

    def make_task(self, slice_payload, *, passed):
        slice_payload["errors"] = [] if passed else ["step 'demo' failed: boom"]
        slice_path = write_json_file(self.state / "slices" / "phase1.json", slice_payload)
        task_path = write_json_file(self.state / "slices" / "task-test.json", task_state(
            passed=passed,
            slices=[{
                "slice": "phase1",
                "status": "passed" if passed else "failed",
                "passed": passed,
                "statePath": str(slice_path),
                "steps": {"total": 1, "passed": 1 if passed else 0, "failed": 0 if passed else 1, "skipped": 0},
                "artifacts": 0,
                "durationSeconds": 1.0,
                "errors": [],
            }],
        ))
        return task_path

    def test_failed_run_detail_has_actionable_remediation(self):
        task_path = self.make_task(
            slice_state("phase1", passed=False, steps=[
                {"id": "demo", "kind": "game.demo", "status": "failed", "seconds": 1.0, "output": "boom", "error": "boom"},
            ]),
            passed=False,
        )
        detail = dashboard._run_detail(str(task_path), state_root=self.state)
        self.assertIsNotNone(detail)
        self.assertFalse(detail["passed"])
        remediation = detail["remediation"]
        self.assertEqual(remediation["failedSteps"], ["phase1 · demo"])
        self.assertIn("Failed step", remediation["summary"])
        self.assertIn(remediation["retryAction"], dashboard.COMMANDS)
        self.assertEqual(remediation["retryAction"], "phase1")
        self.assertTrue(remediation["command"].startswith("python workstream/gypsy.py"))
        self.assertTrue(remediation["runView"].startswith("?view=run&id="))

    def test_passed_run_detail_says_evidence_is_immutable(self):
        task_path = self.make_task(slice_state("phase1", passed=True), passed=True)
        detail = dashboard._run_detail(str(task_path), state_root=self.state)
        self.assertTrue(detail["passed"])
        self.assertEqual(detail["remediation"]["failedSteps"], [])
        self.assertIn("All steps passed", detail["remediation"]["summary"])

    def test_run_detail_rejects_paths_outside_the_state_root(self):
        outside = Path(self._tmp.name) / "outside.json"
        outside.write_text("{}", encoding="utf-8")
        self.assertIsNone(dashboard._run_detail(str(outside), state_root=self.state))


class JobDecorationTests(unittest.TestCase):
    def setUp(self):
        with dashboard.JOB_LOCK:
            self.original = dict(dashboard.JOB)
        self.addCleanup(self.restore)

    def restore(self):
        with dashboard.JOB_LOCK:
            dashboard.JOB.clear()
            dashboard.JOB.update(self.original)

    def set_job(self, **fields):
        with dashboard.JOB_LOCK:
            dashboard.JOB.clear()
            dashboard.JOB.update(fields)

    def test_failed_job_has_copy_command_and_run_link(self):
        self.set_job(
            status="failed",
            action="run_all",
            returncode=2,
            command=[sys.executable, "workstream/gypsy.py", "slices", "run", "--all"],
            commandLine=None,
        )
        job = dashboard._job_public()
        self.assertTrue(job["commandLine"].startswith("python "))
        self.assertIn("failed", job["remediation"]["summary"])
        self.assertEqual(job["remediation"]["retryAction"], "run_all")
        self.assertEqual(job["remediation"]["runView"], "?view=run")
        self.assertTrue(job["remediation"]["copyCommand"])

    def test_idle_job_does_not_invent_a_command(self):
        self.set_job(status="idle", action=None, output="", command=None, commandLine=None)
        job = dashboard._job_public()
        self.assertIsNone(job["commandLine"])
        self.assertEqual(job["remediation"]["copyCommand"], "")
        self.assertIsNone(job["remediation"]["retryAction"])


class StreamExecutionTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        with dashboard.JOB_LOCK:
            self.original = dict(dashboard.JOB)
        self.addCleanup(self.restore)

    def restore(self):
        with dashboard.JOB_LOCK:
            dashboard.JOB.clear()
            dashboard.JOB.update(self.original)

    def test_execute_streams_output_and_records_command_line(self):
        commands = {
            "fake": {
                "label": "Fake",
                "argv": [sys.executable, "-c", "print('STREAM_OK', flush=True)"],
                "hint": "",
            }
        }
        state = Path(self._tmp.name) / "state"
        state.mkdir()
        with mock.patch.dict(dashboard.COMMANDS, commands), mock.patch.object(dashboard, "STATE", state):
            dashboard._execute("fake")
        with dashboard.JOB_LOCK:
            job = dict(dashboard.JOB)
        self.assertEqual(job["status"], "passed")
        self.assertIn("STREAM_OK", job["output"])
        self.assertTrue(job["commandLine"].startswith("python "))
        self.assertFalse(job["timedOut"])
        self.assertTrue((state / "dashboard-job.json").exists())


class InsightServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), dashboard.Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = "http://127.0.0.1:" + str(cls.server.server_address[1])

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def setUp(self):
        with dashboard.JOB_LOCK:
            self.original = dict(dashboard.JOB)
        self.addCleanup(self.restore)

    def restore(self):
        with dashboard.JOB_LOCK:
            dashboard.JOB.clear()
            dashboard.JOB.update(self.original)

    def set_job(self, **fields):
        with dashboard.JOB_LOCK:
            dashboard.JOB.clear()
            dashboard.JOB.update(fields)

    def get(self, path):
        with urllib.request.urlopen(self.base + path, timeout=10) as response:
            return response.status, response.headers, response.read()

    def test_insights_endpoint(self):
        status, _, body = self.get("/api/insights")
        self.assertEqual(status, 200)
        insights = json.loads(body)["insights"]
        self.assertIn("engine", insights)
        self.assertIn("cache", insights)
        self.assertIn("scheduler", insights)
        self.assertIn("nextActions", insights)

    def test_state_endpoint_includes_insights_and_honest_cards(self):
        status, _, body = self.get("/api/state")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertIn("insights", data)
        self.assertIn("cache", data)
        self.assertIn("scheduler", data)
        self.assertIn("commandLine", data["job"])
        self.assertIn("remediation", data["job"])

    def test_logs_stream_idle(self):
        self.set_job(status="idle", action=None, output="", commandLine=None)
        status, headers, body = self.get("/api/logs/stream")
        self.assertEqual(status, 200)
        self.assertIn("text/event-stream", headers.get("Content-Type", ""))
        text = body.decode("utf-8")
        self.assertIn("event: idle", text)
        self.assertIn("No job has run", text)

    def test_logs_stream_done(self):
        self.set_job(
            status="passed",
            action="run_all",
            output="STREAM_DONE_OUTPUT",
            commandLine="python workstream/gypsy.py slices run --all",
            returncode=0,
            finishedAt="2026-10-30T00:00:00+00:00",
            command=[sys.executable, "workstream/gypsy.py", "slices", "run", "--all"],
        )
        status, headers, body = self.get("/api/logs/stream")
        self.assertEqual(status, 200)
        self.assertIn("text/event-stream", headers.get("Content-Type", ""))
        text = body.decode("utf-8")
        self.assertIn("event: job", text)
        self.assertIn("event: done", text)
        self.assertIn("STREAM_DONE_OUTPUT", text)

    def test_job_endpoint_remediation_shape(self):
        self.set_job(
            status="failed",
            action="run_all",
            returncode=1,
            output="boom",
            command=[sys.executable, "workstream/gypsy.py", "slices", "run", "--all"],
            commandLine=None,
        )
        status, _, body = self.get("/api/job")
        self.assertEqual(status, 200)
        job = json.loads(body)
        self.assertEqual(job["status"], "failed")
        self.assertIn("copyCommand", job["remediation"])
        self.assertEqual(job["remediation"]["retryAction"], "run_all")
        self.assertTrue(job["commandLine"].startswith("python "))


class FrontendContractTests(unittest.TestCase):
    def read(self, name):
        return (Path(dashboard.V2_ASSETS) / name).read_text(encoding="utf-8")

    def test_index_has_insights_tab_and_accessibility_hooks(self):
        html = self.read("index.html")
        self.assertIn('data-view="insights"', html)
        self.assertIn('role="tablist"', html)
        self.assertIn('aria-selected="true"', html)
        self.assertIn("Skip to view content", html)
        self.assertIn('aria-live="polite"', html)
        self.assertIn('id="job-actions"', html)
        self.assertIn('id="job-live"', html)
        self.assertIn("gypsy-token", html)

    def test_app_js_implements_insights_sse_and_remediation(self):
        js = self.read("app.js")
        for name in ("renderInsights", "renderOverview", "renderRun", "renderMission", "renderCommands", "renderReview", "renderSlices", "renderArtifacts"):
            self.assertIn(name, js)
        self.assertIn("EventSource", js)
        self.assertIn("/api/logs/stream", js)
        self.assertIn("remediation", js)
        self.assertIn("insights", js)
        self.assertIn("cache", js)
        self.assertIn("scheduler", js)
        self.assertIn("No runs recorded", js)
        self.assertIn("Copy command", js)
        self.assertIn("aria-selected", js)
        self.assertIn("ArrowRight", js)

    def test_app_css_has_responsive_and_focus_states(self):
        css = self.read("app.css")
        self.assertIn(".insights", css)
        self.assertIn(".empty", css)
        self.assertIn(":focus-visible", css)
        self.assertIn("@media(max-width:1200px)", css)
        self.assertIn("@media(max-width:760px)", css)
        self.assertIn(".actionrow", css)
