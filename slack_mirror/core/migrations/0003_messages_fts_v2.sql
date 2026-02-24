DROP TABLE IF EXISTS messages_fts;

CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
  workspace_id UNINDEXED,
  channel_id UNINDEXED,
  user_id UNINDEXED,
  ts UNINDEXED,
  text
);
