DROP TABLE IF EXISTS temp._message_file_backfill;

CREATE TEMP TABLE _message_file_backfill (
  workspace_id INTEGER NOT NULL,
  channel_id TEXT NOT NULL,
  ts TEXT NOT NULL,
  file_id TEXT NOT NULL
);

INSERT INTO _message_file_backfill(workspace_id, channel_id, ts, file_id)
SELECT
  m.workspace_id,
  m.channel_id,
  m.ts,
  json_extract(file_item.value, '$.id') AS file_id
FROM messages m
JOIN json_each(
  m.raw_json,
  '$.files'
) AS file_item
WHERE m.deleted = 0
  AND m.raw_json IS NOT NULL
  AND json_valid(m.raw_json)
  AND json_type(m.raw_json, '$.files') = 'array'
  AND json_extract(file_item.value, '$.id') IS NOT NULL;

CREATE INDEX _idx_message_file_backfill_file
  ON _message_file_backfill(workspace_id, file_id);

INSERT OR IGNORE INTO message_files(workspace_id, channel_id, ts, file_id)
SELECT b.workspace_id, b.channel_id, b.ts, b.file_id
FROM _message_file_backfill b
WHERE EXISTS (
  SELECT 1
  FROM files f
  WHERE f.workspace_id = b.workspace_id
    AND f.file_id = b.file_id
);

DROP TABLE temp._message_file_backfill;
