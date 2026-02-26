#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
from pathlib import Path

ENV_PATTERN = re.compile(r"\$\{([A-Z0-9_]+)(?::-([^}]*))?\}")


def expand_env(text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        fallback = match.group(2)
        return os.getenv(key, fallback if fallback is not None else "")

    return ENV_PATTERN.sub(repl, text)


def main() -> int:
    parser = argparse.ArgumentParser(description="Render Slack app manifest template with env vars")
    parser.add_argument("--template", default="manifests/slack-app.yaml")
    parser.add_argument("--output", default="manifests/slack-app.rendered.yaml")
    args = parser.parse_args()

    template_path = Path(args.template)
    output_path = Path(args.output)

    src = template_path.read_text(encoding="utf-8")
    rendered = expand_env(src)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(rendered, encoding="utf-8")

    print(f"Rendered manifest: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
