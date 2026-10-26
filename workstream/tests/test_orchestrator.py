#!/usr/bin/env python3
"""Tests for the Phase-2 slice manifests and orchestrator (docs/ADR-010-slice-orchestrator.md).

No Godot, network or real game build is used: every step kind except the command-handler
tests runs through injected fake handlers against temporary manifests and state directories.
"""
from __future__ import annotations

import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

WORKSTREAM = Path(__file__).resolve().parents[1]
REPO_ROOT = WORKSTREAM.parent
sys.path.insert(0, str(WORKSTREAM))

import orchestrator  # noqa: E402
import slices  # noqa: E402


def make_manifest(steps, *, slice_id="sample", project=".", artifacts=None):
    return {
        "schema": slices.SCHEMA,
        "id": slice_id,
        "project": project,
        "artifacts": list(artifacts or []),
        "steps": steps,
    }


def make_step(step_id, *, kind="tests", needs=None, required=True, timeout=5, args=None):
    return {
        "id": step_id,
        "kind": kind,
        "needs": list(needs or []),
        "required": required,
        "timeout": timeout,
        "args": dict(args or {}),
    }


class FakeHandlers:
    """A handler for the 'tests' kind that records calls and can fail selected step ids."""

    def __init__(self, failures=()):
        self.failures = set(failures)
        self.calls = []
        self.contexts = []

    def __call__(self, step, context):
        self.calls.append(step["id"])
        self.contexts.append(context)
        if step["id"] in self.failures:
            return {"passed": False, "output": "boom " + step["id"]}
        return {"passed": True, "output": "ok " + step["id"]}

    def registry(self):
        return {"tests": self}


class OrchestratorCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.project = self.root
        self.state = self.root / "state"

    def run_manifest(self, manifest, **kwargs):
        return orchestrator.run_slice(
            manifest,
            project_root=self.project,
            state_dir=self.state,
            **kwargs,
        )

    def load_state(self, slice_id):
        path = slices.step_state_path(self.state, slice_id)
        return json.loads(path.read_text(encoding="utf-8"))


class SchemaTests(unittest.TestCase):
    def test_valid_manifest_has_no_errors(self):
        manifest = make_manifest([make_step("a")])
        self.assertEqual(slices.validate_manifest(manifest), [])

    def test_wrong_schema_is_reported(self):
        manifest = make_manifest([make_step("a")])
        manifest["schema"] = "gypsy.slice/v2"
        self.assertTrue(any("schema" in error for error in slices.validate_manifest(manifest)))

    def test_duplicate_step_ids_are_reported(self):
        manifest = make_manifest([make_step("a"), make_step("a")])
        errors = slices.validate_manifest(manifest)
        self.assertTrue(any("duplicate" in error.lower() for error in errors))

    def test_unknown_kind_is_reported(self):
        manifest = make_manifest([make_step("a", kind="game.explode")])
        errors = slices.validate_manifest(manifest)
        self.assertTrue(any("unknown kind" in error for error in errors))

    def test_missing_need_is_reported(self):
        manifest = make_manifest([make_step("a", needs=["nope"])])
        errors = slices.validate_manifest(manifest)
        self.assertTrue(any("unknown step" in error for error in errors))

    def test_cycle_is_reported(self):
        manifest = make_manifest(
            [make_step("a", needs=["b"]), make_step("b", needs=["a"])]
        )
        self.assertTrue(any("cycle" in error for error in slices.validate_manifest(manifest)))

    def test_artifact_paths_must_stay_inside_the_tree(self):
        manifest = make_manifest([make_step("a")], artifacts=["../escape.bin"])
        errors = slices.validate_manifest(manifest)
        self.assertTrue(any("repo-relative" in error for error in errors))
        with tempfile.TemporaryDirectory() as tmp:
            absolute = str(Path(tmp) / "out.bin")
            manifest = make_manifest([make_step("a")], artifacts=[absolute])
            errors = slices.validate_manifest(manifest)
            self.assertTrue(any("repo-relative" in error for error in errors))

    def test_bad_step_fields_are_reported(self):
        manifest = make_manifest(
            [
                make_step("a", required="yes"),
                make_step("b", timeout=0),
                {
                    "id": "c",
                    "kind": "tests",
                    "needs": [],
                    "required": True,
                    "timeout": 5,
                    "args": [],
                },
                "not-an-object",
            ]
        )
        errors = slices.validate_manifest(manifest)
        self.assertTrue(any("required must be" in error for error in errors))
        self.assertTrue(any("timeout must be" in error for error in errors))
        self.assertTrue(any("args must be" in error for error in errors))
        self.assertTrue(any("must be an object" in error for error in errors))

    def test_empty_steps_is_reported(self):
        errors = slices.validate_manifest(make_manifest([]))
        self.assertTrue(any("non-empty" in error for error in errors))


class OrderTests(unittest.TestCase):
    def test_stable_topological_order(self):
        manifest = make_manifest(
            [make_step("c", needs=["a"]), make_step("b"), make_step("a")]
        )
        self.assertEqual(slices.resolve_order(manifest), ["b", "a", "c"])

    def test_independent_steps_keep_declaration_order(self):
        manifest = make_manifest([make_step("z"), make_step("y"), make_step("x")])
        self.assertEqual(slices.resolve_order(manifest), ["z", "y", "x"])

    def test_later_declared_dependency_runs_first(self):
        manifest = make_manifest([make_step("b", needs=["a"]), make_step("a")])
        self.assertEqual(slices.resolve_order(manifest), ["a", "b"])

    def test_cycle_raises(self):
        manifest = make_manifest(
            [make_step("a", needs=["b"]), make_step("b", needs=["a"])]
        )
        with self.assertRaises(slices.SliceError):
            slices.resolve_order(manifest)

    def test_missing_need_raises(self):
        manifest = make_manifest([make_step("a", needs=["nope"])])
        with self.assertRaises(slices.SliceError):
            slices.resolve_order(manifest)


class LoadTests(unittest.TestCase):
    def test_load_manifest_rejects_invalid_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.json"
            path.write_text("{not json", encoding="utf-8")
            with self.assertRaises(slices.SliceError):
                slices.load_manifest(path)

    def test_load_all_keys_by_id_and_rejects_duplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / "a.json").write_text(
                json.dumps(make_manifest([make_step("a")], slice_id="alpha")),
                encoding="utf-8",
            )
            (directory / "b.json").write_text(
                json.dumps(make_manifest([make_step("b")], slice_id="beta")),
                encoding="utf-8",
            )
            loaded = slices.load_all(directory)
            self.assertEqual(list(loaded), ["alpha", "beta"])
            (directory / "c.json").write_text(
                json.dumps(make_manifest([make_step("c")], slice_id="alpha")),
                encoding="utf-8",
            )
            with self.assertRaises(slices.SliceError):
                slices.load_all(directory)

    def test_step_state_path(self):
        self.assertEqual(
            slices.step_state_path(Path("workstream/state"), "phase1"),
            Path("workstream/state/slices/phase1.json"),
        )
        with self.assertRaises(slices.SliceError):
            slices.step_state_path(Path("state"), "../escape")


class ManifestFileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifests = slices.load_all(REPO_ROOT / "slices")

    def test_repository_manifests_load_and_validate(self):
        self.assertEqual(set(self.manifests), {"phase1", "quality", "toolpacks", "mobile"})
        for slice_id, manifest in self.manifests.items():
            self.assertEqual(slices.validate_manifest(manifest), [], slice_id)
            self.assertEqual(manifest["schema"], "gypsy.slice/v1")

    def test_phase1_manifest_shape(self):
        manifest = self.manifests["phase1"]
        self.assertEqual(manifest["id"], "phase1")
        self.assertEqual(manifest["project"], "game")
        self.assertEqual(slices.resolve_order(manifest), ["demo", "build", "capture"])
        kinds = {step["id"]: step["kind"] for step in manifest["steps"]}
        self.assertEqual(
            kinds,
            {"demo": "game.demo", "build": "game.build", "capture": "game.capture"},
        )
        by_id = {step["id"]: step for step in manifest["steps"]}
        self.assertEqual(by_id["build"]["needs"], ["demo"])
        self.assertEqual(by_id["capture"]["needs"], ["build"])
        self.assertEqual(
            manifest["artifacts"],
            [
                "build/ProjectGypsy.exe",
                "artifacts/game/demo.mp4",
                "artifacts/game/frame.png",
            ],
        )

    def test_quality_manifest_shape(self):
        manifest = self.manifests["quality"]
        self.assertEqual(manifest["id"], "quality")
        self.assertEqual(slices.resolve_order(manifest), ["check", "tests", "records"])
        kinds = {step["id"]: step["kind"] for step in manifest["steps"]}
        self.assertEqual(
            kinds, {"check": "check_all", "tests": "tests", "records": "records"}
        )
        by_id = {step["id"]: step for step in manifest["steps"]}
        self.assertEqual(by_id["tests"]["needs"], ["check"])
        self.assertEqual(by_id["records"]["needs"], ["tests"])
        self.assertEqual(manifest["artifacts"], [])

    def test_handlers_cover_every_schema_kind(self):
        self.assertEqual(set(orchestrator.HANDLERS), set(slices.STEP_KINDS))
        for handler in orchestrator.HANDLERS.values():
            self.assertTrue(callable(handler))


class RunSliceTests(OrchestratorCase):
    def test_successful_slice_writes_atomic_state_and_json_safe_result(self):
        manifest = make_manifest(
            [
                make_step("deploy", needs=["build"]),
                make_step("build", needs=["test"]),
                make_step("test"),
            ]
        )
        fake = FakeHandlers()
        result = self.run_manifest(manifest, handlers=fake.registry())
        self.assertTrue(result["passed"])
        self.assertEqual(result["slice"], "sample")
        self.assertEqual([step["id"] for step in result["steps"]], ["test", "build", "deploy"])
        self.assertEqual(fake.calls, ["test", "build", "deploy"])
        self.assertTrue(all(step["status"] == "passed" for step in result["steps"]))
        self.assertEqual(result["artifacts"], [])
        self.assertTrue(Path(result["statePath"]).is_file())
        json.dumps(result)  # the whole result must be JSON-safe
        state = self.load_state("sample")
        self.assertEqual(state["manifestSha256"], result["manifestSha256"])
        self.assertEqual(state["runId"], result["runId"])
        self.assertEqual(state["stepOrder"], ["test", "build", "deploy"])
        self.assertEqual([step["status"] for step in state["steps"]], ["passed"] * 3)
        self.assertTrue(all(step["seconds"] >= 0 for step in state["steps"]))
        leftovers = sorted(path.name for path in (self.state / "slices").iterdir())
        self.assertEqual(leftovers, ["sample.json"])

    def test_invalid_manifest_raises_before_writing_state(self):
        manifest = make_manifest([make_step("a", kind="nope")])
        with self.assertRaises(slices.SliceError):
            self.run_manifest(manifest, handlers=FakeHandlers().registry())
        self.assertFalse(slices.step_state_path(self.state, "sample").exists())

    def test_required_failure_skips_dependents_but_runs_independent_steps(self):
        manifest = make_manifest(
            [
                make_step("a"),
                make_step("b", needs=["a"]),
                make_step("c", needs=["b"]),
                make_step("d"),
            ]
        )
        fake = FakeHandlers(failures={"a"})
        result = self.run_manifest(manifest, handlers=fake.registry())
        self.assertFalse(result["passed"])
        statuses = {step["id"]: step["status"] for step in result["steps"]}
        self.assertEqual(
            statuses, {"a": "failed", "b": "skipped", "c": "skipped", "d": "passed"}
        )
        self.assertEqual(fake.calls, ["a", "d"])
        self.assertTrue(any("'a' failed" in error for error in result["errors"]))
        state = self.load_state("sample")
        self.assertFalse(state["passed"])
        self.assertEqual(
            {step["id"]: step["status"] for step in state["steps"]}, statuses
        )

    def test_optional_failure_does_not_fail_the_slice(self):
        manifest = make_manifest([make_step("opt", required=False), make_step("main")])
        fake = FakeHandlers(failures={"opt"})
        result = self.run_manifest(manifest, handlers=fake.registry())
        self.assertTrue(result["passed"])
        statuses = {step["id"]: step["status"] for step in result["steps"]}
        self.assertEqual(statuses, {"opt": "failed", "main": "passed"})

    def test_required_dependent_of_failed_optional_step_is_skipped_and_fails(self):
        manifest = make_manifest(
            [make_step("opt", required=False), make_step("after", needs=["opt"])]
        )
        result = self.run_manifest(manifest, handlers=FakeHandlers(failures={"opt"}).registry())
        self.assertFalse(result["passed"])
        statuses = {step["id"]: step["status"] for step in result["steps"]}
        self.assertEqual(statuses, {"opt": "failed", "after": "skipped"})

    def test_timeout_scale_and_context_reach_the_handler(self):
        captured = {}

        def handler(step, context):
            captured.update(context)
            return {"passed": True}

        manifest = make_manifest([make_step("s", timeout=7)], project="game")
        result = self.run_manifest(
            manifest, handlers={"tests": handler}, timeout_scale=2.0
        )
        self.assertTrue(result["passed"])
        self.assertEqual(captured["timeout"], 14.0)
        self.assertEqual(captured["project_root"], self.project)
        self.assertEqual(captured["project_dir"], self.project / "game")
        self.assertEqual(captured["slice_id"], "sample")
        self.assertEqual(captured["step_id"], "s")
        self.assertIn("run_id", captured)


class ResumeTests(OrchestratorCase):
    def test_resume_skips_steps_that_passed_under_the_same_manifest(self):
        manifest = make_manifest([make_step("a"), make_step("b", needs=["a"])])
        first = FakeHandlers()
        first_result = self.run_manifest(manifest, handlers=first.registry())
        self.assertTrue(first_result["passed"])
        second = FakeHandlers()
        second_result = self.run_manifest(manifest, resume=True, handlers=second.registry())
        self.assertTrue(second_result["passed"])
        self.assertEqual(second.calls, [])
        self.assertTrue(all(step["cached"] for step in second_result["steps"]))
        self.assertTrue(all(not step["attempted"] for step in second_result["steps"]))
        self.assertEqual(second_result["manifestSha256"], first_result["manifestSha256"])
        self.assertEqual(second_result["statePath"], first_result["statePath"])
        self.assertTrue(second_result["resumed"])

    def test_force_ignores_previous_state(self):
        manifest = make_manifest([make_step("a")])
        first = FakeHandlers()
        self.run_manifest(manifest, handlers=first.registry())
        second = FakeHandlers()
        result = self.run_manifest(
            manifest, resume=True, force=True, handlers=second.registry()
        )
        self.assertTrue(result["passed"])
        self.assertEqual(second.calls, ["a"])
        self.assertFalse(any(step["cached"] for step in result["steps"]))
        self.assertFalse(result["resumed"])

    def test_resume_is_ignored_when_the_manifest_changed(self):
        manifest = make_manifest([make_step("a")])
        self.run_manifest(manifest, handlers=FakeHandlers().registry())
        changed = copy.deepcopy(manifest)
        changed["steps"][0]["timeout"] = 6
        second = FakeHandlers()
        result = self.run_manifest(changed, resume=True, handlers=second.registry())
        self.assertTrue(result["passed"])
        self.assertEqual(second.calls, ["a"])
        self.assertFalse(result["resumed"])
        self.assertIn("manifest changed", result["resumeIgnored"])


class ArtifactTests(OrchestratorCase):
    def test_artifacts_are_hashed_and_ledgered(self):
        payload = b"gypsy-artifact"
        target = self.project / "artifacts" / "out.bin"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        manifest = make_manifest([make_step("build")], artifacts=["artifacts/out.bin"])
        result = self.run_manifest(manifest, handlers=FakeHandlers().registry())
        self.assertTrue(result["passed"])
        entry = result["artifacts"][0]
        self.assertEqual(entry["path"], "artifacts/out.bin")
        self.assertTrue(entry["exists"])
        self.assertEqual(entry["sha256"], hashlib.sha256(payload).hexdigest())
        self.assertEqual(entry["bytes"], len(payload))
        ledger_path = Path(result["ledgerPath"])
        self.assertTrue(ledger_path.is_file())
        self.assertTrue(ledger_path.name.startswith("sample-"))
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        self.assertEqual(ledger["schema"], "gypsy.artifact-ledger/v1")
        self.assertEqual(ledger["runId"], result["runId"])
        self.assertEqual(ledger["manifestSha256"], result["manifestSha256"])
        self.assertTrue(ledger["passed"])
        self.assertEqual(ledger["artifacts"], result["artifacts"])
        state = self.load_state("sample")
        self.assertEqual(state["artifacts"], result["artifacts"])
        self.assertEqual(state["ledgerPath"], result["ledgerPath"])

    def test_missing_artifact_fails_the_slice_and_is_ledgered(self):
        manifest = make_manifest([make_step("build")], artifacts=["artifacts/missing.bin"])
        result = self.run_manifest(manifest, handlers=FakeHandlers().registry())
        self.assertFalse(result["passed"])
        entry = result["artifacts"][0]
        self.assertFalse(entry["exists"])
        self.assertIsNone(entry["sha256"])
        self.assertIsNone(entry["bytes"])
        self.assertTrue(any("missing declared artifact" in error for error in result["errors"]))
        ledger = json.loads(Path(result["ledgerPath"]).read_text(encoding="utf-8"))
        self.assertFalse(ledger["passed"])
        self.assertEqual(ledger["artifacts"], result["artifacts"])
        self.assertFalse(self.load_state("sample")["passed"])

    def test_failed_step_writes_no_artifact_ledger(self):
        manifest = make_manifest(
            [make_step("build")], artifacts=["artifacts/missing.bin"]
        )
        result = self.run_manifest(
            manifest, handlers=FakeHandlers(failures={"build"}).registry()
        )
        self.assertFalse(result["passed"])
        self.assertEqual(result["artifacts"], [])
        self.assertIsNone(result["ledgerPath"])
        self.assertFalse((self.state / "artifacts").exists())


class RunTaskTests(OrchestratorCase):
    def test_multi_slice_aggregate_and_report(self):
        payload = b"beta-artifact"
        target = self.project / "artifacts" / "beta.bin"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        alpha = make_manifest(
            [make_step("a1"), make_step("a2", needs=["a1"])], slice_id="alpha"
        )
        beta = make_manifest(
            [make_step("b1")], slice_id="beta", artifacts=["artifacts/beta.bin"]
        )
        fake = FakeHandlers()
        result = orchestrator.run_task(
            {"alpha": alpha, "beta": beta},
            project_root=self.project,
            state_dir=self.state,
            handlers=fake.registry(),
        )
        self.assertTrue(result["passed"])
        self.assertEqual(result["sliceOrder"], ["alpha", "beta"])
        self.assertEqual(result["steps"], {"total": 3, "passed": 3, "failed": 0, "skipped": 0})
        self.assertEqual([summary["status"] for summary in result["slices"]], ["passed", "passed"])
        self.assertEqual(fake.calls, ["a1", "a2", "b1"])
        self.assertEqual(len(result["artifacts"]), 1)
        self.assertEqual(result["artifacts"][0]["slice"], "beta")
        self.assertEqual(result["artifacts"][0]["sha256"], hashlib.sha256(payload).hexdigest())
        task_path = Path(result["statePath"])
        self.assertTrue(task_path.is_file())
        self.assertRegex(task_path.name, r"^task-\d{8}T\d{6}Z(-\d+)?\.json$")
        document = json.loads(task_path.read_text(encoding="utf-8"))
        self.assertEqual(document["schema"], "gypsy.task-state/v1")
        self.assertTrue(document["passed"])
        self.assertEqual(document["steps"], result["steps"])
        self.assertEqual(document["artifacts"], result["artifacts"])
        self.assertTrue(document["report"])
        self.assertTrue(any("alpha" in line for line in document["report"]))
        json.dumps(result)

    def test_failed_slice_stops_later_slices(self):
        alpha = make_manifest([make_step("a1")], slice_id="alpha")
        beta = make_manifest([make_step("b1")], slice_id="beta")
        fake = FakeHandlers(failures={"a1"})
        result = orchestrator.run_task(
            [alpha, beta],
            project_root=self.project,
            state_dir=self.state,
            handlers=fake.registry(),
        )
        self.assertFalse(result["passed"])
        self.assertEqual(fake.calls, ["a1"])
        self.assertEqual(result["slices"][0]["status"], "failed")
        self.assertEqual(result["slices"][1]["status"], "not-run")
        self.assertIsNone(result["slices"][1]["passed"])
        self.assertEqual(result["steps"], {"total": 1, "passed": 0, "failed": 1, "skipped": 0})
        self.assertTrue(any("not run" in line for line in result["report"]))

    def test_duplicate_slice_ids_are_rejected_before_running(self):
        alpha = make_manifest([make_step("a1")], slice_id="alpha")
        duplicate = make_manifest([make_step("a2")], slice_id="alpha")
        fake = FakeHandlers()
        with self.assertRaises(slices.SliceError):
            orchestrator.run_task(
                [alpha, duplicate],
                project_root=self.project,
                state_dir=self.state,
                handlers=fake.registry(),
            )
        self.assertEqual(fake.calls, [])
        self.assertFalse(self.state.exists())


class DefaultHandlerTests(OrchestratorCase):
    def test_command_handler_runs_an_explicit_argv_without_a_shell(self):
        manifest = make_manifest(
            [
                make_step(
                    "say",
                    kind="command",
                    args={
                        "argv": [sys.executable, "-c", "print('COMMAND_OK')"],
                        "cwd": ".",
                    },
                )
            ]
        )
        result = self.run_manifest(manifest)
        self.assertTrue(result["passed"])
        step = result["steps"][0]
        self.assertEqual(step["exit"], 0)
        self.assertIn("COMMAND_OK", step["output"])

    def test_command_handler_reports_a_nonzero_exit(self):
        manifest = make_manifest(
            [
                make_step(
                    "fail",
                    kind="command",
                    args={"argv": [sys.executable, "-c", "import sys; sys.exit(3)"]},
                )
            ]
        )
        result = self.run_manifest(manifest)
        self.assertFalse(result["passed"])
        self.assertEqual(result["steps"][0]["exit"], 3)

    def test_command_handler_refuses_a_shell_string(self):
        manifest = make_manifest(
            [make_step("say", kind="command", args={"argv": "echo hello"})]
        )
        result = self.run_manifest(manifest)
        self.assertFalse(result["passed"])
        self.assertIn("explicit list", result["steps"][0]["error"] or "")


if __name__ == "__main__":
    unittest.main()