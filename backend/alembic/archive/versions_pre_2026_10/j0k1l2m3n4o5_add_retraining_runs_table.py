"""add retraining runs table

Revision ID: j0k1l2m3n4o5
Revises: i9j0k1l2m3n4
Create Date: 2025-11-16 10:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "j0k1l2m3n4o5"
down_revision = "i9j0k1l2m3n4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create retraining_runs table for automated retraining pipeline."""
    # Determine database type
    bind = op.get_bind()
    is_postgresql = bind.dialect.name == "postgresql"

    # Use appropriate types based on database
    uuid_type = postgresql.UUID(as_uuid=True) if is_postgresql else sa.String(36)
    json_type = postgresql.JSONB(astext_type=sa.Text()) if is_postgresql else sa.JSON()

    op.create_table(
        "retraining_runs",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("trigger_type", sa.String(50), nullable=False),
        sa.Column("dataset_size", sa.Integer(), nullable=False),
        sa.Column("new_data_count", sa.Integer(), nullable=False),
        sa.Column("model_version_id", uuid_type, nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("training_time_seconds", sa.Integer(), nullable=True),
        sa.Column("metrics", json_type, nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["model_version_id"], ["model_versions.id"], ondelete="SET NULL"
        ),
    )

    # Create indexes for efficient querying
    op.create_index("idx_retraining_runs_status", "retraining_runs", ["status"])
    op.create_index("idx_retraining_runs_started_at", "retraining_runs", ["started_at"])
    op.create_index(
        "idx_retraining_runs_model_version_id", "retraining_runs", ["model_version_id"]
    )


def downgrade() -> None:
    """Drop retraining_runs table."""
    op.drop_index("idx_retraining_runs_model_version_id", table_name="retraining_runs")
    op.drop_index("idx_retraining_runs_started_at", table_name="retraining_runs")
    op.drop_index("idx_retraining_runs_status", table_name="retraining_runs")
    op.drop_table("retraining_runs")
