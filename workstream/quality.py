#!/usr/bin/env python3
"""Visual regression and performance-budget quality gates for the hero slice.

Two independent, fail-closed gates feed one report:

1. Visual regression. Compare a captured frame against a tracked baseline and report the
   image dimensions, the changed-pixel ratio and the threshold it is compared against. The
   comparison uses Pillow. Pillow is an optional dependency of the workstream: when it is
   missing the visual gate raises QualityDependencyError with the install command and never
   silently passes. A dimension mismatch is a failure, not a skipped comparison.
2. Performance budget. Parse a game-benchmark JSON document (as written by
   workstream/game.py benchmark to workstream/state/game-benchmark.json) and check explicit
   thresholds for median/p95 demo wall time, capture GPU ms/frame and demo frame counts.
   Missing metrics and non-numeric metrics fail; the benchmark's own passed flag is recorded
   but not trusted as the gate result.

run_quality_gate combines both gates into one JSON-safe report with schema
gypsy.quality-gate/v1. write_report persists it atomically. The CLI wrapper is
scripts/quality_gate.py, and toolpacks/quality.visual.json + slices/visual.json wire the gate
into the toolpack and slice runners. The visual slice is opt-in: it is not part of
scripts/check_all.py or the default quality slice, and it is run explicitly.

Public API:

    GATE_SCHEMA, DEFAULT_* thresholds, QualityError, QualityDependencyError
    pillow_available() -> bool
    sha256_file(path) -> str
    image_dimensions(path) -> dict
    compare_images(baseline, candidate, *, max_changed_ratio=..., channel_tolerance=...) -> dict
    load_benchmark(path) -> dict
    check_performance(benchmark, *, max_median_seconds=..., max_p95_seconds=...,
                      max_gpu_ms_per_frame=..., required_frames=..., min_runs=None) -> dict
    run_quality_gate(*, frame, baseline, benchmark, ...) -> dict
    write_report(path, report) -> Path
    render_report(report) -> list[str]
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

GATE_SCHEMA = "gypsy.quality-gate/v1"
BASELINE_SCHEMA = "gypsy.baseline/v1"

# A 1280x720 capture has 921600 pixels; 0.002 allows at most 1843 changed pixels. The real
# baselines are compared at channel tolerance 0, so any rendered pixel that differs counts.
DEFAULT_MAX_CHANGED_RATIO = 0.002
DEFAULT_CHANNEL_TOLERANCE = 0
DEFAULT_MAX_MEDIAN_SECONDS = 5.0
DEFAULT_MAX_P95_SECONDS = 8.0
DEFAULT_MAX_GPU_MS_PER_FRAME = 16.67
DEFAULT_REQUIRED_FRAMES = 143


class QualityError(ValueError):
    """A gate input is unreadable, malformed, or a threshold is invalid."""


class QualityDependencyError(QualityError):
    """An optional dependency the gate needs (Pillow) is not installed."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(moment: datetime) -> str:
    return moment.isoformat(timespec="seconds")


def _as_path(value, label: str) -> Path:
    try:
        return Path(value)
    except (TypeError, ValueError):
        raise QualityError(f"{label} is not a usable path: {value!r}") from None


def _existing_file(value, label: str) -> Path:
    path = _as_path(value, label)
    if not path.is_file():
        raise QualityError(f"{label} not found: {path}")
    return path


def _number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _ratio(value, label: str) -> float:
    if not _number(value) or value < 0 or value > 1:
        raise QualityError(f"{label} must be a number between 0 and 1")
    return float(value)


def _tolerance(value) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0 or value > 255:
        raise QualityError("channel_tolerance must be an integer between 0 and 255")
    return int(value)


def _positive_number(value, label: str):
    if value is None:
        return None
    if not _number(value) or value <= 0:
        raise QualityError(f"{label} must be a positive number")
    return float(value)


def _positive_int(value, label: str):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise QualityError(f"{label} must be a positive integer")
    return int(value)


def pillow_available() -> bool:
    """True when Pillow can be imported; the visual gate needs it, the performance gate does not."""
    try:
        import PIL  # noqa: F401
        from PIL import Image, ImageChops  # noqa: F401
    except Exception:  # noqa: BLE001 - any import failure means the dependency is unusable
        return False
    return True


def _import_pillow():
    try:
        import PIL
        from PIL import Image, ImageChops
    except ImportError as exc:
        raise QualityDependencyError(
            "Pillow is required for the visual regression gate but is not installed; "
            "install it with 'python -m pip install Pillow'"
        ) from exc
    return Image, ImageChops, str(getattr(PIL, "__version__", "unknown"))


def sha256_file(path) -> str:
    """Return the SHA-256 hex digest of a file (used for baseline provenance)."""
    path = _existing_file(path, "file")
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def image_dimensions(path) -> dict:
    """Read width, height and mode with Pillow; raises QualityDependencyError without Pillow."""
    Image, _ImageChops, _version = _import_pillow()
    path = _existing_file(path, "image")
    try:
        with Image.open(path) as image:
            return {"width": image.width, "height": image.height, "mode": image.mode}
    except OSError as exc:
        raise QualityError(f"could not read image {path}: {exc}") from exc


def compare_images(
    baseline,
    candidate,
    *,
    max_changed_ratio=DEFAULT_MAX_CHANGED_RATIO,
    channel_tolerance=DEFAULT_CHANNEL_TOLERANCE,
) -> dict:
    """Compare two images and return a JSON-safe visual report.

    Both images are converted to RGB. A pixel counts as changed when its largest
    per-channel absolute difference is greater than channel_tolerance. The gate passes only
    when the changed-pixel ratio is at most max_changed_ratio. A dimension mismatch fails.
    """
    max_changed_ratio = _ratio(max_changed_ratio, "max_changed_ratio")
    channel_tolerance = _tolerance(channel_tolerance)
    baseline_path = _existing_file(baseline, "baseline image")
    candidate_path = _existing_file(candidate, "candidate image")
    Image, ImageChops, pillow_version = _import_pillow()
    try:
        with Image.open(baseline_path) as baseline_image:
            baseline_dimensions = {"width": baseline_image.width, "height": baseline_image.height}
            baseline_mode = baseline_image.mode
            baseline_pixels = baseline_image.convert("RGB")
        with Image.open(candidate_path) as candidate_image:
            candidate_dimensions = {"width": candidate_image.width, "height": candidate_image.height}
            candidate_mode = candidate_image.mode
            candidate_pixels = candidate_image.convert("RGB")
    except OSError as exc:
        raise QualityError(f"could not read image: {exc}") from exc

    report = {
        "kind": "visual",
        "passed": False,
        "baseline": str(baseline_path),
        "candidate": str(candidate_path),
        "dimensions": baseline_dimensions,
        "baselineDimensions": baseline_dimensions,
        "candidateDimensions": candidate_dimensions,
        "baselineMode": baseline_mode,
        "candidateMode": candidate_mode,
        "maxChangedRatio": max_changed_ratio,
        "channelTolerance": channel_tolerance,
        "pillowVersion": pillow_version,
    }
    if baseline_pixels.size != candidate_pixels.size:
        report.update(
            {
                "changedPixels": None,
                "totalPixels": None,
                "changedRatio": None,
                "dimensions": None,
                "reason": (
                    "dimensions differ: baseline "
                    f"{baseline_dimensions['width']}x{baseline_dimensions['height']}, candidate "
                    f"{candidate_dimensions['width']}x{candidate_dimensions['height']}"
                ),
            }
        )
        return report

    width, height = baseline_pixels.size
    total_pixels = width * height
    difference = ImageChops.difference(baseline_pixels, candidate_pixels)
    if difference.getbbox() is None:
        changed_pixels = 0
    else:
        red, green, blue = difference.split()
        largest = ImageChops.lighter(ImageChops.lighter(red, green), blue)
        mask = largest.point(lambda value: 255 if value > channel_tolerance else 0)
        changed_pixels = mask.histogram()[255]
    changed_ratio = (changed_pixels / total_pixels) if total_pixels else 0.0
    passed = changed_ratio <= max_changed_ratio
    report.update(
        {
            "dimensions": {"width": width, "height": height},
            "changedPixels": changed_pixels,
            "totalPixels": total_pixels,
            "changedRatio": round(changed_ratio, 8),
            "passed": passed,
            "reason": (
                None
                if passed
                else "changed ratio {:.8f} exceeds maxChangedRatio {:.8f}".format(
                    changed_ratio, max_changed_ratio
                )
            ),
        }
    )
    return report


def load_benchmark(path) -> dict:
    """Load a game-benchmark JSON document and require it to be an object."""
    path = _as_path(path, "benchmark")
    if not path.is_file():
        raise QualityError(
            f"benchmark JSON not found: {path} "
            "(run 'python workstream/gypsy.py game bench --runs 3' first)"
        )
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise QualityError(f"benchmark JSON unreadable: {exc}") from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise QualityError(f"benchmark JSON invalid: {exc}") from exc
    if not isinstance(data, dict):
        raise QualityError(f"{path}: benchmark must be a JSON object")
    return data


def check_performance(
    benchmark,
    *,
    max_median_seconds=DEFAULT_MAX_MEDIAN_SECONDS,
    max_p95_seconds=DEFAULT_MAX_P95_SECONDS,
    max_gpu_ms_per_frame=DEFAULT_MAX_GPU_MS_PER_FRAME,
    required_frames=DEFAULT_REQUIRED_FRAMES,
    min_runs=None,
) -> dict:
    """Check a parsed game benchmark against explicit budgets.

    Thresholds set to None disable that individual check (the report records the null).
    Missing or non-numeric metrics, a missing GPU time, failing demo runs or a wrong frame
    count fail the gate. The benchmark's own "passed" flag is recorded, not trusted.
    """
    if not isinstance(benchmark, dict):
        raise QualityError("benchmark must be a JSON object")
    max_median_seconds = _positive_number(max_median_seconds, "max_median_seconds")
    max_p95_seconds = _positive_number(max_p95_seconds, "max_p95_seconds")
    max_gpu_ms_per_frame = _positive_number(max_gpu_ms_per_frame, "max_gpu_ms_per_frame")
    required_frames = _positive_int(required_frames, "required_frames")
    min_runs = _positive_int(min_runs, "min_runs")

    checks = []
    failures = []

    def add(identifier, actual, operator, limit, passed, detail=None):
        check = {
            "id": identifier,
            "actual": actual,
            "op": operator,
            "limit": limit,
            "passed": bool(passed),
        }
        if detail:
            check["detail"] = detail
        checks.append(check)
        if not passed:
            failures.append(detail or f"{identifier} failed")

    budgets = (
        ("medianSeconds", max_median_seconds),
        ("p95Seconds", max_p95_seconds),
        ("captureGpuMsPerFrame", max_gpu_ms_per_frame),
    )
    for metric, limit in budgets:
        if limit is None:
            checks.append(
                {"id": metric, "actual": benchmark.get(metric), "op": "<=", "limit": None, "passed": True, "detail": "threshold disabled"}
            )
            continue
        actual = benchmark.get(metric)
        if not _number(actual):
            add(
                metric,
                actual,
                "<=",
                limit,
                False,
                f"{metric} is missing or not a number (found {actual!r})",
            )
        else:
            add(
                metric,
                actual,
                "<=",
                limit,
                actual <= limit,
                None if actual <= limit else f"{metric} {actual:g} exceeds budget {limit:g}",
            )

    demos = benchmark.get("demos")
    if required_frames is not None:
        problems = []
        if not isinstance(demos, list) or not demos:
            problems.append("demos list is missing or empty")
        else:
            for index, demo in enumerate(demos):
                if not isinstance(demo, dict):
                    problems.append(f"demos[{index}] is not an object")
                    continue
                if demo.get("passed") is not True:
                    problems.append(f"demos[{index}] did not pass")
                frames = demo.get("frames")
                if frames != required_frames:
                    problems.append(
                        f"demos[{index}] frames={frames!r}, required {required_frames}"
                    )
        add(
            "demoFrames",
            [demo.get("frames") if isinstance(demo, dict) else None for demo in demos] if isinstance(demos, list) else None,
            "==",
            required_frames,
            not problems,
            None if not problems else "; ".join(problems),
        )

    runs = benchmark.get("runs")
    if min_runs is not None:
        if not _number(runs):
            add("runs", runs, ">=", min_runs, False, "runs is missing or not a number")
        else:
            add(
                "runs",
                runs,
                ">=",
                min_runs,
                runs >= min_runs,
                None if runs >= min_runs else f"runs {runs:g} is below the minimum {min_runs}",
            )

    metrics = {
        "medianSeconds": benchmark.get("medianSeconds"),
        "p95Seconds": benchmark.get("p95Seconds"),
        "captureGpuMsPerFrame": benchmark.get("captureGpuMsPerFrame"),
        "runs": benchmark.get("runs"),
        "demoFrames": [demo.get("frames") for demo in demos if isinstance(demo, dict)] if isinstance(demos, list) else None,
        "benchmarkPassed": benchmark.get("passed"),
        "logicPassed": benchmark.get("logicPassed"),
        "renderPassed": benchmark.get("renderPassed"),
        "captureError": benchmark.get("captureError"),
    }
    passed = all(check["passed"] for check in checks)
    return {
        "kind": "performance",
        "passed": passed,
        "metrics": metrics,
        "thresholds": {
            "maxMedianSeconds": max_median_seconds,
            "maxP95Seconds": max_p95_seconds,
            "maxGpuMsPerFrame": max_gpu_ms_per_frame,
            "requiredFrames": required_frames,
            "minRuns": min_runs,
        },
        "checks": checks,
        "failures": failures,
        "reason": None if passed else "; ".join(failures),
    }


def run_quality_gate(
    *,
    frame,
    baseline,
    benchmark,
    max_changed_ratio=DEFAULT_MAX_CHANGED_RATIO,
    channel_tolerance=DEFAULT_CHANNEL_TOLERANCE,
    max_median_seconds=DEFAULT_MAX_MEDIAN_SECONDS,
    max_p95_seconds=DEFAULT_MAX_P95_SECONDS,
    max_gpu_ms_per_frame=DEFAULT_MAX_GPU_MS_PER_FRAME,
    required_frames=DEFAULT_REQUIRED_FRAMES,
    min_runs=None,
) -> dict:
    """Run the visual and performance gates and return one JSON-safe report.

    A missing Pillow or an unreadable input is recorded as a failed gate with a clear reason
    (dependencyMissing is true for Pillow); the performance gate still runs when possible.
    No exception is raised for gate failures. Invalid argument types still raise QualityError.
    """
    dependency_missing = False
    try:
        visual = compare_images(
            baseline,
            frame,
            max_changed_ratio=max_changed_ratio,
            channel_tolerance=channel_tolerance,
        )
    except QualityDependencyError as exc:
        dependency_missing = True
        visual = {
            "kind": "visual",
            "passed": False,
            "baseline": str(baseline),
            "candidate": str(frame),
            "dependencyMissing": True,
            "error": str(exc),
        }
    except QualityError as exc:
        visual = {
            "kind": "visual",
            "passed": False,
            "baseline": str(baseline),
            "candidate": str(frame),
            "dependencyMissing": False,
            "error": str(exc),
        }

    try:
        performance = check_performance(
            load_benchmark(benchmark),
            max_median_seconds=max_median_seconds,
            max_p95_seconds=max_p95_seconds,
            max_gpu_ms_per_frame=max_gpu_ms_per_frame,
            required_frames=required_frames,
            min_runs=min_runs,
        )
        performance["source"] = str(benchmark)
    except QualityError as exc:
        performance = {
            "kind": "performance",
            "passed": False,
            "source": str(benchmark),
            "error": str(exc),
            "failures": [str(exc)],
        }

    passed = bool(visual.get("passed")) and bool(performance.get("passed"))
    return {
        "schema": GATE_SCHEMA,
        "kind": "quality-gate",
        "generated": _iso(_utc_now()),
        "passed": passed,
        "dependencyMissing": dependency_missing,
        "visual": visual,
        "performance": performance,
        "inputs": {
            "frame": str(frame),
            "baseline": str(baseline),
            "benchmark": str(benchmark),
        },
    }


def write_report(path, report) -> Path:
    """Write a gate report atomically (temp file plus os.replace); returns the report path."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    descriptor, temp_name = tempfile.mkstemp(
        prefix="." + path.stem + "-", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except BaseException:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise
    return path


def _format_ratio(value) -> str:
    return "?" if value is None else "{:.6%}".format(value)


def render_report(report) -> list:
    """Render one line per gate plus a final line for the terminal/CLI."""
    lines = []
    visual = report.get("visual") or {}
    if visual.get("error"):
        lines.append(f"FAIL visual - {visual['error']}")
    elif visual.get("passed"):
        dimensions = visual.get("dimensions") or {}
        lines.append(
            "PASS visual - {}x{} changed={}/{} ({}) <= {}".format(
                dimensions.get("width", "?"),
                dimensions.get("height", "?"),
                visual.get("changedPixels", "?"),
                visual.get("totalPixels", "?"),
                _format_ratio(visual.get("changedRatio")),
                _format_ratio(visual.get("maxChangedRatio")),
            )
        )
    else:
        lines.append(
            "FAIL visual - changed={}/{} ({}) > {}: {}".format(
                visual.get("changedPixels", "?"),
                visual.get("totalPixels", "?"),
                _format_ratio(visual.get("changedRatio")),
                _format_ratio(visual.get("maxChangedRatio")),
                visual.get("reason", "failed"),
            )
        )
    performance = report.get("performance") or {}
    if performance.get("error"):
        lines.append(f"FAIL performance - {performance['error']}")
    elif performance.get("passed"):
        metrics = performance.get("metrics") or {}
        thresholds = performance.get("thresholds") or {}
        lines.append(
            "PASS performance - median={}s <= {}s, p95={}s <= {}s, gpu={}ms <= {}ms, frames={}".format(
                metrics.get("medianSeconds", "?"),
                thresholds.get("maxMedianSeconds", "?"),
                metrics.get("p95Seconds", "?"),
                thresholds.get("maxP95Seconds", "?"),
                metrics.get("captureGpuMsPerFrame", "?"),
                thresholds.get("maxGpuMsPerFrame", "?"),
                thresholds.get("requiredFrames", "-"),
            )
        )
    else:
        failures = performance.get("failures") or [performance.get("reason", "failed")]
        lines.append("FAIL performance - " + "; ".join(str(item) for item in failures))
    lines.append("QUALITY GATE " + ("PASS" if report.get("passed") else "FAIL"))
    return lines
