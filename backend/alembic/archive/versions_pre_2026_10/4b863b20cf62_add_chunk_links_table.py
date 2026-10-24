"""add_chunk_links_table

Revision ID: 4b863b20cf62
Revises: b4b05068fe27
Create Date: 2026-01-23 16:20:03.467977

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "4b863b20cf62"
down_revision: Union[str, Sequence[str], None] = "b4b05068fe27"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    from sqlalchemy.dialects.postgresql import UUID as PG_UUID
    import uuid

    # Determine UUID type based on dialect
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        uuid_type = PG_UUID(as_uuid=True)
    else:
        uuid_type = sa.CHAR(36)

    # Create chunk_links table
    op.create_table(
        "chunk_links",
        sa.Column("id", uuid_type, nullable=False, default=uuid.uuid4),
        sa.Column("source_chunk_id", uuid_type, nullable=False),
        sa.Column("target_chunk_id", uuid_type, nullable=False),
        sa.Column("similarity_score", sa.Float(), nullable=False),
        sa.Column("link_type", sa.String(length=50), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["source_chunk_id"], ["document_chunks.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["target_chunk_id"], ["document_chunks.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create indexes
    op.create_index("idx_chunk_links_source", "chunk_links", ["source_chunk_id"])
    op.create_index("idx_chunk_links_target", "chunk_links", ["target_chunk_id"])
    op.create_index("idx_chunk_links_similarity", "chunk_links", ["similarity_score"])
    op.create_index(
        "idx_chunk_links_source_target",
        "chunk_links",
        ["source_chunk_id", "target_chunk_id"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Drop indexes
    op.drop_index("idx_chunk_links_source_target", table_name="chunk_links")
    op.drop_index("idx_chunk_links_similarity", table_name="chunk_links")
    op.drop_index("idx_chunk_links_target", table_name="chunk_links")
    op.drop_index("idx_chunk_links_source", table_name="chunk_links")

    # Drop table
    op.drop_table("chunk_links")
