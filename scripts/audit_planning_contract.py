#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


ROADMAP_HEADING_RE = re.compile(r"^##\s+P\d{2}\s+\|\s+.+$")
RUNBOOK_TURN_RE = re.compile(r"^##\s+Turn\s+\d+\s+\|\s+\d{4}-\d{2}-\d{2}$")
PLAN_FILE_RE = re.compile(r"^\d{4}-\d{4}-\d{2}-\d{2}-[a-z0-9-]+\.md$")
PLAN_STATE_RE = re.compile(r"(?im)^(?:state|status)\s*:\s*(PLANNED|OPEN|CLOSED|CANCELLED)\s*$")
ROADMAP_LANE_RE = re.compile(r"(?im)^(?:roadmap|lane|phase)\s*:\s*(P\d{2})\b")
CURRENT_STATE_RE = re.compile(r"(?im)^##\s+Current State\s*$|^(?:current state)\s*:", re.MULTILINE)


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def split_roadmap_sections(roadmap_text: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    current_lane: str | None = None
    current_lines: list[str] = []
    for line in roadmap_text.splitlines():
        if line.startswith("## "):
            if current_lane is not None:
                sections[current_lane] = "\n".join(current_lines).strip()
            current_lines = [line]
            match = re.match(r"^##\s+(P\d{2})\s+\|", line)
            current_lane = match.group(1) if match else None
        elif current_lane is not None:
            current_lines.append(line)
    if current_lane is not None:
        sections[current_lane] = "\n".join(current_lines).strip()
    return sections


def audit_repo(root: Path) -> dict:
    roadmap = root / "ROADMAP.md"
    runbook = root / "RUNBOOK.md"
    plans_dir = root / "docs" / "dev" / "plans"

    problems: list[str] = []
    report: dict[str, object] = {
        "repo_root": str(root),
        "roadmap_path": str(roadmap),
        "runbook_path": str(runbook),
        "plans_dir": str(plans_dir),
        "plans": [],
    }

    roadmap_text = read_text(roadmap)
    runbook_text = read_text(runbook)

    if not roadmap_text:
        problems.append("missing ROADMAP.md")
    if not runbook_text:
        problems.append("missing RUNBOOK.md")
    if not plans_dir.exists():
        problems.append("missing docs/dev/plans directory")

    roadmap_headings = [line for line in roadmap_text.splitlines() if line.startswith("## ")]
    bad_headings = [line for line in roadmap_headings if not ROADMAP_HEADING_RE.match(line)]
    if roadmap_text and bad_headings:
        problems.append("ROADMAP.md has top-level headings that do not match '## P## | Title'")
    report["roadmap_headings"] = roadmap_headings
    roadmap_sections = split_roadmap_sections(roadmap_text)
    open_roadmap_lanes = [
        lane_id
        for lane_id, section in roadmap_sections.items()
        if re.search(r"(?im)^(?:state|status)\s*:\s*OPEN\s*$", section)
    ]
    report["open_roadmap_lanes"] = open_roadmap_lanes
    for lane_id in open_roadmap_lanes:
        section = roadmap_sections[lane_id]
        if not CURRENT_STATE_RE.search(section):
            problems.append(f"OPEN roadmap lane missing Current State note: {lane_id}")

    runbook_turns = [line for line in runbook_text.splitlines() if line.startswith("## ")]
    bad_turns = [line for line in runbook_turns if not RUNBOOK_TURN_RE.match(line)]
    if runbook_text and bad_turns:
        problems.append("RUNBOOK.md has headings that do not match '## Turn N | YYYY-MM-DD'")
    report["runbook_turns"] = runbook_turns

    if plans_dir.exists():
        for plan_path in sorted(plans_dir.glob("*.md")):
            entry = {
                "file": plan_path.name,
                "path": str(plan_path),
                "filename_ok": bool(PLAN_FILE_RE.match(plan_path.name)),
                "state": None,
                "state_ok": False,
                "lane_id": None,
                "lane_ok": False,
                "current_state_ok": False,
                "wired_in_roadmap": False,
                "wired_in_runbook": False,
            }
            text = read_text(plan_path)
            state_match = PLAN_STATE_RE.search(text)
            lane_match = ROADMAP_LANE_RE.search(text)
            if state_match:
                entry["state"] = state_match.group(1)
                entry["state_ok"] = True
            if lane_match:
                entry["lane_id"] = lane_match.group(1)
                entry["lane_ok"] = True
            entry["current_state_ok"] = bool(CURRENT_STATE_RE.search(text))
            entry["wired_in_roadmap"] = plan_path.name in roadmap_text
            entry["wired_in_runbook"] = plan_path.name in runbook_text
            if not entry["filename_ok"]:
                problems.append(f"plan filename does not match deterministic pattern: {plan_path.name}")
            if not entry["state_ok"]:
                problems.append(f"plan missing deterministic state: {plan_path.name}")
            if not entry["lane_ok"]:
                problems.append(f"plan missing roadmap lane id: {plan_path.name}")
            if entry["state"] == "OPEN" and not entry["current_state_ok"]:
                problems.append(f"OPEN plan missing Current State section: {plan_path.name}")
            if not entry["wired_in_roadmap"]:
                problems.append(f"plan not wired in ROADMAP.md: {plan_path.name}")
            if not entry["wired_in_runbook"]:
                problems.append(f"plan not wired in RUNBOOK.md: {plan_path.name}")
            cast_list = report["plans"]
            assert isinstance(cast_list, list)
            cast_list.append(entry)
        plans = report["plans"]
        assert isinstance(plans, list)
        actionable_states = {"PLANNED", "OPEN"}
        for lane_id in open_roadmap_lanes:
            if not any(
                plan.get("lane_id") == lane_id and plan.get("state") in actionable_states
                for plan in plans
                if isinstance(plan, dict)
            ):
                problems.append(f"OPEN roadmap lane missing actionable plan coverage: {lane_id}")

    report["ok"] = not problems
    report["problems"] = problems
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = audit_repo(Path(args.repo_root).resolve())
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"ok: {report['ok']}")
        if report["problems"]:
            print("problems:")
            for problem in report["problems"]:
                print(f"- {problem}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
