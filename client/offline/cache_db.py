"""Local SQLite cache + outbox for offline operation (plan section 1.5).

Two tables live here, independent of which business domain is calling them:

- cache_entries: last-known-good server reads, tagged with a fetched_at
  timestamp so the UI can show "Offline, showing data as of HH:MM" and so
  sync_policy can refuse to let a stale read drive an unsafe write.
- outbox: queued writes made while offline, replayed in order on
  reconnect. Every row carries a client-generated idempotency key so a
  replay after a timeout can't double-post (plan section 1.5).
"""
import datetime as dt
import json
import sqlite3
import uuid
from pathlib import Path

DB_PATH = Path.home() / ".erp-client" / "cache.sqlite3"


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    _ensure_schema(conn)
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS cache_entries (
            cache_key   TEXT PRIMARY KEY,
            payload     TEXT NOT NULL,
            fetched_at  TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS outbox (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            idempotency_key TEXT NOT NULL UNIQUE,
            endpoint        TEXT NOT NULL,
            method          TEXT NOT NULL,
            payload         TEXT NOT NULL,
            status          TEXT NOT NULL DEFAULT 'PENDING',
            created_at      TEXT NOT NULL,
            last_error      TEXT
        );
        """
    )
    conn.commit()


def cache_put(conn: sqlite3.Connection, cache_key: str, payload: dict) -> None:
    conn.execute(
        """
        INSERT INTO cache_entries (cache_key, payload, fetched_at) VALUES (?, ?, ?)
        ON CONFLICT(cache_key) DO UPDATE SET payload = excluded.payload, fetched_at = excluded.fetched_at
        """,
        (cache_key, json.dumps(payload), dt.datetime.now(dt.timezone.utc).isoformat()),
    )
    conn.commit()


def cache_get(conn: sqlite3.Connection, cache_key: str) -> tuple[dict, dt.datetime] | None:
    row = conn.execute(
        "SELECT payload, fetched_at FROM cache_entries WHERE cache_key = ?", (cache_key,)
    ).fetchone()
    if row is None:
        return None
    return json.loads(row["payload"]), dt.datetime.fromisoformat(row["fetched_at"])


def enqueue_write(conn: sqlite3.Connection, endpoint: str, method: str, payload: dict) -> str:
    """Queue a write for replay on reconnect. Returns the idempotency key
    the caller must send with the eventual real request, so a retried
    replay after a timeout can't double-post (plan section 1.5).
    """
    idempotency_key = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO outbox (idempotency_key, endpoint, method, payload, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            idempotency_key,
            endpoint,
            method,
            json.dumps(payload),
            dt.datetime.now(dt.timezone.utc).isoformat(),
        ),
    )
    conn.commit()
    return idempotency_key


def pending_outbox_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM outbox WHERE status = 'PENDING' ORDER BY id ASC"
    ).fetchall()


def mark_outbox_row(
    conn: sqlite3.Connection, row_id: int, status: str, error: str | None = None
) -> None:
    conn.execute(
        "UPDATE outbox SET status = ?, last_error = ? WHERE id = ?", (status, error, row_id)
    )
    conn.commit()
