#!/usr/bin/env python3
"""Tests for the loopback authenticated remote action cache (remote_cache.py).

Every server is a real ThreadingHTTPServer on an ephemeral 127.0.0.1 port; every client is
a real urllib client over loopback. No test leaves the machine and no test uses a shell.
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

WORKSTREAM = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKSTREAM))

import cache  # noqa: E402
import gypsy  # noqa: E402
import remote_cache as rc  # noqa: E402

TOKEN = "task19-test-token"
WRONG_TOKEN = "wrong-token-123456"
ENTRY_MAX = 4096
BLOB_MAX = 8192


def sha(data):
    return hashlib.sha256(data).hexdigest()


def key_for(label="entry"):
    return sha(label.encode("utf-8"))


def write(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, bytes):
        path.write_bytes(payload)
    else:
        path.write_text(payload, encoding="utf-8")


def run_cli(argv):
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = gypsy.main(argv)
    return code, stdout.getvalue(), stderr.getvalue()


@contextlib.contextmanager
def remote_env(url=None, token=None):
    env = {
        name: value
        for name, value in os.environ.items()
        if name not in (rc.ENV_URL, rc.ENV_TOKEN)
    }
    if url is not None:
        env[rc.ENV_URL] = url
    if token is not None:
        env[rc.ENV_TOKEN] = token
    with mock.patch.dict(os.environ, env, clear=True):
        yield


class RemoteCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.server = rc.RemoteCacheServer(
            self.root / "server",
            token=TOKEN,
            port=0,
            max_entry_bytes=ENTRY_MAX,
            max_blob_bytes=BLOB_MAX,
        ).start()
        self.addCleanup(self.server.stop)
        self.client = rc.RemoteCacheClient(
            self.server.url,
            TOKEN,
            max_entry_bytes=ENTRY_MAX,
            max_blob_bytes=BLOB_MAX,
        )

    def raw(self, method, path, *, data=None, token=TOKEN, content_type=None):
        headers = {}
        if token is not None:
            headers["Authorization"] = "Bearer " + token
        if content_type:
            headers["Content-Type"] = content_type
        request = Request(self.server.url + path, data=data, headers=headers, method=method)
        try:
            with urlopen(request, timeout=10) as response:
                return response.status, response.read()
        except HTTPError as exc:
            try:
                return exc.code, exc.read()
            finally:
                exc.close()
        except (URLError, ConnectionError, OSError) as exc:
            return "connection-error", str(exc).encode("utf-8")

    def put_blob(self, data):
        digest = sha(data)
        self.assertTrue(self.client.put_blob(digest, data))
        return digest, data

    def entry(self, entry_key, digest, length, path="out/a.bin", result=None):
        return {
            "schema": rc.ENTRY_SCHEMA,
            "key": entry_key,
            "descriptor": {"identity": {"kind": "test"}},
            "createdAt": "2026-10-30T00:00:00+00:00",
            "artifacts": [{"path": path, "sha256": digest, "bytes": length}],
            "result": result or {"exit": 0},
        }


class HealthAuthTests(RemoteCase):
    def test_health_is_unauthenticated_but_minimal(self):
        status, body = self.raw("GET", "/healthz", token=None)
        self.assertEqual(status, 200)
        payload = json.loads(body)
        self.assertEqual(payload["schema"], rc.SCHEMA)
        self.assertEqual(payload["status"], "ok")
        self.assertNotIn("entries", payload)
        self.assertNotIn("token", json.dumps(payload).lower())

    def test_protected_endpoints_reject_missing_and_wrong_tokens(self):
        digest = sha(b"blob")
        entry_key = key_for()
        for path in ("/v1/stats", "/v1/entries/" + entry_key, "/v1/blobs/" + digest):
            for token in (None, WRONG_TOKEN):
                status, _ = self.raw("GET", path, token=token)
                self.assertEqual(status, 401, (path, token))
        status, _ = self.raw(
            "PUT",
            "/v1/blobs/" + digest,
            data=b"blob",
            token=None,
            content_type="application/octet-stream",
        )
        self.assertEqual(status, 401)

    def test_client_reports_auth_rejection(self):
        bad = rc.RemoteCacheClient(self.server.url, WRONG_TOKEN)
        with self.assertRaises(rc.RemoteCacheAuthError):
            bad.stats()
        status = bad.status()
        self.assertTrue(status["reachable"])
        self.assertFalse(status["authenticated"])
        self.assertIn("unauthorized", status["error"])


class BlobTests(RemoteCase):
    def test_client_blob_roundtrip_and_server_stats(self):
        digest, data = self.put_blob(b"remote-artifact")
        self.assertEqual(self.client.get_blob(digest), data)
        stats = self.client.stats()
        self.assertEqual(stats["blobs"], 1)
        self.assertGreaterEqual(stats["puts"], 1)
        self.assertGreaterEqual(stats["gets"], 1)

    def test_missing_blob_is_404_and_none(self):
        missing = sha(b"absent")
        status, _ = self.raw("GET", "/v1/blobs/" + missing)
        self.assertEqual(status, 404)
        self.assertIsNone(self.client.get_blob(missing))

    def test_wrong_digest_put_is_rejected(self):
        data = b"payload"
        status, body = self.raw(
            "PUT",
            "/v1/blobs/" + sha(b"different"),
            data=data,
            content_type="application/octet-stream",
        )
        self.assertEqual(status, 400)
        self.assertIn("sha256", json.loads(body)["error"])

    def test_invalid_blob_ids_are_rejected(self):
        for identifier in ("abc", "A" * 64, "..", "%2e%2e"):
            status, _ = self.raw("GET", "/v1/blobs/" + identifier)
            self.assertIn(status, (400, 404), identifier)

    def test_oversize_blob_is_bounded(self):
        data = b"x" * (BLOB_MAX + 1)
        status, _ = self.raw(
            "PUT",
            "/v1/blobs/" + sha(data),
            data=data,
            content_type="application/octet-stream",
        )
        self.assertEqual(status, 413)
        with self.assertRaises(rc.RemoteCacheError):
            self.client.put_blob(sha(data), data)
        status, _ = self.raw("GET", "/healthz", token=None)
        self.assertEqual(status, 200)  # the server is still healthy

    def test_corrupt_stored_blob_is_detected(self):
        digest, data = self.put_blob(b"good-bytes")
        blob_path = self.server.store.blobs_dir / digest
        blob_path.write_bytes(b"corrupt-bytes")
        with self.assertRaises(rc.RemoteCacheError):
            self.client.get_blob(digest)
        status, _ = self.raw("GET", "/v1/blobs/" + digest)
        self.assertEqual(status, 500)


class EntryTests(RemoteCase):
    def test_client_entry_roundtrip(self):
        digest, data = self.put_blob(b"artifact")
        entry_key = key_for()
        entry = self.entry(entry_key, digest, len(data))
        self.assertTrue(self.client.put_entry(entry_key, entry))
        fetched = self.client.get_entry(entry_key)
        self.assertEqual(fetched["key"], entry_key)
        self.assertEqual(fetched["artifacts"][0]["sha256"], digest)

    def test_missing_entry_is_404_and_none(self):
        entry_key = key_for("missing")
        status, _ = self.raw("GET", "/v1/entries/" + entry_key)
        self.assertEqual(status, 404)
        self.assertIsNone(self.client.get_entry(entry_key))

    def test_invalid_entry_bodies_are_rejected(self):
        entry_key = key_for()
        digest = sha(b"x")
        cases = [
            b"not json",
            json.dumps(self.entry(key_for("other"), digest, 1)).encode("utf-8"),
            json.dumps({"schema": "wrong", "key": entry_key, "artifacts": []}).encode("utf-8"),
            json.dumps(
                self.entry(entry_key, digest, 1, path="../escape.bin")
            ).encode("utf-8"),
        ]
        for body in cases:
            status, _ = self.raw(
                "PUT",
                "/v1/entries/" + entry_key,
                data=body,
                content_type="application/json",
            )
            self.assertEqual(status, 400, body[:80])

    def test_invalid_entry_id_is_rejected(self):
        status, _ = self.raw("GET", "/v1/entries/not-a-key")
        self.assertEqual(status, 400)
        status, _ = self.raw("PUT", "/v1/entries/NOT-A-KEY", data=b"{}", content_type="application/json")
        self.assertEqual(status, 400)

    def test_oversize_entry_is_bounded(self):
        entry_key = key_for()
        entry = self.entry(entry_key, sha(b"x"), 1, result={"blob": "y" * ENTRY_MAX})
        body = json.dumps(entry).encode("utf-8")
        status, _ = self.raw(
            "PUT",
            "/v1/entries/" + entry_key,
            data=body,
            content_type="application/json",
        )
        self.assertEqual(status, 413)
        with self.assertRaises(rc.RemoteCacheError):
            self.client.put_entry(entry_key, entry)

    def test_corrupt_stored_entry_is_detected(self):
        entry_key = key_for("corrupt")
        (self.server.store.entries_dir / (entry_key + ".json")).write_text(
            "{not json", encoding="utf-8"
        )
        status, _ = self.raw("GET", "/v1/entries/" + entry_key)
        self.assertEqual(status, 500)
        with self.assertRaises(rc.RemoteCacheError):
            self.client.get_entry(entry_key)


class ServerValidationTests(RemoteCase):
    def test_server_refuses_weak_tokens_and_non_loopback_hosts(self):
        with self.assertRaises(rc.RemoteCacheError):
            rc.RemoteCacheServer(self.root / "s1", token="")
        with self.assertRaises(rc.RemoteCacheError):
            rc.RemoteCacheServer(self.root / "s2", token="short")
        with self.assertRaises(rc.RemoteCacheError):
            rc.RemoteCacheServer(self.root / "s3", token=TOKEN, host="0.0.0.0")

    def test_status_and_stop_are_honest(self):
        status = self.server.status()
        self.assertTrue(status["loopback"])
        self.assertEqual(status["auth"], "bearer")
        self.assertEqual(status["schema"], rc.SCHEMA)
        self.assertTrue(self.server.stop()["stopped"])
        self.assertTrue(self.server.stop()["stopped"])  # idempotent

    def test_traversal_ids_never_escape_the_store(self):
        outside = self.root / "outside.txt"
        write(outside, "outside")
        status, _ = self.raw("GET", "/v1/blobs/%2e%2e/outside.txt")
        self.assertIn(status, (400, 404))
        self.assertEqual(outside.read_text(encoding="utf-8"), "outside")


class ClientStatusTests(RemoteCase):
    def test_status_is_reachable_and_redacts_the_token(self):
        status = self.client.status()
        self.assertTrue(status["reachable"])
        self.assertTrue(status["authenticated"])
        self.assertTrue(status["tokenPresent"])
        text = json.dumps(status)
        self.assertNotIn(TOKEN, text)
        self.assertNotIn("Bearer", text)

    def test_unreachable_server_is_reported_not_raised_by_status(self):
        probe = rc.RemoteCacheServer(self.root / "probe", token=TOKEN, port=0).start()
        url = probe.url
        probe.stop()
        client = rc.RemoteCacheClient(url, TOKEN, timeout=2.0)
        with self.assertRaises(rc.RemoteCacheError):
            client.health()
        status = client.status()
        self.assertFalse(status["reachable"])
        self.assertTrue(status["error"])

    def test_config_from_env_requires_both_values_and_hides_the_token(self):
        self.assertIsNone(rc.config_from_env({}))
        self.assertIsNone(rc.config_from_env({rc.ENV_URL: "http://127.0.0.1:1"}))
        config = rc.config_from_env(
            {rc.ENV_URL: "http://127.0.0.1:1", rc.ENV_TOKEN: TOKEN}
        )
        self.assertEqual(config["token"], TOKEN)
        summary = rc.env_summary({rc.ENV_TOKEN: TOKEN})
        self.assertTrue(summary["tokenPresent"])
        self.assertNotIn(TOKEN, json.dumps(summary))


class ActionCacheRemoteTests(RemoteCase):
    def _seed_pair(self):
        project_a = self.root / "project-a"
        project_b = self.root / "project-b"
        write(project_a / "out" / "artifact.bin", b"shared-artifact")
        write(project_b / "out" / "artifact.bin", b"shared-artifact")
        inputs = {}
        entry_key, descriptor = cache.action_key(
            identity={"kind": "test"},
            argv=["x"],
            cwd="shared-cwd",
            inputs=inputs,
            artifacts=["out/artifact.bin"],
            tool_versions={"demo": "1"},
        )
        cache_a = cache.ActionCache(self.root / "state-a", remote=self.client)
        cache_b = cache.ActionCache(self.root / "state-b", remote=self.client)
        return project_a, project_b, entry_key, descriptor, cache_a, cache_b

    def test_two_isolated_caches_share_an_entry_and_blob(self):
        project_a, project_b, entry_key, descriptor, cache_a, cache_b = self._seed_pair()
        self.assertIsNotNone(
            cache_a.store(
                entry_key,
                descriptor=descriptor,
                project_root=project_a,
                artifacts=["out/artifact.bin"],
            )
        )
        self.assertEqual(cache_a.counters()["remoteStores"], 1)
        self.assertFalse((cache_b.entries_dir / (entry_key + ".json")).exists())
        entry = cache_b.lookup(entry_key)
        self.assertIsNotNone(entry)
        self.assertEqual(cache_b.counters()["remoteHits"], 1)
        self.assertEqual(cache_b.counters()["remoteErrors"], 0)
        self.assertTrue((cache_b.entries_dir / (entry_key + ".json")).is_file())
        ok, restored, error = cache_b.restore(entry, project_b)
        self.assertTrue(ok, error)
        self.assertEqual(
            (project_b / "out" / "artifact.bin").read_bytes(), b"shared-artifact"
        )

    def test_local_hit_does_not_consult_the_remote(self):
        project_a, project_b, entry_key, descriptor, cache_a, cache_b = self._seed_pair()
        local = cache.ActionCache(self.root / "state-c", remote=False)
        self.assertIsNotNone(
            local.store(
                entry_key,
                descriptor=descriptor,
                project_root=project_b,
                artifacts=["out/artifact.bin"],
            )
        )
        gets_before = self.client.stats()["gets"]
        remote = cache.ActionCache(self.root / "state-c", remote=self.client)
        self.assertIsNotNone(remote.lookup(entry_key))
        self.assertEqual(remote.counters()["remoteHits"], 0)
        self.assertEqual(self.client.stats()["gets"], gets_before)

    def test_corrupt_remote_blob_is_a_local_miss(self):
        project_a, project_b, entry_key, descriptor, cache_a, cache_b = self._seed_pair()
        cache_a.store(
            entry_key,
            descriptor=descriptor,
            project_root=project_a,
            artifacts=["out/artifact.bin"],
        )
        digest = sha(b"shared-artifact")
        (self.server.store.blobs_dir / digest).write_bytes(b"corrupt")
        self.assertIsNone(cache_b.lookup(entry_key))
        self.assertGreaterEqual(cache_b.counters()["remoteErrors"], 1)
        self.assertTrue(cache_b.remote_info()["lastError"])

    def test_remote_entry_with_missing_blob_is_a_miss(self):
        entry_key = key_for("missing-blob")
        digest = sha(b"never-uploaded")
        self.client.put_entry(entry_key, self.entry(entry_key, digest, 14))
        target = cache.ActionCache(self.root / "state-miss", remote=self.client)
        self.assertIsNone(target.lookup(entry_key))
        self.assertGreaterEqual(target.counters()["remoteErrors"], 1)

    def test_remote_push_failure_never_fails_the_local_store(self):
        probe = rc.RemoteCacheServer(self.root / "probe", token=TOKEN, port=0).start()
        unreachable_url = probe.url
        probe.stop()
        client = rc.RemoteCacheClient(unreachable_url, TOKEN, timeout=2.0)
        project = self.root / "project-d"
        write(project / "out" / "artifact.bin", b"local-only")
        entry_key, descriptor = cache.action_key(
            identity={"kind": "dead-remote"},
            argv=["x"],
            cwd="cwd",
            inputs={},
            artifacts=["out/artifact.bin"],
        )
        cache_obj = cache.ActionCache(self.root / "state-d", remote=client)
        summary = cache_obj.store(
            entry_key,
            descriptor=descriptor,
            project_root=project,
            artifacts=["out/artifact.bin"],
        )
        self.assertIsNotNone(summary)
        self.assertTrue((cache_obj.entries_dir / (entry_key + ".json")).is_file())
        self.assertEqual(cache_obj.counters()["remoteStores"], 0)
        self.assertGreaterEqual(cache_obj.counters()["remoteErrors"], 1)
        self.assertIsNotNone(cache_obj.lookup(entry_key))

    def test_environment_enables_the_remote_and_invalid_config_is_loud(self):
        project = self.root / "project-e"
        write(project / "out" / "artifact.bin", b"env-remote")
        entry_key, descriptor = cache.action_key(
            identity={"kind": "env"},
            argv=["x"],
            cwd="cwd",
            inputs={},
            artifacts=["out/artifact.bin"],
        )
        state = self.root / "state-e"
        with remote_env(self.server.url, TOKEN):
            cache_obj = cache.ActionCache(state)
            self.assertIsNotNone(cache_obj.remote)
            self.assertTrue(cache_obj.remote_info()["enabled"])
            cache_obj.store(
                entry_key,
                descriptor=descriptor,
                project_root=project,
                artifacts=["out/artifact.bin"],
            )
            self.assertEqual(cache_obj.counters()["remoteStores"], 1)
        with remote_env("not-a-url", TOKEN):
            with self.assertRaises(cache.CacheError):
                cache.ActionCache(self.root / "state-bad")

    def test_local_only_default_has_no_remote(self):
        with remote_env():
            cache_obj = cache.ActionCache(self.root / "state-local")
            self.assertIsNone(cache_obj.remote)
            stats = cache_obj.stats()
            self.assertFalse(stats["remote"]["enabled"])
            self.assertEqual(stats["counters"]["remoteHits"], 0)


class CliTests(RemoteCase):
    def test_cache_remote_disabled_reports_honestly(self):
        with remote_env():
            code, out, err = run_cli(["cache", "remote", "--json"])
        self.assertEqual(code, 0, out + err)
        data = json.loads(out)
        self.assertFalse(data["enabled"])

    def test_cache_remote_status_with_environment(self):
        with remote_env(self.server.url, TOKEN):
            code, out, err = run_cli(["cache", "remote", "--json"])
        self.assertEqual(code, 0, out + err)
        data = json.loads(out)
        self.assertTrue(data["reachable"])
        self.assertTrue(data["authenticated"])
        self.assertNotIn(TOKEN, out)

    def test_cache_remote_rejects_a_wrong_token(self):
        with remote_env(self.server.url, WRONG_TOKEN):
            code, out, err = run_cli(["cache", "remote", "--json"])
        self.assertEqual(code, 1)
        data = json.loads(out)
        self.assertFalse(data["authenticated"])
        self.assertIn("unauthorized", data["error"])
        self.assertNotIn(WRONG_TOKEN, out)

    def test_cache_stats_includes_remote_status(self):
        with remote_env(self.server.url, TOKEN):
            code, out, err = run_cli(
                ["cache", "stats", "--state-dir", str(self.root / "cli-state"), "--json"]
            )
        self.assertEqual(code, 0, out + err)
        data = json.loads(out)
        self.assertTrue(data["remote"]["enabled"])
        self.assertIn("remoteHits", data["counters"])
        self.assertNotIn(TOKEN, out)

    def test_cache_serve_without_a_token_fails_cleanly(self):
        with remote_env():
            code, out, err = run_cli(["cache", "serve", "--port", "0"])
        self.assertEqual(code, 1)
        self.assertIn(rc.ENV_TOKEN, err)


if __name__ == "__main__":
    unittest.main()
