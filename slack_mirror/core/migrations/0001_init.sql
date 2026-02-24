PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS workspaces (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE,
  team_id TEXT,
  domain TEXT,
  config_json TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS users (
  workspace_id INTEGER NOT NULL,
  user_id TEXT NOT NULL,
  username TEXT,
  display_name TEXT,
  real_name TEXT,
  email TEXT,
  is_bot INTEGER NOT NULL DEFAULT 0,
  raw_json TEXT,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (workspace_id, user_id),
  FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS channels (
  workspace_id INTEGER NOT NULL,
  channel_id TEXT NOT NULL,
  name TEXT,
  is_private INTEGER NOT NULL DEFAULT 0,
  is_im INTEGER NOT NULL DEFAULT 0,
  is_mpim INTEGER NOT NULL DEFAULT 0,
  topic TEXT,
  purpose TEXT,
  raw_json TEXT,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (workspace_id, channel_id),
  FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS messages (
  workspace_id INTEGER NOT NULL,
  channel_id TEXT NOT NULL,
  ts TEXT NOT NULL,
  user_id TEXT,
  text TEXT,
  subtype TEXT,
  thread_ts TEXT,
  edited_ts TEXT,
  deleted INTEGER NOT NULL DEFAULT 0,
  raw_json TEXT,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (workspace_id, channel_id, ts),
  FOREIGN KEY (workspace_id, channel_id) REFERENCES channels(workspace_id, channel_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS files (
  workspace_id INTEGER NOT NULL,
  file_id TEXT NOT NULL,
  name TEXT,
  title TEXT,
  mimetype TEXT,
  size INTEGER,
  local_path TEXT,
  checksum TEXT,
  raw_json TEXT,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (workspace_id, file_id),
  FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS canvases (
  workspace_id INTEGER NOT NULL,
  canvas_id TEXT NOT NULL,
  title TEXT,
  local_path TEXT,
  raw_json TEXT,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (workspace_id, canvas_id),
  FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS events (
  workspace_id INTEGER NOT NULL,
  event_id TEXT NOT NULL,
  event_ts TEXT,
  type TEXT,
  status TEXT NOT NULL DEFAULT 'pending',
  payload_json TEXT NOT NULL,
  error TEXT,
  processed_at TEXT,
  PRIMARY KEY (workspace_id, event_id),
  FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS sync_state (
  workspace_id INTEGER NOT NULL,
  key TEXT NOT NULL,
  value TEXT,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (workspace_id, key),
  FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS content_chunks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  workspace_id INTEGER NOT NULL,
  source_type TEXT NOT NULL,
  source_id TEXT NOT NULL,
  chunk_index INTEGER NOT NULL,
  text TEXT NOT NULL,
  token_count INTEGER,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE,
  UNIQUE (workspace_id, source_type, source_id, chunk_index)
);

CREATE TABLE IF NOT EXISTS embeddings (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  workspace_id INTEGER NOT NULL,
  chunk_id INTEGER NOT NULL,
  model TEXT NOT NULL,
  vector_blob BLOB NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE,
  FOREIGN KEY (chunk_id) REFERENCES content_chunks(id) ON DELETE CASCADE,
  UNIQUE (workspace_id, chunk_id, model)
);

CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
  workspace_name,
  channel_name,
  user_id,
  ts,
  text,
  content=''
);

CREATE VIRTUAL TABLE IF NOT EXISTS content_chunks_fts USING fts5(
  workspace_name,
  source_type,
  source_id,
  text,
  content=''
);
