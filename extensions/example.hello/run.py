#!/usr/bin/env python3
"""Safe reference extension for the Gypsy Studio self-extension pipeline.

This file is deliberately small and offline. It exists to prove the pipeline can run a
passing action and detect a failing one (the manifest's negative test expects exit != 0).
"""
from __future__ import annotations

import argparse
import os
import sys


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Gypsy example extension")
    parser.add_argument("--action", choices=["hello", "fail"], required=True)
    args = parser.parse_args(argv)
    if args.action == "hello":
        print("EXTENSION_HELLO_OK")
        print("EXTENSION_CWD=" + os.getcwd())
        return 0
    print(
        "EXTENSION_EXPECTED_FAILURE: this action intentionally exits nonzero",
        file=sys.stderr,
    )
    return 3


if __name__ == "__main__":
    sys.exit(main())
