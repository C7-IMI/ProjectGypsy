#!/usr/bin/env python3
"""Tests for the TLS remote worker protocol (remote_worker.py).

Every test is real loopback TLS with an ephemeral self-signed certificate generated in
setUpModule (no key is committed). No network beyond 127.0.0.1 and no shell commands are
used; the worker's allowlisted action runs in an isolated git worktree of this repository.
"""
from __future__ import annotations

import http.client
import json
import ssl
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

WORKSTREAM = Path(__file__).resolve().parents[1]
REPO_ROOT = WORKSTREAM.parent
sys.path.insert(0, str(WORKSTREAM))

import remote_worker as rw  # noqa: E402

TOKEN = "task25-test-token"
_TEMP = None
_CERTS = None
_WRONG_CERTS = None


def setUpModule():
    global _TEMP, _CERTS, _WRONG_CERTS
    _TEMP = tempfile.TemporaryDirectory(prefix="gypsy-rw-tests-")
    try:
        _CERTS = rw.generate_self_signed_cert(Path(_TEMP.name) / "tls")
        _WRONG_CERTS = rw.generate_self_signed_cert(Path(_TEMP.name) / "wrong")
    except rw.RemoteWorkerError as exc:
        raise unittest.SkipTest("ephemeral certificate generation unavailable: " + str(exc))


def tearDownModule():
    if _TEMP is not None:
        _TEMP.cleanup()


def _git_status():
    return subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    ).stdout


def _worktree_count():
    output = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    ).stdout
    return output.count("worktree ")


class CoordinatorCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.coordinator = rw.RemoteWorkerCoordinator(
            self.root,
            token=TOKEN,
            certfile=_CERTS["cert"],
            keyfile=_CERTS["key"],
            port=0,
        ).start()
        self.addCleanup(self.coordinator.stop)
        self.client = rw.RemoteWorkerClient(
            self.coordinator.url, TOKEN, _CERTS["cert"]
        )

    def raw(self, method, path, payload=None, *, token=TOKEN, body=None, cafile=None):
        context = rw.make_client_tls_context(cafile or _CERTS["cert"])
        connection = http.client.HTTPSConnection(
            "127.0.0.1", self.coordinator.bound_port, context=context, timeout=15
        )
        headers = {}
        if token is not None:
            headers["Authorization"] = "Bearer " + token
        if body is None and payload is not None:
            body = json.dumps(payload).encode("utf-8")
        if body is not None:
            headers["Content-Type"] = "application/json"
        try:
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            status = response.status
            data = response.read()
        finally:
            connection.close()
        try:
            parsed = json.loads(data.decode("utf-8")) if data else {}
        except (UnicodeDecodeError, json.JSONDecodeError):
            parsed = {}
        return status, parsed

    def submit_toolpack(self, timeout_seconds=None, idempotency_key=None):
        payload = {"toolpack": "hero.wayfarer", "action": "validate"}
        if timeout_seconds is not None:
            payload["timeoutSeconds"] = timeout_seconds
        if idempotency_key is not None:
            payload["idempotencyKey"] = idempotency_key
        status, response = self.raw("POST", "/v1/jobs", payload)
        self.assertIn(status, (200, 201), response)
        return response["job"]

    def wait_expiry(self, seconds=1.2):
        time.sleep(seconds)


class AuthAndTlsTests(CoordinatorCase):
    def test_all_endpoints_require_a_bearer_token(self):
        job = self.submit_toolpack()
        requests = [
            ("GET", "/v1/health"),
            ("GET", "/v1/jobs"),
            ("GET", "/v1/jobs/" + job["id"]),
            ("POST", "/v1/jobs", {"toolpack": "hero.wayfarer", "action": "validate"}),
            ("POST", "/v1/jobs/claim", {}),
            ("POST", "/v1/jobs/" + job["id"] + "/complete", {"passed": True}),
            ("POST", "/v1/jobs/" + job["id"] + "/cancel", {}),
        ]
        for method, path, *rest in [(item[0], item[1], *item[2:]) for item in requests]:
            for token in (None, "wrong-token-123456"):
                payload = rest[0] if rest else None
                status, _ = self.raw(method, path, payload, token=token)
                self.assertEqual(status, 401, (method, path, token))

    def test_tls_verification_failure_is_refused(self):
        with self.assertRaises(rw.RemoteWorkerError) as raised:
            rw.RemoteWorkerClient(
                self.coordinator.url, TOKEN, _WRONG_CERTS["cert"]
            ).health()
        message = str(raised.exception)
        self.assertTrue("TLS" in message or "SSL" in message, message)

    def test_plaintext_url_has_no_fallback(self):
        with self.assertRaises(rw.RemoteWorkerError):
            rw.RemoteWorkerClient(
                "http://127.0.0.1:" + str(self.coordinator.bound_port),
                TOKEN,
                _CERTS["cert"],
            )

    def test_plaintext_http_attempt_fails_against_the_tls_port(self):
        connection = http.client.HTTPConnection(
            "127.0.0.1", self.coordinator.bound_port, timeout=5
        )
        try:
            with self.assertRaises(
                (ConnectionError, OSError, http.client.HTTPException)
            ):
                connection.request("GET", "/v1/health")
                response = connection.getresponse()
                response.read()
        finally:
            connection.close()

    def test_bad_tls_material_and_weak_tokens_are_refused(self):
        with self.assertRaises(rw.RemoteWorkerError):
            rw.RemoteWorkerCoordinator(
                self.root,
                token=TOKEN,
                certfile=self.root / "missing-cert.pem",
                keyfile=self.root / "missing-key.pem",
                port=0,
            )
        with self.assertRaises(rw.RemoteWorkerError):
            rw.RemoteWorkerCoordinator(
                self.root,
                token="short",
                certfile=_CERTS["cert"],
                keyfile=_CERTS["key"],
                port=0,
            )
        with self.assertRaises(rw.RemoteWorkerError):
            rw.RemoteWorkerCoordinator(
                self.root,
                token=TOKEN,
                certfile=_CERTS["cert"],
                keyfile=_CERTS["key"],
                host="0.0.0.0",
                port=0,
            )

    def test_health_is_minimal_and_allowlisted(self):
        status, payload = self.raw("GET", "/v1/health")
        self.assertEqual(status, 200)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["tls"], "required")
        self.assertTrue(payload["loopback"])
        self.assertEqual(payload["allowlist"]["toolpackActions"], [["hero.wayfarer", "validate"]])
        self.assertNotIn(TOKEN, json.dumps(payload))


class JobValidationTests(CoordinatorCase):
    def test_allowlisted_toolpack_and_probe_jobs_are_accepted(self):
        job = self.submit_toolpack()
        self.assertEqual(job["state"], "queued")
        self.assertEqual(job["kind"], "toolpack")
        self.assertEqual(job["request"], {"toolpack": "hero.wayfarer", "action": "validate"})
        status, response = self.raw("POST", "/v1/jobs", {"probe": "godot"})
        self.assertEqual(status, 201, response)
        self.assertEqual(response["job"]["kind"], "probe")
        self.assertEqual(response["job"]["request"], {"probe": "godot"})

    def test_unknown_actions_and_toolpacks_are_rejected(self):
        for payload in (
            {"toolpack": "hero.wayfarer", "action": "generate"},
            {"toolpack": "hero.wayfarer", "action": "capture"},
            {"toolpack": "quality.visual", "action": "compare"},
            {"toolpack": "unknown.pack", "action": "validate"},
            {"probe": "cryengine"},
        ):
            status, response = self.raw("POST", "/v1/jobs", payload)
            self.assertEqual(status, 400, (payload, response))
            self.assertIn("error", response)
        self.assertEqual(self.raw("GET", "/v1/jobs")[1]["jobs"], [])

    def test_argv_cwd_shell_and_extra_keys_are_rejected(self):
        injections = [
            {"toolpack": "hero.wayfarer", "action": "validate", "argv": ["cmd", "/c", "dir"]},
            {"toolpack": "hero.wayfarer", "action": "validate", "cwd": "C:\\Windows"},
            {"toolpack": "hero.wayfarer", "action": "validate", "shell": True},
            {"toolpack": "hero.wayfarer", "action": "validate", "env": {"X": "1"}},
            {"probe": "godot", "argv": ["powershell"]},
        ]
        for payload in injections:
            status, response = self.raw("POST", "/v1/jobs", payload)
            self.assertEqual(status, 400, (payload, response))
            self.assertIn("not allowed", response["error"])
        self.assertEqual(self.raw("GET", "/v1/jobs")[1]["jobs"], [])

    def test_invalid_shapes_and_timeouts_are_rejected(self):
        for payload in (
            {},
            {"toolpack": "hero.wayfarer"},
            {"toolpack": "hero.wayfarer", "action": "validate", "probe": "godot"},
            {"toolpack": "hero.wayfarer", "action": "validate", "timeoutSeconds": 0},
            {"toolpack": "hero.wayfarer", "action": "validate", "timeoutSeconds": 601},
            {"toolpack": "hero.wayfarer", "action": "validate", "timeoutSeconds": "10"},
            {"toolpack": "hero.wayfarer", "action": "validate", "idempotencyKey": ""},
            ["not-an-object"],
        ):
            status, response = self.raw("POST", "/v1/jobs", payload)
            self.assertEqual(status, 400, (payload, response))

    def test_idempotency_key_returns_the_same_job(self):
        first = self.submit_toolpack(idempotency_key="same-key")
        status, second = self.raw(
            "POST",
            "/v1/jobs",
            {
                "toolpack": "hero.wayfarer",
                "action": "validate",
                "idempotencyKey": "same-key",
            },
        )
        self.assertEqual(status, 200)
        self.assertTrue(second["idempotent"])
        self.assertEqual(second["job"]["id"], first["id"])
        third = self.submit_toolpack(idempotency_key="other-key")
        self.assertNotEqual(third["id"], first["id"])


class JobLifecycleTests(CoordinatorCase):
    def test_claim_complete_and_idempotent_completion(self):
        job = self.submit_toolpack()
        claimed = self.client.claim(worker="tester")
        self.assertEqual(claimed["id"], job["id"])
        self.assertEqual(claimed["state"], "claimed")
        artifact = {
            "path": "artifacts/hero/validation.json",
            "sha256": "a" * 64,
            "bytes": 3,
        }
        completed = self.client.complete(
            job["id"],
            passed=True,
            result={"toolpack": "hero.wayfarer", "action": "validate"},
            artifacts=[artifact],
        )
        self.assertEqual(completed["job"]["state"], "completed")
        self.assertTrue(completed["job"]["result"]["passed"])
        self.assertEqual(completed["job"]["result"]["artifacts"], [artifact])
        again = self.client.complete(job["id"], passed=True, result={"ignored": True})
        self.assertTrue(again["idempotent"])
        self.assertEqual(again["job"]["state"], "completed")
        self.assertEqual(again["job"]["result"]["passed"], True)
        self.assertEqual(self.client.list_jobs()["counts"], {"completed": 1})

    def test_completion_before_claim_is_rejected(self):
        job = self.submit_toolpack()
        with self.assertRaises(rw.RemoteWorkerError) as raised:
            self.client.complete(job["id"], passed=True)
        self.assertEqual(raised.exception.status, 409)
        self.assertEqual(raised.exception.code, "not_claimed")

    def test_duplicate_claim_never_returns_the_same_job(self):
        first_job = self.submit_toolpack()
        self.assertEqual(self.client.claim()["id"], first_job["id"])
        self.assertIsNone(self.client.claim())
        second_job = self.submit_toolpack()
        self.assertEqual(self.client.claim()["id"], second_job["id"])

    def test_cancel_queued_job_blocks_claim_and_completion(self):
        job = self.submit_toolpack()
        cancelled = self.client.cancel(job["id"])
        self.assertEqual(cancelled["job"]["state"], "cancelled")
        self.assertIsNone(self.client.claim())
        with self.assertRaises(rw.RemoteWorkerError) as raised:
            self.client.complete(job["id"], passed=True)
        self.assertEqual(raised.exception.status, 409)
        self.assertEqual(raised.exception.code, "cancelled")
        again = self.client.cancel(job["id"])
        self.assertTrue(again["idempotent"])

    def test_cancel_claimed_job_blocks_completion(self):
        job = self.submit_toolpack()
        self.client.claim()
        self.client.cancel(job["id"])
        with self.assertRaises(rw.RemoteWorkerError) as raised:
            self.client.complete(job["id"], passed=True)
        self.assertEqual(raised.exception.code, "cancelled")

    def test_queued_job_expires(self):
        job = self.submit_toolpack(timeout_seconds=1)
        self.wait_expiry()
        self.assertIsNone(self.client.claim())
        self.assertEqual(self.client.get_job(job["id"])["state"], "expired")

    def test_claimed_job_expiry_rejects_completion(self):
        job = self.submit_toolpack(timeout_seconds=1)
        self.client.claim()
        self.wait_expiry()
        with self.assertRaises(rw.RemoteWorkerError) as raised:
            self.client.complete(job["id"], passed=True)
        self.assertEqual(raised.exception.status, 409)
        self.assertEqual(raised.exception.code, "expired")

    def test_clear_error_states_and_methods(self):
        unknown = "f" * 32
        status, response = self.raw("GET", "/v1/jobs/" + unknown)
        self.assertEqual(status, 404)
        self.assertEqual(self.raw("GET", "/v1/jobs/not-an-id")[0], 400)
        status, response = self.raw("PUT", "/v1/jobs", {})
        self.assertEqual(status, 405)
        status, response = self.raw(
            "POST",
            "/v1/jobs",
            body=b"{not json",
        )
        self.assertEqual(status, 400)
        job = self.submit_toolpack()
        self.client.claim()
        for payload in (
            {"passed": "yes"},
            {"passed": True, "artifacts": [{"path": "../escape", "sha256": "a" * 64, "bytes": 1}]},
            {"passed": True, "artifacts": [{"path": "ok.bin", "sha256": "xyz", "bytes": 1}]},
            {"passed": True, "unknown": 1},
        ):
            status, response = self.raw(
                "POST", "/v1/jobs/" + job["id"] + "/complete", payload
            )
            self.assertEqual(status, 400, (payload, response))
            self.assertIn("error", response)


class WorkerTests(CoordinatorCase):
    def test_worker_revalidates_the_allowlist(self):
        worker = rw.RemoteWorker(self.root, self.client, runner=lambda *args: {})
        for job in (
            {"kind": "toolpack", "request": {"toolpack": "hero.wayfarer", "action": "generate"}},
            {"kind": "toolpack", "request": {"toolpack": "hero.wayfarer", "action": "validate", "argv": []}},
            {"kind": "probe", "request": {"probe": "cryengine"}},
        ):
            with self.assertRaises(rw.RemoteWorkerError):
                worker._validate_job(job)

    def test_worker_runs_the_allowlisted_action_in_an_isolated_worktree(self):
        status_before = _git_status()
        worktrees_before = _worktree_count()
        job = self.submit_toolpack()
        worker = rw.RemoteWorker(REPO_ROOT, self.client, worker_name="test-worker")
        outcome = worker.run_once()
        self.assertTrue(outcome["claimed"])
        self.assertTrue(outcome.get("completed"), outcome)
        completed = self.client.get_job(job["id"])
        self.assertEqual(completed["state"], "completed")
        payload = completed["result"]
        self.assertTrue(payload["passed"])
        self.assertEqual(payload["result"]["toolpack"], "hero.wayfarer")
        self.assertEqual(payload["result"]["action"], "validate")
        self.assertTrue(payload["artifacts"])
        artifact = payload["artifacts"][0]
        self.assertEqual(artifact["path"], "artifacts/hero/validation.json")
        self.assertRegex(artifact["sha256"], r"^[0-9a-f]{64}$")
        self.assertGreater(artifact["bytes"], 0)
        validators = payload["result"]["validators"]
        self.assertTrue(validators)
        self.assertTrue(all(validator["passed"] for validator in validators))
        self.assertEqual(_git_status(), status_before)
        self.assertEqual(_worktree_count(), worktrees_before)

    def test_worker_runs_a_read_only_engine_probe(self):
        status, response = self.raw("POST", "/v1/jobs", {"probe": "godot"})
        self.assertEqual(status, 201, response)
        job = response["job"]
        worker = rw.RemoteWorker(REPO_ROOT, self.client)
        outcome = worker.run_once()
        self.assertTrue(outcome.get("completed"), outcome)
        completed = self.client.get_job(job["id"])
        self.assertEqual(completed["state"], "completed")
        self.assertEqual(completed["result"]["result"]["probe"], "godot")
        self.assertIsInstance(completed["result"]["result"]["engine"], dict)

    def test_worker_timeout_produces_a_failed_job(self):
        def slow_runner(request, worktree, state_dir):
            time.sleep(1.0)
            return {"passed": True, "result": {"late": True}, "artifacts": []}

        job = self.submit_toolpack(timeout_seconds=5)
        worker = rw.RemoteWorker(
            REPO_ROOT, self.client, runner=slow_runner, max_runtime=0.2
        )
        outcome = worker.run_once()
        self.assertTrue(outcome.get("completed"), outcome)
        completed = self.client.get_job(job["id"])
        self.assertEqual(completed["state"], "failed")
        self.assertIn("timeout", (completed["result"]["error"] or "").lower())
        self.assertFalse(completed["result"]["passed"])

    def test_worker_respects_cancellation_and_does_not_complete(self):
        job = self.submit_toolpack()

        def cancelling_runner(request, worktree, state_dir):
            self.client.cancel(job["id"])
            return {"passed": True, "result": {"should": "not-complete"}, "artifacts": []}

        worker = rw.RemoteWorker(REPO_ROOT, self.client, runner=cancelling_runner)
        outcome = worker.run_once()
        self.assertTrue(outcome.get("cancelled"), outcome)
        completed = self.client.get_job(job["id"])
        self.assertEqual(completed["state"], "cancelled")
        self.assertIsNone(completed["result"])

    def test_worker_git_failure_is_a_failed_job_not_a_main_checkout_run(self):
        empty_repo = self.root / "not-a-repo"
        empty_repo.mkdir()
        job = self.submit_toolpack()
        status_before = _git_status()
        worker = rw.RemoteWorker(empty_repo, self.client)
        outcome = worker.run_once()
        self.assertTrue(outcome.get("completed"), outcome)
        completed = self.client.get_job(job["id"])
        self.assertEqual(completed["state"], "failed")
        self.assertIn("worktree", (completed["result"]["error"] or "").lower())
        self.assertEqual(_git_status(), status_before)

    def test_worker_claims_nothing_when_a_job_was_already_claimed(self):
        self.submit_toolpack()
        self.client.claim()
        worker = rw.RemoteWorker(REPO_ROOT, self.client)
        outcome = worker.run_once()
        self.assertFalse(outcome["claimed"])


if __name__ == "__main__":
    unittest.main()
