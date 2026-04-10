#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
import os
from pathlib import Path
import tempfile


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VENV_PYTHON = ROOT / ".venv" / "bin" / "python"


def run(*args: str) -> None:
    subprocess.run(args, cwd=ROOT, check=True)


def docs_python() -> str:
    override = os.environ.get("SLACK_MIRROR_DOCS_PYTHON")
    if override:
        return override
    if DEFAULT_VENV_PYTHON.exists():
        return str(DEFAULT_VENV_PYTHON)
    return sys.executable


def main() -> int:
    python = docs_python()
    markdown_path = ROOT / "docs" / "CLI.md"
    man_path = ROOT / "docs" / "slack-mirror.1"
    with tempfile.TemporaryDirectory(prefix="slack-mirror-doc-check-") as tmp_dir:
        tmp_root = Path(tmp_dir)
        generated_markdown = tmp_root / "CLI.md"
        generated_man = tmp_root / "slack-mirror.1"
        run(python, "-m", "slack_mirror.cli.main", "docs", "generate", "--format", "markdown", "--output", str(generated_markdown))
        run(python, "-m", "slack_mirror.cli.main", "docs", "generate", "--format", "man", "--output", str(generated_man))

        if markdown_path.read_text() != generated_markdown.read_text() or man_path.read_text() != generated_man.read_text():
            print("Generated docs are out of date. Run docs generate and commit the changes.", file=sys.stderr)
            return 1
    print("Generated docs are up to date.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
