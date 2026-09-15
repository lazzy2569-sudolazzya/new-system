import client.offline.sync as sync
from client.offline.cache_db import (
    cache_get,
    cache_put,
    enqueue_write,
    get_connection,
    mark_outbox_row,
    pending_outbox_rows,
)
from client.offline.sync import StaleReadBlocked, cached_read, queue_or_send_write, replay_outbox
from client.offline.sync_policy import StalePolicy, policy_for, register_policy


def _conn(tmp_path):
    return get_connection(tmp_path / "cache.sqlite3")


def test_cache_put_and_get_round_trip(tmp_path):
    conn = _conn(tmp_path)
    cache_put(conn, "products", {"items": [1, 2, 3]})
    payload, fetched_at = cache_get(conn, "products")
    assert payload == {"items": [1, 2, 3]}
    assert fetched_at is not None


def test_cache_get_missing_key_returns_none(tmp_path):
    conn = _conn(tmp_path)
    assert cache_get(conn, "nonexistent") is None


def test_outbox_enqueue_and_mark(tmp_path):
    conn = _conn(tmp_path)
    key = enqueue_write(conn, "/api/v1/stock/adjustments", "POST", {"qty": 5})

    pending = pending_outbox_rows(conn)
    assert len(pending) == 1
    assert pending[0]["idempotency_key"] == key
    assert pending[0]["status"] == "PENDING"

    mark_outbox_row(conn, pending[0]["id"], "SENT")
    assert pending_outbox_rows(conn) == []


def test_unregistered_endpoint_defaults_to_requires_fresh():
    # Fail-safe: an endpoint nobody has classified must never be treated
    # as safe to act on while stale.
    assert policy_for("/api/v1/some/new/endpoint") is StalePolicy.REQUIRES_FRESH


def test_registered_endpoint_policy_is_honored():
    register_policy("/api/v1/inventory/receipts", StalePolicy.STALE_OK)
    assert policy_for("/api/v1/inventory/receipts") is StalePolicy.STALE_OK


def test_cached_read_returns_fresh_data_when_online(tmp_path, monkeypatch):
    conn = _conn(tmp_path)
    monkeypatch.setattr(sync, "is_online", lambda: True)

    data, fetched_at, is_stale = cached_read(conn, "products", lambda: {"items": [1]})

    assert data == {"items": [1]}
    assert is_stale is False
    assert cache_get(conn, "products")[0] == {"items": [1]}


def test_cached_read_falls_back_to_cache_when_offline(tmp_path, monkeypatch):
    conn = _conn(tmp_path)
    cache_put(conn, "products", {"items": ["cached"]})
    monkeypatch.setattr(sync, "is_online", lambda: False)

    data, _fetched_at, is_stale = cached_read(conn, "products", lambda: {"items": ["should not be called"]})

    assert data == {"items": ["cached"]}
    assert is_stale is True


def test_cached_read_raises_when_offline_with_nothing_cached(tmp_path, monkeypatch):
    conn = _conn(tmp_path)
    monkeypatch.setattr(sync, "is_online", lambda: False)

    try:
        cached_read(conn, "products", lambda: {})
    except StaleReadBlocked:
        pass
    else:
        raise AssertionError("expected StaleReadBlocked")


def test_write_queues_when_offline(tmp_path, monkeypatch):
    conn = _conn(tmp_path)
    monkeypatch.setattr(sync, "is_online", lambda: False)

    result = queue_or_send_write(conn, "/api/v1/stock/adjustments", "POST", {"qty": 1}, send_fn=lambda *_: {})

    assert result["status"] == "PENDING"
    assert len(pending_outbox_rows(conn)) == 1


def test_write_sends_immediately_when_online(tmp_path, monkeypatch):
    conn = _conn(tmp_path)
    monkeypatch.setattr(sync, "is_online", lambda: True)
    sent = {}

    def send_fn(payload, idempotency_key):
        sent["payload"] = payload
        sent["idempotency_key"] = idempotency_key
        return {"id": 42}

    result = queue_or_send_write(conn, "/api/v1/stock/adjustments", "POST", {"qty": 1}, send_fn=send_fn)

    assert result == {"id": 42}
    assert sent["payload"] == {"qty": 1}
    assert pending_outbox_rows(conn) == []  # sent immediately, never left pending


def test_stale_read_blocks_write_to_requires_fresh_endpoint(tmp_path, monkeypatch):
    conn = _conn(tmp_path)
    monkeypatch.setattr(sync, "is_online", lambda: True)
    register_policy("/api/v1/sales/issue", StalePolicy.REQUIRES_FRESH)

    try:
        queue_or_send_write(
            conn, "/api/v1/sales/issue", "POST", {"qty": 1},
            send_fn=lambda *_: {}, read_was_stale=True,
        )
    except StaleReadBlocked:
        pass
    else:
        raise AssertionError("expected StaleReadBlocked")
    assert pending_outbox_rows(conn) == []  # refused outright, never queued


def test_replay_outbox_reports_per_row_success_and_failure(tmp_path, monkeypatch):
    conn = _conn(tmp_path)
    monkeypatch.setattr(sync, "is_online", lambda: False)
    queue_or_send_write(conn, "/api/v1/a", "POST", {"n": 1}, send_fn=lambda *_: {})
    queue_or_send_write(conn, "/api/v1/b", "POST", {"n": 2}, send_fn=lambda *_: {})

    def send_fn(payload, _key):
        if payload["n"] == 2:
            raise RuntimeError("server rejected it")
        return {}

    results = replay_outbox(conn, send_fn)

    outcomes = {ok for _row_id, ok in results}
    assert outcomes == {True, False}
    # A failed replay is marked FAILED, not left PENDING -- it must not be
    # silently retried forever, but it also must not vanish.
    assert pending_outbox_rows(conn) == []
    failed_row = conn.execute("SELECT * FROM outbox WHERE status = 'FAILED'").fetchone()
    assert failed_row["last_error"] == "server rejected it"
