"""Telegram identities: which Telegram user is which Mnemonic user.

A person who writes to the bot gets a normal `users` row (email `tg-<id>@telegram.invalid`, an
argon2 hash of a random secret nobody ever sees, so the account cannot log in on the web) and one
row here. Everything else (sessions, documents, events) hangs off `users` as before, so deleting
the user deletes the Telegram link too (ON DELETE CASCADE).

Revision ID: 0005
Revises: 0004
"""

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE telegram_accounts (
            telegram_id bigint PRIMARY KEY,
            user_id     uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            created_at  timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    # One Telegram identity per user: also the index the cascade delete uses.
    op.execute("CREATE UNIQUE INDEX telegram_accounts_user_idx ON telegram_accounts (user_id)")


def downgrade() -> None:
    op.execute("DROP TABLE telegram_accounts")
