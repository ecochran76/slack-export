CREATE TABLE IF NOT EXISTS embedding_jobs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  workspace_id INTEGER NOT NULL,
  channel_id TEXT NOT NULL,
  ts TEXT NOT NULL,
  reason TEXT NOT NULL DEFAULT 'upsert',
  status TEXT NOT NULL DEFAULT 'pending',
  error TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (workspace_id, channel_id, ts),
  FOREIGN KEY (workspace_id, channel_id, ts) REFERENCES messages(workspace_id, channel_id, ts) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_embedding_jobs_workspace_status
  ON embedding_jobs(workspace_id, status, id);
