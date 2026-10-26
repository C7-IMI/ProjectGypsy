from __future__ import annotations

import json
import sys
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

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
