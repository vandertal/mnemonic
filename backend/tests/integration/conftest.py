"""Integration tests: the real Postgres + pgvector, the real migrations, the real PgStore.

They run only when TEST_DATABASE_URL is set (CI sets it to a throwaway pgvector container). The
session fixture WIPES that database (drops the `public` schema) and builds it with
`alembic upgrade head`, so it refuses to start when the URL points at the DATABASE_URL database.
"""

import os
from pathlib import Path

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from psycopg.conninfo import conninfo_to_dict

from mnemonic.config import get_settings
from mnemonic.store import PgStore

BACKEND_DIR = Path(__file__).resolve().parents[2]
TABLES = "users, sessions, messages, llm_calls, documents, chunks"


def pytest_collection_modifyitems(config, items):
    if os.environ.get("TEST_DATABASE_URL"):
        return
    skip = pytest.mark.skip(reason="TEST_DATABASE_URL is not set (real Postgres + pgvector)")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)


def same_database(a: str, b: str) -> bool:
    """Same server + database, whatever the user, password or query parameters."""

    def key(url: str) -> tuple:
        info = conninfo_to_dict(url)
        return (info.get("host"), info.get("port") or "5432", info.get("dbname"))

    return key(a) == key(b)


def alembic_config(url: str) -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.attributes["database_url"] = url  # read by migrations/env.py instead of DATABASE_URL
    cfg.attributes["configure_logger"] = False
    return cfg


@pytest.fixture(scope="session")
def pg_url() -> str:
    url = os.environ["TEST_DATABASE_URL"]
    dev_urls = [u for u in (os.environ.get("DATABASE_URL"), get_settings().database_url) if u]
    if any(same_database(url, dev) for dev in dev_urls):
        pytest.exit(
            "REFUSING to run: TEST_DATABASE_URL points at the DATABASE_URL database, and the "
            "integration tests wipe it. Use a separate (throwaway) database.",
            returncode=3,
        )
    # A fresh database: drop everything, then let the migrations build it from zero.
    with psycopg.connect(url, autocommit=True, connect_timeout=10) as conn:
        conn.execute("DROP SCHEMA public CASCADE")
        conn.execute("CREATE SCHEMA public")
    command.upgrade(alembic_config(url), "head")
    return url


@pytest.fixture(autouse=True)
def clean_tables(pg_url):
    """Empty tables before every test in this folder (the schema and alembic_version stay)."""
    with psycopg.connect(pg_url, autocommit=True) as conn:
        conn.execute(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE")


@pytest.fixture
def pg_store(pg_url) -> PgStore:
    return PgStore(pg_url)


@pytest.fixture
def pg_cfg(pg_url) -> Config:
    return alembic_config(pg_url)
