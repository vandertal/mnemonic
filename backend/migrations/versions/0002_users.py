"""Users: accounts for email + password login.

Revision ID: 0002
Revises: 0001
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # gen_random_uuid() is built into Postgres 13+. The CHECK keeps emails lower-case at the DB
    # level too, so UNIQUE really means "case-insensitively unique".
    op.execute(
        """
        CREATE TABLE users (
            id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            email         text NOT NULL UNIQUE,
            password_hash text NOT NULL,
            created_at    timestamptz NOT NULL DEFAULT now(),
            CHECK (email = lower(email))
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE users")
