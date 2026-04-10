CREATE TABLE IF NOT EXISTS outbound_actions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  workspace_id INTEGER NOT NULL,
  kind TEXT NOT NULL,
  channel_id TEXT NOT NULL,
  thread_ts TEXT,
  text TEXT NOT NULL,
  options_json TEXT NOT NULL DEFAULT '{}',
  idempotency_key TEXT,
  status TEXT NOT NULL DEFAULT 'pending',
  response_json TEXT,
  error TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (workspace_id, kind, idempotency_key)
);

CREATE INDEX IF NOT EXISTS idx_outbound_actions_workspace_status
  ON outbound_actions(workspace_id, status, id);

CREATE TABLE IF NOT EXISTS listeners (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  workspace_id INTEGER NOT NULL,
  name TEXT NOT NULL,
  event_types_json TEXT NOT NULL DEFAULT '[]',
  channel_ids_json TEXT NOT NULL DEFAULT '[]',
  target TEXT,
  delivery_mode TEXT NOT NULL DEFAULT 'queue',
  enabled INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (workspace_id, name)
);

CREATE INDEX IF NOT EXISTS idx_listeners_workspace_enabled
  ON listeners(workspace_id, enabled, id);

CREATE TABLE IF NOT EXISTS listener_deliveries (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  workspace_id INTEGER NOT NULL,
  listener_id INTEGER NOT NULL,
  event_type TEXT NOT NULL,
  source_kind TEXT NOT NULL,
  source_ref TEXT,
  payload_json TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  attempts INTEGER NOT NULL DEFAULT 0,
  error TEXT,
  delivered_at TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (listener_id) REFERENCES listeners(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_listener_deliveries_workspace_status
  ON listener_deliveries(workspace_id, status, id);
