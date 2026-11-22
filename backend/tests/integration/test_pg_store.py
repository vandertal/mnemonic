"""PgStore against the real database: constraints, ownership in SQL, cascades, races."""

import threading
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import numpy as np
import psycopg
import pytest

from mnemonic.ingest import db
from mnemonic.ingest.chunker import Chunk as NewChunk
from mnemonic.store import EmailTaken, LLMCall, SessionNotFound, TooManyDocuments

pytestmark = pytest.mark.integration

DIM = 384  # vector(384) in migration 0001


def vec(*hot: int) -> np.ndarray:
    """A unit vector with 1s at the given positions: easy to reason about cosine similarity."""
    v = np.zeros(DIM, dtype=np.float32)
    v[list(hot)] = 1.0
    return v / np.linalg.norm(v)


def chunks(name: str, n: int = 2) -> list[NewChunk]:
    return [NewChunk(name, "Notes", i, f"{name} part {i}") for i in range(n)]


def run_together(n: int, fn):
    """Run fn() in n threads released at the same moment; returns results or exceptions."""
    barrier = threading.Barrier(n)

    def task():
        barrier.wait()
        try:
            return fn()
        except Exception as e:  # the test inspects what each thread got
            return e

    with ThreadPoolExecutor(n) as pool:
        return [f.result() for f in [pool.submit(task) for _ in range(n)]]


def count(url: str, sql: str, *params) -> int:
    with psycopg.connect(url) as conn:
        return conn.execute(sql, params).fetchone()[0]


# --- users ---------------------------------------------------------------------------------


def test_two_parallel_registrations_of_one_email_exactly_one_wins(pg_store, pg_url):
    results = run_together(2, lambda: pg_store.create_user("race@example.com", "hash"))

    winners = [r for r in results if not isinstance(r, Exception)]
    losers = [r for r in results if isinstance(r, Exception)]
    assert len(winners) == 1
    assert len(losers) == 1 and isinstance(losers[0], EmailTaken)
    assert count(pg_url, "SELECT count(*) FROM users WHERE email = %s", "race@example.com") == 1


def test_email_must_be_lower_case_at_the_db_level(pg_store):
    with pytest.raises(psycopg.errors.CheckViolation):
        pg_store.create_user("Alice@Example.com", "hash")


def test_get_user_by_email_returns_the_hash(pg_store):
    user = pg_store.create_user("alice@example.com", "argon2-hash")
    found, password_hash = pg_store.get_user_by_email("alice@example.com")
    assert found == user and password_hash == "argon2-hash"
    assert pg_store.get_user_by_email("nobody@example.com") is None


# --- sessions ------------------------------------------------------------------------------


def test_sessions_are_scoped_to_their_owner(pg_store):
    alice = pg_store.create_user("alice@example.com", "h")
    bob = pg_store.create_user("bob@example.com", "h")
    session = pg_store.create_session(alice.id)

    assert pg_store.get_session(alice.id, session.id) == session
    # Bob: "not yours" looks exactly like "not there".
    assert pg_store.get_session(bob.id, session.id) is None
    assert pg_store.rename_session(bob.id, session.id, "mine now") is None
    assert pg_store.delete_session(bob.id, session.id) is False
    assert pg_store.get_messages(bob.id, session.id) is None
    with pytest.raises(SessionNotFound):
        pg_store.add_message(bob.id, session.id, "user", "hi")
    assert pg_store.list_sessions(bob.id, 10, 0) == ([], 0)
    # ...and Alice's session survived all of it.
    assert pg_store.get_session(alice.id, session.id).title == session.title


def test_first_user_message_becomes_the_title_and_bumps_updated_at(pg_store):
    alice = pg_store.create_user("alice@example.com", "h")
    session = pg_store.create_session(alice.id)
    pg_store.add_message(alice.id, session.id, "user", "  What is   CORS?  ")
    pg_store.add_message(alice.id, session.id, "user", "Second question")

    after = pg_store.get_session(alice.id, session.id)
    assert after.title == "What is CORS?"
    assert after.updated_at >= session.updated_at
    assert [m.content for m in pg_store.get_messages(alice.id, session.id)] == [
        "  What is   CORS?  ",
        "Second question",
    ]


def test_list_sessions_pages_newest_first_with_a_stable_tie_break(pg_store, pg_url):
    alice = pg_store.create_user("alice@example.com", "h")
    made = [pg_store.create_session(alice.id, f"chat {i}") for i in range(5)]
    # Fixed timestamps: two pairs share one, so only the `id` tie-break can order them.
    stamps = ["2026-01-05", "2026-01-04", "2026-01-04", "2026-01-02", "2026-01-02"]
    with psycopg.connect(pg_url) as conn:
        for s, ts in zip(made, stamps, strict=True):
            conn.execute("UPDATE sessions SET updated_at = %s WHERE id = %s", (ts, s.id))

    pages = [pg_store.list_sessions(alice.id, 2, offset) for offset in (0, 2, 4)]
    ids = [s.id for page, _ in pages for s in page]

    assert all(total == 5 for _, total in pages)
    assert [len(page) for page, _ in pages] == [2, 2, 1]
    assert len(set(ids)) == 5  # no row twice, none skipped
    by_id = {s.id: ts for s, ts in zip(made, stamps, strict=True)}
    assert [by_id[i] for i in ids] == sorted(stamps, reverse=True)
    for ts in ("2026-01-04", "2026-01-02"):  # ties: ascending id
        tied = [i for i in ids if by_id[i] == ts]
        assert tied == sorted(tied)
    # The same query twice gives the same pages.
    assert pg_store.list_sessions(alice.id, 2, 2) == pages[1]


# --- documents -----------------------------------------------------------------------------


def test_documents_add_list_limit_delete(pg_store):
    alice = pg_store.create_user("alice@example.com", "h")
    bob = pg_store.create_user("bob@example.com", "h")
    first = pg_store.add_document(alice.id, "a.md", chunks("a.md", 3), [vec(1)] * 3, 2)
    pg_store.add_document(alice.id, "b.md", chunks("b.md", 1), [vec(2)], 2)

    with pytest.raises(TooManyDocuments):
        pg_store.add_document(alice.id, "c.md", chunks("c.md", 1), [vec(3)], 2)

    listed = pg_store.list_documents(alice.id)
    assert [(d.filename, d.chunks) for d in listed] == [("a.md", 3), ("b.md", 1)]
    assert pg_store.count_documents(alice.id) == 2
    assert pg_store.list_documents(bob.id) == []
    assert pg_store.delete_document(bob.id, first.id) is False  # not Bob's
    assert pg_store.delete_document(alice.id, first.id) is True
    assert [d.filename for d in pg_store.list_documents(alice.id)] == ["b.md"]


def test_parallel_uploads_cannot_pass_the_limit(pg_store, pg_url):
    """Without the advisory lock, every thread could count "2 < 3" before any of them inserts."""
    alice = pg_store.create_user("alice@example.com", "h")
    limit, attempts = 3, 8

    def upload():
        return pg_store.add_document(alice.id, f"{uuid4()}.md", chunks("x.md", 1), [vec(1)], limit)

    results = run_together(attempts, upload)

    errors = [r for r in results if isinstance(r, Exception)]
    assert all(isinstance(e, TooManyDocuments) for e in errors), errors
    assert attempts - len(errors) == limit
    assert count(pg_url, "SELECT count(*) FROM documents WHERE owner_id = %s", alice.id) == limit


def test_same_text_in_two_uploads_does_not_collide(pg_store):
    alice = pg_store.create_user("alice@example.com", "h")
    same = chunks("notes.md", 2)
    pg_store.add_document(alice.id, "notes.md", same, [vec(1)] * 2, 5)
    pg_store.add_document(alice.id, "notes.md", same, [vec(1)] * 2, 5)  # no UniqueViolation
    assert [d.chunks for d in pg_store.list_documents(alice.id)] == [2, 2]


# --- chunks --------------------------------------------------------------------------------


def shared_chunk(pg_url) -> int:
    """A knowledge-base chunk (owner_id NULL), inserted the way the ingest CLI does it."""
    with db.connect(pg_url) as conn:
        db.upsert_chunks(
            conn, [NewChunk("tutorial/cors.md", "CORS", 0, "Use CORSMiddleware.")], [vec(0)]
        )
        return conn.execute("SELECT id FROM chunks WHERE owner_id IS NULL").fetchone()[0]


def chunk_ids(pg_url, owner) -> list[int]:
    with psycopg.connect(pg_url) as conn:
        rows = conn.execute("SELECT id FROM chunks WHERE owner_id = %s ORDER BY id", (owner,))
        return [r[0] for r in rows]


def test_chunk_visibility_shared_own_but_never_foreign(pg_store, pg_url):
    alice = pg_store.create_user("alice@example.com", "h")
    bob = pg_store.create_user("bob@example.com", "h")
    shared = shared_chunk(pg_url)
    pg_store.add_document(alice.id, "a.md", chunks("a.md", 1), [vec(1)], 5)
    pg_store.add_document(bob.id, "b.md", chunks("b.md", 1), [vec(2)], 5)
    (alices,), (bobs,) = chunk_ids(pg_url, alice.id), chunk_ids(pg_url, bob.id)
    every = [shared, alices, bobs, 999_999]

    assert [c.id for c in pg_store.get_chunks(every, alice.id)] == [shared, alices]
    assert [c.id for c in pg_store.get_chunks(every, bob.id)] == [shared, bobs]
    assert [c.id for c in pg_store.get_chunks(every, None)] == [shared]


def test_ingest_upsert_is_idempotent(pg_url):
    batch = [NewChunk("tutorial/a.md", "A", i, f"text {i}") for i in range(3)]
    with db.connect(pg_url) as conn:
        assert db.upsert_chunks(conn, batch, [vec(i) for i in range(3)]) == 3
        assert db.upsert_chunks(conn, batch, [vec(i) for i in range(3)]) == 0  # all known
        assert db.count(conn) == 3
        # One new chunk among known ones: only it is inserted.
        more = [*batch, NewChunk("tutorial/a.md", "A", 3, "text 3")]
        assert db.upsert_chunks(conn, more, [vec(i) for i in range(4)]) == 1
        assert db.count(conn) == 4


# --- account deletion ----------------------------------------------------------------------


def test_deleting_an_account_cascades_to_everything_it_owns(pg_store, pg_url):
    alice = pg_store.create_user("alice@example.com", "h")
    bob = pg_store.create_user("bob@example.com", "h")
    shared = shared_chunk(pg_url)
    for user in (alice, bob):
        session = pg_store.create_session(user.id)
        pg_store.add_message(user.id, session.id, "user", "hi")
        pg_store.log_llm_call(LLMCall(session.id, "fake", 1, 1, 0.0, 5, "ok"))
        pg_store.add_document(user.id, "n.md", chunks("n.md", 2), [vec(1)] * 2, 5)

    assert pg_store.delete_user(alice.id) is True
    assert pg_store.delete_user(alice.id) is False  # already gone

    def owned(table_sql: str, user_id) -> int:
        return count(pg_url, table_sql, user_id)

    for user, expected in ((alice, 0), (bob, 1)):
        assert owned("SELECT count(*) FROM sessions WHERE user_id = %s", user.id) == expected
        assert owned("SELECT count(*) FROM documents WHERE owner_id = %s", user.id) == expected
        assert owned("SELECT count(*) FROM chunks WHERE owner_id = %s", user.id) == 2 * expected
    # Messages and llm_calls hang off sessions: only Bob's are left.
    assert count(pg_url, "SELECT count(*) FROM messages") == 1
    assert count(pg_url, "SELECT count(*) FROM llm_calls") == 1
    # The shared knowledge base is nobody's, so it stays.
    assert count(pg_url, "SELECT count(*) FROM chunks WHERE id = %s", shared) == 1
