"""
Backfill embeddings for LangChain chunks.

This script generates embeddings for all chunks that have semantic_summary
but no embedding, using the edge worker's GPU.

Usage:
    cd backend
    python scripts/backfill_chunk_embeddings.py
"""

import asyncio
import os
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app.shared.embeddings import EmbeddingService


def main():
    """Backfill embeddings for chunks."""
    
    # Connect to database
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL not set")
        return
    
    # Convert asyncpg URL to psycopg2 for sync access
    if "asyncpg" in database_url:
        database_url = database_url.replace("postgresql+asyncpg://", "postgresql://")
    
    print("Connecting to database...")
    engine = create_engine(database_url)
    Session = sessionmaker(bind=engine)
    db = Session()
    
    try:
        # Get chunks without embeddings
        print("\nFetching chunks without embeddings...")
        result = db.execute(text("""
            SELECT 
                dc.id,
                dc.semantic_summary
            FROM document_chunks dc
            JOIN resources r ON dc.resource_id = r.id
            WHERE r.source LIKE '%langchain%'
              AND dc.semantic_summary IS NOT NULL
              AND dc.embedding IS NULL
            ORDER BY dc.created_at
        """))
        
        chunks = [(row.id, row.semantic_summary) for row in result]
        print(f"Found {len(chunks)} chunks needing embeddings")
        
        if len(chunks) == 0:
            print("No chunks need embeddings!")
            return
        
        # Confirm
        response = input(f"\nGenerate embeddings for {len(chunks)} chunks? (y/n): ")
        if response.lower() != 'y':
            print("Aborted")
            return
        
        # Initialize embedding service
        print("\nInitializing embedding service (GPU)...")
        embedding_service = EmbeddingService(device="cuda")
        print("Embedding service ready")
        
        # Process chunks in batches
        batch_size = 100
        total = len(chunks)
        processed = 0
        failed = 0
        
        print(f"\nProcessing {total} chunks in batches of {batch_size}...")
        
        for i in range(0, total, batch_size):
            batch = chunks[i:i+batch_size]
            
            for chunk_id, semantic_summary in batch:
                try:
                    # Generate embedding
                    embedding = embedding_service.generate_embedding(semantic_summary)
                    
                    # Update chunk
                    db.execute(text("""
                        UPDATE document_chunks
                        SET embedding = :embedding
                        WHERE id = :chunk_id
                    """), {
                        "chunk_id": chunk_id,
                        "embedding": embedding.tolist()
                    })
                    
                    processed += 1
                    
                except Exception as e:
                    print(f"  ERROR processing chunk {chunk_id}: {e}")
                    failed += 1
            
            # Commit batch
            db.commit()
            
            # Progress
            print(f"  Progress: {processed}/{total} ({(processed/total*100):.1f}%) - Failed: {failed}")
        
        print(f"\nDone!")
        print(f"  Processed: {processed}")
        print(f"  Failed: {failed}")
        print(f"\nNow test search:")
        print(f'  curl -X POST "https://pharos-cloud-api.onrender.com/api/search/advanced" \\')
        print(f'    -H "Authorization: Bearer <REDACTED-PHAROS_ADMIN_TOKEN-rotate>" \\')
        print(f'    -H "Content-Type: application/json" \\')
        print(f'    -d \'{{"query": "message translator", "strategy": "parent-child", "top_k": 5}}\'')
        
    finally:
        db.close()


if __name__ == "__main__":
    main()
