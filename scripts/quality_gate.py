#!/usr/bin/env python3
"""Run the opt-in visual regression and performance-budget quality gate.

    python scripts/quality_gate.py
    python scripts/quality_gate.py --json
    python scripts/quality_gate.py --update-baseline

The visual gate compares artifacts/game/frame.png with the tracked baseline
assets/test/baselines/game-frame.png using Pillow. The performance gate reads
workstream/state/game-benchmark.json (written by 'gypsy.py game bench --runs 3'). Both
thresholds are explicit CLI arguments with documented defaults. The report is written
atomically to workstream/state/quality/gate.json.

Exit codes: 0 both gates pass; 1 a gate failed; 2 the visual dependency (Pillow) is missing.
--update-baseline copies the current frame over the tracked baseline and records its
provenance; it is a deliberate operator action, not part of the gate.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "workstream"))

import quality  # noqa: E402

DEFAULT_FRAME = "artifacts/game/frame.png"
DEFAULT_BASELINE = "assets/test/baselines/game-frame.png"
DEFAULT_BENCH = "workstream/state/game-benchmark.json"
DEFAULT_REPORT = "workstream/state/quality/gate.json"


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def update_baseline(frame: Path, baseline: Path) -> Path:
    """Copy frame to baseline and write <baseline>.json provenance; returns the metadata path."""
    if not frame.is_file():
        raise quality.QualityError(f"frame not found: {frame}")
    payload = frame.read_bytes()
    source_sha256 = quality.sha256_file(frame)
    try:
        dimensions = quality.image_dimensions(frame)
    except quality.QualityDependencyError:
        dimensions = None
    baseline.parent.mkdir(parents=True, exist_ok=True)
    baseline.write_bytes(payload)
    metadata = {
        "schema": quality.BASELINE_SCHEMA,
        "id": baseline.stem,
        "baseline": baseline.name,
        "source": str(frame),
        "sourceSha256": source_sha256,
        "baselineSha256": quality.sha256_file(baseline),
        "dimensions": dimensions,
        "updatedAt": _iso_now(),
        "note": (
            "Tracked visual baseline for the hero slice. Regenerate deliberately with "
            "'python scripts/quality_gate.py --update-baseline' after reviewing the new frame."
        ),
    }
    metadata_path = baseline.with_suffix(".json")
    quality.write_report(metadata_path, metadata)
    return metadata_path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Visual regression + performance budget gate")
    parser.add_argument("--frame", default=DEFAULT_FRAME, help="candidate captured frame")
    parser.add_argument("--baseline", default=DEFAULT_BASELINE, help="tracked baseline image")
    parser.add_argument("--bench", default=DEFAULT_BENCH, help="game benchmark JSON")
    parser.add_argument("--report", default=DEFAULT_REPORT, help="gate report JSON output")
    parser.add_argument(
        "--max-changed-ratio",
        type=float,
        default=quality.DEFAULT_MAX_CHANGED_RATIO,
        help="largest allowed changed-pixel ratio (default: %(default)s)",
    )
    parser.add_argument(
        "--channel-tolerance",
        type=int,
        default=quality.DEFAULT_CHANNEL_TOLERANCE,
        help="per-channel difference that still counts as unchanged (default: %(default)s)",
    )
    parser.add_argument(
        "--max-median-seconds",
        type=float,
        default=quality.DEFAULT_MAX_MEDIAN_SECONDS,
        help="largest allowed demo median wall time (default: %(default)s)",
    )
    parser.add_argument(
        "--max-p95-seconds",
        type=float,
        default=quality.DEFAULT_MAX_P95_SECONDS,
        help="largest allowed demo p95 wall time (default: %(default)s)",
    )
    parser.add_argument(
        "--max-gpu-ms-per-frame",
        type=float,
        default=quality.DEFAULT_MAX_GPU_MS_PER_FRAME,
        help="largest allowed capture GPU ms/frame (default: %(default)s)",
    )
    parser.add_argument(
        "--required-frames",
        type=int,
        default=quality.DEFAULT_REQUIRED_FRAMES,
        help="expected frames per demo run (default: %(default)s)",
    )
    parser.add_argument(
        "--min-runs",
        type=int,
        default=None,
        help="minimum benchmark runs, when set (default: not checked)",
    )
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="copy --frame to --baseline and write provenance, then exit",
    )
    parser.add_argument("--json", action="store_true", dest="as_json", help="print the report JSON")
    args = parser.parse_args(argv)

    frame = Path(args.frame)
    baseline = Path(args.baseline)
    benchmark = Path(args.bench)
    report_path = Path(args.report)

    if args.update_baseline:
        try:
            metadata_path = update_baseline(frame, baseline)
        except quality.QualityError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        except OSError as exc:
            print(f"ERROR: could not update baseline: {exc}", file=sys.stderr)
            return 1
        print(f"baseline updated: {baseline} (metadata {metadata_path})")
        return 0

    try:
        report = quality.run_quality_gate(
            frame=frame,
            baseline=baseline,
            benchmark=benchmark,
            max_changed_ratio=args.max_changed_ratio,
            channel_tolerance=args.channel_tolerance,
            max_median_seconds=args.max_median_seconds,
            max_p95_seconds=args.max_p95_seconds,
            max_gpu_ms_per_frame=args.max_gpu_ms_per_frame,
            required_frames=args.required_frames,
            min_runs=args.min_runs,
        )
    except quality.QualityError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    try:
        quality.write_report(report_path, report)
    except OSError as exc:
        print(f"ERROR: could not write report {report_path}: {exc}", file=sys.stderr)
        return 1
    if args.as_json:
        print(json.dumps(report, indent=2))
    else:
        for line in quality.render_report(report):
            print(line)
    print(f"report: {report_path}")
    if report.get("dependencyMissing"):
        return 2
    return 0 if report.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
