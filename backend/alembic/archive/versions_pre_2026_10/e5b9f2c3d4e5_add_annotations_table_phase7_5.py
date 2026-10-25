"""add_annotations_table_phase7_5

Revision ID: e5b9f2c3d4e5
Revises: d4a8e9f1b2c3
Create Date: 2025-11-09 22:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e5b9f2c3d4e5"
down_revision: Union[str, Sequence[str], None] = "d4a8e9f1b2c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - Add annotations table for Phase 7.5."""
    from sqlalchemy.dialects.postgresql import UUID

    # Determine the appropriate ID type based on database dialect
    bind = op.get_bind()
    id_type = UUID(as_uuid=True) if bind.dialect.name == "postgresql" else sa.String(36)

    # Create annotations table
    op.create_table(
        "annotations",
        sa.Column("id", id_type, primary_key=True),
        sa.Column("resource_id", id_type, nullable=False),
        sa.Column("user_id", sa.String(255), nullable=False),
        sa.Column("start_offset", sa.Integer(), nullable=False),
        sa.Column("end_offset", sa.Integer(), nullable=False),
        sa.Column("highlighted_text", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("tags", sa.Text(), nullable=True),
        sa.Column("color", sa.String(7), nullable=False, server_default="#FFFF00"),
        sa.Column("embedding", sa.JSON(), nullable=True),
        sa.Column("context_before", sa.String(50), nullable=True),
        sa.Column("context_after", sa.String(50), nullable=True),
        sa.Column("is_shared", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("collection_ids", sa.Text(), nullable=True),
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
        sa.ForeignKeyConstraint(["resource_id"], ["resources.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "start_offset >= 0", name="ck_annotation_start_offset_nonnegative"
        ),
        sa.CheckConstraint(
            "end_offset >= 0", name="ck_annotation_end_offset_nonnegative"
        ),
        sa.CheckConstraint(
            "start_offset < end_offset", name="ck_annotation_offsets_valid"
        ),
    )

    # Create indexes for annotations table
    op.create_index("idx_annotations_resource", "annotations", ["resource_id"])
    op.create_index("idx_annotations_user", "annotations", ["user_id"])
    op.create_index(
        "idx_annotations_user_resource", "annotations", ["user_id", "resource_id"]
    )
    op.create_index("idx_annotations_created", "annotations", ["created_at"])


def downgrade() -> None:
    """Downgrade schema - Remove annotations table."""

    # Drop indexes for annotations table
    op.drop_index("idx_annotations_created", table_name="annotations")
    op.drop_index("idx_annotations_user_resource", table_name="annotations")
    op.drop_index("idx_annotations_user", table_name="annotations")
    op.drop_index("idx_annotations_resource", table_name="annotations")

    # Drop annotations table
    op.drop_table("annotations")
