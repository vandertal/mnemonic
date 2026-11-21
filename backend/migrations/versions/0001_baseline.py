"""Baseline: the schema that lab 31 created at app startup.

Every statement is idempotent, so this is a no-op on the live database and builds the whole
schema on an empty one.

Revision ID: 0001
Revises:
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

# 384 = output size of the embedding model (bge-small). Frozen here on purpose: a migration
# must not change when application code does.
UPGRADE = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS chunks (
    id           bigserial PRIMARY KEY,
    file_path    text    NOT NULL,
    heading      text    NOT NULL,
    chunk_index  integer NOT NULL,
    content      text    NOT NULL,
    content_hash text    NOT NULL UNIQUE,
    embedding    vector(384) NOT NULL
);

CREATE INDEX IF NOT EXISTS chunks_embedding_idx
    ON chunks USING hnsw (embedding vector_cosine_ops);

CREATE TABLE IF NOT EXISTS documents (
    id         bigserial PRIMARY KEY,
    owner_id   uuid NOT NULL,
    filename   text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS documents_owner_idx ON documents (owner_id);

ALTER TABLE chunks ADD COLUMN IF NOT EXISTS document_id bigint
    REFERENCES documents(id) ON DELETE CASCADE;
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS owner_id uuid;
CREATE INDEX IF NOT EXISTS chunks_owner_idx ON chunks (owner_id);
CREATE INDEX IF NOT EXISTS chunks_document_idx ON chunks (document_id);

CREATE TABLE IF NOT EXISTS sessions (
    id         uuid PRIMARY KEY,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS messages (
    id         bigserial PRIMARY KEY,
    session_id uuid NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role       text NOT NULL CHECK (role IN ('user', 'assistant')),
    content    text NOT NULL,
    sources    jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS messages_session_idx ON messages (session_id, id);

CREATE TABLE IF NOT EXISTS llm_calls (
    id         bigserial PRIMARY KEY,
    session_id uuid NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    model      text NOT NULL,
    tokens_in  integer NOT NULL,
    tokens_out integer NOT NULL,
    cost_usd   numeric(12, 8) NOT NULL,
    latency_ms integer NOT NULL,
    status     text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
"""

# FK order: children first. The `vector` extension stays (other objects may use it).
DOWNGRADE = """
DROP TABLE IF EXISTS llm_calls;
DROP TABLE IF EXISTS messages;
DROP TABLE IF EXISTS sessions;
DROP TABLE IF EXISTS chunks;
DROP TABLE IF EXISTS documents;
"""


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
