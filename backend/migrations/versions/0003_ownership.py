"""Ownership: every row belongs to a user.

WARNING: this migration DELETES data. Before lab 21 there were no accounts: documents, uploaded
chunks, sessions (and their messages and llm_calls) belonged to random browser-made UUIDs, so
they cannot be assigned to anyone. Upgrade removes all of them. Shared knowledge-base chunks
(owner_id IS NULL) stay.

Downgrade drops the foreign keys and the new columns. The deleted data is NOT restored.

Revision ID: 0003
Revises: 0002
"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # chunks (via document_id) and messages / llm_calls go by ON DELETE CASCADE.
    op.execute("DELETE FROM documents")
    op.execute("DELETE FROM chunks WHERE owner_id IS NOT NULL")
    op.execute("DELETE FROM sessions")
    # NOT NULL without a default is fine: the table is empty now.
    op.execute(
        """
        ALTER TABLE sessions
            ADD COLUMN user_id    uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            ADD COLUMN title      text NOT NULL DEFAULT 'New chat',
            ADD COLUMN updated_at timestamptz NOT NULL DEFAULT now()
        """
    )
    op.execute("CREATE INDEX sessions_user_updated_idx ON sessions (user_id, updated_at DESC)")
    op.execute(
        "ALTER TABLE documents ADD CONSTRAINT documents_owner_id_fkey "
        "FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE"
    )
    op.execute(
        "ALTER TABLE chunks ADD CONSTRAINT chunks_owner_id_fkey "
        "FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE chunks DROP CONSTRAINT chunks_owner_id_fkey")
    op.execute("ALTER TABLE documents DROP CONSTRAINT documents_owner_id_fkey")
    op.execute("DROP INDEX sessions_user_updated_idx")
    # Dropping user_id also drops its foreign key. Rows created after the upgrade stay.
    op.execute(
        "ALTER TABLE sessions DROP COLUMN user_id, DROP COLUMN title, DROP COLUMN updated_at"
    )
