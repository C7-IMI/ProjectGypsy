#!/usr/bin/env python3
"""Tests for the toolkit registry (workstream/toolkit.py) and ActionForge plugin.

No test reaches the internet. Downloads are injected as local bytes, and the CLI tests that
exercise the default urllib path patch urllib.request.urlopen with a local fake. Offline
commands are tested with urlopen patched to raise AssertionError if anything calls it.
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import struct
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

WORKSTREAM = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKSTREAM))

import gypsy  # noqa: E402
import toolkit  # noqa: E402

REGISTRY = toolkit.discover()
ACTIONFORGE = REGISTRY["actionforge"].module
RIG_URL = ACTIONFORGE.RIG_URL

KNOWN_CLIPS = {
    "idle_loop",
    "walk_loop",
    "jog_fwd_loop",
    "sprint_loop",
    "slide_loop",
    "jump_loop",
    "jump_start",
    "jump_land",
    "sword_attack",
    "sword_regular_a",
    "sword_regular_b",
    "sword_regular_combo",
    "hit_chest",
    "hit_head",
    "hit_knockback",
    "death01",
    "punch_jab",
    "melee_hook",
    "overhandthrow",
    "sword_idle",
}


def anim_url(clip_id):
    return ACTIONFORGE.ANIMATION_BASE + clip_id + ".glb"


def make_glb(payload=b"payload"):
    total = 12 + len(payload)
    return b"glTF" + struct.pack("<I", 2) + struct.pack("<I", total) + payload


class FakeResponse:
    def __init__(self, data, status=200):
        self._data = bytes(data)
        self._position = 0
        self.status = status

    def read(self, size=-1):
        if size is None or size < 0:
            chunk = self._data[self._position :]
            self._position = len(self._data)
            return chunk
        chunk = self._data[self._position : self._position + size]
        self._position += len(chunk)
        return chunk

    def getcode(self):
        return self.status

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()


def fake_urlopen(mapping, calls=None):
    def opener(request, timeout=None):
        url = getattr(request, "full_url", request)
        if calls is not None:
            calls.append(url)
        value = mapping.get(url)
        if value is None:
            raise urllib.error.URLError("test URL not mapped: " + str(url))
        if isinstance(value, BaseException):
            raise value
        return FakeResponse(value)

    return opener


def mapped_downloader(mapping, calls=None):
    def download(url, timeout=30.0):
        if calls is not None:
            calls.append(url)
        value = mapping.get(url)
        if value is None:
            raise urllib.error.URLError("test URL not mapped: " + str(url))
        if isinstance(value, BaseException):
            raise value
        return value

    return download


def run_cli(argv):
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = gypsy.main(argv)
    return code, stdout.getvalue(), stderr.getvalue()


def plugin_source(toolkit_id="sample", status="partial", commands="{}"):
    return (
        "TOOLKIT_ID = " + repr(toolkit_id) + "\n"
        "NAME = 'Sample'\n"
        "SUMMARY = 'sample toolkit'\n"
        "LICENSE = 'MIT'\n"
        "STATUS = " + repr(status) + "\n"
        "KIND = 'test'\n"
        "CAPABILITY = 'sample'\n"
        "HOME = 'https://example.invalid/'\n"
        "COMMANDS = " + commands + "\n"
        "def describe():\n"
        "    return {'id': TOOLKIT_ID}\n"
        "def probe(opener=None, timeout=10.0):\n"
        "    return {'reachable': False, 'error': 'not used'}\n"
    )


class TemporaryProject(unittest.TestCase):
    def project(self):
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        return Path(holder.name)

    def asset_map(self, clips=("idle_loop",), rig=True, payloads=None):
        mapping = {}
        if rig:
            mapping[RIG_URL] = make_glb(b"rig-bytes")
        for clip_id in clips:
            mapping[anim_url(clip_id)] = make_glb(("clip-" + clip_id).encode("utf-8"))
        if payloads:
            mapping.update(payloads)
        return mapping


class RegistryTests(unittest.TestCase):
    def test_actionforge_is_registered(self):
        self.assertIn("actionforge", REGISTRY)
        info = REGISTRY["actionforge"].info()
        self.assertEqual(info["id"], "actionforge")
        self.assertEqual(info["status"], "partial")
        self.assertEqual(info["kind"], "asset-library")
        self.assertIn("CC0", info["license"])
        self.assertEqual(info["commands"], ["catalog", "fetch"])
        self.assertTrue(info["plugin"].endswith("workstream/toolkits/actionforge.py"))

    def test_registry_and_capability_link_validate(self):
        self.assertEqual(toolkit.registry_errors(), [])
        rows = toolkit.capability_rows()
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["toolkit"], "actionforge")
        self.assertEqual(row["capability"], "toolkit.actionforge")
        self.assertTrue(row["exists"])
        self.assertEqual(row["schema"], "gypsy.capability/v1")
        self.assertEqual(row["id"], "toolkit.actionforge")
        self.assertEqual(row["maturity"], "partial")
        self.assertIsNone(row["error"])

    def test_broken_plugin_is_rejected_with_a_named_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "broken.py").write_text("TOOLKIT_ID = 'broken'\n", encoding="utf-8")
            with self.assertRaises(toolkit.ToolkitError) as raised:
                toolkit.discover(tmp)
            self.assertIn("NAME", str(raised.exception))

    def test_invalid_status_and_reserved_id_are_rejected(self):
        for source, needle in (
            (plugin_source(status="bogus"), "STATUS"),
            (plugin_source(toolkit_id="list"), "reserved"),
        ):
            with tempfile.TemporaryDirectory() as tmp:
                Path(tmp, "plugin.py").write_text(source, encoding="utf-8")
                with self.assertRaises(toolkit.ToolkitError) as raised:
                    toolkit.discover(tmp)
                self.assertIn(needle, str(raised.exception))

    def test_duplicate_toolkit_id_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "a.py").write_text(plugin_source(), encoding="utf-8")
            Path(tmp, "b.py").write_text(plugin_source(), encoding="utf-8")
            with self.assertRaises(toolkit.ToolkitError) as raised:
                toolkit.discover(tmp)
            self.assertIn("duplicate toolkit id", str(raised.exception))

    def test_missing_capability_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "a.py").write_text(plugin_source(), encoding="utf-8")
            errors = toolkit.registry_errors(tmp, cap_dir=tmp)
            self.assertTrue(any("capability manifest" in error for error in errors), errors)

    def test_offline_registry_operations_do_not_open_network(self):
        with mock.patch("urllib.request.urlopen", side_effect=AssertionError("network used")):
            registered = toolkit.discover()
            toolkit.describe_toolkit(registered["actionforge"])
            toolkit.capability_rows(registered)
            toolkit.registry_errors()


class CatalogTests(unittest.TestCase):
    def test_known_clip_ids_are_all_curated(self):
        catalog = ACTIONFORGE.catalog()
        self.assertEqual(len(catalog), len(KNOWN_CLIPS))
        self.assertEqual({item["id"] for item in catalog}, KNOWN_CLIPS)
        for item in catalog:
            self.assertTrue(item["curated"])
            self.assertEqual(item["url"], anim_url(item["id"]))
        self.assertEqual(
            RIG_URL, "https://actionforge.app/assets/animation-library/rig/rig-human.glb"
        )

    def test_arbitrary_known_clip_id_is_accepted_but_not_curated(self):
        info = ACTIONFORGE.clip_info("custom_new_clip")
        self.assertFalse(info["curated"])
        self.assertEqual(info["url"], anim_url("custom_new_clip"))
        self.assertEqual(
            ACTIONFORGE.parse_clips("idle_loop, custom_new_clip,idle_loop"),
            ["idle_loop", "custom_new_clip"],
        )
        self.assertEqual(ACTIONFORGE.parse_clips(""), [])
        self.assertEqual(ACTIONFORGE.parse_clips(None), [])

    def test_unsafe_clip_ids_are_rejected(self):
        for bad in ("../escape", "Bad Id", "a/b", "1abc", "", "a" * 65, "sword-attack"):
            with self.assertRaises(toolkit.ToolkitError, msg=bad):
                ACTIONFORGE.clip_info(bad)

    def test_invalid_glb_payloads_are_rejected(self):
        cases = (
            b"",
            b"not a glb at all",
            b"glTF" + struct.pack("<I", 1) + struct.pack("<I", 12),
            b"glTF" + struct.pack("<I", 2) + struct.pack("<I", 99),
        )
        for payload in cases:
            with self.assertRaises(toolkit.ToolkitError):
                ACTIONFORGE.validate_glb(payload)
        ACTIONFORGE.validate_glb(make_glb())


class PathSafetyTests(TemporaryProject):
    def test_resolve_within_accepts_inside_and_rejects_escape(self):
        root = self.project()
        self.assertEqual(
            toolkit.resolve_within(root, "assets/actionforge"),
            (root / "assets" / "actionforge").resolve(),
        )
        for bad in ("../outside", "a/../../outside", str(root / "absolute")):
            with self.assertRaises(toolkit.ToolkitError, msg=bad):
                toolkit.resolve_within(root, bad)
        with self.assertRaises(toolkit.ToolkitError):
            toolkit.resolve_within(root, "   ")

    def test_fetch_refuses_escape_before_downloading(self):
        root = self.project()
        calls = []
        with self.assertRaises(toolkit.ToolkitError):
            ACTIONFORGE.fetch(
                root,
                clips=["idle_loop"],
                dest="../escape",
                downloader=mapped_downloader({}, calls),
            )
        self.assertEqual(calls, [])
        self.assertFalse((root.parent / "escape").exists())

    def test_fetch_requires_an_existing_project_directory(self):
        root = self.project()
        with self.assertRaises(toolkit.ToolkitError):
            ACTIONFORGE.fetch(
                root / "missing",
                clips=["idle_loop"],
                downloader=mapped_downloader({}),
            )

    def test_fetch_rejects_absolute_destination(self):
        root = self.project()
        with self.assertRaises(toolkit.ToolkitError):
            ACTIONFORGE.fetch(
                root,
                clips=["idle_loop"],
                dest=str(root / "absolute"),
                downloader=mapped_downloader({}),
            )


class FetchTests(TemporaryProject):
    def test_fetch_writes_glbs_provenance_and_notice(self):
        root = self.project()
        mapping = self.asset_map(clips=("idle_loop", "walk_loop"), rig=True)
        result = ACTIONFORGE.fetch(
            root,
            clips=["idle_loop", "walk_loop"],
            rig=True,
            downloader=mapped_downloader(mapping),
        )
        self.assertTrue(result["passed"], result["errors"])
        self.assertEqual(
            [item["status"] for item in result["files"]],
            ["written", "written", "written"],
        )
        dest = root / "assets" / "actionforge"
        expected = {
            "rig/rig-human.glb": mapping[RIG_URL],
            "animations/idle_loop.glb": mapping[anim_url("idle_loop")],
            "animations/walk_loop.glb": mapping[anim_url("walk_loop")],
        }
        for relative, payload in expected.items():
            self.assertEqual((dest / relative).read_bytes(), payload)
        provenance_path = dest / "provenance.json"
        self.assertTrue(provenance_path.is_file())
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
        self.assertEqual(provenance["schema"], ACTIONFORGE.PROVENANCE_SCHEMA)
        self.assertEqual(provenance["license"]["animations"], "CC0")
        self.assertFalse(provenance["license"]["attributionRequired"])
        entries = {entry["path"]: entry for entry in provenance["files"]}
        self.assertEqual(
            set(entries),
            {
                "assets/actionforge/rig/rig-human.glb",
                "assets/actionforge/animations/idle_loop.glb",
                "assets/actionforge/animations/walk_loop.glb",
            },
        )
        self.assertEqual(
            entries["assets/actionforge/animations/idle_loop.glb"]["sha256"],
            hashlib.sha256(mapping[anim_url("idle_loop")]).hexdigest(),
        )
        self.assertEqual(entries["assets/actionforge/animations/idle_loop.glb"]["clip"], "idle_loop")
        self.assertTrue(entries["assets/actionforge/animations/idle_loop.glb"]["catalogued"])
        self.assertNotIn("clip", entries["assets/actionforge/rig/rig-human.glb"])
        notice = (dest / "NOTICE.md").read_text(encoding="utf-8")
        self.assertIn("CC0", notice)
        self.assertIn("CGstuff", notice)
        self.assertIn("idle_loop", notice)
        self.assertEqual(result["provenance"], "assets/actionforge/provenance.json")
        self.assertEqual(result["notice"], "assets/actionforge/NOTICE.md")

    def test_fetch_is_idempotent(self):
        root = self.project()
        mapping = self.asset_map(clips=("idle_loop",), rig=True)
        ACTIONFORGE.fetch(
            root, clips=["idle_loop"], rig=True, downloader=mapped_downloader(mapping)
        )
        dest = root / "assets" / "actionforge"
        provenance_before = (dest / "provenance.json").read_bytes()
        notice_before = (dest / "NOTICE.md").read_bytes()
        second = ACTIONFORGE.fetch(
            root, clips=["idle_loop"], rig=True, downloader=mapped_downloader(mapping)
        )
        self.assertTrue(second["passed"], second["errors"])
        self.assertEqual(
            [item["status"] for item in second["files"]],
            ["unchanged", "unchanged"],
        )
        self.assertFalse(second["provenanceChanged"])
        self.assertFalse(second["noticeChanged"])
        self.assertEqual(provenance_before, (dest / "provenance.json").read_bytes())
        self.assertEqual(notice_before, (dest / "NOTICE.md").read_bytes())

    def test_differing_file_is_not_overwritten_without_force(self):
        root = self.project()
        first = self.asset_map(clips=("idle_loop",))
        ACTIONFORGE.fetch(root, clips=["idle_loop"], downloader=mapped_downloader(first))
        target = root / "assets" / "actionforge" / "animations" / "idle_loop.glb"
        original = target.read_bytes()
        original_sha = hashlib.sha256(original).hexdigest()
        second = self.asset_map(
            payloads={anim_url("idle_loop"): make_glb(b"different-content")}
        )
        conflict = ACTIONFORGE.fetch(
            root, clips=["idle_loop"], downloader=mapped_downloader(second)
        )
        self.assertFalse(conflict["passed"])
        self.assertEqual(conflict["files"][0]["status"], "conflict")
        self.assertTrue(any("--force" in error for error in conflict["errors"]))
        self.assertEqual(target.read_bytes(), original)
        provenance = json.loads(
            (root / "assets" / "actionforge" / "provenance.json").read_text(encoding="utf-8")
        )
        self.assertEqual(provenance["files"][0]["sha256"], original_sha)
        forced = ACTIONFORGE.fetch(
            root, clips=["idle_loop"], downloader=mapped_downloader(second), force=True
        )
        self.assertTrue(forced["passed"], forced["errors"])
        self.assertEqual(forced["files"][0]["status"], "overwritten")
        self.assertNotEqual(target.read_bytes(), original)
        provenance = json.loads(
            (root / "assets" / "actionforge" / "provenance.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            provenance["files"][0]["sha256"],
            hashlib.sha256(target.read_bytes()).hexdigest(),
        )

    def test_invalid_glb_and_download_failure_fail_honestly(self):
        root = self.project()
        invalid = ACTIONFORGE.fetch(
            root,
            rig=True,
            downloader=mapped_downloader({RIG_URL: b"not a gltf file"}),
        )
        self.assertFalse(invalid["passed"])
        self.assertIn("binary glTF", " ".join(invalid["errors"]))
        self.assertFalse((root / "assets" / "actionforge" / "rig" / "rig-human.glb").exists())
        self.assertIsNone(invalid["provenance"])
        missing_root = self.project()
        offline = ACTIONFORGE.fetch(
            missing_root,
            rig=True,
            downloader=mapped_downloader(
                {RIG_URL: urllib.error.URLError("offline in test")}
            ),
        )
        self.assertFalse(offline["passed"])
        self.assertIn("URLError", " ".join(offline["errors"]))
        self.assertIsNone(offline["provenance"])

    def test_arbitrary_clip_id_is_recorded_as_not_curated(self):
        root = self.project()
        mapping = self.asset_map(clips=("custom_new_clip",), rig=False)
        result = ACTIONFORGE.fetch(
            root, clips="custom_new_clip", downloader=mapped_downloader(mapping)
        )
        self.assertTrue(result["passed"], result["errors"])
        self.assertEqual(result["files"][0]["status"], "written")
        self.assertTrue(any("not in the curated catalog" in item for item in result["warnings"]))
        provenance = json.loads(
            (root / "assets" / "actionforge" / "provenance.json").read_text(encoding="utf-8")
        )
        self.assertFalse(provenance["files"][0]["catalogued"])

    def test_partial_failure_keeps_successful_files(self):
        root = self.project()
        mapping = self.asset_map(clips=("idle_loop",), rig=True)
        mapping.pop(anim_url("idle_loop"))
        result = ACTIONFORGE.fetch(
            root, clips=["idle_loop"], rig=True, downloader=mapped_downloader(mapping)
        )
        self.assertFalse(result["passed"])
        self.assertEqual(result["files"][0]["status"], "written")
        self.assertEqual(result["files"][1]["status"], "error")
        self.assertTrue((root / "assets" / "actionforge" / "rig" / "rig-human.glb").exists())
        provenance = json.loads(
            (root / "assets" / "actionforge" / "provenance.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            [entry["path"] for entry in provenance["files"]],
            ["assets/actionforge/rig/rig-human.glb"],
        )

    def test_second_fetch_preserves_previous_provenance(self):
        root = self.project()
        first = ACTIONFORGE.fetch(
            root,
            clips=["idle_loop"],
            downloader=mapped_downloader(self.asset_map(clips=("idle_loop",), rig=False)),
        )
        self.assertTrue(first["passed"], first["errors"])
        first_provenance = json.loads(
            (root / "assets" / "actionforge" / "provenance.json").read_text(encoding="utf-8")
        )
        first_time = first_provenance["files"][0]["retrievedAt"]
        second = ACTIONFORGE.fetch(
            root,
            clips=["walk_loop"],
            downloader=mapped_downloader(self.asset_map(clips=("walk_loop",), rig=False)),
        )
        self.assertTrue(second["passed"], second["errors"])
        provenance = json.loads(
            (root / "assets" / "actionforge" / "provenance.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            [entry["path"] for entry in provenance["files"]],
            [
                "assets/actionforge/animations/idle_loop.glb",
                "assets/actionforge/animations/walk_loop.glb",
            ],
        )
        self.assertEqual(provenance["files"][0]["retrievedAt"], first_time)


class ProbeTests(unittest.TestCase):
    def test_probe_reports_success(self):
        result = ACTIONFORGE.probe(
            opener=fake_urlopen({RIG_URL: make_glb()}), timeout=1.0
        )
        self.assertTrue(result["reachable"])
        self.assertEqual(result["status"], 200)
        self.assertIsNone(result["error"])
        self.assertIn("checkedAt", result)

    def test_probe_reports_offline_error(self):
        def opener(request, timeout=None):
            raise urllib.error.URLError("offline in test")

        result = ACTIONFORGE.probe(opener=opener, timeout=1.0)
        self.assertFalse(result["reachable"])
        self.assertIn("URLError", result["error"])
        self.assertIn("offline in test", result["error"])

    def test_probe_falls_back_to_get_when_head_is_not_allowed(self):
        def opener(request, timeout=None):
            if request.get_method() == "HEAD":
                raise urllib.error.HTTPError(RIG_URL, 405, "HEAD not allowed", {}, None)
            return FakeResponse(make_glb())

        result = ACTIONFORGE.probe(opener=opener, timeout=1.0)
        self.assertTrue(result["reachable"], result)
        self.assertEqual(result["method"], "GET")


class CliTests(TemporaryProject):
    def test_offline_commands_do_not_open_network(self):
        with mock.patch("urllib.request.urlopen", side_effect=AssertionError("network used")):
            calls = [
                (["toolkit", "list", "--json"], 0),
                (["toolkit", "show", "actionforge", "--json"], 0),
                (["toolkit", "capabilities", "--json"], 0),
                (["toolkit", "actionforge", "catalog", "--json"], 0),
            ]
            for argv, expected in calls:
                code, out, err = run_cli(argv)
                self.assertEqual(code, expected, (argv, out, err))

    def test_list_show_and_capabilities_json(self):
        code, out, err = run_cli(["toolkit", "list", "--json"])
        self.assertEqual(code, 0, err)
        rows = json.loads(out)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], "actionforge")
        self.assertEqual(rows[0]["status"], "partial")
        self.assertIn("CC0", rows[0]["license"])
        code, out, err = run_cli(["toolkit", "show", "actionforge", "--json"])
        self.assertEqual(code, 0, err)
        data = json.loads(out)
        self.assertEqual(data["id"], "actionforge")
        self.assertEqual(len(data["catalog"]), len(KNOWN_CLIPS))
        self.assertIn("fetch", data["commands"])
        self.assertIn("provenance.json", data["layout"]["provenance"])
        code, out, err = run_cli(["toolkit", "capabilities", "--json"])
        self.assertEqual(code, 0, err)
        rows = json.loads(out)
        self.assertEqual(rows[0]["capability"], "toolkit.actionforge")
        self.assertTrue(rows[0]["exists"])
        self.assertNotIn("data", rows[0])

    def test_catalog_json(self):
        code, out, err = run_cli(["toolkit", "actionforge", "catalog", "--json"])
        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        self.assertEqual(payload["count"], len(KNOWN_CLIPS))
        self.assertEqual({item["id"] for item in payload["clips"]}, KNOWN_CLIPS)
        self.assertEqual(payload["rig"], RIG_URL)

    def test_probe_offline_reports_failure_and_exits_nonzero(self):
        with mock.patch(
            "urllib.request.urlopen", side_effect=urllib.error.URLError("offline in test")
        ):
            code, out, err = run_cli(["toolkit", "probe", "actionforge", "--json"])
        self.assertEqual(code, 1)
        data = json.loads(out)
        self.assertFalse(data["reachable"])
        self.assertIn("URLError", data["error"])
        self.assertIn("offline in test", data["error"])

    def test_fetch_with_patched_network_and_cli_dispatch(self):
        root = self.project()
        mapping = self.asset_map(clips=("idle_loop", "walk_loop"), rig=True)
        calls = []
        with mock.patch(
            "urllib.request.urlopen", side_effect=fake_urlopen(mapping, calls)
        ):
            code, out, err = run_cli(
                [
                    "toolkit",
                    "actionforge",
                    "fetch",
                    "--project",
                    str(root),
                    "--clips",
                    "idle_loop,walk_loop",
                    "--rig",
                    "--json",
                ]
            )
        self.assertEqual(code, 0, out + err)
        payload = json.loads(out)
        self.assertTrue(payload["passed"], payload["errors"])
        self.assertEqual(
            [item["status"] for item in payload["files"]],
            ["written", "written", "written"],
        )
        self.assertEqual(
            set(calls), {RIG_URL, anim_url("idle_loop"), anim_url("walk_loop")}
        )
        self.assertTrue(
            (root / "assets" / "actionforge" / "animations" / "idle_loop.glb").is_file()
        )
        self.assertTrue((root / "assets" / "actionforge" / "provenance.json").is_file())

    def test_fetch_escape_fails_without_network(self):
        root = self.project()
        with mock.patch("urllib.request.urlopen", side_effect=AssertionError("network used")):
            code, out, err = run_cli(
                [
                    "toolkit",
                    "actionforge",
                    "fetch",
                    "--project",
                    str(root),
                    "--clips",
                    "idle_loop",
                    "--dest",
                    "../escape",
                ]
            )
        self.assertEqual(code, 1)
        self.assertIn("ERROR:", err)
        self.assertIn("escape", err)

    def test_unknown_toolkit_is_reported(self):
        code, out, err = run_cli(["toolkit", "show", "nope", "--json"])
        self.assertEqual(code, 1)
        self.assertIn("unknown toolkit", err)

    def test_invalid_registry_does_not_break_version_but_toolkit_reports(self):
        with mock.patch.object(
            toolkit, "discover", side_effect=toolkit.ToolkitError("broken plugin")
        ):
            code, out, err = run_cli(["version"])
            self.assertEqual(code, 0, err)
            self.assertIn("Gypsy Studio", out)
            code, out, err = run_cli(["toolkit", "list"])
            self.assertEqual(code, 1)
            self.assertIn("toolkit registry is invalid", err)
            self.assertIn("broken plugin", err)


if __name__ == "__main__":
    unittest.main()
