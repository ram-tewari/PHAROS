"""add_graph_centrality_cache_table

Revision ID: 20260123_centrality
Revises: 20260108_fix_embedding_default
Create Date: 2026-01-23 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20260123_centrality"
down_revision = "20260108_fix_embedding_default"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create graph_centrality_cache table
    op.create_table(
        "graph_centrality_cache",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("in_degree", sa.Integer(), server_default="0", nullable=False),
        sa.Column("out_degree", sa.Integer(), server_default="0", nullable=False),
        sa.Column("betweenness", sa.Float(), server_default="0.0", nullable=False),
        sa.Column("pagerank", sa.Float(), server_default="0.0", nullable=False),
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
    op.create_index(
        "idx_centrality_resource", "graph_centrality_cache", ["resource_id"]
    )
    op.create_index(
        "idx_centrality_computed", "graph_centrality_cache", ["computed_at"]
    )


def downgrade() -> None:
    # Drop indexes
    op.drop_index("idx_centrality_computed", table_name="graph_centrality_cache")
    op.drop_index("idx_centrality_resource", table_name="graph_centrality_cache")

    # Drop table
    op.drop_table("graph_centrality_cache")
