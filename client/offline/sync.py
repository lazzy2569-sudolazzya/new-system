"""Ties cache_db, sync_policy, and connectivity together into the
read/write helpers a screen actually calls (plan section 1.5).
"""
import datetime as dt
import json
import sqlite3
from typing import Callable

from client.offline.cache_db import (
    cache_get,
    cache_put,
    enqueue_write,
    mark_outbox_row,
    pending_outbox_rows,
)
from client.offline.connectivity import is_online
from client.offline.sync_policy import StalePolicy, policy_for


class StaleReadBlocked(Exception):
    """Raised when a write depends on a read whose policy is
    REQUIRES_FRESH -- the caller must tell the user this can't be done
    offline rather than let the write proceed against a stale number.
    """


def cached_read(
    conn: sqlite3.Connection, cache_key: str, fetch_fn: Callable[[], dict]
) -> tuple[dict, dt.datetime, bool]:
    """Returns (data, fetched_at, is_stale).

    Tries a live fetch first; on success refreshes the cache and reports
    fresh. On failure (offline, or the request errors), falls back to the
    cache and reports stale.
    """
    if is_online():
        try:
            data = fetch_fn()
        except Exception:
            pass
        else:
            now = dt.datetime.now(dt.timezone.utc)
            cache_put(conn, cache_key, data)
            return data, now, False

    cached = cache_get(conn, cache_key)
    if cached is None:
        raise StaleReadBlocked(f"No cached data for '{cache_key}' and the server is unreachable")
    data, fetched_at = cached
    return data, fetched_at, True


def queue_or_send_write(
    conn: sqlite3.Connection,
    endpoint: str,
    method: str,
    payload: dict,
    send_fn: Callable[[dict, str], dict],
    *,
    read_was_stale: bool = False,
) -> dict:
    """Sends immediately if online; queues to the outbox if offline.

    read_was_stale flags that this write was informed by a stale cached
    read (see cached_read). If the endpoint's registered policy is
    REQUIRES_FRESH, the write is refused outright rather than queued --
    queuing it would let it replay later against numbers that may no
    longer hold.
    """
    if read_was_stale and policy_for(endpoint) is StalePolicy.REQUIRES_FRESH:
        raise StaleReadBlocked(
            f"{endpoint} requires a fresh read; reconnect before completing this action"
        )

    idempotency_key = enqueue_write(conn, endpoint, method, payload)

    if not is_online():
        return {"status": "PENDING", "idempotency_key": idempotency_key}

    row_id = conn.execute(
        "SELECT id FROM outbox WHERE idempotency_key = ?", (idempotency_key,)
    ).fetchone()["id"]
    try:
        result = send_fn(payload, idempotency_key)
    except Exception:
        # Recorded as PENDING either way -- a network failure mid-send
        # looks the same as never having been online, and gets replayed
        # the same way.
        return {"status": "PENDING", "idempotency_key": idempotency_key}
    else:
        mark_outbox_row(conn, row_id, "SENT")
        return result


def replay_outbox(
    conn: sqlite3.Connection, send_fn: Callable[[dict, str], dict]
) -> list[tuple[int, bool]]:
    """Replays every PENDING outbox row in order. Returns (row_id, ok)
    pairs so the caller can surface failures rather than silently drop
    them -- conflicts surface to the user, never auto-resolved (plan
    section 1.5).
    """
    results = []
    for row in pending_outbox_rows(conn):
        payload = json.loads(row["payload"])
        try:
            send_fn(payload, row["idempotency_key"])
        except Exception as exc:
            mark_outbox_row(conn, row["id"], "FAILED", str(exc))
            results.append((row["id"], False))
        else:
            mark_outbox_row(conn, row["id"], "SENT")
            results.append((row["id"], True))
    return results
