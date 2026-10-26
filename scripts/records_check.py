#!/usr/bin/env python3
"""Records guard for ProjectGypsy (ProjectPack rule 2.1).

Fails unless all of these hold:

  * BuildNotes.md has at least one version heading and the versions are newest-first;
  * BuildNotes.md's "Current version:" header equals the newest heading;
  * no version appears twice in BuildNotes.md;
  * Retrace.md's prompt entries are numbered 1..N, contiguously and in ascending order
    (the newest prompt is at the bottom);
  * every Retrace.md entry carries a non-empty "Status:".

It reads the two files and writes nothing. scripts/check_all.py runs it, so the tracked
pre-commit hook and CI run it too.

Usage:
    python scripts/records_check.py [--root PATH]

Exit code 0 when every rule holds, 1 otherwise.
"""

import argparse
import re
import sys
from datetime import date
from pathlib import Path

VERSION = r"(?P<year>\d{4})\.(?P<month>\d{1,2})\.(?P<day>\d{1,2})\.(?P<seq>\d{3})"
VERSION_RE = re.compile(r"^## " + VERSION + r"\s*$", re.MULTILINE)
HEADER_RE = re.compile(r"^Current version:\s*" + VERSION + r"\s*$", re.MULTILINE)
ENTRY_RE = re.compile(r"^## (\d+) - (\d{4}-\d{2}-\d{2})\s*$")
STATUS_RE = re.compile(r"^\s*-\s+Status:\s*(\S.*?)\s*$")


def version_key(match):
    return tuple(int(match.group(name)) for name in ("year", "month", "day", "seq"))


def version_text(key):
    return "{}.{}.{}.{:03d}".format(*key)


def check_build_notes(path, errors):
    if not path.is_file():
        errors.append("{} is missing".format(path))
        return None
    text = path.read_text(encoding="utf-8")
    headings = list(VERSION_RE.finditer(text))
    if not headings:
        errors.append("BuildNotes.md has no '## YYYY.M.D.NNN' version heading")
        return None
    keys = [version_key(match) for match in headings]
    newest = keys[0]
    for before, after in zip(keys, keys[1:]):
        if not before > after:
            errors.append(
                "BuildNotes.md is not newest-first: {} appears before {} (or repeats)".format(
                    version_text(before), version_text(after)
                )
            )
            break
    counts = {}
    for key in keys:
        counts[key] = counts.get(key, 0) + 1
    for key, count in counts.items():
        if count > 1:
            errors.append("BuildNotes.md repeats version {}".format(version_text(key)))
    header = HEADER_RE.search(text)
    if header is None:
        errors.append("BuildNotes.md is missing a 'Current version: YYYY.M.D.NNN' line")
    elif version_key(header) != newest:
        errors.append(
            "BuildNotes.md header says {} but the newest heading is {}".format(
                version_text(version_key(header)), version_text(newest)
            )
        )
    return newest, len(keys)


def check_retrace(path, errors):
    if not path.is_file():
        errors.append("{} is missing".format(path))
        return None
    numbers = []
    statuses = {}
    current = None
    for line in path.read_text(encoding="utf-8").splitlines():
        entry = ENTRY_RE.match(line)
        if entry:
            current = int(entry.group(1))
            numbers.append(current)
            statuses.setdefault(current, None)
            try:
                date.fromisoformat(entry.group(2))
            except ValueError:
                errors.append(
                    "Retrace.md entry {} has an invalid date {}".format(current, entry.group(2))
                )
            continue
        if current is None:
            continue
        status = STATUS_RE.match(line)
        if status:
            statuses[current] = status.group(1)
    if not numbers:
        errors.append("Retrace.md has no '## N - YYYY-MM-DD' prompt entries")
        return None
    expected = list(range(1, len(numbers) + 1))
    if numbers != expected:
        errors.append("Retrace.md prompt numbers are not contiguous from 1: found {}".format(numbers))
    missing = [number for number in numbers if not statuses.get(number)]
    if missing:
        errors.append("Retrace.md entries without a Status: {}".format(missing))
    return len(numbers)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Check ProjectGypsy's records files.")
    parser.add_argument("--root", help="repository root (default: the parent of scripts/)")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[1]

    errors = []
    build = check_build_notes(root / "BuildNotes.md", errors)
    prompts = check_retrace(root / "Retrace.md", errors)

    if errors:
        for error in errors:
            print("FAIL records - " + error)
        print("records: FAIL ({} problem(s))".format(len(errors)))
        return 1
    newest, versions = build
    print(
        "PASS records - BuildNotes {} versions newest-first ({} first), header matches; "
        "Retrace {} prompts contiguous, every entry has a Status".format(
            versions, version_text(newest), prompts
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
