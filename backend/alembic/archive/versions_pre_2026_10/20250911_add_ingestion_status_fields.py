"""Add ingestion status fields to resources table

Revision ID: 20250911_add_ingestion_status_fields
Revises: 20250911_add_authority_tables
Create Date: 2025-09-11 13:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20250911_add_ingestion_status_fields"
down_revision = "20250911_add_authority_tables"
branch_labels = None
depends_on = None


def upgrade():
    """Add ingestion status fields to resources table."""
    # Add ingestion status fields
    op.add_column(
        "resources",
        sa.Column(
            "ingestion_status", sa.String(), nullable=False, server_default="pending"
        ),
    )
    op.add_column("resources", sa.Column("ingestion_error", sa.Text(), nullable=True))
    op.add_column(
        "resources",
        sa.Column("ingestion_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "resources",
        sa.Column("ingestion_completed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade():
    """Remove ingestion status fields from resources table."""
    op.drop_column("resources", "ingestion_completed_at")
    op.drop_column("resources", "ingestion_started_at")
    op.drop_column("resources", "ingestion_error")
    op.drop_column("resources", "ingestion_status")
