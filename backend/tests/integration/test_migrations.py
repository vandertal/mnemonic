"""The migrations really run on Postgres + pgvector, both ways."""

import psycopg
import pytest
from alembic import command

pytestmark = pytest.mark.integration


def columns(url: str, table: str) -> set[str]:
    with psycopg.connect(url) as conn:
        rows = conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = %s",
            (table,),
        ).fetchall()
    return {r[0] for r in rows}


def tables(url: str) -> set[str]:
    with psycopg.connect(url) as conn:
        rows = conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
        ).fetchall()
    return {r[0] for r in rows}


def test_head_has_the_whole_schema(pg_url):
    assert {
        "users",
        "sessions",
        "messages",
        "llm_calls",
        "documents",
        "chunks",
        "events",
        "telegram_accounts",
    } <= tables(pg_url)
    assert {"telegram_id", "user_id", "created_at"} == columns(pg_url, "telegram_accounts")
    assert {"user_id", "title", "updated_at"} <= columns(pg_url, "sessions")
    assert {"id", "user_id", "name", "props", "created_at"} == columns(pg_url, "events")


def test_down_one_then_up_again(pg_url, pg_cfg):
    assert "error_class" in columns(pg_url, "llm_calls")
    command.downgrade(pg_cfg, "-1")  # 0006 -> 0005: llm_calls loses error_class
    assert "error_class" not in columns(pg_url, "llm_calls")
    assert "telegram_accounts" in tables(pg_url)

    command.downgrade(pg_cfg, "-1")  # 0005 -> 0004: the Telegram link table goes
    assert "telegram_accounts" not in tables(pg_url)
    assert "events" in tables(pg_url)

    command.downgrade(pg_cfg, "-1")  # 0004 -> 0003: the events table goes
    assert "events" not in tables(pg_url)
    assert "user_id" in columns(pg_url, "sessions")

    command.downgrade(pg_cfg, "-1")  # 0003 -> 0002: sessions lose their owner
    assert "user_id" not in columns(pg_url, "sessions")
    assert "users" in tables(pg_url)

    command.upgrade(pg_cfg, "head")
    assert {"user_id", "title", "updated_at"} <= columns(pg_url, "sessions")


def test_down_to_base_then_up_again(pg_url, pg_cfg):
    command.downgrade(pg_cfg, "base")
    assert tables(pg_url) <= {"alembic_version"}  # every table of ours is gone

    command.upgrade(pg_cfg, "head")
    assert {"users", "sessions", "chunks"} <= tables(pg_url)
