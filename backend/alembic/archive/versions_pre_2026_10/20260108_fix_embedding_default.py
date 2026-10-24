"""
Fix embedding column default value

This migration removes the server_default from the embedding column
to allow NULL values instead of empty arrays.

Revision ID: 20260108_fix_embedding_default
Revises: (latest)
Create Date: 2026-01-08 03:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "20260108_fix_embedding_default"
down_revision = "20260105_update_users_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Get bind to check database type
    bind = op.get_bind()

    if bind.dialect.name == "postgresql":
        # Step 1: Remove server_default first
        op.execute("ALTER TABLE resources ALTER COLUMN embedding DROP DEFAULT")

        # Step 2: Change from ARRAY to JSON for better NULL handling
        # PostgreSQL requires explicit USING clause for type conversion
        op.execute(
            "ALTER TABLE resources ALTER COLUMN embedding TYPE JSON USING "
            "CASE WHEN embedding IS NULL THEN NULL ELSE to_json(embedding) END"
        )

        # Step 3: Update existing empty arrays to NULL
        # Use jsonb cast for comparison
        op.execute("UPDATE resources SET embedding = NULL WHERE embedding::text = '[]'")
    else:
        # SQLite: Just remove server_default
        op.alter_column(
            "resources",
            "embedding",
            existing_type=sa.JSON,
            server_default=None,
            nullable=True,
        )

        # Update existing empty arrays to NULL
        op.execute("UPDATE resources SET embedding = NULL WHERE embedding = '[]'")


def downgrade() -> None:
    # Get bind to check database type
    bind = op.get_bind()

    if bind.dialect.name == "postgresql":
        # Restore ARRAY type with server_default
        op.alter_column(
            "resources",
            "embedding",
            existing_type=sa.JSON,
            type_=postgresql.ARRAY(sa.Float),
            server_default="{}",
            nullable=True,
        )
    else:
        # SQLite: Restore server_default
        op.alter_column(
            "resources",
            "embedding",
            existing_type=sa.JSON,
            server_default="[]",
            nullable=True,
        )
