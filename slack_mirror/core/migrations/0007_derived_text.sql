CREATE TABLE IF NOT EXISTS derived_text (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  workspace_id INTEGER NOT NULL,
  source_kind TEXT NOT NULL,
  source_id TEXT NOT NULL,
  derivation_kind TEXT NOT NULL,
  extractor TEXT NOT NULL,
  text TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  media_type TEXT,
  local_path TEXT,
  language_code TEXT,
  confidence REAL,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (workspace_id, source_kind, source_id, derivation_kind, extractor),
  FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_derived_text_workspace_kind
  ON derived_text(workspace_id, derivation_kind, source_kind, updated_at DESC, id);

CREATE VIRTUAL TABLE IF NOT EXISTS derived_text_fts USING fts5(
  workspace_id UNINDEXED,
  source_kind UNINDEXED,
  source_id UNINDEXED,
  derivation_kind UNINDEXED,
  extractor UNINDEXED,
  text
);

CREATE TABLE IF NOT EXISTS derived_text_jobs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  workspace_id INTEGER NOT NULL,
  source_kind TEXT NOT NULL,
  source_id TEXT NOT NULL,
  derivation_kind TEXT NOT NULL,
  reason TEXT NOT NULL DEFAULT 'upsert',
  status TEXT NOT NULL DEFAULT 'pending',
  error TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (workspace_id, source_kind, source_id, derivation_kind),
  FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_derived_text_jobs_workspace_status
  ON derived_text_jobs(workspace_id, derivation_kind, status, id);
