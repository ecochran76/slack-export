from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from slack_mirror import __version__


RunFn = Callable[..., subprocess.CompletedProcess]
PrintFn = Callable[[str], None]


@dataclass(frozen=True)
class ReleaseCheckIssue:
    severity: str
    code: str
    message: str
    command: list[str] | None = None


@dataclass(frozen=True)
class ReleaseCheckReport:
    ok: bool
    status: str
    exit_code: int
    summary: str
    version: str
    require_clean: bool
    require_release_version: bool
    failure_codes: list[str]
    warning_codes: list[str]
    failures: list[ReleaseCheckIssue]
    warnings: list[ReleaseCheckIssue]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _resolve_planning_audit_script(repo_root: Path) -> Path:
    override = os.environ.get("SLACK_MIRROR_PLANNING_AUDIT", "").strip()
    candidates: list[Path] = []
    if override:
        candidates.append(Path(override).expanduser())

    candidates.append(repo_root / "scripts" / "audit_planning_contract.py")
    for base in repo_root.parents:
        candidates.append(base / "agent-policies" / "repo-policy-selector" / "scripts" / "audit_planning_contract.py")

    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if resolved.exists():
            return resolved

    searched = ", ".join(str(path) for path in seen)
    raise FileNotFoundError(
        "planning audit helper not found; set SLACK_MIRROR_PLANNING_AUDIT or place agent-policies beside the repo. "
        f"Searched: {searched}"
    )


def _pyproject_version(repo_root: Path) -> str:
    import tomllib

    pyproject = repo_root / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    return str(data.get("project", {}).get("version", "0.0.0-dev"))


def _run_checked(
    runner: RunFn,
    args: list[str],
    *,
    cwd: Path,
    capture_output: bool = True,
) -> subprocess.CompletedProcess:
    completed = runner(args, check=False, text=True, cwd=str(cwd), capture_output=capture_output)
    if int(completed.returncode) != 0:
        raise RuntimeError((completed.stderr or completed.stdout or "").strip() or f"command failed: {' '.join(args)}")
    return completed


def _issue_payload(items: list[ReleaseCheckIssue]) -> list[dict[str, object]]:
    return [
        {
            "severity": item.severity,
            "code": item.code,
            "message": item.message,
            "command": item.command,
        }
        for item in items
    ]


def _report_payload(report: ReleaseCheckReport) -> dict[str, object]:
    return {
        "ok": report.ok,
        "status": report.status,
        "exit_code": report.exit_code,
        "summary": report.summary,
        "version": report.version,
        "require_clean": report.require_clean,
        "require_release_version": report.require_release_version,
        "failure_codes": report.failure_codes,
        "warning_codes": report.warning_codes,
        "failures": _issue_payload(report.failures),
        "warnings": _issue_payload(report.warnings),
    }


def release_check(
    *,
    repo_root: Path | None = None,
    runner: RunFn = subprocess.run,
    out: PrintFn = print,
    json_output: bool = False,
    require_clean: bool = False,
    require_release_version: bool = False,
) -> int:
    root = (repo_root or _repo_root()).resolve()
    failures: list[ReleaseCheckIssue] = []
    warnings: list[ReleaseCheckIssue] = []

    def fail(code: str, message: str, command: list[str] | None = None) -> None:
        failures.append(ReleaseCheckIssue("fail", code, message, command))

    def warn(code: str, message: str, command: list[str] | None = None) -> None:
        warnings.append(ReleaseCheckIssue("warn", code, message, command))

    version = _pyproject_version(root)
    if __version__ != version:
        fail(
            "VERSION_MISMATCH",
            f"runtime version {__version__} does not match pyproject version {version}",
        )

    if require_release_version and "dev" in version.lower():
        fail(
            "RELEASE_VERSION_REQUIRED",
            f"pyproject version {version} is still a development version",
        )
    elif "dev" in version.lower():
        warn(
            "DEV_VERSION",
            f"pyproject version {version} is a development version",
        )

    docs_cmd = [sys.executable, str(root / "scripts" / "check_generated_docs.py")]
    try:
        _run_checked(runner, docs_cmd, cwd=root)
    except Exception as exc:  # noqa: BLE001
        fail("DOCS_OUT_OF_DATE", f"generated CLI docs check failed: {exc}", docs_cmd)

    try:
        audit_script = _resolve_planning_audit_script(root)
        audit_cmd = [
            sys.executable,
            str(audit_script),
            "--repo-root",
            str(root),
            "--json",
        ]
        _run_checked(runner, audit_cmd, cwd=root)
    except Exception as exc:  # noqa: BLE001
        audit_cmd = locals().get("audit_cmd")
        fail("PLANNING_AUDIT_FAILED", f"planning contract audit failed: {exc}", audit_cmd)

    if require_clean:
        git_cmd = ["git", "status", "--short"]
        try:
            completed = _run_checked(runner, git_cmd, cwd=root)
            if (completed.stdout or "").strip():
                fail("DIRTY_WORKTREE", "git worktree is not clean", git_cmd)
        except Exception as exc:  # noqa: BLE001
            fail("GIT_STATUS_FAILED", f"git status check failed: {exc}", git_cmd)

    if failures:
        report = ReleaseCheckReport(
            ok=False,
            status="fail",
            exit_code=1,
            summary=f"Summary: FAIL ({len(failures)} failure{'s' if len(failures) != 1 else ''})",
            version=version,
            require_clean=require_clean,
            require_release_version=require_release_version,
            failure_codes=sorted({item.code for item in failures}),
            warning_codes=sorted({item.code for item in warnings}),
            failures=failures,
            warnings=warnings,
        )
    elif warnings:
        report = ReleaseCheckReport(
            ok=True,
            status="pass_with_warnings",
            exit_code=0,
            summary=f"Summary: PASS with warnings ({len(warnings)})",
            version=version,
            require_clean=require_clean,
            require_release_version=require_release_version,
            failure_codes=[],
            warning_codes=sorted({item.code for item in warnings}),
            failures=[],
            warnings=warnings,
        )
    else:
        report = ReleaseCheckReport(
            ok=True,
            status="pass",
            exit_code=0,
            summary="Summary: PASS",
            version=version,
            require_clean=require_clean,
            require_release_version=require_release_version,
            failure_codes=[],
            warning_codes=[],
            failures=[],
            warnings=[],
        )

    if json_output:
        out(json.dumps(_report_payload(report), indent=2, sort_keys=True))
        return report.exit_code

    out(f"Version: {report.version}")
    for item in report.failures:
        out(f"FAIL  [{item.code}] {item.message}")
        if item.command:
            out(f"  command: {' '.join(item.command)}")
    for item in report.warnings:
        out(f"WARN  [{item.code}] {item.message}")
        if item.command:
            out(f"  command: {' '.join(item.command)}")
    out(report.summary)
    return report.exit_code
