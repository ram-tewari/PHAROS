"""
Fix boolean columns from INTEGER to BOOLEAN

Revision ID: 20260108_fix_boolean_columns
Revises: 20260108_fix_embedding_type
Create Date: 2026-01-08 03:37:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260108_fix_boolean_columns"
down_revision = "20260108_fix_embedding_type"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Get bind to check database type
    bind = op.get_bind()

    if bind.dialect.name == "postgresql":
        # Change INTEGER columns to BOOLEAN
        # Convert 0/1 to false/true
        boolean_columns = [
            "requires_manual_review",
            "is_quality_outlier",
            "needs_quality_review",
            "is_ocr_processed",
        ]

        for col in boolean_columns:
            # Check current type and only convert if it's INTEGER
            result = bind.execute(
                sa.text(
                    f"SELECT data_type FROM information_schema.columns WHERE table_name = 'resources' AND column_name = '{col}'"
                )
            )
            current_type = result.scalar()

            if current_type == "integer":
                op.execute(f"ALTER TABLE resources ALTER COLUMN {col} DROP DEFAULT")
                op.execute(
                    f"ALTER TABLE resources ALTER COLUMN {col} TYPE BOOLEAN USING CASE WHEN {col} = 0 THEN false ELSE true END"
                )
                op.execute(
                    f"ALTER TABLE resources ALTER COLUMN {col} SET DEFAULT false"
                )
    else:
        # SQLite uses INTEGER for boolean, no change needed
        pass


def downgrade() -> None:
    # Get bind to check database type
    bind = op.get_bind()

    if bind.dialect.name == "postgresql":
        # Change BOOLEAN columns back to INTEGER
        boolean_columns = [
            "requires_manual_review",
            "is_quality_outlier",
            "needs_quality_review",
            "is_ocr_processed",
        ]

        for col in boolean_columns:
            op.execute(
                f"ALTER TABLE resources ALTER COLUMN {col} TYPE INTEGER USING CASE WHEN {col} THEN 1 ELSE 0 END"
            )
            op.execute(f"ALTER TABLE resources ALTER COLUMN {col} SET DEFAULT 0")
    else:
        # SQLite: no change needed
        pass
