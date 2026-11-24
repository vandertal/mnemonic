"""Migration 0005 and the Telegram identity against the real Postgres."""

from concurrent.futures import ThreadPoolExecutor

import psycopg
import pytest

pytestmark = pytest.mark.integration

TG_ID = 7_000_000_001  # larger than int4: the column is a bigint


def rows(url: str, sql: str, *args) -> list:
    with psycopg.connect(url) as conn:
        return conn.execute(sql, args).fetchall()


def test_first_call_creates_the_user_and_the_link(pg_store, pg_url):
    user, created = pg_store.get_or_create_telegram_user(TG_ID, "hash")

    assert created is True
    assert user.email == f"tg-{TG_ID}@telegram.invalid"
    assert rows(pg_url, "SELECT telegram_id, user_id FROM telegram_accounts") == [(TG_ID, user.id)]
    assert pg_store.find_telegram_user(TG_ID) == user


def test_second_call_returns_the_same_user(pg_store, pg_url):
    first, _ = pg_store.get_or_create_telegram_user(TG_ID, "hash")
    second, created = pg_store.get_or_create_telegram_user(TG_ID, "another hash")

    assert created is False
    assert second.id == first.id
    assert rows(pg_url, "SELECT count(*) FROM users") == [(1,)]


def test_parallel_first_messages_make_exactly_one_user(pg_store, pg_url):
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(
            pool.map(lambda _: pg_store.get_or_create_telegram_user(TG_ID, "hash"), range(8))
        )

    assert len({user.id for user, _ in results}) == 1
    assert sum(created for _, created in results) == 1  # only one call really created it
    assert rows(pg_url, "SELECT count(*) FROM users") == [(1,)]
    assert rows(pg_url, "SELECT count(*) FROM telegram_accounts") == [(1,)]


def test_an_unknown_telegram_id_is_none(pg_store):
    assert pg_store.find_telegram_user(TG_ID) is None


def test_deleting_the_user_cascades_to_the_link_and_the_chats(pg_store, pg_url):
    user, _ = pg_store.get_or_create_telegram_user(TG_ID, "hash")
    session = pg_store.create_session(user.id)
    pg_store.add_message(user.id, session.id, "user", "hello")

    assert pg_store.delete_user(user.id) is True

    assert rows(pg_url, "SELECT count(*) FROM telegram_accounts") == [(0,)]
    assert rows(pg_url, "SELECT count(*) FROM sessions") == [(0,)]
    assert rows(pg_url, "SELECT count(*) FROM messages") == [(0,)]


def test_one_user_cannot_have_two_telegram_ids(pg_store, pg_url):
    user, _ = pg_store.get_or_create_telegram_user(TG_ID, "hash")
    with pytest.raises(psycopg.errors.UniqueViolation), psycopg.connect(pg_url) as conn:
        conn.execute(
            "INSERT INTO telegram_accounts (telegram_id, user_id) VALUES (1, %s)", (user.id,)
        )


def test_stats_split_events_by_channel(pg_store):
    web = pg_store.create_user("alice@example.com", "h")
    tg, _ = pg_store.get_or_create_telegram_user(TG_ID, "hash")
    pg_store.log_event("question_answered", web.id, {"cited": True, "refused": False})
    pg_store.log_event("signup", tg.id, {"channel": "telegram"})
    pg_store.log_event(
        "question_answered", tg.id, {"channel": "telegram", "cited": True, "refused": False}
    )
    pg_store.log_event("question_answered", tg.id, {"channel": "telegram", "cited": False})

    stats = pg_store.event_stats()["by_channel"]

    assert stats["web"] == {
        "signup": 0,
        "question_answered": 1,
        "cards_made": 0,
        "search": 0,
        "users": 1,
    }
    assert stats["telegram"] == {
        "signup": 1,
        "question_answered": 2,
        "cards_made": 0,
        "search": 0,
        "users": 1,
    }
