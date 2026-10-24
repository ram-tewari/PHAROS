"""add_scholarly_metadata_fields_phase6_5

Revision ID: c15f564b1ccd
Revises: 23fa08826047
Create Date: 2025-11-09 20:45:53.104187

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c15f564b1ccd"
down_revision: Union[str, Sequence[str], None] = "23fa08826047"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - Add Phase 6.5 scholarly metadata fields."""
    # Author and Attribution
    op.add_column("resources", sa.Column("authors", sa.Text(), nullable=True))
    op.add_column("resources", sa.Column("affiliations", sa.Text(), nullable=True))

    # Academic Identifiers
    op.add_column("resources", sa.Column("doi", sa.String(length=255), nullable=True))
    op.add_column("resources", sa.Column("pmid", sa.String(length=50), nullable=True))
    op.add_column(
        "resources", sa.Column("arxiv_id", sa.String(length=50), nullable=True)
    )
    op.add_column("resources", sa.Column("isbn", sa.String(length=20), nullable=True))

    # Publication Details
    op.add_column("resources", sa.Column("journal", sa.String(), nullable=True))
    op.add_column("resources", sa.Column("conference", sa.String(), nullable=True))
    op.add_column("resources", sa.Column("volume", sa.String(length=50), nullable=True))
    op.add_column("resources", sa.Column("issue", sa.String(length=50), nullable=True))
    op.add_column("resources", sa.Column("pages", sa.String(length=50), nullable=True))
    op.add_column(
        "resources", sa.Column("publication_year", sa.Integer(), nullable=True)
    )

    # Funding and Support
    op.add_column("resources", sa.Column("funding_sources", sa.Text(), nullable=True))
    op.add_column("resources", sa.Column("acknowledgments", sa.Text(), nullable=True))

    # Content Structure Counts
    op.add_column(
        "resources",
        sa.Column("equation_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "resources",
        sa.Column("table_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "resources",
        sa.Column("figure_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "resources", sa.Column("reference_count", sa.Integer(), nullable=True)
    )

    # Structured Content Storage
    op.add_column("resources", sa.Column("equations", sa.Text(), nullable=True))
    op.add_column("resources", sa.Column("tables", sa.Text(), nullable=True))
    op.add_column("resources", sa.Column("figures", sa.Text(), nullable=True))

    # Metadata Quality
    op.add_column(
        "resources", sa.Column("metadata_completeness_score", sa.Float(), nullable=True)
    )
    op.add_column(
        "resources", sa.Column("extraction_confidence", sa.Float(), nullable=True)
    )
    op.add_column(
        "resources",
        sa.Column(
            "requires_manual_review", sa.Integer(), nullable=False, server_default="0"
        ),
    )

    # OCR Metadata
    op.add_column(
        "resources",
        sa.Column("is_ocr_processed", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("resources", sa.Column("ocr_confidence", sa.Float(), nullable=True))
    op.add_column(
        "resources", sa.Column("ocr_corrections_applied", sa.Integer(), nullable=True)
    )

    # Create indexes for frequently queried fields
    op.create_index("idx_resources_doi", "resources", ["doi"])
    op.create_index("idx_resources_pmid", "resources", ["pmid"])
    op.create_index("idx_resources_arxiv_id", "resources", ["arxiv_id"])
    op.create_index("idx_resources_publication_year", "resources", ["publication_year"])


def downgrade() -> None:
    """Downgrade schema - Remove Phase 6.5 scholarly metadata fields."""
    # Drop indexes
    op.drop_index("idx_resources_publication_year", table_name="resources")
    op.drop_index("idx_resources_arxiv_id", table_name="resources")
    op.drop_index("idx_resources_pmid", table_name="resources")
    op.drop_index("idx_resources_doi", table_name="resources")

    # Drop columns in reverse order
    op.drop_column("resources", "ocr_corrections_applied")
    op.drop_column("resources", "ocr_confidence")
    op.drop_column("resources", "is_ocr_processed")
    op.drop_column("resources", "requires_manual_review")
    op.drop_column("resources", "extraction_confidence")
    op.drop_column("resources", "metadata_completeness_score")
    op.drop_column("resources", "figures")
    op.drop_column("resources", "tables")
    op.drop_column("resources", "equations")
    op.drop_column("resources", "reference_count")
    op.drop_column("resources", "figure_count")
    op.drop_column("resources", "table_count")
    op.drop_column("resources", "equation_count")
    op.drop_column("resources", "acknowledgments")
    op.drop_column("resources", "funding_sources")
    op.drop_column("resources", "publication_year")
    op.drop_column("resources", "pages")
    op.drop_column("resources", "issue")
    op.drop_column("resources", "volume")
    op.drop_column("resources", "conference")
    op.drop_column("resources", "journal")
    op.drop_column("resources", "isbn")
    op.drop_column("resources", "arxiv_id")
    op.drop_column("resources", "pmid")
    op.drop_column("resources", "doi")
    op.drop_column("resources", "affiliations")
    op.drop_column("resources", "authors")
