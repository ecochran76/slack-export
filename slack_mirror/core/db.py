import sqlite3
from pathlib import Path


def connect(db_path: str) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def apply_migrations(conn: sqlite3.Connection, migrations_dir: str) -> None:
    mdir = Path(migrations_dir)
    files = sorted(mdir.glob("*.sql"))
    with conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS _migrations (
                name TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        applied = {r[0] for r in conn.execute("SELECT name FROM _migrations")}
        for f in files:
            if f.name in applied:
                continue
            conn.executescript(f.read_text(encoding="utf-8"))
            conn.execute("INSERT INTO _migrations(name) VALUES (?)", (f.name,))
