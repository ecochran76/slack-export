CREATE TABLE IF NOT EXISTS derived_text_chunks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  derived_text_id INTEGER NOT NULL,
  workspace_id INTEGER NOT NULL,
  chunk_index INTEGER NOT NULL,
  start_offset INTEGER NOT NULL,
  end_offset INTEGER NOT NULL,
  text TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (derived_text_id) REFERENCES derived_text(id) ON DELETE CASCADE,
  FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE,
  UNIQUE (derived_text_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS idx_derived_text_chunks_workspace
  ON derived_text_chunks(workspace_id, derived_text_id, chunk_index);

CREATE VIRTUAL TABLE IF NOT EXISTS derived_text_chunks_fts USING fts5(
  workspace_id UNINDEXED,
  derived_text_id UNINDEXED,
  chunk_index UNINDEXED,
  text
);
