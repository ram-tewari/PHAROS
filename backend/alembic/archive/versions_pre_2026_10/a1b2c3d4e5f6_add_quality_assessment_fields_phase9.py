"""add_quality_assessment_fields_phase9

Revision ID: a1b2c3d4e5f6
Revises: f6c3d5e7a8b9
Create Date: 2025-11-10 14:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "f6c3d5e7a8b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - Add Phase 9 multi-dimensional quality assessment fields."""

    # Check if columns already exist (they might be auto-created by SQLAlchemy)
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_columns = [col["name"] for col in inspector.get_columns("resources")]

    # Multi-Dimensional Quality Scores (0.0-1.0 each)
    if "quality_accuracy" not in existing_columns:
        op.add_column(
            "resources", sa.Column("quality_accuracy", sa.Float(), nullable=True)
        )
    if "quality_completeness" not in existing_columns:
        op.add_column(
            "resources", sa.Column("quality_completeness", sa.Float(), nullable=True)
        )
    if "quality_consistency" not in existing_columns:
        op.add_column(
            "resources", sa.Column("quality_consistency", sa.Float(), nullable=True)
        )
    if "quality_timeliness" not in existing_columns:
        op.add_column(
            "resources", sa.Column("quality_timeliness", sa.Float(), nullable=True)
        )
    if "quality_relevance" not in existing_columns:
        op.add_column(
            "resources", sa.Column("quality_relevance", sa.Float(), nullable=True)
        )

    # Weighted Overall Quality
    if "quality_overall" not in existing_columns:
        op.add_column(
            "resources", sa.Column("quality_overall", sa.Float(), nullable=True)
        )
    if "quality_weights" not in existing_columns:
        op.add_column(
            "resources", sa.Column("quality_weights", sa.Text(), nullable=True)
        )

    # Summarization Quality (if summary exists)
    if "summary_coherence" not in existing_columns:
        op.add_column(
            "resources", sa.Column("summary_coherence", sa.Float(), nullable=True)
        )
    if "summary_consistency" not in existing_columns:
        op.add_column(
            "resources", sa.Column("summary_consistency", sa.Float(), nullable=True)
        )
    if "summary_fluency" not in existing_columns:
        op.add_column(
            "resources", sa.Column("summary_fluency", sa.Float(), nullable=True)
        )
    if "summary_relevance" not in existing_columns:
        op.add_column(
            "resources", sa.Column("summary_relevance", sa.Float(), nullable=True)
        )
    if "summary_completeness" not in existing_columns:
        op.add_column(
            "resources", sa.Column("summary_completeness", sa.Float(), nullable=True)
        )
    if "summary_conciseness" not in existing_columns:
        op.add_column(
            "resources", sa.Column("summary_conciseness", sa.Float(), nullable=True)
        )
    if "summary_bertscore" not in existing_columns:
        op.add_column(
            "resources", sa.Column("summary_bertscore", sa.Float(), nullable=True)
        )
    if "summary_quality_overall" not in existing_columns:
        op.add_column(
            "resources", sa.Column("summary_quality_overall", sa.Float(), nullable=True)
        )

    # Anomaly Detection
    if "is_quality_outlier" not in existing_columns:
        op.add_column(
            "resources", sa.Column("is_quality_outlier", sa.Boolean(), nullable=True)
        )
    if "outlier_score" not in existing_columns:
        op.add_column(
            "resources", sa.Column("outlier_score", sa.Float(), nullable=True)
        )
    if "outlier_reasons" not in existing_columns:
        op.add_column(
            "resources", sa.Column("outlier_reasons", sa.Text(), nullable=True)
        )

    # Quality Metadata
    if "quality_last_computed" not in existing_columns:
        op.add_column(
            "resources",
            sa.Column(
                "quality_last_computed", sa.DateTime(timezone=True), nullable=True
            ),
        )
    if "quality_computation_version" not in existing_columns:
        op.add_column(
            "resources",
            sa.Column(
                "quality_computation_version", sa.String(length=20), nullable=True
            ),
        )
    if "needs_quality_review" not in existing_columns:
        op.add_column(
            "resources", sa.Column("needs_quality_review", sa.Boolean(), nullable=True)
        )

    # Check existing indexes
    existing_indexes = [idx["name"] for idx in inspector.get_indexes("resources")]

    # Create indexes for filtering queries
    if "idx_resources_quality_overall" not in existing_indexes:
        op.create_index(
            "idx_resources_quality_overall", "resources", ["quality_overall"]
        )
    if "idx_resources_is_quality_outlier" not in existing_indexes:
        op.create_index(
            "idx_resources_is_quality_outlier", "resources", ["is_quality_outlier"]
        )
    if "idx_resources_needs_quality_review" not in existing_indexes:
        op.create_index(
            "idx_resources_needs_quality_review", "resources", ["needs_quality_review"]
        )

    # Add check constraints ensuring quality scores are between 0.0 and 1.0
    # Note: CHECK constraints are only added for PostgreSQL. SQLite doesn't support
    # adding CHECK constraints via ALTER TABLE. For SQLite, validation is enforced
    # at the application level in the QualityService.
    conn = op.get_bind()
    if conn.dialect.name == "postgresql":
        op.create_check_constraint(
            "ck_quality_accuracy_range",
            "resources",
            "quality_accuracy IS NULL OR (quality_accuracy >= 0.0 AND quality_accuracy <= 1.0)",
        )
        op.create_check_constraint(
            "ck_quality_completeness_range",
            "resources",
            "quality_completeness IS NULL OR (quality_completeness >= 0.0 AND quality_completeness <= 1.0)",
        )
        op.create_check_constraint(
            "ck_quality_consistency_range",
            "resources",
            "quality_consistency IS NULL OR (quality_consistency >= 0.0 AND quality_consistency <= 1.0)",
        )
        op.create_check_constraint(
            "ck_quality_timeliness_range",
            "resources",
            "quality_timeliness IS NULL OR (quality_timeliness >= 0.0 AND quality_timeliness <= 1.0)",
        )
        op.create_check_constraint(
            "ck_quality_relevance_range",
            "resources",
            "quality_relevance IS NULL OR (quality_relevance >= 0.0 AND quality_relevance <= 1.0)",
        )
        op.create_check_constraint(
            "ck_quality_overall_range",
            "resources",
            "quality_overall IS NULL OR (quality_overall >= 0.0 AND quality_overall <= 1.0)",
        )
        op.create_check_constraint(
            "ck_summary_coherence_range",
            "resources",
            "summary_coherence IS NULL OR (summary_coherence >= 0.0 AND summary_coherence <= 1.0)",
        )
        op.create_check_constraint(
            "ck_summary_consistency_range",
            "resources",
            "summary_consistency IS NULL OR (summary_consistency >= 0.0 AND summary_consistency <= 1.0)",
        )
        op.create_check_constraint(
            "ck_summary_fluency_range",
            "resources",
            "summary_fluency IS NULL OR (summary_fluency >= 0.0 AND summary_fluency <= 1.0)",
        )
        op.create_check_constraint(
            "ck_summary_relevance_range",
            "resources",
            "summary_relevance IS NULL OR (summary_relevance >= 0.0 AND summary_relevance <= 1.0)",
        )
        op.create_check_constraint(
            "ck_summary_completeness_range",
            "resources",
            "summary_completeness IS NULL OR (summary_completeness >= 0.0 AND summary_completeness <= 1.0)",
        )
        op.create_check_constraint(
            "ck_summary_conciseness_range",
            "resources",
            "summary_conciseness IS NULL OR (summary_conciseness >= 0.0 AND summary_conciseness <= 1.0)",
        )
        op.create_check_constraint(
            "ck_summary_bertscore_range",
            "resources",
            "summary_bertscore IS NULL OR (summary_bertscore >= 0.0 AND summary_bertscore <= 1.0)",
        )
        op.create_check_constraint(
            "ck_summary_quality_overall_range",
            "resources",
            "summary_quality_overall IS NULL OR (summary_quality_overall >= 0.0 AND summary_quality_overall <= 1.0)",
        )


def downgrade() -> None:
    """Downgrade schema - Remove Phase 9 quality assessment fields."""

    # Drop check constraints (only for PostgreSQL)
    conn = op.get_bind()
    if conn.dialect.name == "postgresql":
        op.drop_constraint(
            "ck_summary_quality_overall_range", "resources", type_="check"
        )
        op.drop_constraint("ck_summary_bertscore_range", "resources", type_="check")
        op.drop_constraint("ck_summary_conciseness_range", "resources", type_="check")
        op.drop_constraint("ck_summary_completeness_range", "resources", type_="check")
        op.drop_constraint("ck_summary_relevance_range", "resources", type_="check")
        op.drop_constraint("ck_summary_fluency_range", "resources", type_="check")
        op.drop_constraint("ck_summary_consistency_range", "resources", type_="check")
        op.drop_constraint("ck_summary_coherence_range", "resources", type_="check")
        op.drop_constraint("ck_quality_overall_range", "resources", type_="check")
        op.drop_constraint("ck_quality_relevance_range", "resources", type_="check")
        op.drop_constraint("ck_quality_timeliness_range", "resources", type_="check")
        op.drop_constraint("ck_quality_consistency_range", "resources", type_="check")
        op.drop_constraint("ck_quality_completeness_range", "resources", type_="check")
        op.drop_constraint("ck_quality_accuracy_range", "resources", type_="check")

    # Drop indexes
    op.drop_index("idx_resources_needs_quality_review", table_name="resources")
    op.drop_index("idx_resources_is_quality_outlier", table_name="resources")
    op.drop_index("idx_resources_quality_overall", table_name="resources")

    # Drop columns in reverse order
    op.drop_column("resources", "needs_quality_review")
    op.drop_column("resources", "quality_computation_version")
    op.drop_column("resources", "quality_last_computed")
    op.drop_column("resources", "outlier_reasons")
    op.drop_column("resources", "outlier_score")
    op.drop_column("resources", "is_quality_outlier")
    op.drop_column("resources", "summary_quality_overall")
    op.drop_column("resources", "summary_bertscore")
    op.drop_column("resources", "summary_conciseness")
    op.drop_column("resources", "summary_completeness")
    op.drop_column("resources", "summary_relevance")
    op.drop_column("resources", "summary_fluency")
    op.drop_column("resources", "summary_consistency")
    op.drop_column("resources", "summary_coherence")
    op.drop_column("resources", "quality_weights")
    op.drop_column("resources", "quality_overall")
    op.drop_column("resources", "quality_relevance")
    op.drop_column("resources", "quality_timeliness")
    op.drop_column("resources", "quality_consistency")
    op.drop_column("resources", "quality_completeness")
    op.drop_column("resources", "quality_accuracy")
