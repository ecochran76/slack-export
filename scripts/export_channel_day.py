#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import shutil
import sqlite3
from pathlib import Path
from zoneinfo import ZoneInfo

from slack_mirror.core.config import load_config
from slack_mirror.exports import build_export_id, build_export_url, resolve_export_base_url, resolve_export_root, slugify


def day_bounds_epoch(day: str, tz_name: str) -> tuple[float, float]:
    tz = ZoneInfo(tz_name)
    d = dt.date.fromisoformat(day)
    start = dt.datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=tz)
    end = start + dt.timedelta(days=1)
    return start.timestamp(), end.timestamp()


def parse_ts(ts: str, tz_name: str) -> str:
    t = dt.datetime.fromtimestamp(float(ts), tz=ZoneInfo(tz_name))
    return t.strftime("%Y-%m-%d %H:%M:%S %Z")


def resolve_user_label(conn: sqlite3.Connection, ws_id: int, user_id: str | None) -> str:
    if not user_id:
        return "unknown"
    row = conn.execute(
        "select raw_json from users where workspace_id=? and user_id=?",
        (ws_id, user_id),
    ).fetchone()
    if not row or not row[0]:
        return user_id
    try:
        data = json.loads(row[0])
    except Exception:
        return user_id
    profile = data.get("profile") or {}
    for key in ("display_name", "real_name", "name"):
        val = profile.get(key) or data.get(key)
        if isinstance(val, str) and val.strip():
            return f"{val.strip()} ({user_id})"
    return user_id


def load_rows(conn: sqlite3.Connection, workspace: str, channel: str, day: str, tz_name: str):
    start_ts, end_ts = day_bounds_epoch(day, tz_name)
    ws = conn.execute("select id from workspaces where name=?", (workspace,)).fetchone()
    if not ws:
        raise SystemExit(f"workspace not found: {workspace}")
    ws_id = int(ws[0])

    ch = conn.execute(
        "select channel_id,name from channels where workspace_id=? and (channel_id=? or name=?)",
        (ws_id, channel, channel),
    ).fetchone()
    if not ch:
        raise SystemExit(f"channel not found: {channel}")
    channel_id, channel_name = ch[0], ch[1] or channel

    base = conn.execute(
        """
        select ts, user_id, text, subtype, thread_ts, edited_ts, deleted, raw_json
        from messages
        where workspace_id=? and channel_id=? and cast(ts as real) >= ? and cast(ts as real) < ?
        order by cast(ts as real)
        """,
        (ws_id, channel_id, start_ts, end_ts),
    ).fetchall()

    roots: set[str] = set()
    seen: set[str] = set()
    rows = []
    for r in base:
        ts = str(r[0])
        seen.add(ts)
        rows.append(r)
        thread_ts = r[4]
        roots.add(str(thread_ts or ts))

    if roots:
        placeholders = ",".join("?" for _ in roots)
        q = f"""
        select ts, user_id, text, subtype, thread_ts, edited_ts, deleted, raw_json
        from messages
        where workspace_id=? and channel_id=? and thread_ts in ({placeholders})
        order by cast(ts as real)
        """
        for r in conn.execute(q, (ws_id, channel_id, *sorted(roots))).fetchall():
            ts = str(r[0])
            if ts in seen:
                continue
            seen.add(ts)
            rows.append(r)

    rows.sort(key=lambda x: float(x[0]))
    return ws_id, channel_id, channel_name, rows


def _copy_attachment_into_bundle(local_path: str, bundle_dir: Path, attachment: dict) -> tuple[str, str] | tuple[None, None]:
    src = Path(local_path).expanduser()
    if not src.exists() or not src.is_file():
        return None, None
    stem = slugify(attachment.get("id") or attachment.get("name") or "attachment", max_length=24)
    safe_name = slugify(Path(attachment.get("name") or src.name).stem, max_length=40)
    suffix = Path(attachment.get("name") or src.name).suffix or src.suffix
    relpath = Path("attachments") / stem / f"{safe_name}{suffix}"
    dst = bundle_dir / relpath
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return str(relpath.as_posix()), str(dst)


def extract_attachments(
    conn: sqlite3.Connection,
    ws_id: int,
    raw_json: str | None,
    *,
    bundle_dir: Path | None = None,
    export_id: str | None = None,
    public_base_url: str | None = None,
) -> list[dict]:
    if not raw_json:
        return []
    try:
        data = json.loads(raw_json)
    except Exception:
        return []
    out: list[dict] = []
    for f in data.get("files", []) or []:
        fid = f.get("id")
        local_path = None
        if fid:
            row = conn.execute(
                "select local_path from files where workspace_id=? and file_id=?", (ws_id, fid)
            ).fetchone()
            local_path = row[0] if row else None
        out.append(
            {
                "id": fid,
                "name": f.get("name") or f.get("title") or fid,
                "mimetype": f.get("mimetype"),
                "permalink": f.get("permalink") or f.get("url_private"),
                "local_path": local_path,
            }
        )
        if bundle_dir and local_path:
            relpath, exported_path = _copy_attachment_into_bundle(local_path, bundle_dir, out[-1])
            if relpath:
                out[-1]["export_relpath"] = relpath
                out[-1]["export_path"] = exported_path
                if public_base_url and export_id:
                    export_url = build_export_url(public_base_url, export_id, relpath)
                    out[-1]["download_url"] = export_url
                    out[-1]["public_url"] = export_url
    return out


def render_html(workspace: str, channel_name: str, day: str, tz_name: str, messages: list[dict]) -> str:
    lines = [
        "<!doctype html>",
        "<html><head><meta charset='utf-8'>",
        f"<title>{html.escape(workspace)} #{html.escape(channel_name)} {html.escape(day)}</title>",
        "<style>body{font-family:Arial,sans-serif;max-width:980px;margin:24px auto;line-height:1.4}"
        ".m{border-bottom:1px solid #ddd;padding:10px 0;position:relative}"
        ".m.reply{margin-left:96px;padding:12px 0 12px 22px;background:#f8fafc;border-radius:6px;border-left:8px solid #334155}"
        ".m.reply:before{content:'';position:absolute;left:-74px;top:22px;width:64px;height:0;border-top:3px solid #334155;opacity:.9}"
        ".reply-badge{display:inline-block;background:#0f172a;color:#fff;font-size:10px;padding:2px 6px;border-radius:999px;margin-right:8px;letter-spacing:.02em}"
        ".meta{color:#555;font-size:12px}.txt{white-space:pre-wrap}.att{margin-top:6px;font-size:13px}"
        ".att a{color:#0b57d0;text-decoration:underline}.thumb{width:3.5in;max-width:100%;height:auto;border:1px solid #ddd;border-radius:4px;margin-top:4px}"
        " code{background:#f4f4f4;padding:1px 4px}"
        "</style></head><body>",
        f"<h1>{html.escape(workspace)} / #{html.escape(channel_name)}</h1>",
        f"<p><b>Date:</b> {html.escape(day)} ({html.escape(tz_name)})</p>",
        f"<p><b>Messages exported:</b> {len(messages)}</p>",
    ]
    for message in messages:
        ts = message.get("ts")
        subtype = message.get("subtype")
        thread_ts = message.get("thread_ts")
        deleted = message.get("deleted")
        attachments = message.get("attachments") or []
        user_label = message.get("user_label") or message.get("user_id") or "unknown"
        is_reply = bool(thread_ts) and str(thread_ts) != str(ts)
        lines.append("<div class='m reply'>" if is_reply else "<div class='m'>")
        meta_prefix = "<span class='reply-badge'>THREAD REPLY</span>" if is_reply else ""
        lines.append(
            f"<div class='meta'>{meta_prefix}<b>{html.escape(str(user_label))}</b> · {html.escape(str(message.get('human_ts') or parse_ts(str(ts), tz_name)))}"
            + (f" · subtype={html.escape(subtype)}" if subtype else "")
            + (" · deleted" if int(deleted or 0) else "")
            + (f" · thread={html.escape(str(thread_ts))}" if thread_ts else "")
            + "</div>"
        )
        lines.append(f"<div class='txt'>{html.escape(message.get('text') or '')}</div>")
        if attachments:
            lines.append("<div class='att'><b>Attachments</b><ul>")
            for a in attachments:
                link = a.get("public_url") or a.get("download_url") or a.get("permalink") or a.get("local_path") or ""
                mimetype = (a.get("mimetype") or "").lower()
                image_src = a.get("public_url") or a.get("download_url") or a.get("export_relpath") or a.get("local_path") or ""
                thumb = ""
                if image_src and mimetype.startswith("image/"):
                    thumb = f"<br><img class='thumb' src='{html.escape(str(image_src))}' alt='{html.escape(a.get('name') or 'attachment')}' />"
                name = html.escape(a.get("name") or "file")
                href = html.escape(str(link)) if link else ""
                label = f"<a href='{href}' target='_blank' rel='noopener'>{name}</a>" if href else name
                lines.append(
                    "<li>"
                    + label
                    + (f" (<code>{html.escape(a.get('mimetype') or '')}</code>)" if a.get("mimetype") else "")
                    + (f" — <code>{href}</code>" if href else "")
                    + thumb
                    + "</li>"
                )
            lines.append("</ul></div>")
        lines.append("</div>")
    lines.append("</body></html>")
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser(description="Export one channel day (+ thread replies) to HTML/JSON")
    p.add_argument("--config", default=None)
    p.add_argument("--db", required=True)
    p.add_argument("--workspace", required=True)
    p.add_argument("--channel", required=True, help="channel name or id")
    p.add_argument("--day", required=True, help="YYYY-MM-DD in target timezone")
    p.add_argument("--tz", default="America/Chicago")
    p.add_argument("--out-html")
    p.add_argument("--out-json")
    p.add_argument("--managed-export", action="store_true", help="write into the configured export root with a deterministic export id")
    p.add_argument("--export-root", help="override export root directory")
    p.add_argument("--export-id", help="explicit export id (default: deterministic from workspace/channel/day)")
    p.add_argument("--link-audience", choices=["local", "external"], default="local", help="base URL audience for generated download links")
    args = p.parse_args()

    conn = sqlite3.connect(args.db)
    ws_id, channel_id, channel_name, rows = load_rows(conn, args.workspace, args.channel, args.day, args.tz)

    config = load_config(args.config) if args.managed_export or args.config else None
    export_id = args.export_id
    bundle_dir: Path | None = None
    public_base_url: str | None = None
    out_html_path = Path(args.out_html).expanduser() if args.out_html else None
    out_json_path = Path(args.out_json).expanduser() if args.out_json else None

    if args.managed_export:
        export_root = Path(args.export_root).expanduser().resolve() if args.export_root else resolve_export_root(config)
        export_id = export_id or build_export_id(
            "channel-day",
            workspace=args.workspace,
            channel=channel_name,
            day=args.day,
        )
        bundle_dir = export_root / export_id
        out_html_path = out_html_path or (bundle_dir / "index.html")
        out_json_path = out_json_path or (bundle_dir / "channel-day.json")
        public_base_url = resolve_export_base_url(config, audience=args.link_audience)

    if out_html_path is None:
        raise SystemExit("--out-html is required unless --managed-export is used")

    serial = []
    for r in rows:
        ts, user_id, text, subtype, thread_ts, edited_ts, deleted, raw_json = r
        serial.append(
            {
                "ts": ts,
                "human_ts": parse_ts(str(ts), args.tz),
                "user_id": user_id,
                "user_label": resolve_user_label(conn, ws_id, user_id),
                "text": text,
                "subtype": subtype,
                "thread_ts": thread_ts,
                "edited_ts": edited_ts,
                "deleted": bool(deleted),
                "attachments": extract_attachments(
                    conn,
                    ws_id,
                    raw_json,
                    bundle_dir=bundle_dir,
                    export_id=export_id,
                    public_base_url=public_base_url,
                ),
            }
        )
    export_payload = {
        "workspace": args.workspace,
        "channel": channel_name,
        "channel_id": channel_id,
        "day": args.day,
        "tz": args.tz,
        "export_id": export_id,
        "public_base_url": public_base_url,
        "messages": serial,
    }
    html_doc = render_html(args.workspace, channel_name, args.day, args.tz, serial)

    out_html_path.parent.mkdir(parents=True, exist_ok=True)
    out_html_path.write_text(html_doc, encoding="utf-8")

    if out_json_path:
        out_json_path.parent.mkdir(parents=True, exist_ok=True)
        out_json_path.write_text(json.dumps(export_payload, indent=2), encoding="utf-8")

    print(f"Exported {len(rows)} messages to {out_html_path}")
    if out_json_path:
        print(f"Wrote JSON bundle: {out_json_path}")
    if bundle_dir:
        print(f"Export bundle: {bundle_dir}")
        if public_base_url:
            print(f"Download base: {public_base_url}/exports/{export_id}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
