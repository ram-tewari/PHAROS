"""phase3_drop_dead_resource_columns

Revision ID: f3a1b2c4d5e6
Revises: ea5d03fc7e80
Create Date: 2026-07-18

Phase 3 column surgery: drops the 36 resources columns that only the
amputated Neo Alexandria scholarly/quality/OCR code ever wrote. The
surviving scholarly core (doi/pmid/arxiv_id/journal/authors/affiliations/
funding_sources/publication_year, the three *_count columns, and
quality_overall) stays — pdf_ingestion and graph/discovery read them.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f3a1b2c4d5e6'
down_revision: Union[str, Sequence[str], None] = 'ea5d03fc7e80'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_DROPPED_COLUMNS = [
    # scholarly long tail
    "isbn",
    "conference",
    "volume",
    "issue",
    "pages",
    "acknowledgments",
    "reference_count",
    "equations",
    "tables",
    "figures",
    "metadata_completeness_score",
    "extraction_confidence",
    "requires_manual_review",
    # quality-dimension engine (only quality_overall survives)
    "quality_accuracy",
    "quality_completeness",
    "quality_consistency",
    "quality_timeliness",
    "quality_relevance",
    "quality_weights",
    "quality_last_computed",
    "quality_computation_version",
    "is_quality_outlier",
    "outlier_score",
    "outlier_reasons",
    "needs_quality_review",
    "summary_coherence",
    "summary_consistency",
    "summary_fluency",
    "summary_relevance",
    # summary-eval columns that existed only in the DB (added by the phase9
    # quality migration, never in the current model)
    "summary_completeness",
    "summary_conciseness",
    "summary_bertscore",
    "summary_quality_overall",
    # OCR metadata
    "is_ocr_processed",
    "ocr_confidence",
    "ocr_corrections_applied",
]


def upgrade() -> None:
    """Drop dead resources columns. Idempotent (IF EXISTS) on Postgres;
    on SQLite (dev/test) only drops columns that exist."""
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # DROP COLUMN drops dependent indexes automatically on Postgres.
        for col in _DROPPED_COLUMNS:
            op.execute(f'ALTER TABLE resources DROP COLUMN IF EXISTS "{col}"')
        return

    inspector = sa.inspect(bind)
    doomed = set(_DROPPED_COLUMNS)
    # SQLite batch mode recreates the table and re-creates existing indexes,
    # which fails for indexes on columns being dropped — drop those first.
    for idx in inspector.get_indexes("resources"):
        if set(idx["column_names"]) & doomed:
            op.drop_index(idx["name"], table_name="resources")
    existing = {c["name"] for c in inspector.get_columns("resources")}
    to_drop = [c for c in _DROPPED_COLUMNS if c in existing]
    if to_drop:
        with op.batch_alter_table("resources") as batch:
            for col in to_drop:
                batch.drop_column(col)


def downgrade() -> None:
    """Irreversible. The columns belonged to removed Neo Alexandria code;
    roll forward from a database backup instead."""
    raise NotImplementedError(
        "Phase 3 column drops are not reversible; restore from a database backup."
    )
