"""add_taxonomy_tables_phase8_5

Revision ID: f6c3d5e7a8b9
Revises: e5b9f2c3d4e5
Create Date: 2025-11-10 10:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f6c3d5e7a8b9"
down_revision: Union[str, Sequence[str], None] = "10bf65d53f59"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - Add taxonomy_nodes and resource_taxonomy tables for Phase 8.5."""
    from sqlalchemy.dialects.postgresql import UUID

    # Check if tables already exist (they might be auto-created by SQLAlchemy)
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = inspector.get_table_names()

    # Determine the appropriate ID type based on database dialect
    id_type = UUID(as_uuid=True) if conn.dialect.name == "postgresql" else sa.String(36)

    # Create taxonomy_nodes table only if it doesn't exist
    if "taxonomy_nodes" not in existing_tables:
        op.create_table(
            "taxonomy_nodes",
            sa.Column("id", id_type, primary_key=True),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("slug", sa.String(255), nullable=False, unique=True),
            sa.Column("parent_id", id_type, nullable=True),
            sa.Column("level", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("path", sa.String(1000), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("keywords", sa.JSON(), nullable=True),
            sa.Column(
                "resource_count", sa.Integer(), nullable=False, server_default="0"
            ),
            sa.Column(
                "descendant_resource_count",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
            sa.Column("is_leaf", sa.Integer(), nullable=False, server_default="1"),
            sa.Column(
                "allow_resources", sa.Integer(), nullable=False, server_default="1"
            ),
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
                ["parent_id"], ["taxonomy_nodes.id"], ondelete="CASCADE"
            ),
            sa.CheckConstraint("level >= 0", name="ck_taxonomy_node_level_nonnegative"),
        )

        # Create indexes for taxonomy_nodes table
        op.create_index("idx_taxonomy_parent_id", "taxonomy_nodes", ["parent_id"])
        op.create_index("idx_taxonomy_path", "taxonomy_nodes", ["path"])
        op.create_index("idx_taxonomy_slug", "taxonomy_nodes", ["slug"], unique=True)

    # Create resource_taxonomy association table only if it doesn't exist
    if "resource_taxonomy" not in existing_tables:
        op.create_table(
            "resource_taxonomy",
            sa.Column("id", id_type, primary_key=True),
            sa.Column("resource_id", id_type, nullable=False),
            sa.Column("taxonomy_node_id", id_type, nullable=False),
            sa.Column("confidence", sa.Float(), nullable=False, server_default="0.0"),
            sa.Column("is_predicted", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("predicted_by", sa.String(100), nullable=True),
            sa.Column("needs_review", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("review_priority", sa.Float(), nullable=True),
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
            sa.ForeignKeyConstraint(
                ["taxonomy_node_id"], ["taxonomy_nodes.id"], ondelete="CASCADE"
            ),
            sa.CheckConstraint(
                "confidence >= 0.0 AND confidence <= 1.0",
                name="ck_resource_taxonomy_confidence_range",
            ),
        )

        # Create indexes for resource_taxonomy table
        op.create_index(
            "idx_resource_taxonomy_resource", "resource_taxonomy", ["resource_id"]
        )
        op.create_index(
            "idx_resource_taxonomy_taxonomy", "resource_taxonomy", ["taxonomy_node_id"]
        )
        op.create_index(
            "idx_resource_taxonomy_needs_review", "resource_taxonomy", ["needs_review"]
        )


def downgrade() -> None:
    """Downgrade schema - Remove taxonomy_nodes and resource_taxonomy tables."""

    # Drop indexes for resource_taxonomy table
    op.drop_index("idx_resource_taxonomy_needs_review", table_name="resource_taxonomy")
    op.drop_index("idx_resource_taxonomy_taxonomy", table_name="resource_taxonomy")
    op.drop_index("idx_resource_taxonomy_resource", table_name="resource_taxonomy")

    # Drop resource_taxonomy table
    op.drop_table("resource_taxonomy")

    # Drop indexes for taxonomy_nodes table
    op.drop_index("idx_taxonomy_slug", table_name="taxonomy_nodes")
    op.drop_index("idx_taxonomy_path", table_name="taxonomy_nodes")
    op.drop_index("idx_taxonomy_parent_id", table_name="taxonomy_nodes")

    # Drop taxonomy_nodes table
    op.drop_table("taxonomy_nodes")
