"""add_collections_tables_phase7

Revision ID: d4a8e9f1b2c3
Revises: c15f564b1ccd
Create Date: 2025-11-09 21:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d4a8e9f1b2c3"
down_revision: Union[str, Sequence[str], None] = "c15f564b1ccd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - Add collections and collection_resources tables for Phase 7."""
    from sqlalchemy.dialects.postgresql import UUID

    # Determine the appropriate ID type based on database dialect
    bind = op.get_bind()
    id_type = UUID(as_uuid=True) if bind.dialect.name == "postgresql" else sa.String(36)

    # Create collections table
    op.create_table(
        "collections",
        sa.Column("id", id_type, primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("owner_id", sa.String(255), nullable=False),
        sa.Column(
            "visibility", sa.String(20), nullable=False, server_default="private"
        ),
        sa.Column("parent_id", id_type, nullable=True),
        sa.Column("embedding", sa.JSON(), nullable=True),
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
        sa.ForeignKeyConstraint(["parent_id"], ["collections.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "visibility IN ('private', 'shared', 'public')",
            name="ck_collection_visibility",
        ),
    )

    # Create indexes for collections table (matching SQLAlchemy naming convention)
    op.create_index("ix_collections_owner_id", "collections", ["owner_id"])
    op.create_index("ix_collections_visibility", "collections", ["visibility"])
    op.create_index("ix_collections_parent_id", "collections", ["parent_id"])

    # Create collection_resources association table
    op.create_table(
        "collection_resources",
        sa.Column("collection_id", id_type, primary_key=True),
        sa.Column("resource_id", id_type, primary_key=True),
        sa.Column(
            "added_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
        sa.ForeignKeyConstraint(
            ["collection_id"], ["collections.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["resource_id"], ["resources.id"], ondelete="CASCADE"),
    )

    # Create composite indexes for collection_resources table
    op.create_index(
        "idx_collection_resources_collection", "collection_resources", ["collection_id"]
    )
    op.create_index(
        "idx_collection_resources_resource", "collection_resources", ["resource_id"]
    )


def downgrade() -> None:
    """Downgrade schema - Remove collections and collection_resources tables."""

    # Drop indexes for collection_resources table
    op.drop_index(
        "idx_collection_resources_resource", table_name="collection_resources"
    )
    op.drop_index(
        "idx_collection_resources_collection", table_name="collection_resources"
    )

    # Drop collection_resources table
    op.drop_table("collection_resources")

    # Drop indexes for collections table (matching SQLAlchemy naming convention)
    op.drop_index("ix_collections_parent_id", table_name="collections")
    op.drop_index("ix_collections_visibility", table_name="collections")
    op.drop_index("ix_collections_owner_id", table_name="collections")

    # Drop collections table
    op.drop_table("collections")
