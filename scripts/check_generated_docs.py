#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(*args: str) -> None:
    subprocess.run(args, cwd=ROOT, check=True)


def main() -> int:
    run(sys.executable, "-m", "slack_mirror.cli.main", "docs", "generate", "--format", "markdown", "--output", "docs/CLI.md")
    run(sys.executable, "-m", "slack_mirror.cli.main", "docs", "generate", "--format", "man", "--output", "docs/slack-mirror.1")

    diff = subprocess.run(["git", "diff", "--exit-code", "--", "docs/CLI.md", "docs/slack-mirror.1"], cwd=ROOT)
    if diff.returncode != 0:
        print("Generated docs are out of date. Run docs generate and commit the changes.", file=sys.stderr)
        return 1
    print("Generated docs are up to date.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
