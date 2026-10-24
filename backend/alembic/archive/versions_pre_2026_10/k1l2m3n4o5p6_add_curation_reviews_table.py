"""add curation reviews table

Revision ID: k1l2m3n4o5p6
Revises: j0k1l2m3n4o5
Create Date: 2025-12-31 10:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "k1l2m3n4o5p6"
down_revision: Union[str, Sequence[str], None] = "j0k1l2m3n4o5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - Add curation_reviews table for Phase 16.7."""
    # Determine database type
    bind = op.get_bind()
    is_postgresql = bind.dialect.name == "postgresql"

    # Use appropriate types based on database
    uuid_type = postgresql.UUID(as_uuid=True) if is_postgresql else sa.String(36)

    # Check if table already exists
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = inspector.get_table_names()

    if "curation_reviews" not in existing_tables:
        # Create curation_reviews table
        op.create_table(
            "curation_reviews",
            sa.Column("id", uuid_type, primary_key=True),
            sa.Column("resource_id", uuid_type, nullable=False),
            sa.Column("curator_id", sa.String(255), nullable=False),
            sa.Column("action", sa.String(50), nullable=False),
            sa.Column("comment", sa.Text(), nullable=True),
            sa.Column(
                "timestamp",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.current_timestamp(),
            ),
            sa.ForeignKeyConstraint(
                ["resource_id"], ["resources.id"], ondelete="CASCADE"
            ),
        )

        # Create indexes for curation_reviews table
        op.create_index(
            "idx_curation_reviews_resource", "curation_reviews", ["resource_id"]
        )
        op.create_index(
            "idx_curation_reviews_curator", "curation_reviews", ["curator_id"]
        )
        op.create_index(
            "idx_curation_reviews_timestamp", "curation_reviews", ["timestamp"]
        )


def downgrade() -> None:
    """Downgrade schema - Remove curation_reviews table."""
    # Drop indexes for curation_reviews table
    op.drop_index("idx_curation_reviews_timestamp", table_name="curation_reviews")
    op.drop_index("idx_curation_reviews_curator", table_name="curation_reviews")
    op.drop_index("idx_curation_reviews_resource", table_name="curation_reviews")

    # Drop curation_reviews table
    op.drop_table("curation_reviews")
