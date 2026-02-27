#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import sqlite3
from zoneinfo import ZoneInfo


def main() -> int:
    ap = argparse.ArgumentParser(description="Audit mirror freshness/completeness by workspace and channel class")
    ap.add_argument("--db", default="./.local/state/slack_mirror_test.db")
    ap.add_argument("--tz", default="America/Chicago")
    ap.add_argument("--stale-hours", type=float, default=24.0)
    args = ap.parse_args()

    conn = sqlite3.connect(args.db)
    stale_cutoff = dt.datetime.now(ZoneInfo(args.tz)).timestamp() - args.stale_hours * 3600

    q = """
    with last_msg as (
      select workspace_id, channel_id, max(cast(ts as real)) as max_ts
      from messages
      group by workspace_id, channel_id
    )
    select w.name as workspace,
           case
             when c.is_im=1 then 'im'
             when c.is_mpim=1 then 'mpim'
             when c.is_private=1 then 'private'
             else 'public'
           end as channel_class,
           count(*) as channels,
           sum(case when lm.max_ts is null then 1 else 0 end) as zero_msg_channels,
           sum(case when lm.max_ts is not null and lm.max_ts < ? then 1 else 0 end) as stale_channels,
           max(lm.max_ts) as class_latest_ts
    from channels c
    join workspaces w on w.id=c.workspace_id
    left join last_msg lm on lm.workspace_id=c.workspace_id and lm.channel_id=c.channel_id
    group by w.name, channel_class
    order by w.name, channel_class
    """

    rows = conn.execute(q, (stale_cutoff,)).fetchall()

    print("workspace\tclass\tchannels\tzero_msg\tstale\tlatest")
    for ws, cls, n, z, s, latest in rows:
        if latest:
            latest_s = dt.datetime.fromtimestamp(float(latest), ZoneInfo(args.tz)).isoformat()
        else:
            latest_s = "-"
        print(f"{ws}\t{cls}\t{n}\t{z}\t{s}\t{latest_s}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
