"""add_sparse_embedding_fields_phase8

Revision ID: 10bf65d53f59
Revises: e5b9f2c3d4e5
Create Date: 2025-11-10 01:10:27.957255

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "10bf65d53f59"
down_revision: Union[str, Sequence[str], None] = "e5b9f2c3d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - Add sparse embedding fields for Phase 8 three-way hybrid search."""

    # Add sparse_embedding field (Text/JSON type) to store token-weight mappings
    op.add_column("resources", sa.Column("sparse_embedding", sa.Text(), nullable=True))

    # Add sparse_embedding_model field (String) to track model version
    op.add_column(
        "resources", sa.Column("sparse_embedding_model", sa.String(100), nullable=True)
    )

    # Add sparse_embedding_updated_at field (DateTime) for batch processing tracking
    op.add_column(
        "resources",
        sa.Column(
            "sparse_embedding_updated_at", sa.DateTime(timezone=True), nullable=True
        ),
    )

    # Create index on sparse_embedding_updated_at for efficient queries
    op.create_index(
        "idx_resources_sparse_updated", "resources", ["sparse_embedding_updated_at"]
    )


def downgrade() -> None:
    """Downgrade schema - Remove sparse embedding fields."""

    # Drop index
    op.drop_index("idx_resources_sparse_updated", table_name="resources")

    # Drop columns in reverse order
    op.drop_column("resources", "sparse_embedding_updated_at")
    op.drop_column("resources", "sparse_embedding_model")
    op.drop_column("resources", "sparse_embedding")
