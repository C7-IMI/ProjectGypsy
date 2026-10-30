#!/usr/bin/env python3
"""Tests for the visual regression and performance-budget quality gates.

Pillow-dependent tests are skipped when Pillow is not installed; the explicit
dependency-failure path is tested without importing Pillow. No Godot, network or real capture
is used: images and benchmark JSON are generated in temporary directories.
"""
from __future__ import annotations

import hashlib
import json
import os
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

WORKSTREAM = Path(__file__).resolve().parents[1]
REPO_ROOT = WORKSTREAM.parent
sys.path.insert(0, str(WORKSTREAM))

import quality  # noqa: E402
import slices  # noqa: E402
import toolpacks  # noqa: E402

PILLOW_AVAILABLE = quality.pillow_available()
PILLOW_REQUIRED = unittest.skipUnless(
    PILLOW_AVAILABLE, "Pillow is not installed; visual gate tests need it"
)

FRAME_ARTIFACT = "artifacts/game/frame.png"
BASELINE_ARTIFACT = "assets/test/baselines/game-frame.png"
BENCH_ARTIFACT = "workstream/state/game-benchmark.json"
REPORT_ARTIFACT = "workstream/state/quality/gate.json"


def make_image(path, size=(16, 16), color=(0, 0, 0), pixels=None):
    from PIL import Image

    image = Image.new("RGB", size, color)
    for position, pixel in (pixels or {}).items():
        image.putpixel(position, pixel)
    image.save(path)
    return path


def good_benchmark():
    return {
        "schema": "gypsy.artifact/v1",
        "kind": "game.benchmark",
        "engine": "godot",
        "runs": 3,
        "demos": [
            {"seconds": 2.5, "frames": 143, "passed": True},
            {"seconds": 2.6, "frames": 143, "passed": True},
            {"seconds": 2.4, "frames": 143, "passed": True},
        ],
        "medianSeconds": 2.5,
        "p95Seconds": 2.6,
        "captureGpuMsPerFrame": 0.8,
        "captureError": None,
        "logicPassed": True,
        "renderPassed": True,
        "passed": True,
    }


class TempCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.baseline = self.root / "baseline.png"
        self.frame = self.root / "frame.png"
        self.bench = self.root / "bench.json"
        self.report = self.root / "gate.json"

    def write_json(self, path, payload):
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path


class VisualGateTests(TempCase):
    @PILLOW_REQUIRED
    def test_identical_images_pass_with_zero_ratio(self):
        make_image(self.baseline)
        make_image(self.frame)
        result = quality.compare_images(self.baseline, self.frame)
        self.assertTrue(result["passed"])
        self.assertEqual(result["changedPixels"], 0)
        self.assertEqual(result["changedRatio"], 0.0)
        self.assertEqual(result["totalPixels"], 256)
        self.assertEqual(result["dimensions"], {"width": 16, "height": 16})
        self.assertEqual(result["maxChangedRatio"], quality.DEFAULT_MAX_CHANGED_RATIO)
        self.assertIsNone(result["reason"])
        self.assertEqual(result["kind"], "visual")

    @PILLOW_REQUIRED
    def test_changed_ratio_is_measured_and_threshold_is_enforced(self):
        make_image(self.baseline, size=(10, 10))
        make_image(self.frame, size=(10, 10), pixels={(0, 0): (255, 255, 255)})
        failed = quality.compare_images(
            self.baseline, self.frame, max_changed_ratio=0.005
        )
        self.assertEqual(failed["changedPixels"], 1)
        self.assertEqual(failed["totalPixels"], 100)
        self.assertAlmostEqual(failed["changedRatio"], 0.01)
        self.assertFalse(failed["passed"])
        self.assertIn("exceeds maxChangedRatio", failed["reason"])
        boundary = quality.compare_images(
            self.baseline, self.frame, max_changed_ratio=0.01
        )
        self.assertTrue(boundary["passed"], "the threshold is inclusive")

    @PILLOW_REQUIRED
    def test_dimension_mismatch_fails_instead_of_skipping(self):
        make_image(self.baseline, size=(10, 10))
        make_image(self.frame, size=(8, 10))
        result = quality.compare_images(self.baseline, self.frame)
        self.assertFalse(result["passed"])
        self.assertEqual(result["baselineDimensions"], {"width": 10, "height": 10})
        self.assertEqual(result["candidateDimensions"], {"width": 8, "height": 10})
        self.assertIsNone(result["changedRatio"])
        self.assertIn("dimensions differ", result["reason"])

    @PILLOW_REQUIRED
    def test_channel_tolerance_controls_small_differences(self):
        make_image(self.baseline, size=(4, 4))
        make_image(self.frame, size=(4, 4), pixels={(0, 0): (0, 0, 2)})
        strict = quality.compare_images(self.baseline, self.frame, channel_tolerance=0)
        self.assertFalse(strict["passed"])
        self.assertEqual(strict["changedPixels"], 1)
        tolerant = quality.compare_images(self.baseline, self.frame, channel_tolerance=2)
        self.assertTrue(tolerant["passed"])
        self.assertEqual(tolerant["changedPixels"], 0)

    @PILLOW_REQUIRED
    def test_missing_and_unreadable_images_raise_quality_error(self):
        make_image(self.frame)
        with self.assertRaises(quality.QualityError):
            quality.compare_images(self.root / "missing.png", self.frame)
        make_image(self.baseline)
        self.frame.write_text("not an image", encoding="utf-8")
        with self.assertRaises(quality.QualityError):
            quality.compare_images(self.baseline, self.frame)

    @PILLOW_REQUIRED
    def test_invalid_thresholds_raise(self):
        make_image(self.baseline)
        make_image(self.frame)
        with self.assertRaises(quality.QualityError):
            quality.compare_images(self.baseline, self.frame, max_changed_ratio=1.5)
        with self.assertRaises(quality.QualityError):
            quality.compare_images(self.baseline, self.frame, max_changed_ratio=True)
        with self.assertRaises(quality.QualityError):
            quality.compare_images(self.baseline, self.frame, channel_tolerance=300)

    @PILLOW_REQUIRED
    def test_image_dimensions_and_sha256_helpers(self):
        make_image(self.baseline, size=(7, 3))
        self.assertEqual(
            quality.image_dimensions(self.baseline),
            {"width": 7, "height": 3, "mode": "RGB"},
        )
        expected = hashlib.sha256(self.baseline.read_bytes()).hexdigest()
        self.assertEqual(quality.sha256_file(self.baseline), expected)


class DependencyTests(TempCase):
    def test_compare_images_raises_explicit_dependency_error(self):
        self.frame.write_bytes(b"not read")
        self.baseline.write_bytes(b"not read")
        error = quality.QualityDependencyError("Pillow is required")
        with mock.patch.object(quality, "_import_pillow", side_effect=error):
            with self.assertRaises(quality.QualityDependencyError) as caught:
                quality.compare_images(self.baseline, self.frame)
        self.assertIn("Pillow", str(caught.exception))

    def test_run_quality_gate_reports_missing_pillow_without_hiding_performance(self):
        self.frame.write_bytes(b"not read")
        self.baseline.write_bytes(b"not read")
        self.write_json(self.bench, good_benchmark())
        error = quality.QualityDependencyError("Pillow is required for the visual gate")
        with mock.patch.object(quality, "_import_pillow", side_effect=error):
            report = quality.run_quality_gate(
                frame=self.frame, baseline=self.baseline, benchmark=self.bench
            )
        self.assertFalse(report["passed"])
        self.assertTrue(report["dependencyMissing"])
        self.assertFalse(report["visual"]["passed"])
        self.assertIn("Pillow", report["visual"]["error"])
        self.assertTrue(report["performance"]["passed"])
        self.assertIn("FAIL visual - Pillow", "\n".join(quality.render_report(report)))


class PerformanceGateTests(unittest.TestCase):
    def test_good_benchmark_passes(self):
        result = quality.check_performance(good_benchmark())
        self.assertTrue(result["passed"])
        self.assertEqual(result["failures"], [])
        self.assertEqual(
            result["metrics"]["medianSeconds"], good_benchmark()["medianSeconds"]
        )
        self.assertEqual(result["thresholds"]["maxMedianSeconds"], 5.0)
        self.assertEqual(result["thresholds"]["requiredFrames"], 143)
        self.assertEqual(
            [check["id"] for check in result["checks"]],
            ["medianSeconds", "p95Seconds", "captureGpuMsPerFrame", "demoFrames"],
        )

    def test_median_and_p95_over_budget_fail(self):
        benchmark = good_benchmark()
        benchmark["medianSeconds"] = 9.0
        benchmark["p95Seconds"] = 12.0
        result = quality.check_performance(benchmark)
        self.assertFalse(result["passed"])
        self.assertTrue(any("medianSeconds" in item for item in result["failures"]))
        self.assertTrue(any("p95Seconds" in item for item in result["failures"]))
        self.assertIn("exceeds budget", result["reason"])

    def test_missing_gpu_metric_fails(self):
        benchmark = good_benchmark()
        benchmark["captureGpuMsPerFrame"] = None
        result = quality.check_performance(benchmark)
        self.assertFalse(result["passed"])
        self.assertTrue(
            any("captureGpuMsPerFrame" in item for item in result["failures"])
        )

    def test_wrong_frames_or_failed_demo_fails(self):
        benchmark = good_benchmark()
        benchmark["demos"][0]["frames"] = 142
        benchmark["demos"][1]["passed"] = False
        result = quality.check_performance(benchmark)
        self.assertFalse(result["passed"])
        self.assertTrue(any("frames=142" in item for item in result["failures"]))
        self.assertTrue(any("demos[1] did not pass" in item for item in result["failures"]))

    def test_min_runs_is_enforced_when_set(self):
        benchmark = good_benchmark()
        benchmark["runs"] = 1
        self.assertFalse(quality.check_performance(benchmark, min_runs=3)["passed"])
        benchmark["runs"] = 3
        self.assertTrue(quality.check_performance(benchmark, min_runs=3)["passed"])

    def test_disabled_threshold_is_explicit_and_not_a_pass_claim(self):
        benchmark = good_benchmark()
        benchmark["captureGpuMsPerFrame"] = None
        result = quality.check_performance(benchmark, max_gpu_ms_per_frame=None)
        self.assertTrue(result["passed"])
        check = next(item for item in result["checks"] if item["id"] == "captureGpuMsPerFrame")
        self.assertIsNone(check["limit"])
        self.assertEqual(check["detail"], "threshold disabled")

    def test_invalid_thresholds_raise(self):
        for kwargs in (
            {"max_median_seconds": 0},
            {"max_p95_seconds": "8"},
            {"max_gpu_ms_per_frame": True},
            {"required_frames": 0},
            {"min_runs": 0},
        ):
            with self.assertRaises(quality.QualityError):
                quality.check_performance(good_benchmark(), **kwargs)

    def test_load_benchmark_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(quality.QualityError):
                quality.load_benchmark(root / "missing.json")
            bad = root / "bad.json"
            bad.write_text("{not json", encoding="utf-8")
            with self.assertRaises(quality.QualityError):
                quality.load_benchmark(bad)
            array = root / "array.json"
            array.write_text("[]", encoding="utf-8")
            with self.assertRaises(quality.QualityError):
                quality.load_benchmark(array)


class GateReportTests(TempCase):
    @PILLOW_REQUIRED
    def test_run_quality_gate_pass_and_fail_aggregate(self):
        make_image(self.baseline, size=(8, 8))
        make_image(self.frame, size=(8, 8))
        self.write_json(self.bench, good_benchmark())
        report = quality.run_quality_gate(
            frame=self.frame, baseline=self.baseline, benchmark=self.bench
        )
        self.assertEqual(report["schema"], quality.GATE_SCHEMA)
        self.assertTrue(report["passed"])
        self.assertFalse(report["dependencyMissing"])
        self.assertEqual(report["inputs"]["frame"], str(self.frame))
        self.assertTrue(report["visual"]["passed"])
        self.assertTrue(report["performance"]["passed"])

        make_image(self.frame, size=(8, 8), pixels={(0, 0): (255, 255, 255)})
        failed = quality.run_quality_gate(
            frame=self.frame,
            baseline=self.baseline,
            benchmark=self.bench,
            max_changed_ratio=0.0,
        )
        self.assertFalse(failed["passed"])
        self.assertFalse(failed["visual"]["passed"])
        self.assertTrue(failed["performance"]["passed"])

    def test_missing_inputs_are_failures_not_crashes(self):
        report = quality.run_quality_gate(
            frame=self.root / "no-frame.png",
            baseline=self.root / "no-baseline.png",
            benchmark=self.root / "no-bench.json",
        )
        self.assertFalse(report["passed"])
        self.assertIn("not found", report["visual"]["error"])
        self.assertIn("not found", report["performance"]["error"])

    @PILLOW_REQUIRED
    def test_write_report_is_atomic_and_json_safe(self):
        make_image(self.baseline)
        make_image(self.frame)
        self.write_json(self.bench, good_benchmark())
        report = quality.run_quality_gate(
            frame=self.frame, baseline=self.baseline, benchmark=self.bench
        )
        path = quality.write_report(self.report, report)
        self.assertEqual(path, self.report)
        stored = json.loads(self.report.read_text(encoding="utf-8"))
        self.assertEqual(stored, report)
        leftovers = [item.name for item in self.root.iterdir() if item.name.endswith(".tmp")]
        self.assertEqual(leftovers, [])

    @PILLOW_REQUIRED
    def test_render_report_has_one_line_per_gate_and_a_final_verdict(self):
        make_image(self.baseline)
        make_image(self.frame)
        self.write_json(self.bench, good_benchmark())
        report = quality.run_quality_gate(
            frame=self.frame, baseline=self.baseline, benchmark=self.bench
        )
        lines = quality.render_report(report)
        self.assertTrue(lines[0].startswith("PASS visual - 16x16"))
        self.assertTrue(lines[1].startswith("PASS performance"))
        self.assertEqual(lines[-1], "QUALITY GATE PASS")


class RepositoryWiringTests(unittest.TestCase):
    def test_tracked_baseline_is_a_1280x720_png_with_provenance(self):
        baseline = REPO_ROOT / BASELINE_ARTIFACT
        self.assertTrue(baseline.is_file(), baseline)
        data = baseline.read_bytes()
        self.assertTrue(data.startswith(b"\x89PNG\r\n\x1a\n"))
        width, height = struct.unpack(">II", data[16:24])
        self.assertEqual((width, height), (1280, 720))
        metadata = json.loads(
            baseline.with_suffix(".json").read_text(encoding="utf-8")
        )
        self.assertEqual(metadata["schema"], quality.BASELINE_SCHEMA)
        self.assertEqual(metadata["baseline"], baseline.name)
        self.assertEqual(metadata["dimensions"]["width"], 1280)
        self.assertEqual(metadata["dimensions"]["height"], 720)
        self.assertEqual(metadata["baselineSha256"], quality.sha256_file(baseline))

    def test_quality_toolpack_manifest_is_valid_and_references_the_gate(self):
        manifest = toolpacks.load_manifest(REPO_ROOT / "toolpacks" / "quality.visual.json")
        self.assertEqual(toolpacks.validate_manifest(manifest), [])
        self.assertEqual(manifest["id"], "quality.visual")
        actions = {action["id"]: action for action in manifest["actions"]}
        self.assertEqual(list(actions), ["capture", "bench", "gate"])
        self.assertIn("scripts/quality_gate.py", actions["gate"]["argv"])
        self.assertIn("--baseline", actions["gate"]["argv"])
        self.assertIn(BASELINE_ARTIFACT, actions["gate"]["argv"])
        declared = [artifact for action in manifest["actions"] for artifact in action.get("artifacts", [])]
        self.assertIn(FRAME_ARTIFACT, declared)
        self.assertIn(BENCH_ARTIFACT, declared)
        self.assertIn(REPORT_ARTIFACT, declared)
        for validator in manifest["validators"]:
            pattern = validator["artifact"]
            self.assertTrue(
                any(
                    artifact == pattern or artifact.startswith(pattern.split("*")[0])
                    for artifact in declared
                ),
                validator,
            )
        self.assertTrue((REPO_ROOT / "scripts" / "quality_gate.py").is_file())
        self.assertTrue((REPO_ROOT / "assets" / "test" / "baselines" / "game-frame.png").is_file())

    def test_visual_slice_manifest_is_valid_and_opt_in(self):
        manifest = slices.load_manifest(REPO_ROOT / "slices" / "visual.json")
        self.assertEqual(slices.validate_manifest(manifest), [])
        self.assertEqual(manifest["id"], "visual")
        self.assertEqual(slices.resolve_order(manifest), ["quality"])
        step = manifest["steps"][0]
        self.assertEqual(step["kind"], "toolpack")
        self.assertEqual(step["args"]["toolpack"], "quality.visual")
        self.assertIn("opt-in", manifest["description"].lower())
        self.assertEqual(
            manifest["artifacts"],
            [FRAME_ARTIFACT, BENCH_ARTIFACT, REPORT_ARTIFACT],
        )


@unittest.skipUnless(PILLOW_AVAILABLE, "Pillow is not installed; CLI visual tests need it")
class QualityScriptTests(TempCase):
    def _script(self):
        return str(REPO_ROOT / "scripts" / "quality_gate.py")

    def _args(self, *extra):
        return [
            sys.executable,
            self._script(),
            "--frame",
            str(self.frame),
            "--baseline",
            str(self.baseline),
            "--bench",
            str(self.bench),
            "--report",
            str(self.report),
            "--required-frames",
            "143",
        ] + list(extra)

    def test_cli_pass_writes_report_and_exits_zero(self):
        make_image(self.baseline)
        make_image(self.frame)
        self.write_json(self.bench, good_benchmark())
        completed = subprocess.run(
            self._args(), cwd=str(REPO_ROOT), capture_output=True, text=True
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("QUALITY GATE PASS", completed.stdout)
        self.assertTrue(self.report.is_file())
        report = json.loads(self.report.read_text(encoding="utf-8"))
        self.assertTrue(report["passed"])
        self.assertTrue(report["visual"]["passed"])
        self.assertEqual(report["visual"]["dimensions"], {"width": 16, "height": 16})

    def test_cli_fail_exits_one_and_still_writes_report(self):
        make_image(self.baseline, size=(10, 10))
        make_image(self.frame, size=(10, 10), pixels={(0, 0): (255, 255, 255)})
        self.write_json(self.bench, good_benchmark())
        completed = subprocess.run(
            self._args("--max-changed-ratio", "0.0"),
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 1, completed.stdout + completed.stderr)
        self.assertIn("FAIL visual", completed.stdout)
        self.assertIn("QUALITY GATE FAIL", completed.stdout)
        report = json.loads(self.report.read_text(encoding="utf-8"))
        self.assertFalse(report["passed"])
        self.assertFalse(report["visual"]["passed"])

    def test_cli_missing_benchmark_fails_cleanly(self):
        make_image(self.baseline)
        make_image(self.frame)
        completed = subprocess.run(
            self._args(), cwd=str(REPO_ROOT), capture_output=True, text=True
        )
        self.assertEqual(completed.returncode, 1, completed.stdout + completed.stderr)
        self.assertIn("FAIL performance", completed.stdout)
        self.assertTrue(self.report.is_file())
        report = json.loads(self.report.read_text(encoding="utf-8"))
        self.assertFalse(report["passed"])
        self.assertIn("not found", report["performance"]["error"])

    def test_cli_update_baseline_copies_frame_and_records_provenance(self):
        make_image(self.frame, size=(12, 5), color=(10, 20, 30))
        completed = subprocess.run(
            [
                sys.executable,
                self._script(),
                "--frame",
                str(self.frame),
                "--baseline",
                str(self.baseline),
                "--update-baseline",
            ],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("baseline updated", completed.stdout)
        self.assertEqual(self.baseline.read_bytes(), self.frame.read_bytes())
        metadata = json.loads(
            self.baseline.with_suffix(".json").read_text(encoding="utf-8")
        )
        self.assertEqual(metadata["schema"], quality.BASELINE_SCHEMA)
        self.assertEqual(metadata["dimensions"], {"width": 12, "height": 5, "mode": "RGB"})
        self.assertEqual(metadata["sourceSha256"], quality.sha256_file(self.baseline))

    def test_cli_reports_missing_pillow_as_dependency_failure(self):
        make_image(self.baseline)
        make_image(self.frame)
        self.write_json(self.bench, good_benchmark())
        fake = self.root / "fake_pillow"
        fake.mkdir()
        (fake / "PIL.py").write_text(
            "raise ImportError('Pillow blocked for test')\n", encoding="utf-8"
        )
        environment = dict(os.environ)
        environment["PYTHONPATH"] = str(fake)
        completed = subprocess.run(
            self._args(),
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            env=environment,
        )
        self.assertEqual(completed.returncode, 2, completed.stdout + completed.stderr)
        self.assertIn("FAIL visual - Pillow is required", completed.stdout)
        report = json.loads(self.report.read_text(encoding="utf-8"))
        self.assertTrue(report["dependencyMissing"])
        self.assertFalse(report["passed"])


if __name__ == "__main__":
    unittest.main()
