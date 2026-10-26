#!/usr/bin/env python3
"""Install ProjectGypsy's tracked git hooks (ProjectPack rule 2.23).

Points git at the repository's tracked .githooks directory with core.hooksPath, so the
pre-commit hook that runs scripts/check_all.py is versioned with the code instead of living
in a machine's own .git/hooks. The hook is a convenience; the gate is
.github/workflows/checks.yml, which has no --no-verify.

Failures are silent on purpose: when the directory is not a git repository (a source
archive, or the tree consumed as a dependency), the script reports that and exits 0 rather
than failing the install.

Usage:
    python scripts/install-hooks.py
    git config --unset core.hooksPath      # undo

Exit code 0 when installed or intentionally skipped, 1 when git refuses.
"""

import subprocess
import sys
from pathlib import Path

HOOKS_DIR = ".githooks"
ROOT = Path(__file__).resolve().parents[1]


def main():
    def git(*args):
        return subprocess.run(["git", *args], cwd=str(ROOT), capture_output=True, text=True)

    try:
        probe = git("rev-parse", "--git-dir")
    except FileNotFoundError:
        print("install-hooks: git is not on PATH; skipped (this is not an error)")
        return 0
    if probe.returncode != 0:
        print("install-hooks: not a git repository; skipped (this is not an error)")
        return 0
    hook = ROOT / HOOKS_DIR / "pre-commit"
    if not hook.is_file():
        print("install-hooks: {} is missing; skipped".format(HOOKS_DIR + "/pre-commit"))
        return 0
    try:
        hook.chmod(0o755)
    except OSError:
        pass  # Windows has no executable bit; git does not need one there
    configured = git("config", "core.hooksPath", HOOKS_DIR)
    if configured.returncode != 0:
        print("install-hooks: could not set core.hooksPath: " + configured.stderr.strip())
        return 1
    read_back = git("config", "--get", "core.hooksPath")
    if read_back.stdout.strip() != HOOKS_DIR:
        print(
            "install-hooks: core.hooksPath did not read back as expected: "
            + read_back.stdout.strip()
        )
        return 1
    print("install-hooks: core.hooksPath = " + HOOKS_DIR + " (read back from git config)")
    print("install-hooks: the hook runs python scripts/check_all.py; CI runs the same file")
    return 0


if __name__ == "__main__":
    sys.exit(main())
