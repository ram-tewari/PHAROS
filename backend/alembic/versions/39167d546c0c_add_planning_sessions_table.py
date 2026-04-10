"""add_planning_sessions_table

Revision ID: 39167d546c0c
Revises: 20260123_community
Create Date: 2026-01-23 17:27:08.424531

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "39167d546c0c"
down_revision: Union[str, Sequence[str], None] = "20260123_community"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create planning_sessions table
    op.create_table(
        "planning_sessions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("task_description", sa.Text(), nullable=False),
        sa.Column("context", sa.JSON(), nullable=False),
        sa.Column("steps", sa.JSON(), nullable=False),
        sa.Column("dependencies", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create indexes
    op.create_index("idx_planning_status", "planning_sessions", ["status"])
    op.create_index("idx_planning_created", "planning_sessions", ["created_at"])


def downgrade() -> None:
    """Downgrade schema."""
    # Drop indexes
    op.drop_index("idx_planning_created", table_name="planning_sessions")
    op.drop_index("idx_planning_status", table_name="planning_sessions")

    # Drop table
    op.drop_table("planning_sessions")
