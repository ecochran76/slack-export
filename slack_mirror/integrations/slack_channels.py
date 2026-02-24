from __future__ import annotations

import json
import subprocess
from pathlib import Path

SCRIPT = Path.home() / ".openclaw/workspace/scripts/slack_channels"
STORE = Path.home() / ".openclaw/notes/dev-projects/slack-channels.json"


class SlackChannelsAdapter:
    def __init__(self, script: Path = SCRIPT):
        self.script = script

    def _run(self, *args: str) -> str:
        result = subprocess.run(
            [str(self.script), *args],
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip())
        return result.stdout.strip()

    def resolve(self, name: str) -> str:
        return self._run("resolve", name)

    def fetch(self, name: str) -> str:
        return self._run("fetch", name)

    def list_mappings(self) -> dict[str, str]:
        if not STORE.exists():
            return {}
        data = json.loads(STORE.read_text(encoding="utf-8"))
        return data.get("channels", {})
