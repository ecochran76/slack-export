CREATE TABLE IF NOT EXISTS child_event_journal (
  workspace_id INTEGER NOT NULL,
  event_id TEXT NOT NULL,
  event_type TEXT NOT NULL,
  subject_kind TEXT NOT NULL,
  subject_id TEXT NOT NULL,
  actor_user_id TEXT,
  actor_label TEXT,
  channel_id TEXT,
  privacy TEXT NOT NULL DEFAULT 'user',
  occurred_at TEXT,
  recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  source_refs_json TEXT NOT NULL DEFAULT '{}',
  payload_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (workspace_id, event_id),
  FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_child_event_journal_workspace_recorded
  ON child_event_journal(workspace_id, recorded_at, event_id);

CREATE INDEX IF NOT EXISTS idx_child_event_journal_type
  ON child_event_journal(workspace_id, event_type, recorded_at);

CREATE INDEX IF NOT EXISTS idx_child_event_journal_actor
  ON child_event_journal(workspace_id, actor_user_id, recorded_at);

CREATE INDEX IF NOT EXISTS idx_child_event_journal_channel
  ON child_event_journal(workspace_id, channel_id, recorded_at);
