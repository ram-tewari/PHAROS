# Search API

Search endpoints for hybrid search combining keyword, semantic, and sparse retrieval methods.

## Overview

The Search API provides state-of-the-art search functionality combining multiple retrieval methods:
- **FTS5**: Full-text search with SQLite FTS5 or PostgreSQL tsvector
- **Dense vectors**: Semantic similarity using transformer embeddings
- **Sparse vectors**: Learned keyword importance using SPLADE
- **Three-way hybrid**: RRF fusion of all three methods with adaptive weighting
- **Reranking**: Optional ColBERT cross-encoder reranking

## Endpoints

### POST /search

Execute standard search with FTS5, filters, and pagination.

**Request Body:**
```json
{
  "text": "machine learning",
  "limit": 20,
  "offset": 0,
  "hybrid_weight": 0.5,
  "filters": {
    "classification_code": "004",
    "type": "article",
    "language": "en",
    "min_quality": 0.7
  }
}
```

**Response:**
```json
{
  "total": 42,
  "items": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "title": "Machine Learning Fundamentals",
      "description": "Comprehensive guide to ML concepts",
      "creator": "John Doe",
      "type": "article",
      "quality_score": 0.85,
      "created_at": "2024-01-01T10:00:00Z"
    }
  ],
  "facets": {
    "type": {"article": 30, "paper": 12},
    "language": {"en": 40, "es": 2}
  },
  "snippets": {
    "550e8400-e29b-41d4-a716-446655440000": "...machine learning algorithms..."
  }
}
```

**Example:**
```bash
curl -X POST http://127.0.0.1:8000/search \
  -H "Content-Type: application/json" \
  -d '{
    "text": "machine learning",
    "limit": 10,
    "filters": {
      "min_quality": 0.7
    }
  }'
```

---

### GET /search/three-way-hybrid

Execute three-way hybrid search combining FTS5, dense vectors, and sparse vectors.

This endpoint implements state-of-the-art search by:
1. Executing three retrieval methods in parallel (FTS5, dense, sparse)
2. Merging results using Reciprocal Rank Fusion (RRF)
3. Applying query-adaptive weighting based on query characteristics
4. Optionally reranking top results using ColBERT cross-encoder

**Query Parameters:**

| Parameter | Type | Description | Default |
|-----------|------|-------------|---------|
| `query` | string | Search query text (required) | - |
| `limit` | integer | Number of results (1-100) | 20 |
| `offset` | integer | Pagination offset | 0 |
| `enable_reranking` | boolean | Apply ColBERT reranking | true |
| `adaptive_weighting` | boolean | Use query-adaptive RRF weights | true |
| `hybrid_weight` | float | Fusion weight for compatibility (0.0-1.0) | - |

**Response:**
```json
{
  "total": 42,
  "items": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "title": "Machine Learning Fundamentals",
      "description": "Comprehensive guide to ML concepts",
      "creator": "John Doe",
      "type": "article",
      "quality_score": 0.85,
      "created_at": "2024-01-01T10:00:00Z"
    }
  ],
  "facets": {
    "type": {"article": 30, "paper": 12}
  },
  "snippets": {
    "550e8400-e29b-41d4-a716-446655440000": "...machine learning algorithms..."
  },
  "latency_ms": 245.3,
  "method_contributions": {
    "fts5": 8,
    "dense": 12,
    "sparse": 10
  },
  "weights_used": [0.3, 0.5, 0.2]
}
```

**Example:**
```bash
curl "http://127.0.0.1:8000/search/three-way-hybrid?query=machine+learning&limit=10&enable_reranking=true"
```

---

### GET /search/compare-methods

Compare different search methods side-by-side for debugging and analysis.

Executes all available search methods:
- FTS5 only (keyword matching)
- Dense only (semantic similarity)
- Sparse only (learned keyword importance)
- Two-way hybrid (FTS5 + dense)
- Three-way hybrid (FTS5 + dense + sparse with RRF)
- Three-way with reranking (+ ColBERT reranking)

**Query Parameters:**

| Parameter | Type | Description | Default |
|-----------|------|-------------|---------|
| `query` | string | Search query text (required) | - |
| `limit` | integer | Number of results per method (1-100) | 20 |

**Response:**
```json
{
  "query": "machine learning",
  "methods": {
    "fts5_only": {
      "results": [...],
      "latency_ms": 45.2,
      "total": 42
    },
    "dense_only": {
      "results": [...],
      "latency_ms": 120.5,
      "total": 38
    },
    "sparse_only": {
      "results": [...],
      "latency_ms": 95.3,
      "total": 35
    },
    "two_way_hybrid": {
      "results": [...],
      "latency_ms": 165.8,
      "total": 45
    },
    "three_way_hybrid": {
      "results": [...],
      "latency_ms": 210.4,
      "total": 48
    },
    "three_way_reranked": {
      "results": [...],
      "latency_ms": 285.7,
      "total": 48
    }
  }
}
```

**Example:**
```bash
curl "http://127.0.0.1:8000/search/compare-methods?query=machine+learning&limit=10"
```

---

### POST /search/evaluate

Evaluate search quality using information retrieval metrics.

Accepts a query and relevance judgments (ground truth) and computes:
- nDCG@20: Normalized Discounted Cumulative Gain
- Recall@20: Proportion of relevant documents retrieved
- Precision@20: Proportion of retrieved documents that are relevant
- MRR: Mean Reciprocal Rank (position of first relevant result)

**Request Body:**
```json
{
  "query": "machine learning",
  "relevance_judgments": {
    "550e8400-e29b-41d4-a716-446655440000": 3,
    "660e8400-e29b-41d4-a716-446655440001": 2,
    "770e8400-e29b-41d4-a716-446655440002": 1,
    "880e8400-e29b-41d4-a716-446655440003": 0
  }
}
```

**Relevance Scale:**
- 0: Not relevant
- 1: Marginally relevant
- 2: Relevant
- 3: Highly relevant

**Response:**
```json
{
  "query": "machine learning",
  "metrics": {
    "ndcg_at_20": 0.87,
    "recall_at_20": 0.75,
    "precision_at_20": 0.65,
    "mrr": 0.92
  },
  "baseline_comparison": {
    "two_way_ndcg": 0.82,
    "improvement": 0.061
  }
}
```

**Example:**
```bash
curl -X POST http://127.0.0.1:8000/search/evaluate \
  -H "Content-Type: application/json" \
  -d '{
    "query": "machine learning",
    "relevance_judgments": {
      "550e8400-e29b-41d4-a716-446655440000": 3,
      "660e8400-e29b-41d4-a716-446655440001": 2
    }
  }'
```

---

### POST /search/advanced

**Phase 17.5** - Execute advanced search with multiple retrieval strategies.

This endpoint provides access to advanced RAG retrieval strategies:
- **parent-child**: Search at chunk level, return parent resources with context
- **graphrag**: Leverage knowledge graph for relationship-aware search
- **hybrid**: Combine multiple strategies with weighted fusion

**Request Body:**
```json
{
  "query": "What is gradient descent?",
  "strategy": "parent-child",
  "top_k": 5,
  "context_window": 2,
  "relation_types": ["EXTENDS", "SUPPORTS"]
}
```

**Parameters:**
- `query` (required): Search query text
- `strategy` (required): Retrieval strategy - `parent-child`, `graphrag`, or `hybrid`
- `top_k` (optional): Number of results to return (default: 5)
- `context_window` (optional): Number of surrounding chunks for parent-child (default: 2)
- `relation_types` (optional): Relationship types for GraphRAG (default: all)
- `include_code` (optional, default `false`): Fetch and attach source code to each result chunk. Local chunks use stored content; remote (GitHub) chunks are fetched on demand and cached in Redis for 1 hour. Adds `code`, `source`, and `cache_hit` fields to each chunk plus a top-level `code_metrics` object.

**Request Body (with code attachment):**
```json
{
  "query": "hash map implementation",
  "strategy": "parent-child",
  "top_k": 5,
  "include_code": true
}
```

**Response (Parent-Child Strategy):**
```json
{
  "query": "What is gradient descent?",
  "strategy": "parent-child",
  "results": [
    {
      "chunk": {
        "id": "chunk-uuid-1",
        "resource_id": "550e8400-e29b-41d4-a716-446655440000",
        "content": "Gradient descent is an iterative optimization algorithm...",
        "chunk_index": 5
      },
      "parent_resource": {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "title": "Introduction to Machine Learning"
      },
      "surrounding_chunks": [
        {
          "chunk_index": 4,
          "content": "...optimization algorithms are fundamental..."
        },
        {
          "chunk_index": 6,
          "content": "...converges to a local minimum..."
        }
      ],
      "score": 0.92
    }
  ],
  "total": 5,
  "latency_ms": 185.3
}
```

**Response (with `include_code=true`):**
```json
{
  "query": "hash map implementation",
  "strategy": "parent-child",
  "results": [
    {
      "chunk": {
        "id": "chunk-uuid-1",
        "resource_id": "550e8400-e29b-41d4-a716-446655440000",
        "content": "",
        "chunk_index": 12,
        "code": "def __init__(self):\n    self.table = [None] * 256\n",
        "source": "github",
        "cache_hit": false
      },
      "parent_resource": { "id": "550e8400-e29b-41d4-a716-446655440000", "title": "HashMap" },
      "score": 0.94
    }
  ],
  "total": 5,
  "latency_ms": 342.1,
  "code_metrics": {
    "total_chunks": 5,
    "local_chunks": 2,
    "remote_chunks": 3,
    "fetched_ok": 3,
    "fetch_errors": 0,
    "cache_hits": 1,
    "total_latency_ms": 154.7
  }
}
```

**Response (GraphRAG Strategy):**
```json
{
  "query": "gradient descent optimization",
  "strategy": "graphrag",
  "results": [
    {
      "chunk": {
        "id": "chunk-uuid-1",
        "content": "Stochastic Gradient Descent (SGD) extends gradient descent..."
      },
      "parent_resource": {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "title": "Introduction to Machine Learning"
      },
      "graph_path": [
        {
          "entity_name": "Gradient Descent",
          "relation_type": "EXTENDS",
          "entity_name": "Stochastic Gradient Descent",
          "weight": 0.9
        }
      ],
      "score": 0.88
    }
  ],
  "total": 5,
  "latency_ms": 425.7
}
```

**Example (Parent-Child):**
```bash
curl -X POST http://127.0.0.1:8000/search/advanced \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What is gradient descent?",
    "strategy": "parent-child",
    "top_k": 5,
    "context_window": 2
  }'
```

**Example (GraphRAG):**
```bash
curl -X POST http://127.0.0.1:8000/search/advanced \
  -H "Content-Type: application/json" \
  -d '{
    "query": "gradient descent optimization",
    "strategy": "graphrag",
    "relation_types": ["EXTENDS", "SUPPORTS"]
  }'
```

---

### POST /admin/sparse-embeddings/generate

Queue batch generation of sparse embeddings for existing resources.

This endpoint initiates a background task to generate sparse embeddings for:
- Specific resources (if resource_ids provided)
- All resources without sparse embeddings (if resource_ids is None)

**Request Body:**
```json
{
  "resource_ids": [
    "550e8400-e29b-41d4-a716-446655440000",
    "660e8400-e29b-41d4-a716-446655440001"
  ],
  "batch_size": 32
}
```

**Response:**
```json
{
  "status": "completed",
  "job_id": "990e8400-e29b-41d4-a716-446655440010",
  "estimated_duration_minutes": 5,
  "resources_to_process": 120
}
```

**Example:**
```bash
curl -X POST http://127.0.0.1:8000/admin/sparse-embeddings/generate \
  -H "Content-Type: application/json" \
  -d '{
    "batch_size": 32
  }'
```

---

### GET /search/health

Health check endpoint for Search module.

**Response:**
```json
{
  "status": "healthy",
  "module": {
    "name": "search",
    "version": "1.0.0",
    "domain": "search"
  },
  "database": {
    "healthy": true,
    "message": "Database connection healthy"
  },
  "services": {
    "search_service": {
      "available": true,
      "message": "Search service available"
    }
  },
  "event_handlers": {
    "registered": false,
    "count": 0,
    "events": []
  },
  "timestamp": "2024-01-01T10:00:00Z"
}
```

## Data Models

### Search Query Model

```json
{
  "text": "string (required)",
  "limit": "integer (1-100, default: 20)",
  "offset": "integer (default: 0)",
  "hybrid_weight": "float (0.0-1.0, optional)",
  "filters": {
    "classification_code": "string (optional)",
    "type": "string (optional)",
    "language": "string (optional)",
    "min_quality": "float (0.0-1.0, optional)",
    "created_from": "datetime (optional)",
    "created_to": "datetime (optional)"
  }
}
```

## Module Structure

The Search module is implemented as a self-contained vertical slice:

**Module**: `app.modules.search`  
**Router Prefix**: `/search`  
**Version**: 1.0.0

```python
from app.modules.search import (
    router,
    SearchQuery,
    SearchResults,
    ThreeWayHybridResults
)
```

### Events

**Emitted Events:**
- None (Search is a read-only module)

**Subscribed Events:**
- `resource.created` - Indexes new resources for search
- `resource.updated` - Updates search index
- `resource.deleted` - Removes from search index

## Performance Targets

- **Standard search**: < 200ms (P95)
- **Three-way hybrid**: < 500ms (P95)
- **With reranking**: < 1000ms (P95)
- **Batch embedding generation**: ~60 resources/minute

## Related Documentation

- [Resources API](resources.md) - Resource management
- [Collections API](collections.md) - Collection management
- [Architecture: Modules](../architecture/modules.md) - Module architecture
- [Architecture: Events](../architecture/events.md) - Event system
- [API Overview](overview.md) - Authentication, errors, pagination
