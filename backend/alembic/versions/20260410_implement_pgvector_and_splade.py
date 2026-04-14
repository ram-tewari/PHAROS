"""Implement pgvector and SPLADE for true vector search

Revision ID: 20260410_pgvector_splade
Revises: [previous_revision]
Create Date: 2026-04-10

This migration implements true vector search capabilities:
1. Enables pgvector extension
2. Converts embedding columns from TEXT to vector(768)
3. Adds sparse_embedding columns for SPLADE (JSONB format)
4. Creates vector indexes for performance
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20260410_pgvector_splade'
down_revision = None  # Replace with actual previous revision
branch_labels = None
depends_on = None


def upgrade():
    """
    Upgrade to pgvector-based vector search (PostgreSQL only).
    For SQLite, this migration is a no-op.
    
    Steps (PostgreSQL only):
    1. Enable pgvector extension
    2. Convert resources.embedding from TEXT to vector(768)
    3. Convert document_chunks.embedding from TEXT to vector(768)
    4. Add sparse_embedding columns (JSONB) for SPLADE
    5. Create vector indexes for performance
    """
    
    # Check database dialect
    bind = op.get_bind()
    dialect_name = bind.dialect.name
    
    if dialect_name != 'postgresql':
        print(f"⚠️  Skipping pgvector migration for {dialect_name} (PostgreSQL only)")
        return
    
    # Step 1: Enable pgvector extension
    op.execute('CREATE EXTENSION IF NOT EXISTS vector;')
    
    # Step 2: Convert resources.embedding to vector(768)
    # First, add new column
    op.add_column('resources', 
                  sa.Column('embedding_vector', 
                           postgresql.ARRAY(sa.Float), 
                           nullable=True))
    
    # Migrate data: Parse TEXT JSON arrays to vector
    # Handle NULL and empty string cases
    op.execute("""
        UPDATE resources 
        SET embedding_vector = CASE 
            WHEN embedding IS NULL OR embedding = '' THEN NULL
            WHEN embedding = '[]' THEN NULL
            ELSE (
                SELECT array_agg(value::float)
                FROM json_array_elements_text(embedding::json) AS value
            )
        END
        WHERE embedding IS NOT NULL AND embedding != '';
    """)
    
    # Drop old TEXT column
    op.drop_column('resources', 'embedding')
    
    # Rename new column to embedding
    op.alter_column('resources', 'embedding_vector', new_column_name='embedding')
    
    # Cast to vector(768) type
    op.execute("""
        ALTER TABLE resources 
        ALTER COLUMN embedding TYPE vector(768) 
        USING embedding::vector(768);
    """)
    
    # Step 3: Add sparse_embedding column to resources (JSONB)
    op.add_column('resources',
                  sa.Column('sparse_embedding_jsonb', 
                           postgresql.JSONB, 
                           nullable=True))
    
    # Migrate existing sparse_embedding TEXT data to JSONB
    op.execute("""
        UPDATE resources 
        SET sparse_embedding_jsonb = CASE 
            WHEN sparse_embedding IS NULL OR sparse_embedding = '' THEN NULL
            ELSE sparse_embedding::jsonb
        END
        WHERE sparse_embedding IS NOT NULL AND sparse_embedding != '';
    """)
    
    # Drop old TEXT column
    op.drop_column('resources', 'sparse_embedding')
    
    # Rename new column
    op.alter_column('resources', 'sparse_embedding_jsonb', new_column_name='sparse_embedding')
    
    # Step 4: Handle document_chunks table
    # Check if embedding column exists (it might not based on schema)
    # Add embedding column if it doesn't exist
    op.execute("""
        DO $$ 
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name='document_chunks' AND column_name='embedding'
            ) THEN
                ALTER TABLE document_chunks ADD COLUMN embedding vector(768);
            END IF;
        END $$;
    """)
    
    # If embedding exists as TEXT, convert it
    op.execute("""
        DO $$ 
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name='document_chunks' 
                AND column_name='embedding' 
                AND data_type='text'
            ) THEN
                -- Add temporary column
                ALTER TABLE document_chunks ADD COLUMN embedding_vector float[];
                
                -- Migrate data
                UPDATE document_chunks 
                SET embedding_vector = CASE 
                    WHEN embedding IS NULL OR embedding = '' THEN NULL
                    WHEN embedding = '[]' THEN NULL
                    ELSE (
                        SELECT array_agg(value::float)
                        FROM json_array_elements_text(embedding::json) AS value
                    )
                END
                WHERE embedding IS NOT NULL AND embedding != '';
                
                -- Drop old column
                ALTER TABLE document_chunks DROP COLUMN embedding;
                
                -- Rename and cast
                ALTER TABLE document_chunks RENAME COLUMN embedding_vector TO embedding;
                ALTER TABLE document_chunks ALTER COLUMN embedding TYPE vector(768) USING embedding::vector(768);
            END IF;
        END $$;
    """)
    
    # Add sparse_embedding to document_chunks
    op.add_column('document_chunks',
                  sa.Column('sparse_embedding', 
                           postgresql.JSONB, 
                           nullable=True))
    
    # Step 5: Create vector indexes for performance
    # HNSW index for resources.embedding (cosine distance)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_resources_embedding_hnsw 
        ON resources USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64);
    """)
    
    # IVFFlat index for document_chunks.embedding (L2 distance)
    # Note: IVFFlat requires training, so we use a reasonable default
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_chunks_embedding_ivfflat 
        ON document_chunks USING ivfflat (embedding vector_l2_ops)
        WITH (lists = 100);
    """)
    
    # GIN index for sparse embeddings (JSONB)
    op.create_index('idx_resources_sparse_embedding_gin',
                    'resources',
                    ['sparse_embedding'],
                    postgresql_using='gin')
    
    op.create_index('idx_chunks_sparse_embedding_gin',
                    'document_chunks',
                    ['sparse_embedding'],
                    postgresql_using='gin')
    
    print("✅ pgvector extension enabled")
    print("✅ Dense embeddings converted to vector(768)")
    print("✅ Sparse embeddings converted to JSONB")
    print("✅ Vector indexes created")


def downgrade():
    """
    Downgrade from pgvector back to TEXT-based storage.
    
    WARNING: This is a lossy operation. Vector data will be converted to JSON text.
    """
    
    # Drop indexes
    op.drop_index('idx_chunks_sparse_embedding_gin', table_name='document_chunks')
    op.drop_index('idx_resources_sparse_embedding_gin', table_name='resources')
    op.execute('DROP INDEX IF EXISTS idx_chunks_embedding_ivfflat;')
    op.execute('DROP INDEX IF EXISTS idx_resources_embedding_hnsw;')
    
    # Convert resources.embedding back to TEXT
    op.add_column('resources',
                  sa.Column('embedding_text', sa.Text, nullable=True))
    
    op.execute("""
        UPDATE resources 
        SET embedding_text = CASE 
            WHEN embedding IS NULL THEN NULL
            ELSE embedding::text
        END;
    """)
    
    op.drop_column('resources', 'embedding')
    op.alter_column('resources', 'embedding_text', new_column_name='embedding')
    
    # Convert resources.sparse_embedding back to TEXT
    op.add_column('resources',
                  sa.Column('sparse_embedding_text', sa.Text, nullable=True))
    
    op.execute("""
        UPDATE resources 
        SET sparse_embedding_text = CASE 
            WHEN sparse_embedding IS NULL THEN NULL
            ELSE sparse_embedding::text
        END;
    """)
    
    op.drop_column('resources', 'sparse_embedding')
    op.alter_column('resources', 'sparse_embedding_text', new_column_name='sparse_embedding')
    
    # Convert document_chunks.embedding back to TEXT
    op.add_column('document_chunks',
                  sa.Column('embedding_text', sa.Text, nullable=True))
    
    op.execute("""
        UPDATE document_chunks 
        SET embedding_text = CASE 
            WHEN embedding IS NULL THEN NULL
            ELSE embedding::text
        END;
    """)
    
    op.drop_column('document_chunks', 'embedding')
    op.alter_column('document_chunks', 'embedding_text', new_column_name='embedding')
    
    # Drop sparse_embedding from chunks
    op.drop_column('document_chunks', 'sparse_embedding')
    
    # Optionally drop pgvector extension (commented out for safety)
    # op.execute('DROP EXTENSION IF EXISTS vector;')
    
    print("⚠️  Downgraded to TEXT-based embeddings (lossy operation)")
