"""add_community_assignments_table

Revision ID: 20260123_community
Revises: 08fc64e7d3b0
Create Date: 2026-01-23 17:05:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260123_community"
down_revision: Union[str, None] = "08fc64e7d3b0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add community_assignments table for Phase 20 community detection."""
    op.create_table(
        "community_assignments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("community_id", sa.Integer(), nullable=False),
        sa.Column("modularity", sa.Float(), server_default="0.0", nullable=False),
        sa.Column("resolution", sa.Float(), server_default="1.0", nullable=False),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["resource_id"], ["resources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create indexes
    op.create_index("idx_community_resource", "community_assignments", ["resource_id"])
    op.create_index("idx_community_id", "community_assignments", ["community_id"])
    op.create_index("idx_community_computed", "community_assignments", ["computed_at"])


def downgrade() -> None:
    """Remove community_assignments table."""
    op.drop_index("idx_community_computed", table_name="community_assignments")
    op.drop_index("idx_community_id", table_name="community_assignments")
    op.drop_index("idx_community_resource", table_name="community_assignments")
    op.drop_table("community_assignments")
