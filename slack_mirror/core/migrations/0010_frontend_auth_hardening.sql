CREATE TABLE IF NOT EXISTS auth_login_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    remote_addr TEXT,
    success INTEGER NOT NULL DEFAULT 0,
    attempted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_auth_login_attempts_username_attempted_at
ON auth_login_attempts(username, attempted_at DESC);
