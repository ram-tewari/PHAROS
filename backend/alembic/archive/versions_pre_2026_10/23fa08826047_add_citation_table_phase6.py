"""add_citation_table_phase6

Revision ID: 23fa08826047
Revises: 20250912_add_vector_embeddings
Create Date: 2025-11-09 19:56:29.083823

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "23fa08826047"
down_revision: Union[str, Sequence[str], None] = "20250912_add_vector_embeddings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - Add citations table for Phase 6."""
    from sqlalchemy.dialects.postgresql import UUID

    # Determine the appropriate ID type based on database dialect
    bind = op.get_bind()
    id_type = UUID(as_uuid=True) if bind.dialect.name == "postgresql" else sa.String(36)

    # Create citations table
    op.create_table(
        "citations",
        sa.Column("id", id_type, primary_key=True),
        sa.Column("source_resource_id", id_type, nullable=False),
        sa.Column("target_resource_id", id_type, nullable=True),
        sa.Column("target_url", sa.String(), nullable=False),
        sa.Column(
            "citation_type", sa.String(), nullable=False, server_default="reference"
        ),
        sa.Column("context_snippet", sa.Text(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=True),
        sa.Column("importance_score", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
        sa.ForeignKeyConstraint(
            ["source_resource_id"], ["resources.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["target_resource_id"], ["resources.id"], ondelete="SET NULL"
        ),
        sa.CheckConstraint(
            "citation_type IN ('reference', 'dataset', 'code', 'general')",
            name="ck_citation_type",
        ),
    )

    # Create indexes for performance
    op.create_index("idx_citations_source", "citations", ["source_resource_id"])
    op.create_index("idx_citations_target", "citations", ["target_resource_id"])
    op.create_index("idx_citations_url", "citations", ["target_url"])


def downgrade() -> None:
    """Downgrade schema - Remove citations table."""
    op.drop_index("idx_citations_url", table_name="citations")
    op.drop_index("idx_citations_target", table_name="citations")
    op.drop_index("idx_citations_source", table_name="citations")
    op.drop_table("citations")
