# Vector Search Quick Reference

**Last Updated**: April 10, 2026  
**Status**: Production Ready

---

## Quick Start

### 1. Dense Vector Search

```python
from app.modules.search.vector_search_real import RealVectorSearchService

service = RealVectorSearchService(db)

# Search with cosine distance
results = service.dense_vector_search(
    query_embedding=[0.1, 0.2, ...],  # 768-dim vector
    top_k=10,
    distance_metric="cosine"  # or "l2", "inner_product"
)

# Returns: [(resource_id, distance), ...]
```

### 2. Sparse Vector Search (SPLADE)

```python
from app.modules.search.sparse_embeddings_real import RealSPLADEService

service = RealSPLADEService(db)

# Generate sparse embedding
sparse_vec = service.generate_embedding("OAuth authentication")
# Returns: {1000: 0.847, 2000: 0.623, ...}

# Search with sparse embedding
from app.modules.search.vector_search_real import RealVectorSearchService
search_service = RealVectorSearchService(db)

results = search_service.sparse_vector_search(
    query_sparse_embedding=sparse_vec,
    top_k=10
)

# Returns: [(resource_id, score), ...]
```

### 3. Hybrid Search (Dense + Sparse)

```python
service = RealVectorSearchService(db)

results = service.hybrid_vector_search(
    query_dense_embedding=[0.1, 0.2, ...],
    query_sparse_embedding={1000: 0.8, 2000: 0.6},
    top_k=10,
    dense_weight=0.5,
    sparse_weight=0.5
)

# Returns: [(resource_id, combined_score), ...]
```

### 4. Three-Way Hybrid (Dense + Sparse + Keyword)

```python
# Get results from three strategies
dense_results = service.dense_vector_search(...)
sparse_results = service.sparse_vector_search(...)
keyword_results = [...]  # From FTS5 or tsvector

# Fuse with RRF
fused_results = service.reciprocal_rank_fusion(
    result_lists=[dense_results, sparse_results, keyword_results],
    k=60,
    top_k=10
)

# Returns: [(resource_id, rrf_score), ...]
```

---

## Distance Metrics

### Cosine Distance (`<=>`)
- Range: [0, 2]
- 0 = identical, 2 = opposite
- Best for: Normalized embeddings
- Use case: Semantic similarity

```python
results = service.dense_vector_search(
    query_embedding=embedding,
    distance_metric="cosine"
)
```

### L2 Distance (`<->`)
- Range: [0, ∞)
- 0 = identical, larger = more different
- Best for: Euclidean distance
- Use case: Spatial similarity

```python
results = service.dense_vector_search(
    query_embedding=embedding,
    distance_metric="l2"
)
```

### Inner Product (`<#>`)
- Range: (-∞, ∞)
- Negative for consistency (lower = better)
- Best for: Dot product similarity
- Use case: Magnitude-aware similarity

```python
results = service.dense_vector_search(
    query_embedding=embedding,
    distance_metric="inner_product"
)
```

---

## Filters

```python
results = service.dense_vector_search(
    query_embedding=embedding,
    top_k=10,
    filters={
        "resource_type": "code",
        "min_quality_score": 0.7,
        "language": "Python"
    }
)
```

**Available Filters:**
- `resource_type`: Filter by type (code, pdf, etc.)
- `min_quality_score`: Minimum quality threshold
- `language`: Filter by programming language

---

## Batch Operations

### Generate Sparse Embeddings for All Resources

```python
service = RealSPLADEService(db)

service.batch_update_sparse_embeddings(
    resource_ids=None,  # None = all resources
    batch_size=16,
    force_update=False  # True = regenerate existing
)
```

### Generate Sparse Embeddings for Specific Resources

```python
service.batch_update_sparse_embeddings(
    resource_ids=["uuid1", "uuid2", "uuid3"],
    batch_size=16
)
```

---

## Debugging

### Decode SPLADE Tokens

```python
service = RealSPLADEService(db)

sparse_vec = service.generate_embedding("OAuth authentication")

# Decode top tokens
tokens = service.decode_tokens(sparse_vec, top_k=10)
# Returns: [("oauth", 0.847), ("authentication", 0.623), ...]
```

### Check Vector Column Types

```sql
-- Check resources.embedding
SELECT data_type, udt_name 
FROM information_schema.columns 
WHERE table_name = 'resources' AND column_name = 'embedding';

-- Should return: USER-DEFINED, vector
```

### Verify Indexes

```sql
-- List all indexes
\di

-- Check HNSW index
SELECT * FROM pg_indexes WHERE indexname = 'idx_resources_embedding_hnsw';

-- Check IVFFlat index
SELECT * FROM pg_indexes WHERE indexname = 'idx_chunks_embedding_ivfflat';
```

---

## Performance Tips

### 1. Use Appropriate Distance Metric
- Cosine: Best for normalized embeddings (most common)
- L2: Best for unnormalized embeddings
- Inner Product: Best when magnitude matters

### 2. Tune Index Parameters

```sql
-- HNSW index (for resources)
-- m: number of connections (default: 16, higher = better recall, slower build)
-- ef_construction: build-time search depth (default: 64)
CREATE INDEX idx_resources_embedding_hnsw 
ON resources USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

-- IVFFlat index (for chunks)
-- lists: number of clusters (default: 100, rule of thumb: sqrt(rows))
CREATE INDEX idx_chunks_embedding_ivfflat 
ON document_chunks USING ivfflat (embedding vector_l2_ops)
WITH (lists = 100);
```

### 3. Use Filters to Reduce Search Space

```python
# Bad: Search all resources
results = service.dense_vector_search(query_embedding, top_k=10)

# Good: Filter first
results = service.dense_vector_search(
    query_embedding,
    top_k=10,
    filters={"resource_type": "code", "min_quality_score": 0.7}
)
```

### 4. Batch Process Embeddings

```python
# Bad: One at a time
for text in texts:
    embedding = service.generate_embedding(text)

# Good: Batch processing
embeddings = service.batch_generate_embeddings(texts, batch_size=16)
```

---

## Common Errors

### Error: "pgvector extension not found"

```bash
# Solution: Install pgvector extension
psql -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

### Error: "transformers not installed"

```bash
# Solution: Install transformers
pip install transformers torch
```

### Error: "column embedding is of type text"

```bash
# Solution: Run migration
cd backend
alembic upgrade head
```

### Error: "SPLADE model not found"

```python
# Solution: Model will download on first use (130MB)
# Or manually download:
from transformers import AutoModelForMaskedLM, AutoTokenizer
model = AutoModelForMaskedLM.from_pretrained("naver/splade-cocondenser-ensembledistil")
```

---

## Testing

### Run Integration Tests

```bash
# All vector search tests
pytest tests/integration/test_hybrid_vector_search.py -v

# Specific test
pytest tests/integration/test_hybrid_vector_search.py::TestPgvectorIntegration::test_l2_distance_ordering -v

# With coverage
pytest tests/integration/test_hybrid_vector_search.py --cov=app.modules.search
```

### Benchmark Performance

```bash
# Run performance tests
pytest tests/integration/test_hybrid_vector_search.py::TestVectorSearchPerformance -v --benchmark-only
```

---

## Migration

### Apply Migration

```bash
cd backend
alembic upgrade head
```

### Rollback Migration

```bash
alembic downgrade -1
```

### Check Migration Status

```bash
alembic current
alembic history
```

---

## SQL Examples

### Direct Vector Search

```sql
-- Cosine distance search
SELECT id, title, embedding <=> '[0.1, 0.2, ...]'::vector AS distance
FROM resources
WHERE embedding IS NOT NULL
ORDER BY distance ASC
LIMIT 10;

-- L2 distance search
SELECT id, title, embedding <-> '[0.1, 0.2, ...]'::vector AS distance
FROM resources
WHERE embedding IS NOT NULL
ORDER BY distance ASC
LIMIT 10;
```

### Sparse Vector Search

```sql
-- Find resources with overlapping tokens
WITH query_tokens AS (
    SELECT key::int as token_id, value::float as query_weight
    FROM jsonb_each_text('{"1000": 0.8, "2000": 0.6}'::jsonb)
)
SELECT r.id, r.title, 
       SUM(LEAST(qt.query_weight, (r.sparse_embedding->>(qt.token_id::text))::float)) as score
FROM resources r
CROSS JOIN query_tokens qt
WHERE r.sparse_embedding ? (qt.token_id::text)
GROUP BY r.id, r.title
ORDER BY score DESC
LIMIT 10;
```

---

## Configuration

### Environment Variables

```bash
# SPLADE model (optional, default: naver/splade-cocondenser-ensembledistil)
SPLADE_MODEL_NAME=naver/splade-cocondenser-ensembledistil

# Device for SPLADE inference (optional, default: cpu)
SPLADE_DEVICE=cpu  # or "cuda" for GPU

# Vector search defaults
VECTOR_SEARCH_TOP_K=10
VECTOR_SEARCH_DISTANCE_METRIC=cosine
```

### Database Configuration

```bash
# PostgreSQL with pgvector
DATABASE_URL=postgresql://user:pass@localhost:5432/pharos

# Minimum version: PostgreSQL 11+
# Recommended: PostgreSQL 15+
```

---

## Resources

- [pgvector Documentation](https://github.com/pgvector/pgvector)
- [SPLADE Paper](https://arxiv.org/abs/2109.10086)
- [RRF Paper](https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf)
- [Technical Summary](docs/VECTOR_RECONCILIATION_SUMMARY.md)
- [Module Manifest](docs/MODULE_MANIFEST.md)

---

**Quick Reference Version**: 1.0  
**Last Updated**: April 10, 2026  
**Status**: Production Ready
