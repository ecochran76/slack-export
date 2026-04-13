from __future__ import annotations

import json
from typing import Callable

from slack_mirror.service.runtime_report import write_runtime_report_snapshot
from slack_mirror.service.user_env import UserEnvPaths, default_user_env_paths


PrintFn = Callable[[str], None]


def snapshot_runtime_report_user_env(
    *,
    paths: UserEnvPaths | None = None,
    base_url: str = "http://slack.localhost",
    name: str = "runtime-report",
    timeout: float = 5.0,
    json_output: bool = False,
    out: PrintFn = print,
) -> int:
    managed_paths = paths or default_user_env_paths()
    result = write_runtime_report_snapshot(
        config_path=str(managed_paths.config_path),
        base_url=base_url,
        name=name,
        timeout=timeout,
    )
    if json_output:
        out(json.dumps(result, indent=2))
    else:
        out(
            "Runtime report snapshot "
            f"name={result['name']} status={result['status']} "
            f"markdown={result['markdown_path']} html={result['html_path']}"
        )
        out(f"Latest markdown: {result['latest_markdown_path']}")
        out(f"Latest html: {result['latest_html_path']}")
        out(f"Latest metadata: {result['latest_json_path']}")
    return 0
