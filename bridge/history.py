"""Minimal local SQLite spool submission history (no receipt contents)."""
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

_LOCK = Lock()
_DB = Path(os.getenv("PRINT_HISTORY_DB", str(Path(__file__).resolve().parent.parent / "print-history.sqlite3")))

def _connect():
    conn = sqlite3.connect(_DB, timeout=5)
    conn.execute("""CREATE TABLE IF NOT EXISTS jobs
        (id INTEGER PRIMARY KEY AUTOINCREMENT, queued_at TEXT NOT NULL,
         spooler_id INTEGER NOT NULL, printer TEXT NOT NULL)""")
    return conn

def record(job_id: int, printer: str):
    with _LOCK:
        with _connect() as conn:
            conn.execute("INSERT INTO jobs(queued_at, spooler_id, printer) VALUES(?,?,?)",
                         (datetime.now(timezone.utc).isoformat(), job_id, printer))
            conn.execute("DELETE FROM jobs WHERE id NOT IN (SELECT id FROM jobs ORDER BY id DESC LIMIT 500)")

def recent(limit=20):
    limit = max(1, min(int(limit), 100))
    with _LOCK:
        with _connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT queued_at, spooler_id, printer FROM jobs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
            return [dict(row) for row in rows]
