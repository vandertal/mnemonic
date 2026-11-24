"""The events table and the stats query against the real Postgres."""

import psycopg
import pytest
from fastapi.testclient import TestClient

from mnemonic.auth import create_access_token
from mnemonic.config import Settings, get_settings
from mnemonic.main import app
from mnemonic.store import LLMCall, get_store

pytestmark = pytest.mark.integration


def test_stats_from_real_rows(pg_store):
    alice = pg_store.create_user("alice@example.com", "h")
    bob = pg_store.create_user("bob@example.com", "h")
    pg_store.create_user("carol@example.com", "h")
    for u in (alice, bob):
        pg_store.log_event("signup", u.id, {})
    pg_store.log_event("question_answered", alice.id, {"cited": True, "refused": False})
    pg_store.log_event("question_answered", bob.id, {"cited": False, "refused": True})
    pg_store.log_event("search", None, {"results": True})
    session = pg_store.create_session(alice.id)
    pg_store.log_llm_call(LLMCall(session.id, "m", 100, 50, 0.04, 10, "ok"))

    stats = pg_store.event_stats()

    assert stats["totals"] == {"signup": 2, "question_answered": 2, "cards_made": 0, "search": 1}
    assert stats["distinct_users"] == 2  # the anonymous search row has no user
    assert stats["registered_users"] == 3
    assert len(stats["last_days"]) == 7
    assert stats["last_days"][-1]["question_answered"] == 2
    assert stats["main_action"]["users"] == 1
    assert stats["main_action"]["rate"] == round(1 / 3, 3)
    assert stats["llm_cost"]["total_usd"] == 0.04
    assert stats["llm_cost"]["active_users"] == 2
    assert stats["llm_cost"]["avg_per_active_user_usd"] == 0.02


def test_deleting_an_account_keeps_the_counts_but_drops_the_link(pg_store, pg_url):
    alice = pg_store.create_user("alice@example.com", "h")
    pg_store.log_event("question_answered", alice.id, {"cited": True, "refused": False})

    assert pg_store.delete_user(alice.id) is True

    with psycopg.connect(pg_url) as conn:
        rows = conn.execute("SELECT name, user_id FROM events").fetchall()
    assert rows == [("question_answered", None)]


def test_admin_stats_over_http_with_the_real_store(pg_store, pg_url):
    admin = pg_store.create_user("owner@example.com", "h")
    pg_store.log_event("signup", admin.id, {})
    settings = Settings(_env_file=None, admin_emails="owner@example.com")
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_store] = lambda: pg_store
    token = create_access_token(admin.id, settings)
    try:
        with TestClient(app, headers={"Authorization": f"Bearer {token}"}) as client:
            body = client.get("/admin/stats").json()
    finally:
        app.dependency_overrides.clear()
    assert body["totals"]["signup"] == 1
    assert body["registered_users"] == 1
