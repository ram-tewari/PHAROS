"""add_mcp_sessions_table

Revision ID: 20260123_add_mcp_sessions
Revises: 20260108_add_authority_timestamps
Create Date: 2026-01-23 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20260123_add_mcp_sessions"
down_revision = "20260108_add_authority_timestamps"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create mcp_sessions table"""
    op.create_table(
        "mcp_sessions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("context", sa.JSON(), nullable=False),
        sa.Column("tool_invocations", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_activity", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_mcp_user", "mcp_sessions", ["user_id"], unique=False)
    op.create_index("idx_mcp_status", "mcp_sessions", ["status"], unique=False)
    op.create_index("idx_mcp_activity", "mcp_sessions", ["last_activity"], unique=False)


def downgrade() -> None:
    """Drop mcp_sessions table"""
    op.drop_index("idx_mcp_activity", table_name="mcp_sessions")
    op.drop_index("idx_mcp_status", table_name="mcp_sessions")
    op.drop_index("idx_mcp_user", table_name="mcp_sessions")
    op.drop_table("mcp_sessions")
