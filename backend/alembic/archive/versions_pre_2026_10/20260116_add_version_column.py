"""Add version column for optimistic locking

Revision ID: 20260116_add_version_column
Revises:
Create Date: 2026-01-16

This migration adds a 'version' column to the resources table for
optimistic concurrency control. The version is incremented on each
update to detect concurrent modifications.

Related files:
- app/database/models.py: Resource model with version field
- app/modules/resources/service.py: Update logic with version checking
- app/shared/circuit_breaker.py: Added in same release
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260116_add_version_column"
down_revision = None  # Will be set by Alembic based on current head
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add version column to resources table."""
    # Add version column with default value of 1
    op.add_column(
        "resources",
        sa.Column(
            "version",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
    )

    print("Added 'version' column to resources table for optimistic locking")


def downgrade() -> None:
    """Remove version column from resources table."""
    op.drop_column("resources", "version")

    print("Removed 'version' column from resources table")
