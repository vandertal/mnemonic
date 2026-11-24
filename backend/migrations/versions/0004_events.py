"""Events: a tiny first-party product-metrics log (see docs/decisions/0006-capstone-metrics.md).

One row per thing that happened (`signup`, `question_answered`, `cards_made`, `search`). `props`
holds small non-sensitive flags (never question text). `user_id` is nullable and goes to NULL when
the account is deleted: the aggregate counts stay, the link to the person does not.

Revision ID: 0004
Revises: 0003
"""

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE events (
            id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            user_id    uuid REFERENCES users(id) ON DELETE SET NULL,
            name       text NOT NULL,
            props      jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX events_name_created_idx ON events (name, created_at)")
    op.execute("CREATE INDEX events_user_idx ON events (user_id)")


def downgrade() -> None:
    op.execute("DROP TABLE events")
