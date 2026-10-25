"""add_pgvector_hnsw_indexes

Enables the pgvector extension and adds an HNSW index on resources.embedding
for fast cosine-similarity search, plus B-tree indexes on common filter columns.

Target: reduces semantic search latency from ~7,000 ms → ~250 ms.

Revision ID: 20260410_hnsw_indexes
Revises: 20260123_community, 20260123_add_mcp_sessions
Create Date: 2026-04-10 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20260410_hnsw_indexes"
down_revision: Union[str, Sequence[str], None] = (
    "20260123_community",
    "20260123_add_mcp_sessions",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add pgvector extension and performance indexes to the resources table."""
    
    # Check if we're using PostgreSQL
    bind = op.get_bind()
    dialect_name = bind.dialect.name
    
    if dialect_name == 'postgresql':
        # Enable the pgvector extension (idempotent)
        op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

        # Check if embedding column is vector type before creating HNSW index
        # This migration might run before the pgvector conversion migration
        result = bind.execute(sa.text("""
            SELECT data_type 
            FROM information_schema.columns 
            WHERE table_name = 'resources' 
            AND column_name = 'embedding'
        """))
        row = result.fetchone()
        
        if row and row[0] == 'USER-DEFINED':  # pgvector type shows as USER-DEFINED
            # HNSW index for fast approximate nearest-neighbour search on embeddings.
            # vector_cosine_ops matches the cosine similarity used in semantic search queries.
            op.execute(
                "CREATE INDEX IF NOT EXISTS idx_resources_embedding_hnsw "
                "ON resources USING hnsw (embedding vector_cosine_ops);"
            )
        else:
            # Skip HNSW index creation - embedding column is not vector type yet
            print("Skipping HNSW index creation: embedding column is not vector type yet")
    
    # B-tree indexes for equality / range filters (work on both SQLite and PostgreSQL)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_resources_title ON resources(title);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_resources_type ON resources(type);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_resources_language ON resources(language);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_resources_quality_score ON resources(quality_score);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_resources_created_at ON resources(created_at);"
    )


def downgrade() -> None:
    """Remove all indexes added in this migration."""
    
    bind = op.get_bind()
    dialect_name = bind.dialect.name

    op.execute("DROP INDEX IF EXISTS idx_resources_created_at;")
    op.execute("DROP INDEX IF EXISTS idx_resources_quality_score;")
    op.execute("DROP INDEX IF EXISTS idx_resources_language;")
    op.execute("DROP INDEX IF EXISTS idx_resources_type;")
    op.execute("DROP INDEX IF EXISTS idx_resources_title;")
    
    if dialect_name == 'postgresql':
        op.execute("DROP INDEX IF EXISTS idx_resources_embedding_hnsw;")
        # Note: we intentionally leave the vector extension in place on downgrade
        # to avoid breaking other indexes that may depend on it.
