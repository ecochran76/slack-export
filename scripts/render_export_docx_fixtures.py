#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

DEFAULT_RENDER_SCRIPT = (
    Path("/home/ecochran76/workspace.local/agent-skills/docx-skill/render_docx.py")
)


def _load_module(module_name: str, script_name: str):
    script_path = Path(__file__).resolve().parent / script_name
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def fixture_profiles() -> dict[str, dict[str, Any]]:
    return {
        "compact_default": {
            "font_family": "Arial",
            "body_font_size_pt": 10,
            "margin_in": 1.0,
            "compactness": "compact",
            "accent_color": "3B5B7A",
        },
        "cozy_review": {
            "font_family": "Aptos",
            "body_font_size_pt": 11,
            "margin_in": 1.25,
            "compactness": "cozy",
            "accent_color": "8B5CF6",
        },
    }


def _sample_messages(
    *,
    day: str,
    lead_user: str,
    reply_user: str,
    local_attachment: str,
    local_docx: str,
    permalink_attachment: str,
) -> list[dict[str, Any]]:
    return [
        {
            "ts": "10.0",
            "human_ts": f"{day} 09:14:00 CDT",
            "user_id": "U1",
            "user_label": lead_user,
            "text": (
                "Daily launch brief\n"
                "Primary risks are queue lag, export regression, and customer follow-up.\n"
                "Keep the closeout compact and preserve attachment context."
            ),
            "thread_ts": None,
            "deleted": False,
            "attachments": [
                {
                    "name": "launch-brief.pdf",
                    "mimetype": "application/pdf",
                    "local_path": local_attachment,
                    "permalink": None,
                },
                {
                    "name": "speaker-notes.docx",
                    "mimetype": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    "local_path": local_docx,
                    "permalink": None,
                },
                {
                    "name": "roadmap-link.png",
                    "mimetype": "image/png",
                    "local_path": None,
                    "permalink": permalink_attachment,
                },
            ],
        },
        {
            "ts": "10.1",
            "human_ts": f"{day} 09:19:00 CDT",
            "user_id": "U2",
            "user_label": reply_user,
            "text": (
                "Reply detail\n"
                "Keep attachments readable and thread context quiet.\n"
                "Use the canonical JSON artifact for all renderers."
            ),
            "thread_ts": "10.0",
            "deleted": False,
            "attachments": [],
        },
        {
            "ts": "11.0",
            "human_ts": f"{day} 13:05:00 CDT",
            "user_id": "U3",
            "user_label": "Jordan (U3)",
            "text": (
                "Follow-up note\n"
                "Visual QA should rely on stable fixture outputs rather than ad hoc sample generation."
            ),
            "thread_ts": None,
            "deleted": False,
            "attachments": [],
        },
    ]


def _write_fixture_json(
    path: Path,
    *,
    workspace: str,
    channel: str,
    channel_id: str,
    day: str,
    messages: list[dict[str, Any]],
) -> None:
    payload = {
        "workspace": workspace,
        "channel": channel,
        "channel_id": channel_id,
        "day": day,
        "tz": "America/Chicago",
        "messages": messages,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def build_fixture_inputs(output_dir: Path) -> dict[str, Any]:
    source_dir = output_dir / "fixture_inputs"
    attachments_dir = source_dir / "attachments"
    attachments_dir.mkdir(parents=True, exist_ok=True)

    pdf_path = attachments_dir / "launch-brief.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n% fixture\n")
    docx_path = attachments_dir / "speaker-notes.docx"
    docx_path.write_bytes(b"PK\x03\x04fixture-docx")

    day_one = source_dir / "channel-day-2026-04-11.json"
    day_two = source_dir / "channel-day-2026-04-12.json"

    _write_fixture_json(
        day_one,
        workspace="default",
        channel="general",
        channel_id="C1",
        day="2026-04-11",
        messages=_sample_messages(
            day="2026-04-11",
            lead_user="Eric (U1)",
            reply_user="Alicia (U2)",
            local_attachment=str(pdf_path),
            local_docx=str(docx_path),
            permalink_attachment="https://example.test/roadmap-link.png",
        ),
    )
    _write_fixture_json(
        day_two,
        workspace="default",
        channel="launches",
        channel_id="C2",
        day="2026-04-12",
        messages=_sample_messages(
            day="2026-04-12",
            lead_user="Morgan (U4)",
            reply_user="Sam (U5)",
            local_attachment=str(pdf_path),
            local_docx=str(docx_path),
            permalink_attachment="https://example.test/launches-roadmap.png",
        ),
    )

    return {
        "source_dir": source_dir,
        "day_inputs": [day_one, day_two],
    }


def _render_docx_artifact(
    render_script: Path,
    docx_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    if not render_script.exists():
        raise FileNotFoundError(f"render script not found: {render_script}")
    output_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        str(render_script),
        str(docx_path),
        "--output_dir",
        str(output_dir),
        "--emit_pdf",
    ]
    proc = subprocess.run(
        cmd,
        check=False,
        capture_output=True,
        text=True,
    )
    rendered_files = sorted(
        path.name for path in output_dir.iterdir() if path.is_file()
    )
    return {
        "command": cmd,
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "rendered_files": rendered_files,
    }


def generate_fixture_artifacts(
    output_dir: Path,
    *,
    render: bool = True,
    render_script: Path = DEFAULT_RENDER_SCRIPT,
) -> dict[str, Any]:
    export_module = _load_module("export_channel_day_docx", "export_channel_day_docx.py")
    validator_module = _load_module("validate_export_docx", "validate_export_docx.py")

    output_dir.mkdir(parents=True, exist_ok=True)
    inputs = build_fixture_inputs(output_dir)
    profiles_manifest: dict[str, Any] = {}

    for profile_name, style_kwargs in fixture_profiles().items():
        profile_dir = output_dir / profile_name
        docx_dir = profile_dir / "docx"
        render_dir = profile_dir / "rendered"
        docx_dir.mkdir(parents=True, exist_ok=True)

        style = export_module._build_style(**style_kwargs)
        single_docx = docx_dir / "channel-day.docx"
        multi_docx = docx_dir / "daypack.docx"

        export_module.render_channel_day_docx(
            inputs["day_inputs"][0],
            single_docx,
            docx_style=style,
        )
        export_module.render_multi_day_docx(
            list(inputs["day_inputs"]),
            multi_docx,
            package_title="Slack Export DOCX Fixture Package",
            docx_style=style,
        )

        single_validation = validator_module.inspect_docx(single_docx)
        multi_validation = validator_module.inspect_docx(multi_docx)
        profile_manifest: dict[str, Any] = {
            "style": style_kwargs,
            "artifacts": {
                "channel_day": {
                    "input_json": str(inputs["day_inputs"][0].relative_to(output_dir)),
                    "docx": str(single_docx.relative_to(output_dir)),
                    "validation": single_validation,
                },
                "daypack": {
                    "input_jsons": [
                        str(path.relative_to(output_dir)) for path in inputs["day_inputs"]
                    ],
                    "docx": str(multi_docx.relative_to(output_dir)),
                    "validation": multi_validation,
                },
            },
        }

        if render:
            single_render_dir = render_dir / "channel-day"
            multi_render_dir = render_dir / "daypack"
            profile_manifest["artifacts"]["channel_day"]["render"] = _render_docx_artifact(
                render_script,
                single_docx,
                single_render_dir,
            )
            profile_manifest["artifacts"]["daypack"]["render"] = _render_docx_artifact(
                render_script,
                multi_docx,
                multi_render_dir,
            )

        profiles_manifest[profile_name] = profile_manifest

    manifest = {
        "profiles": profiles_manifest,
        "fixture_inputs": [str(path.relative_to(output_dir)) for path in inputs["day_inputs"]],
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Generate canonical DOCX export fixture artifacts for visual review"
    )
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--skip-render", action="store_true")
    ap.add_argument("--render-script", default=str(DEFAULT_RENDER_SCRIPT))
    args = ap.parse_args()

    output_dir = Path(args.output_dir).expanduser().resolve()
    manifest = generate_fixture_artifacts(
        output_dir,
        render=not args.skip_render,
        render_script=Path(args.render_script).expanduser().resolve(),
    )
    print(
        json.dumps(
            {
                "output_dir": str(output_dir),
                "profiles": sorted(manifest["profiles"].keys()),
                "rendered": not args.skip_render,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
