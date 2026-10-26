#!/usr/bin/env python3
"""Phase-5 live-iteration watcher for the ProjectGypsy workstream.

docs/ADR-003-workstream-architecture.md puts a fast iteration loop before any in-game editor:
edit the game source, re-run the deterministic headless slice, read the evidence, repeat. This
module is the watcher half of that loop and nothing more:

- snapshot(paths) records mtime/size for files under the given files or directories;
- changed_paths(before, after) reports added, modified and deleted paths;
- watch(...) sleeps, waits for a change to settle (optional debounce), calls runner() once per
  settled change, and stops after `iterations` changes when a limit is given;
- main(argv) is the CLI: watch paths (default `game`), optional interval/debounce/iterations,
  --once to run immediately, and --command demo|verify to re-run the Godot slice lazily.

Standing rules this obeys:

- **stdlib only** - no Godot, no shell and no network at import time. The default runner imports
  workstream/game.py only when a run actually happens; `--help` and the library API never do.
- **no writes** - the watcher records nothing and mutates nothing. It has no state directory, no
  shell call and no cache. The runner it calls is what touches workstream/state and build/.
- **honest labels** - this is not engine hot reload. A changed file triggers a full re-run of the
  deterministic demo; the engine process restarts and the evidence file is rewritten by game.py.

Ctrl+C stops the loop cleanly (exit 0). One run per settled change, no duplicate runs.

Usage:
    python workstream/live.py [--paths PATH ...] [--interval SEC] [--debounce SEC]
                              [--iterations N] [--once] [--command demo|verify]
"""
from __future__ import annotations

import argparse
import json
import math
import os
import time
from pathlib import Path

DEFAULT_PATHS = ("game",)
COMMANDS = ("demo", "verify")
DEFAULT_INTERVAL = 0.5
DEFAULT_DEBOUNCE = 0.0
DEFAULT_COMMAND = "demo"


def _entry(path: Path):
    """Return the watched signature of one file, or None when it cannot be stat'ed."""
    try:
        stat = path.stat()
    except OSError:
        return None
    return {"mtime": float(stat.st_mtime), "size": int(stat.st_size)}


def snapshot(paths):
    """Return {path: {"mtime": float, "size": int}} for every file under `paths`.

    Each item may be a file or a directory (recursed). Missing and unreadable paths contribute
    nothing rather than raising. Keys keep the form they were given - relative paths stay
    relative - and are sorted. Duplicate coverage (a file also under a watched directory) is
    merged because the result is keyed by path.
    """
    if isinstance(paths, (str, os.PathLike)):
        paths = [paths]
    files = {}
    for raw in paths:
        target = Path(raw)
        try:
            if target.is_dir():
                for child in target.rglob("*"):
                    if child.is_file():
                        entry = _entry(child)
                        if entry is not None:
                            files[str(child)] = entry
            elif target.is_file():
                entry = _entry(target)
                if entry is not None:
                    files[str(target)] = entry
        except OSError:
            continue
    return {name: files[name] for name in sorted(files)}


def _signature(entry):
    """Comparable (mtime, size) for a snapshot entry, tolerant of plain values."""
    if isinstance(entry, dict):
        return (entry.get("mtime"), entry.get("size"))
    return entry


def changed_paths(before, after):
    """Return the sorted paths added, removed or modified between two snapshots.

    A path is modified when its mtime or size differs; content hashing is deliberately not done
    so a poll stays cheap.
    """
    changed = []
    for name in set(before) | set(after):
        old = before.get(name)
        new = after.get(name)
        if old is None or new is None:
            changed.append(name)
        elif _signature(old) != _signature(new):
            changed.append(name)
    return sorted(changed)


def _json_safe(value):
    """Return a JSON-serialisable copy of a runner result (repr fallback for odd objects)."""
    try:
        return json.loads(json.dumps(value, default=str))
    except (TypeError, ValueError, RecursionError):
        return repr(value)


def _settle(paths, candidate, debounce, interval, sleep, now, max_polls):
    """Sleep until a changed snapshot has been stable for `debounce` seconds.

    `max_polls` is a safety valve for a non-advancing `now` callable (or very small intervals),
    so a fake clock can never trap the loop forever.
    """
    stable_since = now()
    stable_polls = 0
    while True:
        sleep(interval)
        latest = snapshot(paths)
        if changed_paths(candidate, latest):
            candidate = latest
            stable_since = now()
            stable_polls = 0
            continue
        stable_polls += 1
        if now() - stable_since >= debounce - 1e-9 or stable_polls >= max_polls:
            return candidate


def watch(
    paths,
    *,
    runner,
    iterations=None,
    interval=DEFAULT_INTERVAL,
    debounce=DEFAULT_DEBOUNCE,
    sleep=time.sleep,
    now=time.time,
    on_event=None,
):
    """Watch `paths` and call `runner()` once per settled change.

    - snapshot the tree, sleep `interval` seconds between polls, then diff;
    - when `debounce` > 0, wait for the snapshot to stay unchanged that long so a burst of
      edits becomes one run;
    - `iterations` limits how many settled changes are processed (None = until interrupted);
    - runner exceptions are recorded in `errors` and never stop the loop;
    - `on_event(event)` is called after each run with the JSON-safe event dict
      {iteration, paths, result, error, seconds}; an exception from it is recorded, not fatal.

    Returns a JSON-safe summary:
    {iterations, runs, changes, runnerResults, errors}, where `changes` holds one
    {iteration, paths} record per settled change and `runs` counts runner invocations
    (including failed ones).
    """
    if isinstance(paths, (str, os.PathLike)):
        paths = [paths]
    watched = [str(path) for path in paths]
    if not watched:
        raise ValueError("paths must not be empty")
    if not callable(runner):
        raise TypeError("runner must be callable")
    if interval < 0:
        raise ValueError("interval must be >= 0")
    if debounce < 0:
        raise ValueError("debounce must be >= 0")
    if iterations is not None and iterations < 0:
        raise ValueError("iterations must be >= 0 or None")

    max_polls = max(1, math.ceil(debounce / interval)) + 1 if debounce > 0 and interval > 0 else 1
    current = snapshot(watched)
    changes = []
    runner_results = []
    errors = []
    runs = 0

    while iterations is None or len(changes) < iterations:
        sleep(interval)
        candidate = snapshot(watched)
        if not changed_paths(current, candidate):
            continue
        if debounce > 0:
            candidate = _settle(watched, candidate, debounce, interval, sleep, now, max_polls)
        diff = changed_paths(current, candidate)
        current = candidate
        if not diff:
            continue

        number = len(changes) + 1
        changes.append({"iteration": number, "paths": diff})
        runs += 1
        started = now()
        result = None
        error_text = None
        try:
            result = _json_safe(runner())
            runner_results.append(result)
        except KeyboardInterrupt:
            raise
        except Exception as exc:  # a broken run is data, not the end of the watch
            error_text = f"{type(exc).__name__}: {exc}"
            errors.append({"iteration": number, "type": type(exc).__name__, "error": str(exc)})
        event = {
            "iteration": number,
            "paths": list(diff),
            "result": result,
            "error": error_text,
            "seconds": round(now() - started, 3),
        }
        if on_event is not None:
            try:
                on_event(event)
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                errors.append({"iteration": number, "type": "on_event", "error": str(exc)})

    return {
        "iterations": len(changes),
        "runs": runs,
        "changes": changes,
        "runnerResults": runner_results,
        "errors": errors,
    }


def _command_runner(command):
    """Return a lazy runner for `game.demo` or `game.verify`.

    workstream/game.py is imported only inside the runner so importing live.py stays stdlib-only
    and side-effect free.
    """
    if command not in COMMANDS:
        raise ValueError(f"unknown command: {command!r} (expected one of {', '.join(COMMANDS)})")

    def runner():
        import game  # local module, present when live.py runs like the rest of workstream/

        return game.demo() if command == "demo" else game.verify()

    runner.__name__ = f"command_{command}"
    return runner


def _positive_float(text):
    value = float(text)
    if value <= 0:
        raise argparse.ArgumentTypeError("must be > 0")
    return value


def _non_negative_float(text):
    value = float(text)
    if value < 0:
        raise argparse.ArgumentTypeError("must be >= 0")
    return value


def _non_negative_int(text):
    value = int(text)
    if value < 0:
        raise argparse.ArgumentTypeError("must be >= 0")
    return value


def _build_parser():
    parser = argparse.ArgumentParser(
        prog="live.py",
        description="watch ProjectGypsy paths and re-run the deterministic slice on each settled change",
    )
    parser.add_argument(
        "--paths",
        action="append",
        default=None,
        metavar="PATH",
        help="file or directory to watch; repeatable (default: game)",
    )
    parser.add_argument(
        "--interval",
        type=_positive_float,
        default=DEFAULT_INTERVAL,
        metavar="SEC",
        help="seconds between polls (default: 0.5)",
    )
    parser.add_argument(
        "--debounce",
        type=_non_negative_float,
        default=DEFAULT_DEBOUNCE,
        metavar="SEC",
        help="seconds a change must stay stable before it runs (default: 0)",
    )
    parser.add_argument(
        "--iterations",
        type=_non_negative_int,
        default=None,
        metavar="N",
        help="stop after N settled changes (default: until interrupted)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="run the command once immediately and exit; does not watch",
    )
    parser.add_argument(
        "--command",
        choices=COMMANDS,
        default=DEFAULT_COMMAND,
        help="runner to call through workstream/game.py (default: demo)",
    )
    return parser


def main(argv=None, *, runner=None, sleep=time.sleep, now=time.time) -> int:
    """CLI entry point. Returns 0 on success/Ctrl+C, 1 when a run failed or the watch errored.

    `runner`, `sleep` and `now` are injection points for tests; normally they come from
    --command and the standard library.
    """
    args = _build_parser().parse_args(argv)
    paths = args.paths or list(DEFAULT_PATHS)
    if runner is None:
        runner = _command_runner(args.command)
    failures = []

    def report_run(number, result, error, seconds, suffix=""):
        if error:
            print(f"[live] run {number}{suffix}: error: {error}")
            failures.append(error)
            return
        status = "FAIL" if isinstance(result, dict) and result.get("passed") is False else "ok"
        print(f"[live] run {number}{suffix}: {status} ({seconds:.3f}s)")
        if status != "ok":
            failures.append(status)

    if args.once:
        started = now()
        try:
            result = runner()
        except KeyboardInterrupt:
            print("[live] stopped (interrupted)")
            return 0
        except Exception as exc:
            report_run(1, None, f"{type(exc).__name__}: {exc}", now() - started, " (once)")
            return 1
        report_run(1, result, None, now() - started, " (once)")
        return 1 if failures else 0

    limit = f", stop after {args.iterations} change(s)" if args.iterations is not None else ""
    print(f"[live] watching {len(paths)} path(s): {', '.join(paths)}")
    print(f"[live] interval {args.interval:g}s, debounce {args.debounce:g}s{limit}")

    def on_event(event):
        shown = ", ".join(event["paths"][:3])
        more = f" (+{len(event['paths']) - 3} more)" if len(event["paths"]) > 3 else ""
        print(f"[live] change {event['iteration']}: {len(event['paths'])} path(s): {shown}{more}")
        report_run(event["iteration"], event["result"], event["error"], event["seconds"])

    try:
        summary = watch(
            paths,
            runner=runner,
            iterations=args.iterations,
            interval=args.interval,
            debounce=args.debounce,
            sleep=sleep,
            now=now,
            on_event=on_event,
        )
    except KeyboardInterrupt:
        print("[live] stopped (interrupted)")
        return 0
    print(
        f"[live] done: {summary['iterations']} change(s), {summary['runs']} run(s), "
        f"{len(summary['errors'])} error(s)"
    )
    return 1 if failures or summary["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
