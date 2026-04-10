"""
Change embedding column from JSON to TEXT to avoid casting issues

Revision ID: 20260108_fix_embedding_type
Revises: 20260108_fix_embedding_default
Create Date: 2026-01-08 03:25:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260108_fix_embedding_type"
down_revision = "20260108_fix_embedding_default"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Get bind to check database type
    bind = op.get_bind()

    if bind.dialect.name == "postgresql":
        # Change from JSON to TEXT to avoid casting issues with NULL
        op.execute(
            "ALTER TABLE resources ALTER COLUMN embedding TYPE TEXT USING embedding::text"
        )
    else:
        # SQLite: JSON is already flexible, no change needed
        pass


def downgrade() -> None:
    # Get bind to check database type
    bind = op.get_bind()

    if bind.dialect.name == "postgresql":
        # Change back from TEXT to JSON
        op.execute(
            "ALTER TABLE resources ALTER COLUMN embedding TYPE JSON USING embedding::json"
        )
    else:
        # SQLite: no change needed
        pass
