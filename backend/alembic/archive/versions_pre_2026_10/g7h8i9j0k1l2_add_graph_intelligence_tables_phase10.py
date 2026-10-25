"""add_graph_intelligence_tables_phase10

Revision ID: g7h8i9j0k1l2
Revises: f6c3d5e7a8b9
Create Date: 2025-11-11 10:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "g7h8i9j0k1l2"
down_revision: Union[str, Sequence[str], None] = "f6c3d5e7a8b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - Add graph_edges, graph_embeddings, and discovery_hypotheses tables for Phase 10."""
    from sqlalchemy.dialects.postgresql import UUID

    # Check if tables already exist (they might be auto-created by SQLAlchemy)
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = inspector.get_table_names()

    # Determine the appropriate ID type based on database dialect
    id_type = UUID(as_uuid=True) if conn.dialect.name == "postgresql" else sa.String(36)

    # Create graph_edges table only if it doesn't exist
    if "graph_edges" not in existing_tables:
        op.create_table(
            "graph_edges",
            sa.Column("id", id_type, primary_key=True),
            sa.Column("source_id", id_type, nullable=False),
            sa.Column("target_id", id_type, nullable=False),
            sa.Column("edge_type", sa.String(50), nullable=False),
            sa.Column("weight", sa.Float(), nullable=False),
            sa.Column("metadata", sa.Text(), nullable=True),
            sa.Column("created_by", sa.String(100), nullable=False),
            sa.Column("confidence", sa.Float(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.current_timestamp(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.current_timestamp(),
            ),
            sa.ForeignKeyConstraint(
                ["source_id"], ["resources.id"], ondelete="CASCADE"
            ),
            sa.ForeignKeyConstraint(
                ["target_id"], ["resources.id"], ondelete="CASCADE"
            ),
        )

        # Create indexes for graph_edges table
        op.create_index("idx_graph_edges_source", "graph_edges", ["source_id"])
        op.create_index("idx_graph_edges_target", "graph_edges", ["target_id"])
        op.create_index("idx_graph_edges_type", "graph_edges", ["edge_type"])
        op.create_index(
            "idx_graph_edges_composite",
            "graph_edges",
            ["source_id", "target_id", "edge_type"],
            unique=True,
        )

    # Create graph_embeddings table only if it doesn't exist
    if "graph_embeddings" not in existing_tables:
        op.create_table(
            "graph_embeddings",
            sa.Column("id", id_type, primary_key=True),
            sa.Column("resource_id", id_type, nullable=False, unique=True),
            sa.Column("structural_embedding", sa.JSON(), nullable=True),
            sa.Column("fusion_embedding", sa.JSON(), nullable=True),
            sa.Column("embedding_method", sa.String(50), nullable=False),
            sa.Column("embedding_version", sa.String(20), nullable=False),
            sa.Column("hnsw_index_id", sa.Integer(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.current_timestamp(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.current_timestamp(),
            ),
            sa.ForeignKeyConstraint(
                ["resource_id"], ["resources.id"], ondelete="CASCADE"
            ),
        )

        # Create indexes for graph_embeddings table
        op.create_index(
            "idx_graph_embeddings_resource",
            "graph_embeddings",
            ["resource_id"],
            unique=True,
        )

    # Create discovery_hypotheses table only if it doesn't exist
    if "discovery_hypotheses" not in existing_tables:
        op.create_table(
            "discovery_hypotheses",
            sa.Column("id", id_type, primary_key=True),
            sa.Column("a_resource_id", id_type, nullable=False),
            sa.Column("c_resource_id", id_type, nullable=False),
            sa.Column("b_resource_ids", sa.Text(), nullable=False),
            sa.Column("hypothesis_type", sa.String(20), nullable=False),
            sa.Column("plausibility_score", sa.Float(), nullable=False),
            sa.Column("path_strength", sa.Float(), nullable=False),
            sa.Column("path_length", sa.Integer(), nullable=False),
            sa.Column(
                "common_neighbors", sa.Integer(), nullable=False, server_default="0"
            ),
            sa.Column(
                "discovered_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.current_timestamp(),
            ),
            sa.Column("user_id", sa.String(255), nullable=True),
            sa.Column("is_validated", sa.Integer(), nullable=True),
            sa.Column("validation_notes", sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(
                ["a_resource_id"], ["resources.id"], ondelete="CASCADE"
            ),
            sa.ForeignKeyConstraint(
                ["c_resource_id"], ["resources.id"], ondelete="CASCADE"
            ),
        )

        # Create indexes for discovery_hypotheses table
        op.create_index(
            "idx_discovery_a_c",
            "discovery_hypotheses",
            ["a_resource_id", "c_resource_id"],
        )
        op.create_index(
            "idx_discovery_type", "discovery_hypotheses", ["hypothesis_type"]
        )
        op.create_index(
            "idx_discovery_plausibility", "discovery_hypotheses", ["plausibility_score"]
        )


def downgrade() -> None:
    """Downgrade schema - Remove graph_edges, graph_embeddings, and discovery_hypotheses tables."""

    # Drop indexes for discovery_hypotheses table
    op.drop_index("idx_discovery_plausibility", table_name="discovery_hypotheses")
    op.drop_index("idx_discovery_type", table_name="discovery_hypotheses")
    op.drop_index("idx_discovery_a_c", table_name="discovery_hypotheses")

    # Drop discovery_hypotheses table
    op.drop_table("discovery_hypotheses")

    # Drop indexes for graph_embeddings table
    op.drop_index("idx_graph_embeddings_resource", table_name="graph_embeddings")

    # Drop graph_embeddings table
    op.drop_table("graph_embeddings")

    # Drop indexes for graph_edges table
    op.drop_index("idx_graph_edges_composite", table_name="graph_edges")
    op.drop_index("idx_graph_edges_type", table_name="graph_edges")
    op.drop_index("idx_graph_edges_target", table_name="graph_edges")
    op.drop_index("idx_graph_edges_source", table_name="graph_edges")

    # Drop graph_edges table
    op.drop_table("graph_edges")
