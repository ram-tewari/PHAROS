"""Add metadata field to graph_relationships for code intelligence

Revision ID: 20260105_add_metadata
Revises: 20260103_add_advanced_rag_tables
Create Date: 2026-01-05 00:20:00.000000

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260105_add_metadata"
down_revision = "20260103_add_advanced_rag_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add relationship_metadata JSON field to graph_relationships table."""
    # Add relationship_metadata column for storing code-specific relationship metadata
    # (source_file, target_symbol, line_number, confidence, etc.)
    op.add_column(
        "graph_relationships",
        sa.Column("relationship_metadata", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    """Remove relationship_metadata field from graph_relationships table."""
    op.drop_column("graph_relationships", "relationship_metadata")
