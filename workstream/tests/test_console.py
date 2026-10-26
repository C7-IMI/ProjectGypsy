#!/usr/bin/env python3
"""Tests for the Phase-4 read-only console (workstream/console.py).

Everything runs against temporary state directories, generated PNG/WAV/JSON/GLB/MP4/AVI
fixtures and (when git is installed) a throwaway git repository. No Godot, no network and no
writes outside the temporary directory are required.
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import wave
import zlib
from pathlib import Path
from unittest import mock

WORKSTREAM = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKSTREAM))

import console  # noqa: E402

GIT = shutil.which("git")


# -- fixtures ---------------------------------------------------------------


def write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def png_bytes(width=1280, height=720):
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    ihdr_chunk = (
        struct.pack(">I", len(ihdr))
        + b"IHDR"
        + ihdr
        + struct.pack(">I", zlib.crc32(b"IHDR" + ihdr) & 0xFFFFFFFF)
    )
    iend = b"\x00\x00\x00\x00IEND\xaeB\x60\x82"
    return console.PNG_SIGNATURE + ihdr_chunk + iend


def wav_bytes(seconds=0.5, channels=2, rate=8000):
    frames = int(seconds * rate)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(b"\x00\x00" * frames * channels)
    return buffer.getvalue()


def mp4_bytes():
    payload = b"isomisom"
    return struct.pack(">I", 8 + len(payload)) + b"ftyp" + payload


def avi_bytes():
    payload = b"\x00" * 16
    return b"RIFF" + struct.pack("<I", 4 + len(payload)) + b"AVI " + payload


def glb_bytes(version=2):
    return b"glTF" + struct.pack("<II", version, 28) + b"\x00" * 16


def make_step(step_id, status="passed", seconds=0.1):
    return {"id": step_id, "kind": "tests", "status": status, "seconds": seconds}


def make_slice_state(slice_id, *, passed=True, artifacts=None, duration=1.5, errors=None, steps=None):
    return {
        "schema": console.SLICE_SCHEMA,
        "slice": slice_id,
        "project": ".",
        "runId": "20260101T000000Z-abcdef",
        "manifestSha256": "0" * 64,
        "startedAt": "2026-01-01T00:00:00+00:00",
        "finishedAt": "2026-01-01T00:00:02+00:00",
        "durationSeconds": duration,
        "passed": passed,
        "steps": steps if steps is not None else [make_step("demo"), make_step("build")],
        "artifacts": artifacts or [],
        "errors": errors or [],
    }


def artifact_entry(path, *, exists=True, size=10):
    return {
        "path": path,
        "exists": exists,
        "sha256": "a" * 64 if exists else None,
        "bytes": size if exists else None,
    }


def make_task(slices=None, *, passed=True, artifacts=None, steps=None, duration=3.0, task="task-20260101T000000Z"):
    return {
        "schema": console.TASK_SCHEMA,
        "task": task,
        "startedAt": "2026-01-01T00:00:00+00:00",
        "finishedAt": "2026-01-01T00:00:03+00:00",
        "durationSeconds": duration,
        "passed": passed,
        "sliceOrder": [row.get("slice") for row in (slices or [])],
        "slices": slices or [],
        "steps": steps or {"total": 2, "passed": 2, "failed": 0, "skipped": 0},
        "artifacts": artifacts or [],
        "report": [],
    }


def slice_summary(slice_id, *, status="passed", passed=True, steps=None, artifacts=0, duration=1.0, errors=None):
    return {
        "slice": slice_id,
        "status": status,
        "passed": passed,
        "statePath": f"workstream/state/slices/{slice_id}.json",
        "steps": steps or {"total": 2, "passed": 2, "failed": 0, "skipped": 0},
        "artifacts": artifacts,
        "durationSeconds": duration,
        "errors": errors or [],
    }


class TempCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.state = self.root / "state"
        self.slices_dir = self.state / "slices"

    def write(self, relative, payload):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(payload, bytes):
            path.write_bytes(payload)
        else:
            path.write_text(payload, encoding="utf-8")
        return path


# -- board ------------------------------------------------------------------


class BoardCase(TempCase):
    def read(self):
        return console.collect_board(self.state, self.root)

    def test_no_state_has_clean_message(self):
        board = self.read()
        self.assertFalse(board["hasState"])
        self.assertEqual(board["stateKind"], "none")
        self.assertEqual(board["slices"], [])
        self.assertEqual(board["steps"], {"total": 0, "passed": 0, "failed": 0, "skipped": 0})
        self.assertEqual(board["message"], console.NO_STATE_MESSAGE)
        self.assertEqual(board["approvals"], {"pending": [], "note": console.APPROVAL_NOTE})
        self.assertTrue(board["approvals"]["pending"] == [])
        self.assertEqual(console.render_board(board), console.NO_STATE_MESSAGE)

    def test_missing_state_directory_is_not_an_error(self):
        missing = self.root / "nowhere"
        board = console.collect_board(missing, self.root)
        self.assertFalse(board["hasState"])
        self.assertEqual(console.render_board(board), console.NO_STATE_MESSAGE)

    def test_task_state_board_counts_steps_artifacts_and_errors(self):
        slices = [
            slice_summary("phase1", artifacts=3, duration=12.5),
            slice_summary(
                "quality",
                status="failed",
                passed=False,
                steps={"total": 3, "passed": 2, "failed": 1, "skipped": 0},
                duration=7.0,
                errors=["step 'records' failed: boom"],
            ),
        ]
        artifacts = [
            artifact_entry("build/ProjectGypsy.exe", size=100),
            artifact_entry("artifacts/game/demo.mp4", size=200),
            artifact_entry("artifacts/game/frame.png", exists=False),
        ]
        task = make_task(
            slices,
            passed=False,
            artifacts=artifacts,
            steps={"total": 6, "passed": 5, "failed": 1, "skipped": 0},
            duration=19.5,
        )
        write_json(self.slices_dir / "task-20260101T000000Z.json", task)
        board = self.read()
        self.assertTrue(board["hasState"])
        self.assertEqual(board["stateKind"], "task")
        self.assertEqual(board["task"], "task-20260101T000000Z")
        self.assertFalse(board["passed"])
        self.assertEqual(len(board["slices"]), 2)
        self.assertEqual(board["steps"], {"total": 6, "passed": 5, "failed": 1, "skipped": 0})
        self.assertEqual(board["artifacts"]["total"], 3)
        self.assertEqual(board["artifacts"]["present"], 2)
        self.assertEqual(board["artifacts"]["missing"], 1)
        self.assertEqual(board["artifacts"]["bytes"], 300)
        self.assertEqual(board["artifacts"]["missingPaths"], ["artifacts/game/frame.png"])
        self.assertIn("quality: step 'records' failed: boom", board["errors"])
        rendered = console.render_board(board)
        self.assertIn("task task-20260101T000000Z: FAIL", rendered)
        self.assertIn("(5/6 steps, 3 artifacts, 19.5s)", rendered)
        self.assertIn("phase1: PASS (2/2 steps, 3 artifacts, 12.5s)", rendered)
        self.assertIn("quality: FAIL (2/3 steps, 0 artifacts, 7s)", rendered)
        self.assertIn("artifacts: 3 declared, 2 present, 1 missing (300 bytes)", rendered)
        self.assertIn("MISSING artifacts/game/frame.png", rendered)
        self.assertIn("approvals: 0 pending - no approval workflow; gates are automated", rendered)
        self.assertIn("errors:", rendered)

    def test_task_not_run_slice_renders_not_run(self):
        slices = [
            slice_summary("phase1", status="failed", passed=False, errors=["step 'demo' failed"]),
            slice_summary("quality", status="not-run", passed=False, steps={"total": 0}),
        ]
        write_json(self.slices_dir / "task-20260101T000000Z.json", make_task(slices, passed=False))
        rendered = console.render_board(self.read())
        self.assertIn("quality: NOT RUN", rendered)
        self.assertIn("phase1: FAIL", rendered)

    def test_latest_task_by_mtime_wins(self):
        old = write_json(self.slices_dir / "task-20260101T000000Z.json", make_task(task="task-old"))
        new = write_json(self.slices_dir / "task-20260102T000000Z.json", make_task(task="task-new"))
        os.utime(old, (1_600_000_000, 1_600_000_000))
        os.utime(new, (1_700_000_000, 1_700_000_000))
        self.assertEqual(self.read()["task"], "task-new")

    def test_corrupt_newest_task_falls_back_with_error(self):
        old = write_json(self.slices_dir / "task-20260101T000000Z.json", make_task(task="task-old"))
        bad = self.write("state/slices/task-20260102T000000Z.json", "{not json")
        os.utime(old, (1_600_000_000, 1_600_000_000))
        os.utime(bad, (1_700_000_000, 1_700_000_000))
        board = self.read()
        self.assertEqual(board["task"], "task-old")
        self.assertTrue(board["errors"])
        self.assertTrue(any("invalid JSON" in error for error in board["errors"]))

    def test_only_corrupt_state_reports_failure_instead_of_raising(self):
        self.write("state/slices/task-20260101T000000Z.json", "{not json")
        board = self.read()
        self.assertTrue(board["hasState"])
        self.assertFalse(board["passed"])
        self.assertEqual(board["slices"], [])
        self.assertTrue(any("invalid JSON" in error for error in board["errors"]))
        rendered = console.render_board(board)
        self.assertIn("slices: FAIL", rendered)
        self.assertIn("errors:", rendered)

    def test_per_slice_states_used_when_no_task_state(self):
        write_json(
            self.slices_dir / "phase1.json",
            make_slice_state(
                "phase1",
                artifacts=[artifact_entry("build/ProjectGypsy.exe", size=50), artifact_entry("artifacts/game/frame.png", exists=False)],
                duration=12.5,
            ),
        )
        write_json(
            self.slices_dir / "quality.json",
            make_slice_state("quality", duration=7.25, artifacts=[]),
        )
        board = self.read()
        self.assertEqual(board["stateKind"], "slices")
        self.assertTrue(board["hasState"])
        self.assertEqual([row["slice"] for row in board["slices"]], ["phase1", "quality"])
        self.assertTrue(board["passed"])
        self.assertEqual(board["steps"], {"total": 4, "passed": 4, "failed": 0, "skipped": 0})
        self.assertEqual(board["artifacts"]["total"], 2)
        self.assertEqual(board["artifacts"]["present"], 1)
        self.assertEqual(board["artifacts"]["missing"], 1)
        rendered = console.render_board(board)
        self.assertIn("slices: PASS (2 slices, 4/4 steps, 2 artifacts)", rendered)
        self.assertIn("phase1: PASS (2/2 steps, 2 artifacts, 12.5s)", rendered)
        self.assertIn("quality: PASS (2/2 steps, 0 artifacts, 7.25s)", rendered)
        self.assertIn("MISSING artifacts/game/frame.png", rendered)

    def test_per_slice_failure_marks_board_failed(self):
        write_json(self.slices_dir / "phase1.json", make_slice_state("phase1"))
        write_json(
            self.slices_dir / "quality.json",
            make_slice_state("quality", passed=False, steps=[make_step("check"), make_step("tests", status="failed")], errors=["step 'tests' failed: boom"]),
        )
        board = self.read()
        self.assertFalse(board["passed"])
        self.assertEqual(board["steps"], {"total": 4, "passed": 3, "failed": 1, "skipped": 0})
        self.assertIn("quality: step 'tests' failed: boom", board["errors"])
        rendered = console.render_board(board)
        self.assertIn("slices: FAIL", rendered)
        self.assertIn("quality: FAIL", rendered)

    def test_board_does_not_write(self):
        write_json(self.slices_dir / "task-20260101T000000Z.json", make_task([slice_summary("phase1")]))
        before = sorted(str(path.relative_to(self.root)) for path in self.root.rglob("*"))
        console.render_board(console.collect_board(self.state, self.root))
        after = sorted(str(path.relative_to(self.root)) for path in self.root.rglob("*"))
        self.assertEqual(before, after)


# -- artifact preview -------------------------------------------------------


class PreviewCase(TempCase):
    def test_png_dimensions_hash_and_bytes(self):
        payload = png_bytes(640, 360)
        self.write("artifacts/frame.png", payload)
        data = console.preview_artifact("artifacts/frame.png", self.root)
        self.assertTrue(data["exists"])
        self.assertEqual(data["kind"], "png")
        self.assertEqual(data["bytes"], len(payload))
        self.assertEqual(data["sha256"], hashlib.sha256(payload).hexdigest())
        self.assertEqual((data["width"], data["height"]), (640, 360))
        self.assertIsNone(data["error"])
        rendered = console.render_preview(data)
        self.assertIn("kind=png", rendered)
        self.assertIn("PNG 640x360", rendered)
        self.assertIn(data["sha256"], rendered)

    def test_wav_duration_channels_rate(self):
        payload = wav_bytes(seconds=0.5, channels=2, rate=8000)
        self.write("artifacts/musicgen.wav", payload)
        data = console.preview_artifact("artifacts/musicgen.wav", self.root)
        self.assertEqual(data["kind"], "wav")
        self.assertEqual(data["channels"], 2)
        self.assertEqual(data["sampleRate"], 8000)
        self.assertEqual(data["frames"], 4000)
        self.assertEqual(data["durationSeconds"], 0.5)
        self.assertIn("WAV 0.5s 2ch 8000Hz", console.render_preview(data))

    def test_json_top_level_keys(self):
        payload = (json.dumps({"beta": 2, "alpha": [1, 2]}) + "\n").encode("utf-8")
        self.write("workstream/state/import-matrix.json", payload)
        data = console.preview_artifact("workstream/state/import-matrix.json", self.root)
        self.assertEqual(data["kind"], "json")
        self.assertEqual(data["jsonType"], "object")
        self.assertEqual(data["topLevelKeys"], ["alpha", "beta"])
        self.assertIn("JSON object keys: alpha, beta", console.render_preview(data))

    def test_json_array(self):
        self.write("data.json", b"[1, 2, 3]")
        data = console.preview_artifact("data.json", self.root)
        self.assertEqual(data["kind"], "json")
        self.assertEqual(data["jsonType"], "array")
        self.assertIsNone(data["topLevelKeys"])
        self.assertIn("JSON array", console.render_preview(data))

    def test_invalid_json_is_reported(self):
        self.write("data.json", b"{not json")
        data = console.preview_artifact("data.json", self.root)
        self.assertEqual(data["kind"], "json")
        self.assertIn("invalid JSON", data["error"])
        self.assertIn("ERROR", console.render_preview(data))

    def test_glb_magic_and_version(self):
        self.write("artifacts/model.glb", glb_bytes(2))
        data = console.preview_artifact("artifacts/model.glb", self.root)
        self.assertEqual(data["kind"], "glb")
        self.assertEqual(data["glbMagic"], "glTF")
        self.assertEqual(data["glbVersion"], 2)
        self.assertEqual(data["glbLength"], 28)
        self.assertIn("GLB glTF v2", console.render_preview(data))

    def test_glb_wrong_version_is_reported(self):
        self.write("artifacts/model.glb", glb_bytes(1))
        data = console.preview_artifact("artifacts/model.glb", self.root)
        self.assertEqual(data["glbVersion"], 1)
        self.assertIn("unsupported GLB version 1", data["error"])

    def test_mp4_size_and_format(self):
        payload = mp4_bytes()
        self.write("artifacts/game/demo.mp4", payload)
        data = console.preview_artifact("artifacts/game/demo.mp4", self.root)
        self.assertEqual(data["kind"], "video")
        self.assertEqual(data["videoFormat"], "mp4")
        self.assertEqual(data["bytes"], len(payload))
        self.assertIn("video mp4", console.render_preview(data))

    def test_avi_size_and_format(self):
        payload = avi_bytes()
        self.write("artifacts/demo.avi", payload)
        data = console.preview_artifact("artifacts/demo.avi", self.root)
        self.assertEqual(data["kind"], "video")
        self.assertEqual(data["videoFormat"], "avi")
        self.assertEqual(data["bytes"], len(payload))

    def test_missing_file(self):
        data = console.preview_artifact("artifacts/nope.png", self.root)
        self.assertFalse(data["exists"])
        self.assertEqual(data["kind"], "missing")
        self.assertIsNone(data["sha256"])
        self.assertIn("no such file", data["error"])
        rendered = console.render_preview(data)
        self.assertIn("MISSING", rendered)
        self.assertIn("artifacts/nope.png", rendered)

    def test_text_and_binary_kinds(self):
        self.write("notes.txt", b"hello\nworld\n")
        self.assertEqual(console.preview_artifact("notes.txt", self.root)["kind"], "text")
        self.write("blob.bin", b"\x00\x01\x02\xff")
        self.assertEqual(console.preview_artifact("blob.bin", self.root)["kind"], "binary")

    def test_extension_mismatch_is_reported(self):
        self.write("bad.png", b"not a png at all")
        data = console.preview_artifact("bad.png", self.root)
        self.assertEqual(data["kind"], "png")
        self.assertTrue(data["error"])
        self.assertIn("ERROR", console.render_preview(data))

    def test_absolute_path_is_shown_project_relative(self):
        path = self.write("artifacts/frame.png", png_bytes(8, 8))
        data = console.preview_artifact(str(path), self.root)
        self.assertEqual(data["path"], "artifacts/frame.png")
        self.assertTrue(data["exists"])

    def test_preview_does_not_write(self):
        self.write("artifacts/frame.png", png_bytes(8, 8))
        self.write("artifacts/musicgen.wav", wav_bytes())
        self.write("data.json", b"{}")
        before = sorted(str(path.relative_to(self.root)) for path in self.root.rglob("*"))
        for name in ("artifacts/frame.png", "artifacts/musicgen.wav", "data.json", "absent.txt"):
            console.render_preview(console.preview_artifact(name, self.root))
        after = sorted(str(path.relative_to(self.root)) for path in self.root.rglob("*"))
        self.assertEqual(before, after)


# -- diff -------------------------------------------------------------------


class DiffCase(TempCase):
    def git(self, *args, check=True):
        completed = subprocess.run(
            ["git", *args],
            cwd=str(self.root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if check and completed.returncode != 0:
            raise RuntimeError("git " + " ".join(args) + " failed: " + completed.stderr)
        return completed

    def init_repo(self):
        self.git("init")
        self.git("config", "user.name", "Console Test")
        self.git("config", "user.email", "console@example.invalid")
        self.git("config", "commit.gpgsign", "false")
        self.write("a.txt", "one\n")
        self.git("add", "a.txt")
        self.git("commit", "-m", "initial")

    def test_invalid_commit_is_rejected_before_git(self):
        data = console.diff_report(self.root, commit="--output=owned.txt")
        self.assertFalse(data["available"])
        self.assertIn("invalid commit", data["error"])
        self.assertFalse((self.root / "owned.txt").exists())
        self.assertIn("invalid commit", console.render_diff(data))

    def test_empty_commit_is_rejected(self):
        data = console.diff_report(self.root, commit="")
        self.assertFalse(data["available"])
        self.assertIn("invalid commit", data["error"])

    def test_missing_git_is_graceful(self):
        with mock.patch("console.subprocess.run", side_effect=FileNotFoundError("git")):
            data = console.diff_report(self.root)
        self.assertFalse(data["available"])
        self.assertIn("git unavailable", data["error"])
        self.assertIn("git unavailable", console.render_diff(data))

    @unittest.skipUnless(GIT, "git is not installed")
    def test_not_a_repository_is_graceful(self):
        self.write("a.txt", "one\n")
        data = console.diff_report(self.root)
        self.assertFalse(data["available"])
        self.assertIn("not a git repository", data["error"].lower())
        self.assertTrue(console.render_diff(data))

    @unittest.skipUnless(GIT, "git is not installed")
    def test_worktree_diff_returns_stat_text_and_files(self):
        self.init_repo()
        self.write("a.txt", "two\n")
        data = console.diff_report(self.root)
        self.assertTrue(data["available"])
        self.assertTrue(data["text"])
        self.assertIn("a.txt", data["text"])
        self.assertEqual(len(data["files"]), 1)
        self.assertEqual(data["files"][0]["status"], "M")
        self.assertEqual(data["files"][0]["path"], "a.txt")
        rendered = console.render_diff(data)
        self.assertIn("diff working tree changes", rendered)
        self.assertIn("a.txt", rendered)
        self.assertIn("M a.txt", rendered)

    @unittest.skipUnless(GIT, "git is not installed")
    def test_staged_diff_and_clean_diff(self):
        self.init_repo()
        self.write("a.txt", "two\n")
        self.git("add", "a.txt")
        staged = console.diff_report(self.root, staged=True)
        self.assertTrue(staged["available"])
        self.assertEqual([entry["path"] for entry in staged["files"]], ["a.txt"])
        self.assertIn("diff staged changes", console.render_diff(staged))
        clean = console.diff_report(self.root)
        self.assertTrue(clean["available"])
        self.assertEqual(clean["files"], [])
        self.assertEqual(clean["text"], "")
        self.assertIn("no changes", console.render_diff(clean))

    @unittest.skipUnless(GIT, "git is not installed")
    def test_commit_diff(self):
        self.init_repo()
        self.write("a.txt", "two\n")
        self.git("add", "a.txt")
        self.git("commit", "-m", "second")
        data = console.diff_report(self.root, commit="HEAD~1")
        self.assertTrue(data["available"])
        self.assertEqual([entry["path"] for entry in data["files"]], ["a.txt"])
        self.assertIn("changes vs HEAD~1", console.render_diff(data))

    @unittest.skipUnless(GIT, "git is not installed")
    def test_diff_does_not_change_worktree_or_index(self):
        self.init_repo()
        self.write("a.txt", "two\n")
        before = self.git("status", "--porcelain").stdout
        console.diff_report(self.root)
        console.render_diff(console.diff_report(self.root, staged=True))
        after = self.git("status", "--porcelain").stdout
        self.assertEqual(before, after)
        self.assertEqual((self.root / "a.txt").read_text(encoding="utf-8"), "two\n")


# -- manual entry point -----------------------------------------------------


class MainCase(TempCase):
    def run_main(self, argv):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = console.main(["--state-dir", str(self.state), "--project-root", str(self.root), *argv])
        return code, buffer.getvalue()

    def test_board_prints_pass_and_returns_zero(self):
        write_json(self.slices_dir / "task-20260101T000000Z.json", make_task([slice_summary("phase1")]))
        code, output = self.run_main(["board"])
        self.assertEqual(code, 0)
        self.assertIn("task task-20260101T000000Z: PASS", output)

    def test_board_without_state_returns_one_and_prints_message(self):
        code, output = self.run_main(["board"])
        self.assertEqual(code, 1)
        self.assertEqual(output.strip(), console.NO_STATE_MESSAGE)

    def test_board_json_is_parseable(self):
        write_json(self.slices_dir / "task-20260101T000000Z.json", make_task([slice_summary("phase1")]))
        code, output = self.run_main(["--json", "board"])
        self.assertEqual(code, 0)
        payload = json.loads(output)
        self.assertEqual(payload["schema"], console.BOARD_SCHEMA)
        self.assertTrue(payload["hasState"])

    def test_preview_cli(self):
        self.write("artifacts/frame.png", png_bytes(32, 16))
        code, output = self.run_main(["--json", "preview", "artifacts/frame.png"])
        self.assertEqual(code, 0)
        payload = json.loads(output)
        self.assertEqual(payload["kind"], "png")
        self.assertEqual((payload["width"], payload["height"]), (32, 16))

    def test_preview_cli_missing_returns_one(self):
        code, output = self.run_main(["preview", "artifacts/nope.png"])
        self.assertEqual(code, 1)
        self.assertIn("MISSING", output)

    def test_diff_cli_invalid_commit_returns_one(self):
        code, output = self.run_main(["diff", "--commit=--output=owned.txt"])
        self.assertEqual(code, 1)
        self.assertIn("invalid commit", output)
        self.assertFalse((self.root / "owned.txt").exists())

    def test_diff_cli_git_unavailable_json(self):
        with mock.patch("console.subprocess.run", side_effect=FileNotFoundError("git")):
            code, output = self.run_main(["--json", "diff"])
        self.assertEqual(code, 1)
        payload = json.loads(output)
        self.assertFalse(payload["available"])
        self.assertIn("git unavailable", payload["error"])

    def test_cli_does_not_write(self):
        write_json(self.slices_dir / "task-20260101T000000Z.json", make_task([slice_summary("phase1")]))
        before = sorted(str(path.relative_to(self.root)) for path in self.root.rglob("*"))
        self.run_main(["board"])
        self.run_main(["--json", "board"])
        after = sorted(str(path.relative_to(self.root)) for path in self.root.rglob("*"))
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
