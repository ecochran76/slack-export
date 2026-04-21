CREATE TABLE IF NOT EXISTS message_files (
  workspace_id INTEGER NOT NULL,
  channel_id TEXT NOT NULL,
  ts TEXT NOT NULL,
  file_id TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (workspace_id, channel_id, ts, file_id),
  FOREIGN KEY (workspace_id, channel_id, ts) REFERENCES messages(workspace_id, channel_id, ts) ON DELETE CASCADE,
  FOREIGN KEY (workspace_id, file_id) REFERENCES files(workspace_id, file_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_message_files_file
  ON message_files(workspace_id, file_id);
