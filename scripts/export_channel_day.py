#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import sqlite3
from pathlib import Path
from zoneinfo import ZoneInfo


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


def extract_attachments(conn: sqlite3.Connection, ws_id: int, raw_json: str | None) -> list[dict]:
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
    return out


def render_html(workspace: str, channel_name: str, day: str, tz_name: str, rows, conn, ws_id: int) -> str:
    lines = [
        "<!doctype html>",
        "<html><head><meta charset='utf-8'>",
        f"<title>{html.escape(workspace)} #{html.escape(channel_name)} {html.escape(day)}</title>",
        "<style>body{font-family:Arial,sans-serif;max-width:980px;margin:24px auto;line-height:1.4}"
        ".m{border-bottom:1px solid #ddd;padding:10px 0}.m.reply{margin-left:28px;border-left:3px solid #e5e7eb;padding-left:12px}"
        ".meta{color:#555;font-size:12px}.txt{white-space:pre-wrap}.att{margin-top:6px;font-size:13px}"
        ".thumb{width:3.5in;max-width:100%;height:auto;border:1px solid #ddd;border-radius:4px;margin-top:4px}"
        " code{background:#f4f4f4;padding:1px 4px}"
        "</style></head><body>",
        f"<h1>{html.escape(workspace)} / #{html.escape(channel_name)}</h1>",
        f"<p><b>Date:</b> {html.escape(day)} ({html.escape(tz_name)})</p>",
        f"<p><b>Messages exported:</b> {len(rows)}</p>",
    ]
    for r in rows:
        ts, user_id, text, subtype, thread_ts, edited_ts, deleted, raw_json = r
        attachments = extract_attachments(conn, ws_id, raw_json)
        user_label = resolve_user_label(conn, ws_id, user_id)
        is_reply = bool(thread_ts) and str(thread_ts) != str(ts)
        lines.append("<div class='m reply'>" if is_reply else "<div class='m'>")
        lines.append(
            f"<div class='meta'><b>{html.escape(user_label)}</b> · {html.escape(parse_ts(str(ts), tz_name))}"
            + (f" · subtype={html.escape(subtype)}" if subtype else "")
            + (" · deleted" if int(deleted or 0) else "")
            + (f" · thread={html.escape(str(thread_ts))}" if thread_ts else "")
            + "</div>"
        )
        lines.append(f"<div class='txt'>{html.escape(text or '')}</div>")
        if attachments:
            lines.append("<div class='att'><b>Attachments</b><ul>")
            for a in attachments:
                link = a.get("local_path") or a.get("permalink") or ""
                mimetype = (a.get("mimetype") or "").lower()
                local_path = a.get("local_path") or ""
                thumb = ""
                if local_path and mimetype.startswith("image/"):
                    thumb = f"<br><img class='thumb' src='{html.escape(local_path)}' alt='{html.escape(a.get('name') or 'attachment')}' />"
                lines.append(
                    "<li>"
                    + html.escape(a.get("name") or "file")
                    + (f" (<code>{html.escape(a.get('mimetype') or '')}</code>)" if a.get("mimetype") else "")
                    + (f" — {html.escape(str(link))}" if link else "")
                    + thumb
                    + "</li>"
                )
            lines.append("</ul></div>")
        lines.append("</div>")
    lines.append("</body></html>")
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser(description="Export one channel day (+ thread replies) to HTML/JSON")
    p.add_argument("--db", required=True)
    p.add_argument("--workspace", required=True)
    p.add_argument("--channel", required=True, help="channel name or id")
    p.add_argument("--day", required=True, help="YYYY-MM-DD in target timezone")
    p.add_argument("--tz", default="America/Chicago")
    p.add_argument("--out-html", required=True)
    p.add_argument("--out-json", required=False)
    args = p.parse_args()

    conn = sqlite3.connect(args.db)
    ws_id, channel_id, channel_name, rows = load_rows(conn, args.workspace, args.channel, args.day, args.tz)
    html_doc = render_html(args.workspace, channel_name, args.day, args.tz, rows, conn, ws_id)

    out_html = Path(args.out_html)
    out_html.parent.mkdir(parents=True, exist_ok=True)
    out_html.write_text(html_doc, encoding="utf-8")

    if args.out_json:
        out_json = Path(args.out_json)
        out_json.parent.mkdir(parents=True, exist_ok=True)
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
                    "attachments": extract_attachments(conn, ws_id, raw_json),
                }
            )
        out_json.write_text(json.dumps({"workspace": args.workspace, "channel": channel_name, "channel_id": channel_id, "day": args.day, "tz": args.tz, "messages": serial}, indent=2), encoding="utf-8")

    print(f"Exported {len(rows)} messages to {out_html}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
