"""add_ab_testing_tables

Revision ID: i9j0k1l2m3n4
Revises: 7c607a7908f4
Create Date: 2025-11-16 10:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "i9j0k1l2m3n4"
down_revision: Union[str, Sequence[str], None] = "7c607a7908f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def table_exists(table_name: str) -> bool:
    """Check if a table exists in the database."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    return table_name in inspector.get_table_names()


def index_exists(table_name: str, index_name: str) -> bool:
    """Check if an index exists on a table."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    try:
        indexes = [idx["name"] for idx in inspector.get_indexes(table_name)]
        return index_name in indexes
    except Exception:
        return False


def upgrade() -> None:
    """
    Upgrade schema - Add A/B testing tables for model version comparison.

    Creates:
    - model_versions: Track trained model versions with metadata
    - ab_test_experiments: A/B test experiment configuration
    - prediction_logs: Log predictions for analysis
    """

    # Get database connection for dialect-specific operations
    conn = op.get_bind()

    # Define GUID type based on dialect
    if conn.dialect.name == "postgresql":
        guid_type = postgresql.UUID()
    else:
        guid_type = sa.CHAR(36)

    # Create model_versions table if it doesn't exist
    if not table_exists("model_versions"):
        op.create_table(
            "model_versions",
            sa.Column("id", guid_type, nullable=False),
            sa.Column("version", sa.String(length=20), nullable=False),
            sa.Column("model_type", sa.String(length=50), nullable=False),
            sa.Column("model_path", sa.Text(), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("metadata", sa.JSON(), nullable=True),
            sa.Column("metrics", sa.JSON(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("version"),
        )
        print("Created model_versions table")
    else:
        print("model_versions table already exists")

    # Create indexes for model_versions table
    if not index_exists("model_versions", "idx_model_versions_version"):
        op.create_index("idx_model_versions_version", "model_versions", ["version"])
    if not index_exists("model_versions", "idx_model_versions_status"):
        op.create_index("idx_model_versions_status", "model_versions", ["status"])

    # Create ab_test_experiments table if it doesn't exist
    if not table_exists("ab_test_experiments"):
        op.create_table(
            "ab_test_experiments",
            sa.Column("id", guid_type, nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("control_version_id", guid_type, nullable=False),
            sa.Column("treatment_version_id", guid_type, nullable=False),
            sa.Column("traffic_split", sa.Float(), nullable=False),
            sa.Column(
                "start_date",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.Column("end_date", sa.DateTime(timezone=True), nullable=True),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("results", sa.JSON(), nullable=True),
            sa.ForeignKeyConstraint(
                ["control_version_id"], ["model_versions.id"], ondelete="CASCADE"
            ),
            sa.ForeignKeyConstraint(
                ["treatment_version_id"], ["model_versions.id"], ondelete="CASCADE"
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        print("Created ab_test_experiments table")
    else:
        print("ab_test_experiments table already exists")

    # Create indexes for ab_test_experiments table
    if not index_exists("ab_test_experiments", "idx_ab_test_experiments_status"):
        op.create_index(
            "idx_ab_test_experiments_status", "ab_test_experiments", ["status"]
        )
    if not index_exists("ab_test_experiments", "idx_ab_test_experiments_dates"):
        op.create_index(
            "idx_ab_test_experiments_dates",
            "ab_test_experiments",
            ["start_date", "end_date"],
        )

    # Add check constraint for traffic_split range (0.0-1.0)
    if conn.dialect.name == "postgresql":
        op.create_check_constraint(
            "ck_ab_test_experiments_traffic_split_range",
            "ab_test_experiments",
            "traffic_split >= 0.0 AND traffic_split <= 1.0",
        )

    # Create prediction_logs table if it doesn't exist
    if not table_exists("prediction_logs"):
        op.create_table(
            "prediction_logs",
            sa.Column("id", guid_type, nullable=False),
            sa.Column("experiment_id", guid_type, nullable=False),
            sa.Column("model_version_id", guid_type, nullable=False),
            sa.Column("input_text", sa.Text(), nullable=False),
            sa.Column("predictions", sa.JSON(), nullable=False),
            sa.Column("latency_ms", sa.Float(), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.Column("user_id", guid_type, nullable=True),
            sa.ForeignKeyConstraint(
                ["experiment_id"], ["ab_test_experiments.id"], ondelete="CASCADE"
            ),
            sa.ForeignKeyConstraint(
                ["model_version_id"], ["model_versions.id"], ondelete="CASCADE"
            ),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        print("Created prediction_logs table")
    else:
        print("prediction_logs table already exists")

    # Create indexes for prediction_logs table
    if not index_exists("prediction_logs", "idx_prediction_logs_experiment_id"):
        op.create_index(
            "idx_prediction_logs_experiment_id", "prediction_logs", ["experiment_id"]
        )
    if not index_exists("prediction_logs", "idx_prediction_logs_model_version_id"):
        op.create_index(
            "idx_prediction_logs_model_version_id",
            "prediction_logs",
            ["model_version_id"],
        )
    if not index_exists("prediction_logs", "idx_prediction_logs_created_at"):
        op.create_index(
            "idx_prediction_logs_created_at", "prediction_logs", ["created_at"]
        )


def downgrade() -> None:
    """
    Downgrade schema - Remove A/B testing tables.

    Drops tables in reverse order to respect foreign key constraints.
    """

    # Get database connection for dialect-specific operations
    conn = op.get_bind()

    # Drop prediction_logs table and its indexes
    if table_exists("prediction_logs"):
        if index_exists("prediction_logs", "idx_prediction_logs_created_at"):
            op.drop_index(
                "idx_prediction_logs_created_at", table_name="prediction_logs"
            )
        if index_exists("prediction_logs", "idx_prediction_logs_model_version_id"):
            op.drop_index(
                "idx_prediction_logs_model_version_id", table_name="prediction_logs"
            )
        if index_exists("prediction_logs", "idx_prediction_logs_experiment_id"):
            op.drop_index(
                "idx_prediction_logs_experiment_id", table_name="prediction_logs"
            )
        op.drop_table("prediction_logs")
        print("Dropped prediction_logs table")

    # Drop ab_test_experiments table, its indexes, and check constraints
    if table_exists("ab_test_experiments"):
        if conn.dialect.name == "postgresql":
            op.drop_constraint(
                "ck_ab_test_experiments_traffic_split_range",
                "ab_test_experiments",
                type_="check",
            )

        if index_exists("ab_test_experiments", "idx_ab_test_experiments_dates"):
            op.drop_index(
                "idx_ab_test_experiments_dates", table_name="ab_test_experiments"
            )
        if index_exists("ab_test_experiments", "idx_ab_test_experiments_status"):
            op.drop_index(
                "idx_ab_test_experiments_status", table_name="ab_test_experiments"
            )
        op.drop_table("ab_test_experiments")
        print("Dropped ab_test_experiments table")

    # Drop model_versions table and its indexes
    if table_exists("model_versions"):
        if index_exists("model_versions", "idx_model_versions_status"):
            op.drop_index("idx_model_versions_status", table_name="model_versions")
        if index_exists("model_versions", "idx_model_versions_version"):
            op.drop_index("idx_model_versions_version", table_name="model_versions")
        op.drop_table("model_versions")
        print("Dropped model_versions table")
