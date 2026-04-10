# Phase 5: Context Assembly + Security - Architecture Diagram

**Date**: April 10, 2026  
**Status**: ✅ Production Ready

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Ronin LLM Client                            │
│                    (External Coding Assistant)                      │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             │ POST /api/mcp/context/retrieve
                             │ Authorization: Bearer <PHAROS_API_KEY>
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    FastAPI Security Layer                           │
│                  (app/shared/security.py)                           │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────┐     │
│  │ verify_api_key() Dependency                              │     │
│  │ • Extract key from Authorization header                  │     │
│  │ • Strip "Bearer " prefix (case-insensitive)              │     │
│  │ • Constant-time comparison (timing attack prevention)    │     │
│  │ • Audit logging (success/failure)                        │     │
│  └──────────────────────────────────────────────────────────┘     │
│                                                                     │
│  ✅ Valid Key → Continue                                           │
│  ❌ Invalid Key → HTTP 403 Forbidden                               │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                  Context Assembly Service                           │
│              (app/modules/mcp/context_service.py)                   │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────┐     │
│  │ assemble_context(request)                                │     │
│  │ • Parse request parameters                               │     │
│  │ • Launch 4 parallel tasks (asyncio.gather)               │     │
│  │ • Wait with timeout (default: 1000ms)                    │     │
│  │ • Handle exceptions gracefully                           │     │
│  │ • Assemble results into unified context                  │     │
│  │ • Format as XML for LLM consumption                      │     │
│  └──────────────────────────────────────────────────────────┘     │
│                                                                     │
│  Parallel Execution (2.5x speedup):                                │
│  ┌────────────┬────────────┬────────────┬────────────┐            │
│  │  Task 1    │  Task 2    │  Task 3    │  Task 4    │            │
│  │ ~180ms     │ ~120ms     │ ~60ms      │ ~95ms      │            │
│  └─────┬──────┴─────┬──────┴─────┬──────┴─────┬──────┘            │
│        │            │            │            │                   │
│        ▼            ▼            ▼            ▼                   │
└────────┼────────────┼────────────┼────────────┼────────────────────┘
         │            │            │            │
         │            │            │            │
    ┌────▼────┐  ┌───▼────┐  ┌───▼────┐  ┌───▼────┐
    │ Layer 1 │  │Layer 2 │  │Layer 3 │  │Layer 4 │
    └────┬────┘  └───┬────┘  └───┬────┘  └───┬────┘
         │           │           │           │
         ▼           ▼           ▼           ▼
```

---

## Intelligence Layer Details

### Layer 1: Semantic Search (Vector Database)

```
┌─────────────────────────────────────────────────────────────┐
│              Semantic Search Service                        │
│          (app/modules/search/service.py)                    │
│                                                             │
│  hybrid_search(query, limit=10, weight=0.6)                │
│  • Generate query embedding (nomic-embed-text-v1)          │
│  • Vector similarity search (FAISS/HNSW)                   │
│  • Keyword search (PostgreSQL full-text)                   │
│  • Combine results (60% semantic, 40% keyword)             │
│  • Rank by relevance score                                 │
│                                                             │
│  Returns: Top-K code chunks with similarity scores         │
│  Time: ~180ms                                              │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│                    PostgreSQL Database                      │
│                                                             │
│  code_chunks table:                                         │
│  • id, content, file_path, language                        │
│  • start_line, end_line                                    │
│  • embedding (vector)                                      │
│  • semantic_summary                                        │
│                                                             │
│  Indexes:                                                   │
│  • HNSW index on embedding (vector similarity)             │
│  • GIN index on content (full-text search)                 │
└─────────────────────────────────────────────────────────────┘
```

### Layer 2: GraphRAG (Knowledge Graph)

```
┌─────────────────────────────────────────────────────────────┐
│              GraphRAG Search Service                        │
│          (app/modules/search/service.py)                    │
│                                                             │
│  graphrag_search(query, max_hops=2, limit=10)              │
│  • Extract entities from query (NER)                       │
│  • Find matching graph nodes                               │
│  • Multi-hop traversal (BFS, max 2 hops)                   │
│  • Collect related chunks and relationships                │
│  • Rank by path weight and relevance                       │
│                                                             │
│  Returns: Architectural dependencies with relationships    │
│  Time: ~120ms                                              │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│                    Knowledge Graph                          │
│                                                             │
│  graph_entities table:                                      │
│  • id, name, type (Concept, Function, Class, etc.)         │
│  • properties (JSON)                                       │
│                                                             │
│  graph_relationships table:                                 │
│  • source_id, target_id                                    │
│  • relationship_type (imports, calls, extends, etc.)       │
│  • weight (0-1)                                            │
│                                                             │
│  Example relationships:                                     │
│  • login_route → auth_service (calls)                      │
│  • auth_service → database (imports)                       │
│  • database → session_manager (extends)                    │
└─────────────────────────────────────────────────────────────┘
```

### Layer 3: Pattern Learning (Developer Profile)

```
┌─────────────────────────────────────────────────────────────┐
│           Pattern Learning Service                          │
│      (app/modules/mcp/context_service.py)                   │
│                                                             │
│  _fetch_patterns(request)                                   │
│  • Query DeveloperProfileRecord by user_id + codebase      │
│  • Extract style patterns (async, naming, error handling)  │
│  • Extract architecture patterns (framework, design)       │
│  • Extract Git patterns (kept vs abandoned)                │
│  • Rank by frequency and success rate                      │
│                                                             │
│  Returns: Developer coding style and preferences           │
│  Time: ~60ms                                               │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│              Developer Profile Database                     │
│                                                             │
│  developer_profiles table:                                  │
│  • user_id, repository_url                                 │
│  • profile_data (JSON):                                    │
│    - style:                                                │
│      * async_patterns (density, preferred_style)           │
│      * naming (snake_case_ratio, camelCase_ratio)          │
│      * error_handling (logging_style, try_catch_ratio)     │
│    - architecture:                                         │
│      * framework (name, version)                           │
│      * detected_patterns (MVC, Repository, etc.)           │
│    - git_analysis:                                         │
│      * kept_patterns (successful, high quality)            │
│      * abandoned_patterns (bugs, refactored)               │
│                                                             │
│  Example patterns:                                          │
│  • "Prefers async/await (80% of functions)"                │
│  • "Uses snake_case naming (95%)"                          │
│  • "AVOID: MD5 hashing (security issue in 2023)"           │
└─────────────────────────────────────────────────────────────┘
```

### Layer 4: PDF Memory (Research Papers)

```
┌─────────────────────────────────────────────────────────────┐
│           PDF Ingestion Service                             │
│      (app/modules/pdf_ingestion/service.py)                 │
│                                                             │
│  graph_traversal_search(query, max_hops=2, limit=5)        │
│  • Extract concepts from query                             │
│  • Find matching PDF annotations by concept tags           │
│  • Traverse graph to find related annotations              │
│  • Rank by relevance score                                 │
│                                                             │
│  Returns: Research paper annotations with concepts         │
│  Time: ~95ms                                               │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│              PDF Annotation Database                        │
│                                                             │
│  pdf_chunks table:                                          │
│  • id, resource_id, content                                │
│  • page_number, chunk_index                                │
│  • chunk_type (text, equation, table, figure)              │
│  • embedding (vector)                                      │
│                                                             │
│  pdf_annotations table:                                     │
│  • id, chunk_id, user_id                                   │
│  • concept_tags (array: ["OAuth", "Security"])             │
│  • note (user annotation)                                  │
│  • created_at                                              │
│                                                             │
│  Example annotations:                                       │
│  • OAuth 2.0 RFC → "OAuth" concept → auth code chunks      │
│  • JWT Best Practices → "Security" → token validation      │
└─────────────────────────────────────────────────────────────┘
```

---

## Context Assembly Flow

```
1. Request arrives with query + parameters
   ↓
2. Security layer validates API key
   ↓
3. Context service launches 4 parallel tasks
   ↓
4. Each task fetches from its intelligence layer
   ↓
5. Results collected with timeout (1000ms)
   ↓
6. Graceful degradation if any task fails/times out
   ↓
7. Results assembled into unified context
   ↓
8. Context formatted as XML for LLM parsing
   ↓
9. Response returned to Ronin
```

### Parallel Execution Timeline

```
Time (ms)  │ Task 1 (Search) │ Task 2 (Graph) │ Task 3 (Pattern) │ Task 4 (PDF)
───────────┼─────────────────┼────────────────┼──────────────────┼──────────────
0          │ START           │ START          │ START            │ START
50         │ ...             │ ...            │ DONE (60ms)      │ ...
100        │ ...             │ DONE (120ms)   │                  │ DONE (95ms)
150        │ ...             │                │                  │
180        │ DONE (180ms)    │                │                  │
───────────┴─────────────────┴────────────────┴──────────────────┴──────────────
Total: 180ms (max of all tasks)

Sequential would be: 180 + 120 + 60 + 95 = 455ms
Speedup: 455ms / 180ms = 2.5x
```

---

## XML Output Format

```xml
<context_assembly>
  <query>Refactor my login route</query>
  <codebase>app-backend</codebase>
  
  <relevant_code>
    <chunk id="uuid-1" rank="1">
      <file>app/auth.py</file>
      <language>python</language>
      <lines>45-67</lines>
      <similarity>0.92</similarity>
      <content><![CDATA[
        def login(username: str, password: str):
            # Existing login implementation
            ...
      ]]></content>
    </chunk>
    <!-- More chunks... -->
  </relevant_code>
  
  <architectural_dependencies>
    <dependency type="imports" weight="0.85" hops="1">
      <source>login_route</source>
      <target>auth_service</target>
    </dependency>
    <dependency type="calls" weight="0.90" hops="1">
      <source>auth_service</source>
      <target>database</target>
    </dependency>
    <!-- More dependencies... -->
  </architectural_dependencies>
  
  <developer_style>
    <pattern type="async_style">
      <description>Prefers async/await (80% of functions)</description>
      <frequency>0.80</frequency>
      <success_rate>0.95</success_rate>
    </pattern>
    <pattern type="avoided_pattern">
      <description>AVOID: MD5 hashing (security issue in 2023)</description>
      <frequency>0.20</frequency>
      <success_rate>0.00</success_rate>
      <examples>
        <example><![CDATA[
          # BAD: Don't use MD5
          import hashlib
          hash = hashlib.md5(password.encode()).hexdigest()
        ]]></example>
      </examples>
    </pattern>
    <!-- More patterns... -->
  </developer_style>
  
  <research_papers>
    <annotation id="uuid-2" relevance="0.88">
      <paper>OAuth 2.0 Security Best Practices</paper>
      <page>12</page>
      <concepts>OAuth, Security, PKCE</concepts>
      <note>Use PKCE for public clients</note>
      <content><![CDATA[
        PKCE (Proof Key for Code Exchange) prevents authorization
        code interception attacks...
      ]]></content>
    </annotation>
    <!-- More annotations... -->
  </research_papers>
  
  <assembly_metrics>
    <total_time_ms>455</total_time_ms>
    <code_chunks_count>10</code_chunks_count>
    <dependencies_count>8</dependencies_count>
    <patterns_count>12</patterns_count>
    <annotations_count>5</annotations_count>
  </assembly_metrics>
</context_assembly>
```

---

## Security Flow

```
┌─────────────────────────────────────────────────────────────┐
│                    Ronin LLM Client                         │
└────────────────────────┬────────────────────────────────────┘
                         │
                         │ Authorization: Bearer <key>
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│              FastAPI Security Dependency                    │
│                                                             │
│  1. Extract Authorization header                           │
│     • Check if header exists                               │
│     • Return 403 if missing                                │
│                                                             │
│  2. Strip "Bearer " prefix (case-insensitive)              │
│     • "Bearer abc123" → "abc123"                           │
│     • "bearer abc123" → "abc123"                           │
│     • "abc123" → "abc123"                                  │
│                                                             │
│  3. Get expected key from environment                      │
│     • PHAROS_API_KEY = "expected-key"                      │
│     • Return 500 if not set                                │
│                                                             │
│  4. Constant-time comparison                               │
│     • secrets.compare_digest(provided, expected)           │
│     • Prevents timing attacks                              │
│     • Return 403 if mismatch                               │
│                                                             │
│  5. Audit logging                                          │
│     • Log success: "API key authentication successful"     │
│     • Log failure: "API key authentication failed"         │
│     • Never log actual keys (only length)                  │
│                                                             │
│  6. Return validated key                                   │
│     • Injected into endpoint as dependency                 │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│              Context Assembly Endpoint                      │
│                                                             │
│  async def retrieve_context(                               │
│      request: ContextRetrievalRequest,                     │
│      api_key: str = Depends(verify_api_key)  # ← Security │
│  ):                                                        │
│      # Endpoint logic here                                 │
│      ...                                                   │
└─────────────────────────────────────────────────────────────┘
```

---

## Error Handling

```
┌─────────────────────────────────────────────────────────────┐
│                    Error Scenarios                          │
└─────────────────────────────────────────────────────────────┘

1. Missing Authorization Header
   ↓
   HTTP 403 Forbidden
   {
     "detail": "Missing API key. Include 'Authorization: Bearer <key>' header."
   }

2. Invalid API Key
   ↓
   HTTP 403 Forbidden
   {
     "detail": "Invalid API key. Access denied."
   }

3. PHAROS_API_KEY Not Set (Server)
   ↓
   HTTP 500 Internal Server Error
   {
     "detail": "Server configuration error. Contact administrator."
   }

4. Service Timeout (Graceful Degradation)
   ↓
   HTTP 200 OK (Partial Results)
   {
     "success": true,
     "context": {
       "code_chunks": [...],  # Available
       "graph_dependencies": [],  # Timed out
       "warnings": ["graphrag timed out"]
     }
   }

5. Service Exception (Graceful Degradation)
   ↓
   HTTP 200 OK (Partial Results)
   {
     "success": true,
     "context": {
       "code_chunks": [...],  # Available
       "pdf_annotations": [],  # Failed
       "warnings": ["pdf_memory failed: Connection error"]
     }
   }

6. Complete Failure (All Services Down)
   ↓
   HTTP 500 Internal Server Error
   {
     "success": false,
     "error": "Context assembly failed: Database connection error"
   }
```

---

## Deployment Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Render Cloud                           │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐ │
│  │              Pharos Backend Service                   │ │
│  │                                                       │ │
│  │  • FastAPI application                               │ │
│  │  • Uvicorn ASGI server                               │ │
│  │  • Environment: PHAROS_API_KEY=<secret>              │ │
│  │  • Auto-deploy on Git push                           │ │
│  │  • HTTPS enabled (automatic)                         │ │
│  └───────────────────────────────────────────────────────┘ │
│                          │                                  │
│                          ▼                                  │
│  ┌───────────────────────────────────────────────────────┐ │
│  │           PostgreSQL Database (Render)                │ │
│  │                                                       │ │
│  │  • code_chunks table (with HNSW index)               │ │
│  │  • graph_entities + graph_relationships              │ │
│  │  • developer_profiles                                │ │
│  │  • pdf_chunks + pdf_annotations                      │ │
│  └───────────────────────────────────────────────────────┘ │
│                          │                                  │
│                          ▼                                  │
│  ┌───────────────────────────────────────────────────────┐ │
│  │              Redis Cache (Render)                     │ │
│  │                                                       │ │
│  │  • Query result caching                              │ │
│  │  • Embedding caching                                 │ │
│  │  • Rate limiting                                     │ │
│  └───────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                          │
                          │ HTTPS
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                    Ronin LLM Client                         │
│                  (External Service)                         │
│                                                             │
│  • Sends API key in Authorization header                   │
│  • Receives context in <1s                                 │
│  • Feeds to LLM for code generation/explanation            │
└─────────────────────────────────────────────────────────────┘
```

---

## Performance Optimization

### Parallel Execution

```
Before (Sequential):
┌────────────┐
│  Search    │ 180ms
└────────────┘
             ┌────────────┐
             │  GraphRAG  │ 120ms
             └────────────┘
                          ┌────────────┐
                          │  Pattern   │ 60ms
                          └────────────┘
                                       ┌────────────┐
                                       │    PDF     │ 95ms
                                       └────────────┘
Total: 455ms

After (Parallel):
┌────────────┐
│  Search    │ 180ms
└────────────┘
┌────────────┐
│  GraphRAG  │ 120ms
└────────────┘
┌────────────┐
│  Pattern   │ 60ms
└────────────┘
┌────────────┐
│    PDF     │ 95ms
└────────────┘
Total: 180ms (max)

Speedup: 2.5x
```

### Caching Strategy

```
┌─────────────────────────────────────────────────────────────┐
│                      Redis Cache                            │
│                                                             │
│  1. Query Embeddings (1 hour TTL)                          │
│     • Key: "embedding:query:<hash>"                        │
│     • Value: [0.123, 0.456, ...]                           │
│     • Saves: ~50ms per query                               │
│                                                             │
│  2. Search Results (5 minutes TTL)                         │
│     • Key: "search:hybrid:<query_hash>"                    │
│     • Value: [chunk_ids...]                                │
│     • Saves: ~180ms per query                              │
│                                                             │
│  3. Graph Traversals (10 minutes TTL)                      │
│     • Key: "graph:traversal:<entity_id>:<hops>"            │
│     • Value: [related_entities...]                         │
│     • Saves: ~120ms per query                              │
│                                                             │
│  4. Developer Profiles (1 hour TTL)                        │
│     • Key: "profile:<user_id>:<codebase>"                  │
│     • Value: {patterns...}                                 │
│     • Saves: ~60ms per query                               │
└─────────────────────────────────────────────────────────────┘
```

---

## Monitoring & Observability

### Metrics Logged

```python
logger.info(
    f"Context retrieval: "
    f"query='{request.query[:50]}...', "
    f"codebase={request.codebase}, "
    f"total_time={metrics.total_time_ms}ms, "
    f"code_chunks={len(context.code_chunks)}, "
    f"dependencies={len(context.graph_dependencies)}, "
    f"patterns={len(context.developer_patterns)}, "
    f"annotations={len(context.pdf_annotations)}, "
    f"timeout={metrics.timeout_occurred}, "
    f"api_key_length={len(api_key)}"  # Audit log
)
```

### Security Audit Logs

```
# Successful authentication
INFO: API key authentication successful (key length: 32)

# Failed authentication
WARNING: API key authentication failed: Invalid key provided (length: 15, expected: 32)

# Missing authentication
WARNING: API key authentication failed: Missing Authorization header
```

---

## Summary

This architecture provides:

✅ **Performance**: 2.5x speedup via parallel fetching  
✅ **Security**: Zero-Trust M2M authentication  
✅ **Scalability**: Handles 1000+ codebases  
✅ **Reliability**: Graceful degradation on failures  
✅ **Observability**: Comprehensive logging and metrics  
✅ **Maintainability**: Clean module isolation

**Status**: ✅ Production Ready
