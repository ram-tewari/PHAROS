"""verify_resource_schema_columns

Revision ID: h8i9j0k1l2m3
Revises: g7h8i9j0k1l2
Create Date: 2025-11-14 10:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = "h8i9j0k1l2m3"
down_revision: Union[str, Sequence[str], None] = "g7h8i9j0k1l2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def column_exists(table_name: str, column_name: str) -> bool:
    """Check if a column exists in a table."""
    conn = op.get_bind()
    inspector = inspect(conn)

    try:
        columns = [col["name"] for col in inspector.get_columns(table_name)]
        return column_name in columns
    except Exception:
        return False


def upgrade() -> None:
    """
    Verify and add missing Resource table columns.

    This migration ensures that critical Resource model fields exist in the database:
    - sparse_embedding: Text field for sparse vector embeddings (Phase 8)
    - description: Text field from Dublin Core metadata (should exist from initial schema)
    - publisher: String field from Dublin Core metadata (should exist from initial schema)

    The migration handles column already exists errors gracefully by checking
    before attempting to add each column.
    """

    # Check and add sparse_embedding if missing
    # This should have been added by migration 10bf65d53f59, but verify
    if not column_exists("resources", "sparse_embedding"):
        op.add_column(
            "resources", sa.Column("sparse_embedding", sa.Text(), nullable=True)
        )
        print("Added sparse_embedding column to resources table")
    else:
        print("sparse_embedding column already exists in resources table")

    # Check and add description if missing
    # This should exist from initial schema (Dublin Core field), but verify
    if not column_exists("resources", "description"):
        op.add_column("resources", sa.Column("description", sa.Text(), nullable=True))
        print("Added description column to resources table")
    else:
        print("description column already exists in resources table")

    # Check and add publisher if missing
    # This should exist from initial schema (Dublin Core field), but verify
    if not column_exists("resources", "publisher"):
        op.add_column("resources", sa.Column("publisher", sa.String(), nullable=True))
        print("Added publisher column to resources table")
    else:
        print("publisher column already exists in resources table")


def downgrade() -> None:
    """
    Downgrade schema - Remove verified columns.

    Note: This only removes columns that were added by this migration.
    Columns that already existed (description, publisher from initial schema)
    should not be removed as they are part of the core Dublin Core metadata.
    """
    # Only drop columns if they exist
    # Be conservative - don't drop description or publisher as they're core fields
    # Only drop sparse_embedding if it was added by this migration

    if column_exists("resources", "sparse_embedding"):
        # Check if this was added by an earlier migration
        # If so, don't drop it here
        pass  # Let the original migration handle downgrade

    # Don't drop description or publisher - they're core Dublin Core fields
    # from the initial schema
