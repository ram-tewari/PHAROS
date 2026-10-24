"""
Neo Alexandria 2.0 - Vector Embeddings Migration (Phase 4)

This migration adds vector embedding storage to the resources table for Phase 4's
semantic search capabilities. It supports cross-database compatibility using JSON
columns that work with both SQLite and PostgreSQL.

Related files:
- app/services/ai_core.py: Generates embeddings during ingestion
- app/services/hybrid_search_methods.py: Uses embeddings for vector search
- app/database/models.py: Resource model with embedding field

Features:
- JSON column for cross-database compatibility (SQLite/PostgreSQL)
- Default empty array for backward compatibility
- Supports vector embeddings from sentence-transformers models
- Enables semantic search and hybrid search functionality

Revision ID: 20250912_add_vector_embeddings
Revises: 20250912_add_classification_codes
Create Date: 2025-09-12 14:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "20250912_add_vector_embeddings"
down_revision = "20250912_add_classification_codes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Get bind to check database type
    bind = op.get_bind()

    if bind.dialect.name == "postgresql":
        # PostgreSQL: Use ARRAY(Float) for native array support
        op.add_column(
            "resources",
            sa.Column(
                "embedding",
                postgresql.ARRAY(sa.Float),
                nullable=True,
                server_default="{}",
            ),
        )
    else:
        # SQLite and others: Use JSON column for cross-database compatibility
        op.add_column(
            "resources",
            sa.Column("embedding", sa.JSON, nullable=True, server_default="[]"),
        )


def downgrade() -> None:
    op.drop_column("resources", "embedding")
