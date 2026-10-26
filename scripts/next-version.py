#!/usr/bin/env python3
"""Compute the next BuildNotes version (ProjectPack rule 2.1: numbering is computed, not guessed).

Reads the version headings ("## YYYY.M.D.NNN") from BuildNotes.md and prints the next
version for today:

  * if the newest version is dated today, its sequence advances by one;
  * otherwise today starts a new date at sequence 001.

The sequence is zero-padded to three digits, so versions sort in the changelog's newest-first
order. The newest heading is the maximum, not necessarily the first line: records_check.py
enforces newest-first separately.

Usage:
    python scripts/next-version.py
    python scripts/next-version.py --date 2026-10-26
    python scripts/next-version.py --root PATH

Exit code 0 with the version on stdout; 2 when BuildNotes.md is missing or malformed.
"""

import argparse
import re
import sys
from datetime import date
from pathlib import Path

VERSION_RE = re.compile(r"^## (\d{4})\.(\d{1,2})\.(\d{1,2})\.(\d{3})\s*$", re.MULTILINE)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Print the next BuildNotes version.")
    parser.add_argument("--root", help="repository root (default: the parent of scripts/)")
    parser.add_argument("--date", help="YYYY-MM-DD to compute for (default: today)")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[1]

    notes = root / "BuildNotes.md"
    if not notes.is_file():
        print("next-version: {} does not exist".format(notes), file=sys.stderr)
        return 2
    matches = list(VERSION_RE.finditer(notes.read_text(encoding="utf-8")))
    if not matches:
        print("next-version: BuildNotes.md has no version headings", file=sys.stderr)
        return 2
    newest = max(
        tuple(int(match.group(index)) for index in (1, 2, 3, 4)) for match in matches
    )
    try:
        today = date.fromisoformat(args.date) if args.date else date.today()
    except ValueError:
        print("next-version: --date must be YYYY-MM-DD", file=sys.stderr)
        return 2
    same_day = newest[:3] == (today.year, today.month, today.day)
    sequence = newest[3] + 1 if same_day else 1
    if sequence > 999:
        print("next-version: sequence would exceed 999", file=sys.stderr)
        return 2
    print("{}.{}.{}.{:03d}".format(today.year, today.month, today.day, sequence))
    return 0


if __name__ == "__main__":
    sys.exit(main())
