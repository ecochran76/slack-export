CREATE TABLE IF NOT EXISTS channel_members (
  workspace_id INTEGER NOT NULL,
  channel_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (workspace_id, channel_id, user_id),
  FOREIGN KEY (workspace_id, channel_id) REFERENCES channels(workspace_id, channel_id) ON DELETE CASCADE
);
