CREATE TABLE IF NOT EXISTS message_embeddings (
  workspace_id INTEGER NOT NULL,
  channel_id TEXT NOT NULL,
  ts TEXT NOT NULL,
  model_id TEXT NOT NULL,
  dim INTEGER NOT NULL,
  embedding_blob BLOB NOT NULL,
  content_hash TEXT NOT NULL,
  embedded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (workspace_id, channel_id, ts, model_id),
  FOREIGN KEY (workspace_id, channel_id, ts) REFERENCES messages(workspace_id, channel_id, ts) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_message_embeddings_workspace_model
  ON message_embeddings(workspace_id, model_id);

CREATE INDEX IF NOT EXISTS idx_message_embeddings_workspace_message
  ON message_embeddings(workspace_id, channel_id, ts);

CREATE INDEX IF NOT EXISTS idx_message_embeddings_workspace_hash
  ON message_embeddings(workspace_id, content_hash);
