CREATE TABLE IF NOT EXISTS derived_text_chunk_embeddings (
  derived_text_chunk_id INTEGER NOT NULL,
  workspace_id INTEGER NOT NULL,
  model_id TEXT NOT NULL,
  dim INTEGER NOT NULL,
  embedding_blob BLOB NOT NULL,
  content_hash TEXT NOT NULL,
  embedded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (derived_text_chunk_id, model_id),
  FOREIGN KEY (derived_text_chunk_id) REFERENCES derived_text_chunks(id) ON DELETE CASCADE,
  FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_dt_chunk_embeddings_workspace_model
  ON derived_text_chunk_embeddings(workspace_id, model_id);

CREATE INDEX IF NOT EXISTS idx_dt_chunk_embeddings_workspace_chunk
  ON derived_text_chunk_embeddings(workspace_id, derived_text_chunk_id);
