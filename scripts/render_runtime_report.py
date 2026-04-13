from __future__ import annotations

import argparse
from pathlib import Path

from slack_mirror.service.runtime_report import build_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Render a shareable Slack Mirror runtime report from the local API")
    parser.add_argument("--base-url", default="http://slack.localhost", help="base URL for the local API")
    parser.add_argument("--format", choices=["markdown", "html"], default="markdown", help="output format")
    parser.add_argument("--output", default=None, help="write report to this path instead of stdout")
    parser.add_argument("--timeout", type=float, default=5.0, help="request timeout in seconds")
    args = parser.parse_args()

    report = build_report(base_url=args.base_url, output_format=args.format, timeout=float(args.timeout))
    if args.output:
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(report, encoding="utf-8")
    else:
        print(report, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
