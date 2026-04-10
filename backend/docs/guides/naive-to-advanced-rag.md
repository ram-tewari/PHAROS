# Migration Guide: Naive RAG to Advanced RAG

> **Phase 17.5** - Upgrading Your RAG Architecture

## Overview

This guide walks you through migrating from Pharos's naive RAG implementation (whole-document retrieval) to the advanced RAG architecture (chunking, graph-based retrieval, synthetic questions).

## Table of Contents

1. [Migration Overview](#migration-overview)
2. [Pre-Migration Checklist](#pre-migration-checklist)
3. [Step-by-Step Migration](#step-by-step-migration)
4. [Chunking Existing Resources](#chunking-existing-resources)
5. [Enabling Advanced Features](#enabling-advanced-features)
6. [Rollback Procedures](#rollback-procedures)
7. [Troubleshooting](#troubleshooting)

---

## Migration Overview

### What Changes?

**Before (Naive RAG)**:
```
User Query → Semantic Search → Retrieve Whole Documents → LLM Generation
```

**After (Advanced RAG)**:
```
User Query → Multiple Strategies → Retrieve Chunks + Context → LLM Generation
                ↓
    ┌───────────┴───────────┬──────────────┐
    │                       │              │
Parent-Child          GraphRAG      Question-Based
```

### New Capabilities

1. **Document Chunking**: Break documents into smaller, searchable pieces
2. **Parent-Child Retrieval**: Search chunks, return parent context
3. **GraphRAG**: Leverage knowledge graphs for relationship-aware search
4. **Synthetic Questions**: Match queries against pre-generated questions
5. **Hybrid Strategies**: Combine multiple retrieval methods

### Database Changes

**5 New Tables**:
- `document_chunks` - Chunked content with embeddings
- `graph_entities` - Extracted entities (concepts, people, methods)
- `graph_relationships` - Semantic triples (entity-relation-entity)
- `synthetic_questions` - Pre-generated questions for chunks
- `rag_evaluations` - Quality metrics and monitoring

### Backward Compatibility

✅ **Existing resources continue to work** - chunking is optional
✅ **Existing search endpoints unchanged** - new endpoints added
✅ **Existing embeddings preserved** - new embeddings for chunks
✅ **Zero downtime migration** - can be done incrementally

---

## Pre-Migration Checklist

### 1. Backup Your Database

**SQLite**:
```bash
cd backend
cp backend.db backend.db.backup_$(date +%Y%m%d_%H%M%S)
```

**PostgreSQL**:
```bash
pg_dump -U username -d neo_alexandria > backup_$(date +%Y%m%d_%H%M%S).sql
```

### 2. Check Current System State

```bash
# Check number of resources
sqlite3 backend.db "SELECT COUNT(*) FROM resources;"

# Check database size
du -h backend.db

# Check available disk space
df -h .
```

### 3. Review Configuration

```bash
# Check current settings
cat backend/.env | grep -E "(CHUNK|GRAPH|SYNTHETIC)"

# Ensure you have enough resources
# - Memory: 4GB minimum, 8GB recommended
# - Disk: 2x current database size
# - CPU: 2+ cores recommended
```

### 4. Update Dependencies

```bash
cd backend
pip install -r requirements.txt --upgrade
```

### 5. Run Tests

```bash
# Ensure existing tests pass
pytest tests/ -v

# Check for any warnings
pytest tests/ -v --tb=short
```

---

## Step-by-Step Migration

### Step 1: Run Database Migration

```bash
cd backend

# Generate migration (if not already done)
alembic revision --autogenerate -m "Add Advanced RAG Tables"

# Review migration file
cat alembic/versions/*_add_advanced_rag_tables.py

# Apply migration
alembic upgrade head

# Verify tables created
sqlite3 backend.db ".tables"
# Should see: document_chunks, graph_entities, graph_relationships, 
#             synthetic_questions, rag_evaluations
```

**Expected Output**:
```
INFO  [alembic.runtime.migration] Running upgrade -> 20260103, Add Advanced RAG Tables
INFO  [alembic.runtime.migration] Context impl SQLiteImpl.
INFO  [alembic.runtime.migration] Will assume non-transactional DDL.
```

### Step 2: Verify Migration

```bash
# Check table schemas
sqlite3 backend.db ".schema document_chunks"
sqlite3 backend.db ".schema graph_entities"
sqlite3 backend.db ".schema graph_relationships"
sqlite3 backend.db ".schema synthetic_questions"
sqlite3 backend.db ".schema rag_evaluations"

# Verify foreign keys
sqlite3 backend.db "PRAGMA foreign_key_list(document_chunks);"
```

### Step 3: Configure Advanced Features

Edit `backend/.env`:

```bash
# Chunking Configuration
CHUNK_ON_RESOURCE_CREATE=false          # Start with manual chunking
CHUNKING_STRATEGY=semantic              # or "fixed"
CHUNK_SIZE=512                          # tokens
CHUNK_OVERLAP=50                        # tokens

# Graph Extraction Configuration
GRAPH_EXTRACT_ON_CHUNK=false            # Start with manual extraction
GRAPH_EXTRACTION_METHOD=hybrid          # "llm", "spacy", or "hybrid"

# Synthetic Questions Configuration
SYNTHETIC_QUESTIONS_ENABLED=false       # Start disabled
QUESTIONS_PER_CHUNK=3
QUESTION_GENERATION_METHOD=pattern      # or "llm"

# Retrieval Configuration
DEFAULT_RETRIEVAL_STRATEGY=parent-child # or "graphrag", "hybrid"
PARENT_CHILD_CONTEXT_WINDOW=2
GRAPHRAG_MAX_HOPS=2
```

### Step 4: Restart Application

```bash
# Stop application
pkill -f "uvicorn app.main:app"

# Start with new configuration
uvicorn app.main:app --reload

# Verify startup
curl http://localhost:8000/health
```

### Step 5: Test New Endpoints

```bash
# Test chunking endpoint
curl -X POST http://localhost:8000/api/resources/{resource_id}/chunks \
  -H "Content-Type: application/json" \
  -d '{"strategy": "semantic", "chunk_size": 512, "overlap": 50}'

# Test advanced search
curl -X POST http://localhost:8000/api/search/advanced \
  -H "Content-Type: application/json" \
  -d '{"query": "test query", "strategy": "parent-child", "top_k": 5}'

# Test graph extraction
curl -X POST http://localhost:8000/api/graph/extract/{chunk_id}
```

---

## Chunking Existing Resources

### Option 1: Manual Migration Script

Use the provided migration script to chunk existing resources:

```bash
cd backend

# Run migration script
python scripts/migrate_existing_resources.py \
  --batch-size 10 \
  --strategy semantic \
  --chunk-size 512 \
  --overlap 50

# Monitor progress
tail -f logs/migration.log
```

**Script Features**:
- Processes resources in batches
- Tracks progress (processed count, success count, failure count)
- Logs errors and continues processing
- Supports resume from last processed resource
- Estimates time remaining

**Example Output**:
```
[2024-01-15 10:30:00] Starting migration...
[2024-01-15 10:30:00] Found 1,234 resources without chunks
[2024-01-15 10:30:05] Batch 1/124: Processed 10 resources (10 success, 0 failed)
[2024-01-15 10:30:10] Batch 2/124: Processed 10 resources (9 success, 1 failed)
[2024-01-15 10:30:15] Progress: 20/1234 (1.6%) - ETA: 2h 15m
...
[2024-01-15 12:45:00] Migration complete!
[2024-01-15 12:45:00] Total: 1234 resources, 1220 success, 14 failed
[2024-01-15 12:45:00] Failed resources logged to: logs/migration_failures.log
```

### Option 2: Incremental Migration

Chunk resources gradually as they're accessed:

```python
# In app/modules/resources/service.py

async def get_resource(resource_id: str, db: Session):
    resource = db.query(Resource).filter(Resource.id == resource_id).first()
    
    # Check if resource has chunks
    if not resource.chunks:
        # Chunk on-demand
        await chunk_resource_async(resource_id)
    
    return resource
```

### Option 3: Selective Migration

Chunk only high-value resources:

```bash
# Chunk resources by collection
python scripts/migrate_existing_resources.py \
  --collection-id "important-papers" \
  --strategy semantic

# Chunk resources by date
python scripts/migrate_existing_resources.py \
  --created-after "2024-01-01" \
  --strategy semantic

# Chunk resources by size
python scripts/migrate_existing_resources.py \
  --min-size 5000 \
  --strategy semantic
```

### Monitoring Migration Progress

```python
# Check migration status
GET /api/resources/migration/status

# Response
{
  "total_resources": 1234,
  "chunked_resources": 856,
  "pending_resources": 378,
  "failed_resources": 14,
  "progress_percentage": 69.4,
  "estimated_time_remaining": "45 minutes"
}
```

---

## Enabling Advanced Features

### Phase 1: Enable Chunking (Week 1)

```bash
# Update .env
CHUNK_ON_RESOURCE_CREATE=true
CHUNKING_STRATEGY=semantic
CHUNK_SIZE=512
CHUNK_OVERLAP=50

# Restart application
systemctl restart neo-alexandria

# Monitor chunking performance
tail -f logs/chunking.log
```

**Validation**:
```bash
# Check chunk creation
sqlite3 backend.db "SELECT COUNT(*) FROM document_chunks;"

# Check average chunks per resource
sqlite3 backend.db "
  SELECT AVG(chunk_count) 
  FROM (
    SELECT resource_id, COUNT(*) as chunk_count 
    FROM document_chunks 
    GROUP BY resource_id
  );
"
```

### Phase 2: Enable Parent-Child Retrieval (Week 2)

```bash
# Update .env
DEFAULT_RETRIEVAL_STRATEGY=parent-child
PARENT_CHILD_CONTEXT_WINDOW=2

# Test retrieval quality
python scripts/test_retrieval_quality.py \
  --strategy parent-child \
  --benchmark-file data/benchmark_queries.json
```

**Validation**:
```bash
# Compare retrieval metrics
python scripts/compare_retrieval_strategies.py \
  --strategies naive,parent-child \
  --queries data/test_queries.json
```

### Phase 3: Enable Graph Extraction (Week 3)

```bash
# Update .env
GRAPH_EXTRACT_ON_CHUNK=true
GRAPH_EXTRACTION_METHOD=hybrid

# Monitor graph growth
watch -n 60 'sqlite3 backend.db "
  SELECT 
    (SELECT COUNT(*) FROM graph_entities) as entities,
    (SELECT COUNT(*) FROM graph_relationships) as relationships;
"'
```

**Validation**:
```bash
# Check entity extraction quality
python scripts/validate_entity_extraction.py \
  --sample-size 100

# Check relationship quality
python scripts/validate_relationship_extraction.py \
  --sample-size 100
```

### Phase 4: Enable Synthetic Questions (Week 4)

```bash
# Update .env
SYNTHETIC_QUESTIONS_ENABLED=true
QUESTIONS_PER_CHUNK=3
QUESTION_GENERATION_METHOD=pattern

# Monitor question generation
tail -f logs/question_generation.log
```

**Validation**:
```bash
# Check question quality
python scripts/validate_synthetic_questions.py \
  --sample-size 50

# Test question-based retrieval
python scripts/test_retrieval_quality.py \
  --strategy question \
  --benchmark-file data/benchmark_queries.json
```

### Phase 5: Enable Hybrid Retrieval (Week 5)

```bash
# Update .env
DEFAULT_RETRIEVAL_STRATEGY=hybrid
HYBRID_METHODS=parent-child,graphrag,question
HYBRID_WEIGHTS=0.4,0.3,0.3

# Run comprehensive evaluation
python scripts/evaluate_rag_quality.py \
  --strategy hybrid \
  --benchmark-file data/benchmark_queries.json
```

---

## Rollback Procedures

### Rollback Database Migration

```bash
cd backend

# Rollback one migration
alembic downgrade -1

# Rollback to specific version
alembic downgrade <revision_id>

# Rollback all Advanced RAG changes
alembic downgrade <pre_advanced_rag_revision>

# Verify rollback
sqlite3 backend.db ".tables"
# Should NOT see: document_chunks, graph_entities, etc.
```

### Restore from Backup

**SQLite**:
```bash
cd backend

# Stop application
systemctl stop neo-alexandria

# Restore backup
cp backend.db.backup_20240115_103000 backend.db

# Restart application
systemctl start neo-alexandria
```

**PostgreSQL**:
```bash
# Stop application
systemctl stop neo-alexandria

# Drop database
dropdb neo_alexandria

# Restore from backup
createdb neo_alexandria
psql neo_alexandria < backup_20240115_103000.sql

# Restart application
systemctl start neo-alexandria
```

### Disable Advanced Features

```bash
# Update .env to disable all advanced features
CHUNK_ON_RESOURCE_CREATE=false
GRAPH_EXTRACT_ON_CHUNK=false
SYNTHETIC_QUESTIONS_ENABLED=false
DEFAULT_RETRIEVAL_STRATEGY=naive

# Restart application
systemctl restart neo-alexandria
```

### Partial Rollback

Keep database changes but disable features:

```bash
# Keep chunks but disable automatic chunking
CHUNK_ON_RESOURCE_CREATE=false

# Keep graph but disable automatic extraction
GRAPH_EXTRACT_ON_CHUNK=false

# Keep questions but disable generation
SYNTHETIC_QUESTIONS_ENABLED=false

# Use naive retrieval
DEFAULT_RETRIEVAL_STRATEGY=naive
```

---

## Troubleshooting

### Issue 1: Migration Fails

**Symptom**: `alembic upgrade head` fails with error

**Solutions**:

```bash
# Check current revision
alembic current

# Check migration history
alembic history

# Try manual migration
alembic upgrade head --sql > migration.sql
# Review migration.sql
sqlite3 backend.db < migration.sql

# If still failing, check logs
tail -f logs/alembic.log
```

### Issue 2: Chunking Takes Too Long

**Symptom**: Migration script runs for hours

**Solutions**:

```bash
# Reduce batch size
python scripts/migrate_existing_resources.py --batch-size 5

# Use fixed chunking (faster)
python scripts/migrate_existing_resources.py --strategy fixed

# Chunk in parallel (if multiple cores)
python scripts/migrate_existing_resources.py --parallel 4

# Chunk only small resources first
python scripts/migrate_existing_resources.py --max-size 10000
```

### Issue 3: Out of Memory

**Symptom**: Process killed during chunking

**Solutions**:

```bash
# Reduce batch size
python scripts/migrate_existing_resources.py --batch-size 1

# Disable embeddings during migration
python scripts/migrate_existing_resources.py --skip-embeddings

# Increase system memory or use swap
sudo swapon -s
sudo fallocate -l 4G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
```

### Issue 4: Foreign Key Violations

**Symptom**: Errors about foreign key constraints

**Solutions**:

```bash
# Check foreign key integrity
sqlite3 backend.db "PRAGMA foreign_key_check;"

# Disable foreign keys temporarily (SQLite only)
sqlite3 backend.db "PRAGMA foreign_keys=OFF;"

# Re-enable after fixing
sqlite3 backend.db "PRAGMA foreign_keys=ON;"

# For PostgreSQL, check constraints
psql neo_alexandria -c "
  SELECT conname, conrelid::regclass, confrelid::regclass
  FROM pg_constraint
  WHERE contype = 'f';
"
```

### Issue 5: Retrieval Quality Degraded

**Symptom**: Search results worse after migration

**Solutions**:

```bash
# Check chunk sizes
sqlite3 backend.db "
  SELECT AVG(LENGTH(content)) as avg_chunk_size
  FROM document_chunks;
"

# Adjust chunk size if too large/small
# Edit .env: CHUNK_SIZE=512

# Re-chunk problematic resources
python scripts/rechunk_resources.py \
  --resource-ids uuid-1,uuid-2,uuid-3 \
  --strategy semantic \
  --chunk-size 512

# Compare strategies
python scripts/compare_retrieval_strategies.py \
  --strategies naive,parent-child,graphrag \
  --queries data/test_queries.json
```

### Issue 6: Graph Extraction Errors

**Symptom**: Graph extraction fails or produces poor results

**Solutions**:

```bash
# Check extraction method
cat backend/.env | grep GRAPH_EXTRACTION_METHOD

# Try different method
# Edit .env: GRAPH_EXTRACTION_METHOD=spacy  # or "llm" or "hybrid"

# Check entity extraction
python scripts/validate_entity_extraction.py --sample-size 10

# Re-extract for specific chunks
python scripts/reextract_graph.py \
  --chunk-ids uuid-1,uuid-2,uuid-3 \
  --method hybrid
```

### Issue 7: Disk Space Issues

**Symptom**: Database grows too large

**Solutions**:

```bash
# Check database size
du -h backend.db

# Check table sizes
sqlite3 backend.db "
  SELECT 
    name,
    SUM(pgsize) as size_bytes
  FROM dbstat
  GROUP BY name
  ORDER BY size_bytes DESC;
"

# Vacuum database
sqlite3 backend.db "VACUUM;"

# Disable expensive features
# Edit .env:
SYNTHETIC_QUESTIONS_ENABLED=false
GRAPH_EXTRACT_ON_CHUNK=false

# Delete old evaluations
sqlite3 backend.db "
  DELETE FROM rag_evaluations
  WHERE created_at < datetime('now', '-30 days');
"
```

---

## Performance Optimization

### Chunking Performance

```bash
# Monitor chunking time
sqlite3 backend.db "
  SELECT 
    resource_id,
    COUNT(*) as chunk_count,
    MAX(created_at) - MIN(created_at) as processing_time
  FROM document_chunks
  GROUP BY resource_id
  ORDER BY processing_time DESC
  LIMIT 10;
"

# Optimize chunking strategy
# - Use fixed chunking for speed
# - Use semantic chunking for quality
# - Adjust chunk size based on content type
```

### Retrieval Performance

```bash
# Monitor retrieval latency
tail -f logs/retrieval.log | grep "latency"

# Add indexes if needed
sqlite3 backend.db "
  CREATE INDEX IF NOT EXISTS idx_chunks_resource_chunk 
  ON document_chunks(resource_id, chunk_index);
  
  CREATE INDEX IF NOT EXISTS idx_entities_name_type
  ON graph_entities(name, type);
  
  CREATE INDEX IF NOT EXISTS idx_relationships_source
  ON graph_relationships(source_entity_id);
"

# Analyze query performance
sqlite3 backend.db "EXPLAIN QUERY PLAN
  SELECT * FROM document_chunks
  WHERE resource_id = 'uuid-123'
  ORDER BY chunk_index;
"
```

### Memory Optimization

```bash
# Monitor memory usage
ps aux | grep uvicorn

# Reduce embedding cache size
# Edit .env: EMBEDDING_CACHE_SIZE=500

# Use batch processing
# Edit .env: CHUNK_BATCH_SIZE=10

# Disable features if needed
SYNTHETIC_QUESTIONS_ENABLED=false
```

---

## Post-Migration Validation

### Validation Checklist

- [ ] All database tables created successfully
- [ ] Foreign key constraints working
- [ ] Existing resources still accessible
- [ ] New chunking endpoints working
- [ ] Graph extraction working
- [ ] Advanced search working
- [ ] Evaluation endpoints working
- [ ] Performance within acceptable range
- [ ] No data loss
- [ ] Backup created and verified

### Validation Scripts

```bash
# Run full validation suite
python scripts/validate_migration.py

# Check data integrity
python scripts/check_data_integrity.py

# Run performance tests
python scripts/run_performance_tests.py

# Compare before/after metrics
python scripts/compare_metrics.py \
  --before backup_20240115_103000 \
  --after backend.db
```

---

## Related Documentation

- [Advanced RAG Guide](advanced-rag.md) - Using advanced features
- [RAG Evaluation Guide](rag-evaluation.md) - Quality monitoring
- [Database Architecture](../architecture/database.md) - Schema details
- [API Documentation](../api/search.md) - Endpoint reference

---

## Support

If you encounter issues not covered in this guide:

1. Check logs: `tail -f logs/application.log`
2. Review error messages carefully
3. Search existing issues on GitHub
4. Create a new issue with:
   - Error message
   - Steps to reproduce
   - System information
   - Relevant logs

---

## Appendix: Migration Script

### migrate_existing_resources.py

```python
#!/usr/bin/env python3
"""
Migrate existing resources to Advanced RAG architecture.

Usage:
    python scripts/migrate_existing_resources.py [options]

Options:
    --batch-size N          Process N resources at a time (default: 10)
    --strategy STRATEGY     Chunking strategy: semantic or fixed (default: semantic)
    --chunk-size N          Chunk size in tokens (default: 512)
    --overlap N             Overlap in tokens (default: 50)
    --collection-id ID      Only process resources in collection
    --created-after DATE    Only process resources created after date
    --min-size N            Only process resources with size >= N
    --max-size N            Only process resources with size <= N
    --parallel N            Use N parallel workers (default: 1)
    --skip-embeddings       Skip embedding generation (faster)
    --resume                Resume from last processed resource
    --dry-run               Show what would be done without doing it
"""

import argparse
import logging
from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session
from app.shared.database import get_db
from app.modules.resources.service import ChunkingService
from app.modules.resources.model import Resource

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(message)s',
    handlers=[
        logging.FileHandler('logs/migration.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def get_resources_to_migrate(
    db: Session,
    collection_id: Optional[str] = None,
    created_after: Optional[datetime] = None,
    min_size: Optional[int] = None,
    max_size: Optional[int] = None
) -> List[Resource]:
    """Get list of resources that need chunking."""
    query = db.query(Resource).filter(
        ~Resource.chunks.any()  # Resources without chunks
    )
    
    if collection_id:
        query = query.filter(Resource.collection_id == collection_id)
    
    if created_after:
        query = query.filter(Resource.created_at >= created_after)
    
    if min_size:
        query = query.filter(Resource.content_length >= min_size)
    
    if max_size:
        query = query.filter(Resource.content_length <= max_size)
    
    return query.all()


def migrate_resource(
    resource: Resource,
    db: Session,
    chunking_service: ChunkingService,
    skip_embeddings: bool = False
) -> bool:
    """Migrate a single resource."""
    try:
        logger.info(f"Processing resource {resource.id}: {resource.title}")
        
        # Chunk resource
        chunks = chunking_service.chunk_resource(
            resource=resource,
            generate_embeddings=not skip_embeddings
        )
        
        logger.info(f"  Created {len(chunks)} chunks")
        return True
        
    except Exception as e:
        logger.error(f"  Failed: {str(e)}")
        return False


def main():
    parser = argparse.ArgumentParser(description='Migrate existing resources')
    parser.add_argument('--batch-size', type=int, default=10)
    parser.add_argument('--strategy', choices=['semantic', 'fixed'], default='semantic')
    parser.add_argument('--chunk-size', type=int, default=512)
    parser.add_argument('--overlap', type=int, default=50)
    parser.add_argument('--collection-id', type=str)
    parser.add_argument('--created-after', type=str)
    parser.add_argument('--min-size', type=int)
    parser.add_argument('--max-size', type=int)
    parser.add_argument('--parallel', type=int, default=1)
    parser.add_argument('--skip-embeddings', action='store_true')
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--dry-run', action='store_true')
    
    args = parser.parse_args()
    
    # Get database session
    db = next(get_db())
    
    # Initialize chunking service
    chunking_service = ChunkingService(
        db=db,
        strategy=args.strategy,
        chunk_size=args.chunk_size,
        overlap=args.overlap
    )
    
    # Get resources to migrate
    created_after = datetime.fromisoformat(args.created_after) if args.created_after else None
    resources = get_resources_to_migrate(
        db=db,
        collection_id=args.collection_id,
        created_after=created_after,
        min_size=args.min_size,
        max_size=args.max_size
    )
    
    logger.info(f"Found {len(resources)} resources to migrate")
    
    if args.dry_run:
        logger.info("Dry run - no changes will be made")
        for resource in resources[:10]:
            logger.info(f"  Would process: {resource.id} - {resource.title}")
        return
    
    # Process resources in batches
    success_count = 0
    failure_count = 0
    
    for i in range(0, len(resources), args.batch_size):
        batch = resources[i:i + args.batch_size]
        batch_num = i // args.batch_size + 1
        total_batches = (len(resources) + args.batch_size - 1) // args.batch_size
        
        logger.info(f"Batch {batch_num}/{total_batches}: Processing {len(batch)} resources")
        
        for resource in batch:
            if migrate_resource(resource, db, chunking_service, args.skip_embeddings):
                success_count += 1
            else:
                failure_count += 1
        
        # Commit batch
        db.commit()
        
        # Progress update
        progress = (i + len(batch)) / len(resources) * 100
        logger.info(f"Progress: {i + len(batch)}/{len(resources)} ({progress:.1f}%)")
    
    logger.info("Migration complete!")
    logger.info(f"Total: {len(resources)} resources, {success_count} success, {failure_count} failed")


if __name__ == '__main__':
    main()
```
