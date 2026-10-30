#!/usr/bin/env python3
"""Tests for the Phase-3 toolpack runner and validators (workstream/toolpacks.py).

No Godot, network or real art tool is used: every command is sys.executable -c against
temporary directories, and PNG/WAV/GLB fixtures are generated in Python.
"""
from __future__ import annotations

import hashlib
import io
import json
import math
import struct
import sys
import tempfile
import time
import unittest
import wave
import zlib
from pathlib import Path

WORKSTREAM = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKSTREAM))

import toolpacks  # noqa: E402


def python_argv(code):
    return [sys.executable, "-c", code]


def write_argv(rel, payload):
    code = (
        "from pathlib import Path\n"
        f"path = Path({rel!r})\n"
        "path.parent.mkdir(parents=True, exist_ok=True)\n"
        f"path.write_bytes({payload!r})\n"
        "print('TOOLPACK_OK')\n"
    )
    return python_argv(code)


def make_action(action_id="run", argv=None, **overrides):
    if argv is None:
        argv = python_argv("print('TOOLPACK_OK')")
    elif isinstance(argv, (list, tuple)):
        argv = list(argv)
    action = {"id": action_id, "argv": argv}
    action.update(overrides)
    return action


def make_manifest(actions=None, *, validators=None, toolpack_id="sample", name="Sample toolpack"):
    manifest = {
        "schema": toolpacks.SCHEMA,
        "id": toolpack_id,
        "name": name,
        "tools": ["fixture-tool 1.0"],
        "license": "MIT",
        "actions": actions if actions is not None else [make_action()],
    }
    if validators is not None:
        manifest["validators"] = validators
    return manifest


def png_bytes(width, height):
    signature = b"\x89PNG\r\n\x1a\n"
    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    chunk = struct.pack(">I", 13) + b"IHDR" + ihdr_data
    crc = struct.pack(">I", zlib.crc32(b"IHDR" + ihdr_data) & 0xFFFFFFFF)
    return signature + chunk + crc


def wav_bytes(seconds=0.2, rate=8000, amplitude=20000, sample_width=2):
    if sample_width == 2:
        frames = b"".join(
            struct.pack(
                "<h", int(amplitude * math.sin(2 * math.pi * 220 * index / rate))
            )
            for index in range(int(rate * seconds))
        )
    else:
        frames = bytes([128]) * int(rate * seconds)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(sample_width)
        handle.setframerate(rate)
        handle.writeframes(frames)
    return buffer.getvalue()


def glb_bytes(version=2):
    return b"glTF" + struct.pack("<I", version) + struct.pack("<I", 12)


class SchemaTests(unittest.TestCase):
    def test_valid_manifest_has_no_errors(self):
        validators = [
            {"id": "file", "kind": "file", "artifact": "artifacts/out.bin", "minBytes": 1},
            {
                "id": "json",
                "kind": "json",
                "artifact": "artifacts/out.json",
                "checks": [{"path": "a.b", "equals": 7}],
            },
            {"id": "text", "kind": "text", "artifact": "artifacts/out.txt", "contains": "ok"},
            {
                "id": "wav",
                "kind": "wav",
                "artifact": "artifacts/out.wav",
                "minSeconds": 0.1,
                "minRms": 0.01,
            },
            {"id": "png", "kind": "png", "artifact": "artifacts/out.png", "minWidth": 2},
            {"id": "glb", "kind": "glb", "artifact": "artifacts/out.glb"},
        ]
        manifest = make_manifest(validators=validators)
        manifest["tools"] = [
            "blender 5.2.3",
            {"name": "glTF-Transform", "version": "4.5.1"},
        ]
        self.assertEqual(toolpacks.validate_manifest(manifest), [])

    def test_wrong_schema_is_reported(self):
        manifest = make_manifest()
        manifest["schema"] = "gypsy.toolpack/v2"
        errors = toolpacks.validate_manifest(manifest)
        self.assertTrue(any("schema" in error for error in errors))

    def test_unknown_top_level_key_is_reported(self):
        manifest = make_manifest()
        manifest["notes"] = "not documented"
        errors = toolpacks.validate_manifest(manifest)
        self.assertTrue(any("unknown top-level key" in error for error in errors))

    def test_required_top_level_fields_are_reported(self):
        for key in ("name", "tools", "license", "actions"):
            manifest = make_manifest()
            del manifest[key]
            errors = toolpacks.validate_manifest(manifest)
            self.assertTrue(errors, key)
        manifest = make_manifest()
        manifest["id"] = "../bad"
        manifest["name"] = ""
        manifest["license"] = 3
        errors = toolpacks.validate_manifest(manifest)
        self.assertTrue(any("id must be" in error for error in errors))
        self.assertTrue(any("name must be" in error for error in errors))
        self.assertTrue(any("license must be" in error for error in errors))
        errors = toolpacks.validate_manifest(make_manifest(actions=[]))
        self.assertTrue(any("actions must be" in error for error in errors))

    def test_tools_entries_are_strings_or_objects(self):
        manifest = make_manifest()
        manifest["tools"] = [42]
        errors = toolpacks.validate_manifest(manifest)
        self.assertTrue(any("tools[0]" in error for error in errors))
        manifest["tools"] = [""]
        errors = toolpacks.validate_manifest(manifest)
        self.assertTrue(any("non-empty string" in error for error in errors))

    def test_duplicate_action_ids_are_reported(self):
        manifest = make_manifest([make_action("a"), make_action("a")])
        errors = toolpacks.validate_manifest(manifest)
        self.assertTrue(any("duplicate action id" in error for error in errors))

    def test_argv_must_be_an_explicit_non_empty_list(self):
        cases = [
            ({"id": "a"}, "argv must be"),
            ({"id": "a", "argv": []}, "argv must be"),
            ({"id": "a", "argv": "echo hello"}, "never a shell string"),
            ({"id": "a", "argv": [sys.executable, 3]}, "must be a string"),
            ({"id": "a", "argv": [sys.executable, ""]}, "must not be empty"),
        ]
        for raw, expected in cases:
            errors = toolpacks.validate_manifest(make_manifest([raw]))
            self.assertTrue(
                any(expected in error for error in errors), (raw, errors)
            )

    def test_cwd_must_stay_repo_relative(self):
        for cwd in ("../escape", "C:/tmp", "/tmp", ".."):
            errors = toolpacks.validate_manifest(
                make_manifest([make_action(cwd=cwd)])
            )
            self.assertTrue(any("cwd" in error for error in errors), cwd)

    def test_timeout_must_be_positive(self):
        for timeout in (0, -1, "5", True):
            errors = toolpacks.validate_manifest(
                make_manifest([make_action(timeout=timeout)])
            )
            self.assertTrue(any("timeout must be" in error for error in errors), timeout)

    def test_artifact_paths_stay_relative_with_only_a_trailing_glob(self):
        for artifact in ("../escape.bin", "C:/tmp/out.bin", "a/*/b.png", "**/*.png"):
            errors = toolpacks.validate_manifest(
                make_manifest([make_action(artifacts=[artifact])])
            )
            self.assertTrue(errors, artifact)
        errors = toolpacks.validate_manifest(
            make_manifest([make_action(artifacts=["artifacts/export/*.glb"])])
        )
        self.assertEqual(errors, [])

    def test_unknown_action_key_and_bad_args_are_reported(self):
        manifest = make_manifest([make_action("a", note="nope", args=[])])
        errors = toolpacks.validate_manifest(manifest)
        self.assertTrue(any("unknown key" in error for error in errors))
        self.assertTrue(any("args must be" in error for error in errors))

    def test_validator_ids_kinds_and_artifacts_are_strict(self):
        manifest = make_manifest(
            validators=[
                {"id": "dup", "kind": "glb", "artifact": "a.glb"},
                {"id": "dup", "kind": "glb", "artifact": "a.glb"},
                {"id": "bad-kind", "kind": "exr", "artifact": "a.exr"},
                {"id": "bad-artifact", "kind": "glb", "artifact": "../a.glb"},
            ]
        )
        errors = toolpacks.validate_manifest(manifest)
        self.assertTrue(any("duplicate validator id" in error for error in errors))
        self.assertTrue(any("unknown kind" in error for error in errors))
        self.assertTrue(any("artifact must" in error for error in errors))

    def test_kind_specific_validator_fields_are_strict(self):
        cases = [
            {"id": "a", "kind": "file", "artifact": "a.bin", "minBytes": -1},
            {"id": "b", "kind": "json", "artifact": "a.json", "checks": []},
            {
                "id": "c",
                "kind": "json",
                "artifact": "a.json",
                "checks": [{"path": "a", "equals": 1, "gte": 1}],
            },
            {
                "id": "d",
                "kind": "json",
                "artifact": "a.json",
                "checks": [{"path": "a..b", "equals": 1}],
            },
            {"id": "e", "kind": "text", "artifact": "a.txt", "contains": ""},
            {"id": "f", "kind": "wav", "artifact": "a.wav", "minRms": 0},
            {"id": "g", "kind": "png", "artifact": "a.png", "minWidth": 0},
            {"id": "h", "kind": "glb", "artifact": "a.glb", "magic": "glTF"},
        ]
        for validator in cases:
            errors = toolpacks.validate_manifest(make_manifest(validators=[validator]))
            self.assertTrue(errors, validator)

    def test_manifest_must_be_an_object(self):
        self.assertEqual(
            toolpacks.validate_manifest("not-an-object"),
            ["manifest must be a JSON object"],
        )


class LoadTests(unittest.TestCase):
    def test_load_manifest_rejects_invalid_json_and_non_object(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.json"
            bad.write_text("{not json", encoding="utf-8")
            with self.assertRaises(toolpacks.ToolpackError):
                toolpacks.load_manifest(bad)
            array = Path(tmp) / "array.json"
            array.write_text("[]", encoding="utf-8")
            with self.assertRaises(toolpacks.ToolpackError):
                toolpacks.load_manifest(array)
            with self.assertRaises(toolpacks.ToolpackError):
                toolpacks.load_manifest(Path(tmp) / "missing.json")

    def test_load_all_keys_by_id_and_rejects_duplicates_and_missing_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / "a.json").write_text(
                json.dumps(make_manifest(toolpack_id="alpha")), encoding="utf-8"
            )
            (directory / "b.json").write_text(
                json.dumps(make_manifest(toolpack_id="beta")), encoding="utf-8"
            )
            loaded = toolpacks.load_all(directory)
            self.assertEqual(list(loaded), ["alpha", "beta"])
            (directory / "c.json").write_text(
                json.dumps(make_manifest(toolpack_id="alpha")), encoding="utf-8"
            )
            with self.assertRaises(toolpacks.ToolpackError):
                toolpacks.load_all(directory)
            with self.assertRaises(toolpacks.ToolpackError):
                toolpacks.load_all(directory / "nope")


class ToolpackCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.project = self.root / "project"
        self.project.mkdir(parents=True, exist_ok=True)
        self.state = self.root / "state"

    def write(self, rel, content):
        path = self.project / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding="utf-8")
        return path

    def run_action(self, manifest=None, action_id="run", **kwargs):
        if manifest is None:
            manifest = make_manifest()
        return toolpacks.run_action(
            manifest,
            action_id,
            project_root=self.project,
            state_dir=self.state,
            **kwargs,
        )

    def run_toolpack(self, manifest=None, **kwargs):
        if manifest is None:
            manifest = make_manifest()
        return toolpacks.run_toolpack(
            manifest,
            project_root=self.project,
            state_dir=self.state,
            **kwargs,
        )

    def state_files(self):
        directory = self.state / "toolpacks"
        if not directory.is_dir():
            return []
        return sorted(path.name for path in directory.iterdir())

    def read_state(self, result):
        return json.loads(Path(result["statePath"]).read_text(encoding="utf-8"))

    def assert_clean_state_dir(self):
        names = self.state_files()
        self.assertFalse([name for name in names if name.endswith(".tmp")], names)
        self.assertTrue(all(name.endswith(".json") for name in names), names)
        return names


class RunActionTests(ToolpackCase):
    def test_successful_action_writes_atomic_state_and_provenance(self):
        payload = b"gypsy-artifact"
        manifest = make_manifest(
            [
                make_action(
                    "make",
                    argv=write_argv("artifacts/out.bin", payload),
                    timeout=7,
                    artifacts=["artifacts/out.bin"],
                    args={"asset": "demo"},
                )
            ]
        )
        result = self.run_action(manifest, "make", timeout_scale=2.0)
        self.assertTrue(result["passed"])
        self.assertEqual(result["schema"], toolpacks.STATE_SCHEMA)
        self.assertEqual(result["scope"], "action")
        self.assertEqual(result["toolpack"], "sample")
        self.assertEqual(result["action"], "make")
        self.assertEqual(result["exit"], 0)
        self.assertIn("TOOLPACK_OK", result["stdout"])
        self.assertEqual(result["timeoutSeconds"], 14.0)
        self.assertEqual(result["command"], {"argv": manifest["actions"][0]["argv"], "cwd": "."})
        self.assertEqual(result["args"], {"asset": "demo"})
        self.assertEqual(result["license"], "MIT")
        self.assertEqual(result["tools"], ["fixture-tool 1.0"])
        self.assertRegex(result["runId"], r"^\d{8}T\d{6}Z-[0-9a-f]{6}$")
        self.assertTrue(result["manifestSha256"])
        self.assertEqual(result["validators"], [])
        self.assertEqual(result["errors"], [])
        entry = result["artifacts"][0]
        self.assertEqual(entry["path"], "artifacts/out.bin")
        self.assertEqual(entry["declaredAs"], "artifacts/out.bin")
        self.assertTrue(entry["exists"])
        self.assertEqual(entry["sha256"], hashlib.sha256(payload).hexdigest())
        self.assertEqual(entry["bytes"], len(payload))
        json.dumps(result)

        state_path = Path(result["statePath"])
        self.assertTrue(state_path.is_file())
        self.assertTrue(state_path.name.startswith("sample-make-"))
        document = self.read_state(result)
        for key in (
            "schema",
            "scope",
            "toolpack",
            "action",
            "runId",
            "manifestSha256",
            "passed",
            "timedOut",
            "seconds",
            "timeoutSeconds",
            "command",
            "exit",
            "stdout",
            "stderr",
            "artifacts",
            "validators",
            "license",
            "tools",
            "errors",
        ):
            self.assertIn(key, document)
        self.assertEqual(document["artifacts"], result["artifacts"])
        self.assertEqual(self.assert_clean_state_dir(), [state_path.name])

    def test_unknown_action_raises_before_writing_state(self):
        with self.assertRaises(toolpacks.ToolpackError):
            self.run_action(make_manifest(), "missing")
        self.assertEqual(self.state_files(), [])

    def test_invalid_manifest_raises_before_writing_state(self):
        manifest = make_manifest([make_action(argv="echo hello")])
        with self.assertRaises(toolpacks.ToolpackError):
            self.run_action(manifest)
        self.assertFalse(self.state.exists())

    def test_missing_declared_artifact_fails_and_is_recorded(self):
        manifest = make_manifest(
            [make_action("build", artifacts=["artifacts/missing.bin"])]
        )
        result = self.run_action(manifest, "build")
        self.assertFalse(result["passed"])
        entry = result["artifacts"][0]
        self.assertFalse(entry["exists"])
        self.assertIsNone(entry["sha256"])
        self.assertIsNone(entry["bytes"])
        self.assertTrue(
            any("missing declared artifact" in error for error in result["errors"])
        )
        self.assertFalse(self.read_state(result)["passed"])

    def test_glob_artifacts_expand_and_hash_each_file(self):
        code = (
            "from pathlib import Path\n"
            "base = Path('artifacts/out')\n"
            "base.mkdir(parents=True, exist_ok=True)\n"
            "(base / 'a.txt').write_bytes(b'alpha')\n"
            "(base / 'b.txt').write_bytes(b'beta')\n"
            "print('GLOB_OK')\n"
        )
        manifest = make_manifest(
            [
                make_action(
                    "export",
                    argv=python_argv(code),
                    artifacts=["artifacts/out/*.txt"],
                )
            ]
        )
        result = self.run_action(manifest, "export")
        self.assertTrue(result["passed"])
        self.assertEqual(
            [entry["path"] for entry in result["artifacts"]],
            ["artifacts/out/a.txt", "artifacts/out/b.txt"],
        )
        for entry in result["artifacts"]:
            self.assertTrue(entry["exists"])
            self.assertEqual(entry["declaredAs"], "artifacts/out/*.txt")
            self.assertIsNotNone(entry["sha256"])
            self.assertGreater(entry["bytes"], 0)

    def test_glob_artifact_with_no_matches_fails(self):
        manifest = make_manifest(
            [make_action("export", artifacts=["artifacts/none/*.txt"])]
        )
        result = self.run_action(manifest, "export")
        self.assertFalse(result["passed"])
        self.assertEqual(result["artifacts"][0]["path"], "artifacts/none/*.txt")
        self.assertFalse(result["artifacts"][0]["exists"])
        self.assertTrue(
            any("missing declared artifact" in error for error in result["errors"])
        )

    def test_command_failure_records_exit_and_stderr(self):
        code = "import sys; print('OUT'); sys.stderr.write('BAD_NEWS'); sys.exit(3)"
        manifest = make_manifest([make_action("fail", argv=python_argv(code))])
        result = self.run_action(manifest, "fail")
        self.assertFalse(result["passed"])
        self.assertEqual(result["exit"], 3)
        self.assertIn("OUT", result["stdout"])
        self.assertIn("BAD_NEWS", result["stderr"])
        self.assertTrue(any("command exited 3" in error for error in result["errors"]))
        self.assertEqual(self.read_state(result)["exit"], 3)

    def test_timeout_is_recorded_and_does_not_raise(self):
        code = "import time; time.sleep(5)"
        manifest = make_manifest(
            [make_action("slow", argv=python_argv(code), timeout=0.3)]
        )
        result = self.run_action(manifest, "slow")
        self.assertFalse(result["passed"])
        self.assertTrue(result["timedOut"])
        self.assertIsNone(result["exit"])
        self.assertLess(result["seconds"], 3.0)
        self.assertTrue(any("timeout after" in error for error in result["errors"]))
        self.assertTrue(self.read_state(result)["timedOut"])

    def test_timeout_scale_stretches_the_budget(self):
        manifest = make_manifest([make_action("fast", timeout=5)])
        result = self.run_action(manifest, "fast", timeout_scale=2.5)
        self.assertTrue(result["passed"])
        self.assertEqual(result["timeoutSeconds"], 12.5)

    def test_cwd_is_resolved_under_the_project_root(self):
        (self.project / "sub").mkdir()
        manifest = make_manifest(
            [
                make_action(
                    "inside",
                    argv=write_argv("made.txt", b"inside"),
                    cwd="sub",
                    artifacts=["sub/made.txt"],
                )
            ]
        )
        result = self.run_action(manifest, "inside")
        self.assertTrue(result["passed"])
        self.assertEqual(result["command"]["cwd"], "sub")
        self.assertTrue((self.project / "sub" / "made.txt").is_file())

    def test_missing_cwd_fails_cleanly_and_records_state(self):
        manifest = make_manifest([make_action("where", cwd="nope")])
        result = self.run_action(manifest, "where")
        self.assertFalse(result["passed"])
        self.assertEqual(result["errors"], ["cwd does not exist: nope"])
        self.assertTrue(Path(result["statePath"]).is_file())

    def test_output_is_clipped(self):
        manifest = make_manifest(
            [make_action("chatty", argv=python_argv("print('x' * 10000)"))]
        )
        result = self.run_action(manifest, "chatty")
        self.assertTrue(result["passed"])
        self.assertTrue(result["stdout"].startswith("...[truncated]..."))
        self.assertLessEqual(len(result["stdout"]), 4200)

    def test_two_runs_write_distinct_state_files_atomically(self):
        first = self.run_action()
        second = self.run_action()
        self.assertNotEqual(first["runId"], second["runId"])
        self.assertNotEqual(first["statePath"], second["statePath"])
        names = self.assert_clean_state_dir()
        self.assertEqual(len(names), 2)
        for result in (first, second):
            self.assertTrue(self.read_state(result)["passed"])


class ValidatorTests(ToolpackCase):
    def run_validator(self, validator, files, *, artifacts=None):
        for rel, content in files.items():
            self.write(rel, content)
        declared = list(files) if artifacts is None else list(artifacts)
        manifest = make_manifest(
            [make_action("check", artifacts=declared)], validators=[validator]
        )
        return self.run_action(manifest, "check")

    def test_file_validator_min_bytes(self):
        passed = self.run_validator(
            {"id": "size", "kind": "file", "artifact": "out.bin", "minBytes": 4},
            {"out.bin": b"abcd"},
        )
        self.assertTrue(passed["passed"])
        self.assertEqual(passed["validators"][0]["details"]["bytes"], 4)
        failed = self.run_validator(
            {"id": "size", "kind": "file", "artifact": "out.bin", "minBytes": 5},
            {"out.bin": b"abcd"},
        )
        self.assertFalse(failed["passed"])
        self.assertFalse(failed["validators"][0]["passed"])
        self.assertIn("below minBytes", failed["validators"][0]["error"])

    def test_json_validator_equals_exists_and_gte(self):
        document = json.dumps({"a": {"b": 7}, "flag": True, "words": [1, 2, 3]})
        result = self.run_validator(
            {
                "id": "shape",
                "kind": "json",
                "artifact": "out.json",
                "checks": [
                    {"path": "a.b", "equals": 7},
                    {"path": "flag", "exists": True},
                    {"path": "a.b", "gte": 5},
                    {"path": "words.0", "equals": 1},
                ],
            },
            {"out.json": document},
        )
        self.assertTrue(result["passed"])
        self.assertEqual(result["validators"][0]["details"], {"checks": 4, "failed": 0})

    def test_json_validator_reports_each_failure(self):
        document = json.dumps({"a": {"b": 7}, "flag": True})
        result = self.run_validator(
            {
                "id": "shape",
                "kind": "json",
                "artifact": "out.json",
                "checks": [
                    {"path": "a.b", "equals": 8},
                    {"path": "flag", "exists": False},
                    {"path": "a.b", "gte": 9},
                    {"path": "missing", "equals": 1},
                ],
            },
            {"out.json": document},
        )
        self.assertFalse(result["passed"])
        self.assertEqual(result["validators"][0]["details"]["failed"], 4)
        error = result["validators"][0]["error"]
        for fragment in ("expected 8", "exists=False", "expected >= 9", "missing"):
            self.assertIn(fragment, error)

    def test_text_validator_contains(self):
        passed = self.run_validator(
            {"id": "word", "kind": "text", "artifact": "out.txt", "contains": "gypsy"},
            {"out.txt": "hello gypsy world"},
        )
        self.assertTrue(passed["passed"])
        failed = self.run_validator(
            {"id": "word", "kind": "text", "artifact": "out.txt", "contains": "absent"},
            {"out.txt": "hello gypsy world"},
        )
        self.assertFalse(failed["passed"])
        self.assertIn("does not contain", failed["validators"][0]["error"])

    def test_wav_validator_seconds_and_rms(self):
        result = self.run_validator(
            {
                "id": "audio",
                "kind": "wav",
                "artifact": "out.wav",
                "minSeconds": 0.1,
                "minRms": 0.1,
            },
            {"out.wav": wav_bytes(seconds=0.25, amplitude=20000)},
        )
        self.assertTrue(result["passed"])
        details = result["validators"][0]["details"]
        self.assertGreaterEqual(details["seconds"], 0.1)
        self.assertGreaterEqual(details["rms"], 0.1)

    def test_wav_validator_rejects_short_and_unsupported_files(self):
        short = self.run_validator(
            {
                "id": "audio",
                "kind": "wav",
                "artifact": "out.wav",
                "minSeconds": 10,
            },
            {"out.wav": wav_bytes(seconds=0.1)},
        )
        self.assertFalse(short["passed"])
        self.assertIn("below minSeconds", short["validators"][0]["error"])
        unsupported = self.run_validator(
            {
                "id": "audio",
                "kind": "wav",
                "artifact": "out.wav",
                "minRms": 0.01,
            },
            {"out.wav": wav_bytes(seconds=0.1, sample_width=1)},
        )
        self.assertFalse(unsupported["passed"])
        self.assertIn("unsupported WAV", unsupported["validators"][0]["error"])

    def test_png_validator_reads_ihdr_dimensions(self):
        result = self.run_validator(
            {
                "id": "image",
                "kind": "png",
                "artifact": "out.png",
                "minWidth": 8,
                "minHeight": 6,
            },
            {"out.png": png_bytes(8, 6)},
        )
        self.assertTrue(result["passed"])
        self.assertEqual(result["validators"][0]["details"], {"width": 8, "height": 6})
        small = self.run_validator(
            {
                "id": "image",
                "kind": "png",
                "artifact": "out.png",
                "minWidth": 8,
            },
            {"out.png": png_bytes(4, 4)},
        )
        self.assertFalse(small["passed"])
        self.assertIn("below minWidth", small["validators"][0]["error"])
        not_png = self.run_validator(
            {"id": "image", "kind": "png", "artifact": "out.png"},
            {"out.png": b"not a png"},
        )
        self.assertFalse(not_png["passed"])
        self.assertIn("not a PNG", not_png["validators"][0]["error"])

    def test_glb_validator_magic_and_version(self):
        passed = self.run_validator(
            {"id": "mesh", "kind": "glb", "artifact": "out.glb"},
            {"out.glb": glb_bytes(2)},
        )
        self.assertTrue(passed["passed"])
        self.assertEqual(passed["validators"][0]["details"], {"version": 2})
        bad_version = self.run_validator(
            {"id": "mesh", "kind": "glb", "artifact": "out.glb"},
            {"out.glb": glb_bytes(1)},
        )
        self.assertFalse(bad_version["passed"])
        self.assertIn("version must be 2", bad_version["validators"][0]["error"])
        bad_magic = self.run_validator(
            {"id": "mesh", "kind": "glb", "artifact": "out.glb"},
            {"out.glb": b"nope" + b"\x00" * 8},
        )
        self.assertFalse(bad_magic["passed"])
        self.assertIn("bad magic", bad_magic["validators"][0]["error"])

    def test_validator_glob_applies_to_every_matching_declared_artifact(self):
        result = self.run_validator(
            {"id": "word", "kind": "text", "artifact": "artifacts/*.txt", "contains": "x"},
            {"artifacts/a.txt": "x-one", "artifacts/b.txt": "x-two"},
            artifacts=["artifacts/*.txt"],
        )
        self.assertTrue(result["passed"])
        self.assertEqual(len(result["validators"]), 2)
        self.assertEqual(
            [entry["target"] for entry in result["validators"]],
            ["artifacts/a.txt", "artifacts/b.txt"],
        )

    def test_validator_is_not_applied_to_undeclared_artifacts(self):
        result = self.run_validator(
            {
                "id": "other",
                "kind": "text",
                "artifact": "other/value.txt",
                "contains": "x",
            },
            {"artifacts/out.txt": "hello"},
        )
        self.assertTrue(result["passed"])
        self.assertEqual(result["validators"], [])

    def test_validator_on_declared_but_missing_literal_fails(self):
        result = self.run_validator(
            {
                "id": "missing",
                "kind": "json",
                "artifact": "artifacts/missing.json",
                "checks": [{"path": "a", "exists": True}],
            },
            {},
            artifacts=["artifacts/missing.json"],
        )
        self.assertFalse(result["passed"])
        self.assertEqual(len(result["validators"]), 1)
        self.assertFalse(result["validators"][0]["passed"])
        self.assertIn("artifact missing", result["validators"][0]["error"])


class RunToolpackTests(ToolpackCase):
    def test_all_actions_pass_with_one_aggregate_state_and_ledger(self):
        actions = [
            make_action(
                "first",
                argv=write_argv("artifacts/a.txt", b"alpha"),
                artifacts=["artifacts/a.txt"],
            ),
            make_action(
                "second",
                argv=write_argv("artifacts/b.txt", b"beta"),
                artifacts=["artifacts/b.txt"],
            ),
        ]
        manifest = make_manifest(
            actions,
            validators=[
                {
                    "id": "words",
                    "kind": "text",
                    "artifact": "artifacts/*.txt",
                    "contains": "a",
                }
            ],
        )
        result = self.run_toolpack(manifest)
        self.assertTrue(result["passed"])
        self.assertEqual(result["schema"], toolpacks.STATE_SCHEMA)
        self.assertEqual(result["scope"], "toolpack")
        self.assertEqual(result["actionOrder"], ["first", "second"])
        self.assertEqual(
            [summary["status"] for summary in result["actions"]],
            ["passed", "passed"],
        )
        self.assertTrue(all(summary["passed"] for summary in result["actions"]))
        self.assertEqual([entry["action"] for entry in result["artifacts"]], ["first", "second"])
        self.assertEqual(len(result["validators"]), 2)
        self.assertEqual([entry["action"] for entry in result["validators"]], ["first", "second"])
        self.assertEqual(result["license"], "MIT")
        self.assertEqual(result["tools"], ["fixture-tool 1.0"])
        self.assertEqual(result["errors"], [])
        json.dumps(result)
        document = self.read_state(result)
        self.assertEqual(document["actions"], result["actions"])
        self.assertEqual(document["artifacts"], result["artifacts"])
        for summary in result["actions"]:
            self.assertTrue(Path(summary["statePath"]).is_file())
        names = self.assert_clean_state_dir()
        self.assertEqual(len(names), 3)
        aggregate_path = Path(result["statePath"])
        self.assertTrue(
            aggregate_path.name.startswith("sample-") and "first" not in aggregate_path.name
        )

    def test_failure_stops_later_actions_and_is_reported(self):
        actions = [
            make_action(
                "first",
                argv=write_argv("artifacts/a.txt", b"alpha"),
                artifacts=["artifacts/a.txt"],
            ),
            make_action(
                "second",
                argv=python_argv("import sys; sys.exit(3)"),
            ),
            make_action(
                "third",
                argv=write_argv("artifacts/c.txt", b"gamma"),
                artifacts=["artifacts/c.txt"],
            ),
        ]
        result = self.run_toolpack(make_manifest(actions))
        self.assertFalse(result["passed"])
        self.assertEqual(result["actionOrder"], ["first", "second", "third"])
        self.assertEqual(
            [summary["status"] for summary in result["actions"]],
            ["passed", "failed", "not-run"],
        )
        self.assertIsNone(result["actions"][2]["passed"])
        self.assertIsNone(result["actions"][2]["statePath"])
        self.assertIn("not run", result["actions"][2]["label"])
        self.assertFalse((self.project / "artifacts" / "c.txt").exists())
        self.assertEqual([entry["action"] for entry in result["artifacts"]], ["first"])
        self.assertTrue(any("'second' failed" in error for error in result["errors"]))
        self.assertEqual(len(self.assert_clean_state_dir()), 3)

    def test_invalid_manifest_raises_before_state(self):
        manifest = make_manifest(actions=[])
        with self.assertRaises(toolpacks.ToolpackError):
            self.run_toolpack(manifest)
        self.assertFalse(self.state.exists())

    def test_timeout_scale_reaches_actions(self):
        actions = [
            make_action(
                "sleeper",
                argv=python_argv("import time; time.sleep(0.3)"),
                timeout=0.2,
            )
        ]
        result = self.run_toolpack(make_manifest(actions), timeout_scale=5.0)
        self.assertTrue(result["passed"])
        self.assertEqual(result["timeoutScale"], 5.0)
        action_state = json.loads(
            Path(result["actions"][0]["statePath"]).read_text(encoding="utf-8")
        )
        self.assertEqual(action_state["timeoutSeconds"], 1.0)


class CacheParallelTests(ToolpackCase):
    def counter_argv(
        self,
        counter_rel,
        *,
        artifact_rel="artifacts/out.bin",
        payload=b"artifact",
        fail=False,
        sleep=0.0,
    ):
        lines = ["from pathlib import Path", "import sys", "import time"]
        if sleep:
            lines.append(f"time.sleep({sleep})")
        if counter_rel:
            lines.extend(
                [
                    f"counter = Path({counter_rel!r})",
                    "counter.write_text((counter.read_text() if counter.exists() else '') + 'x')",
                ]
            )
        lines.extend(
            [
                f"artifact = Path({artifact_rel!r})",
                "artifact.parent.mkdir(parents=True, exist_ok=True)",
                f"artifact.write_bytes({payload!r})",
            ]
        )
        if fail:
            lines.append("sys.exit(1)")
        lines.append("print('TOOLPACK_OK')")
        return python_argv("\n".join(lines))

    def cached_manifest(self, *, counter_rel="counter.txt", fail=False):
        action = make_action(
            "run",
            argv=self.counter_argv(counter_rel, fail=fail),
            artifacts=["artifacts/out.bin"],
            cache={"inputs": [], "artifacts": ["artifacts/out.bin"]},
        )
        validators = [
            {"id": "file", "kind": "file", "artifact": "artifacts/out.bin", "minBytes": 1}
        ]
        return make_manifest([action], validators=validators)

    def test_action_cache_hit_skips_command_and_restores_artifact(self):
        manifest = self.cached_manifest()
        first = self.run_action(manifest)
        self.assertTrue(first["passed"], first)
        self.assertFalse(first["cache"]["hit"])
        self.assertTrue(first["cache"]["stored"])
        self.assertEqual((self.project / "counter.txt").read_text(encoding="utf-8"), "x")
        (self.project / "artifacts" / "out.bin").unlink()
        second = self.run_action(manifest)
        self.assertTrue(second["passed"], second)
        self.assertTrue(second["cache"]["hit"])
        self.assertEqual(second["cache"]["restored"], ["artifacts/out.bin"])
        self.assertEqual((self.project / "counter.txt").read_text(encoding="utf-8"), "x")
        self.assertTrue((self.project / "artifacts" / "out.bin").is_file())
        self.assertTrue(second["validators"])
        self.assertTrue(all(validator["passed"] for validator in second["validators"]))
        action_state = self.read_state(second)
        self.assertTrue(action_state["cache"]["hit"])

    def test_changed_input_misses(self):
        manifest = self.cached_manifest()
        manifest["actions"][0]["cache"] = {
            "inputs": ["src/in.txt"],
            "artifacts": ["artifacts/out.bin"],
        }
        self.write("src/in.txt", "v1")
        self.run_action(manifest)
        self.write("src/in.txt", "v2")
        changed = self.run_action(manifest)
        self.assertTrue(changed["passed"])
        self.assertFalse(changed["cache"]["hit"])
        self.assertEqual((self.project / "counter.txt").read_text(encoding="utf-8"), "xx")

    def test_failure_is_not_cached(self):
        manifest = self.cached_manifest(fail=True)
        first = self.run_action(manifest)
        self.assertFalse(first["passed"])
        self.assertFalse(first["cache"]["stored"])
        second = self.run_action(manifest)
        self.assertFalse(second["passed"])
        self.assertFalse(second["cache"]["hit"])
        self.assertEqual((self.project / "counter.txt").read_text(encoding="utf-8"), "xx")

    def test_force_bypasses_the_lookup(self):
        manifest = self.cached_manifest()
        self.run_action(manifest)
        forced = self.run_action(manifest, force=True)
        self.assertTrue(forced["passed"])
        self.assertFalse(forced["cache"]["hit"])
        self.assertTrue(forced["cache"]["stored"])
        self.assertEqual((self.project / "counter.txt").read_text(encoding="utf-8"), "xx")

    def test_no_cache_switch_disables_the_cache(self):
        manifest = self.cached_manifest()
        first = self.run_action(manifest, cache_enabled=False)
        self.assertTrue(first["passed"])
        self.assertFalse(first["cache"]["hit"])
        self.assertIn("disabled", first["cache"]["error"])
        self.run_action(manifest, cache_enabled=False)
        self.assertEqual((self.project / "counter.txt").read_text(encoding="utf-8"), "xx")

    def test_invalid_cache_config_is_rejected(self):
        action = make_action(
            "run",
            argv=self.counter_argv("counter.txt"),
            cache={"inputs": [], "artifacts": ["../escape.bin"]},
        )
        manifest = make_manifest([action])
        errors = toolpacks.validate_manifest(manifest)
        self.assertTrue(any("cache" in error for error in errors), errors)
        with self.assertRaises(toolpacks.ToolpackError):
            self.run_action(manifest)

    def test_parallel_actions_overlap(self):
        stamps = self.project / "stamps"
        actions = []
        for action_id in ("a", "b"):
            code = (
                "import time\n"
                "from pathlib import Path\n"
                "time.sleep(0.25)\n"
                f"Path({str(stamps / (action_id + '.txt'))!r}).parent.mkdir(parents=True, exist_ok=True)\n"
                f"Path({str(stamps / (action_id + '.txt'))!r}).write_text(str(time.time()))\n"
                "print('TOOLPACK_OK')\n"
            )
            actions.append(make_action(action_id, argv=python_argv(code), timeout=30))
        result = self.run_toolpack(make_manifest(actions), max_workers=2)
        self.assertTrue(result["passed"], result)
        self.assertEqual(result["parallel"]["workers"], 2)
        first = float((stamps / "a.txt").read_text())
        second = float((stamps / "b.txt").read_text())
        self.assertLess(abs(first - second), 0.2)

    def test_parallel_failure_cancels_pending_and_keeps_order(self):
        actions = [
            make_action("first", argv=python_argv("import sys; sys.exit(1)")),
            make_action(
                "second", argv=python_argv("import time; time.sleep(0.2)"), timeout=10
            ),
            make_action("third", argv=python_argv("print('TOOLPACK_OK')")),
        ]
        result = self.run_toolpack(make_manifest(actions), max_workers=2)
        self.assertFalse(result["passed"])
        self.assertEqual(result["actionOrder"], ["first", "second", "third"])
        self.assertEqual(
            [summary["status"] for summary in result["actions"]],
            ["failed", "passed", "not-run"],
        )
        self.assertTrue(result["parallel"]["cancelled"])
        self.assertEqual(result["parallel"]["cancelledActions"], ["third"])
        self.assertEqual(
            result["parallel"]["log"],
            ["first: failed", "second: passed", "third: not-run"],
        )

    def test_state_exposes_parallel_and_cache(self):
        actions = [
            make_action("first", argv=python_argv("print('TOOLPACK_OK')")),
            make_action("second", argv=python_argv("print('TOOLPACK_OK')")),
        ]
        result = self.run_toolpack(make_manifest(actions), max_workers=2)
        self.assertTrue(result["passed"])
        document = self.read_state(result)
        self.assertEqual(document["parallel"]["workers"], 2)
        self.assertTrue(document["cache"]["enabled"])
        self.assertEqual(
            [summary["cache"] for summary in document["actions"]], [None, None]
        )

    def test_worker_bounds_are_rejected(self):
        for bad in (0, 9):
            with self.assertRaises(toolpacks.ToolpackError):
                self.run_toolpack(make_manifest(), max_workers=bad)


if __name__ == "__main__":
    unittest.main()
