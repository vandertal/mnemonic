"""llm_calls.error_class: why a failed LLM call failed (quota, overloaded, blocked, ...).

NULL for successful calls and for rows written before this migration. Lets GET /admin/stats show
what really fails in production.

Revision ID: 0006
Revises: 0005
"""

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE llm_calls ADD COLUMN error_class text")


def downgrade() -> None:
    op.execute("ALTER TABLE llm_calls DROP COLUMN error_class")
