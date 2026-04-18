# Vertical Slice Modules & Service Architecture

Module architecture, service layer, and class hierarchies for Pharos.

> **Last Updated**: Phase 17 - Production Hardening

## Modular Architecture Overview (Phase 17 - Complete)

Production-ready architecture with 11 self-contained vertical slice modules. (Recommendations, Curation, and Taxonomy were removed in Phase 21 — see ADR-008, ADR-009, ADR-012.)

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                    Pharos - COMPLETE MODULAR ARCHITECTURE                   │
│                              (11 Vertical Slice Modules)                                │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                         │
│  ┌──────────────────────────────────────────────────────────────────────────────────┐   │
│  │                         FastAPI Application (main.py)                            │   │
│  │                    Registers all module routers & event handlers                 │   │
│  │                    Global Authentication & Rate Limiting Middleware              │   │
│  └────────────────────────────────────┬─────────────────────────────────────────────┘   │
│                                       │                                                 │
│                                       │ Module Registration                             │
│                                       │                                                 │
│       ┌───────────────────────────────┼───────────────────────────────────┐             │
│       │                               │                                   │             │
│       ▼                               ▼                                   ▼             │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │   Auth   │  │Resources │  │Collections│ │  Search  │  │Annotations│ │ Scholarly│   │
│  │  Module  │  │  Module  │  │  Module  │  │  Module  │  │  Module  │  │  Module  │   │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘   │
│       │             │             │             │             │             │          │
│       │             │             │             │             │             │          │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐               │
│  │ Authority│  │  Quality │  │  Graph   │  │Monitoring│  │   MCP    │               │
│  │  Module  │  │  Module  │  │  Module  │  │  Module  │  │  Module  │               │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘               │
│       │             │             │             │             │                      │
│       │             │             │             │             │                      │
│       │    ┌────────┴─────────────┴─────────────┴─────────────┴────────────┘          │
│       │    │                                                                           │
│       │    ▼                                                                           │
│       │  ┌─────────────────────────────────────────────────────────────────┐           │
│       │  │                      Shared Kernel                              │           │
│       │  │  ┌──────────┐  ┌──────────────┐  ┌──────────────┐              │           │
│       └─►│  │ Database │  │  Event Bus   │  │  Base Model  │              │◄──────────┘
│          │  │ (Session)│  │  (Pub/Sub)   │  │   (GUID)     │              │           │
│          │  └──────────┘  └──────────────┘  └──────────────┘              │           │
│          │  ┌──────────────────────────────────────────────────────────┐   │           │
│          │  │  Cross-Cutting Services:                                 │   │           │
│          │  │  • EmbeddingService (dense & sparse embeddings)          │   │           │
│          │  │  • AICore (summarization, entity extraction)             │   │           │
│          │  │  • CacheService (Redis caching with TTL)                 │   │           │
│          │  │  • Security (JWT, password hashing, OAuth2)              │   │           │
│          │  │  • RateLimiter (tiered rate limiting with Redis)         │   │           │
│          │  └──────────────────────────────────────────────────────────┘   │           │
│          └─────────────────────────────────────────────────────────────────┘           │
│                                                                                         │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

### All 11 Modules

| # | Module | Domain | Events Emitted | Events Consumed |
|---|--------|--------|----------------|-----------------|
| 1 | **Auth** | Perimeter defense | - | - |
| 2 | **Resources** | Content management | resource.created, resource.updated, resource.deleted | - |
| 3 | **Collections** | Organization | collection.created, collection.updated, collection.resource_added | resource.deleted |
| 4 | **Search** | Discovery | search.executed | resource.created, resource.updated, resource.deleted |
| 5 | **Annotations** | Highlights & notes | annotation.created, annotation.updated, annotation.deleted | resource.deleted |
| 6 | **Scholarly** | Academic metadata | metadata.extracted, equations.parsed, tables.extracted | resource.created |
| 7 | **Authority** | Subject authority | - | - |
| 8 | **Quality** | Quality assessment | quality.computed, quality.outlier_detected, quality.degradation_detected | resource.created, resource.updated |
| 9 | **Graph** | Knowledge graph | citation.extracted, graph.updated, hypothesis.discovered | resource.created, resource.deleted |
| 10 | **Monitoring** | System health | - | All events (metrics) |
| 11 | **MCP** | Model Context Protocol | - | - |
| 12 | **GitHub** | On-demand code fetch | - | - |

### GitHub Module (`app.modules.github`)

The GitHub module provides on-demand retrieval of raw source code from GitHub, with Redis caching and SSRF protection.

**Components:**
- `fetcher.py` — `GitHubFetcher` async context manager; `FetchRequest`/`FetchResult` dataclasses; `fetch_chunks_for_results()` convenience helper
- `code_resolver.py` — `resolve_code_for_chunks(chunks)` partitions chunks by `is_remote`, reads local content directly and fetches remote chunks via `GitHubFetcher` with `asyncio.gather` + per-chunk timeout; returns `{chunk_id: {code, source, cache_hit}}` and aggregate metrics
- `router.py` — `POST /api/github/fetch`, `POST /api/github/fetch-batch`, `GET /api/github/health` (thin wrappers; no new service class)
- `schema.py` — `GitHubFetchRequest/Response`, `GitHubBatchFetchRequest/Response`, `GitHubHealthResponse`

**Safeguards:**
- SSRF allowlist: only `raw.githubusercontent.com` and `api.github.com`
- Hard cap: 50 remote chunks per `resolve_code_for_chunks` call
- Per-chunk timeout: 5 s
- Cache TTL: 1 hour (keyed on commit SHA + path + line range)

---

## Vertical Slice Module Pattern

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    VERTICAL SLICE MODULE PATTERN                        │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  Each module (Resources, Collections, Search) follows this structure:   │
│                                                                         │
│  app/modules/{module_name}/                                             │
│  │                                                                      │
│  ├── __init__.py          # Public interface & exports                  │
│  │   • router                                                          │
│  │   • service functions                                               │
│  │   • schemas                                                         │
│  │   • models                                                          │
│  │   • module metadata (__version__, __domain__)                       │
│  │                                                                      │
│  ├── router.py            # FastAPI endpoints                          │
│  │   • HTTP request/response handling                                  │
│  │   • Input validation                                                │
│  │   • Calls service layer                                             │
│  │                                                                      │
│  ├── service.py           # Business logic                             │
│  │   • Core domain operations                                          │
│  │   • Orchestration                                                   │
│  │   • Event emission                                                  │
│  │                                                                      │
│  ├── schema.py            # Pydantic models                            │
│  │   • Request/response validation                                     │
│  │   • Data serialization                                              │
│  │                                                                      │
│  ├── model.py             # SQLAlchemy models                          │
│  │   • Database entities                                               │
│  │   • String-based relationships (avoid circular imports)             │
│  │                                                                      │
│  ├── handlers.py          # Event handlers                             │
│  │   • Subscribe to events from other modules                          │
│  │   • React to system events                                          │
│  │                                                                      │
│  ├── README.md            # Module documentation                       │
│  │                                                                      │
│  └── tests/               # Module-specific tests                      │
│      └── __init__.py                                                   │
│                                                                         │
│  Benefits:                                                              │
│  • High cohesion - related code stays together                         │
│  • Low coupling - modules communicate via events                       │
│  • Independent deployment - modules can be extracted to microservices  │
│  • Clear boundaries - explicit public interfaces                       │
│  • Easy testing - isolated module tests                                │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Code Intelligence Pipeline (Phase 18)

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                    CODE INTELLIGENCE PIPELINE ARCHITECTURE                              │
│                              (Phase 18 - Repository Analysis)                           │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                         │
│  ┌──────────────────────────────────────────────────────────────────────────────────┐   │
│  │                         API Layer (Resources Module)                             │   │
│  │                    POST /resources/ingest-repo                                   │   │
│  │                    GET /resources/ingest-repo/{task_id}/status                   │   │
│  └────────────────────────────────┬─────────────────────────────────────────────────┘   │
│                                   │                                                     │
│                                   │ Triggers Celery Task                                │
│                                   │                                                     │
│                                   ▼                                                     │
│  ┌──────────────────────────────────────────────────────────────────────────────────┐   │
│  │                         Async Task Layer (Celery)                                │   │
│  │                         ingest_repo_task()                                       │   │
│  │                    • Progress tracking (files_processed, total_files)            │   │
│  │                    • Error handling and retry logic                              │   │
│  │                    • Batch processing (50 files per transaction)                 │   │
│  └────────────────────────────────┬─────────────────────────────────────────────────┘   │
│                                   │                                                     │
│                                   │ Calls                                               │
│                                   │                                                     │
│                                   ▼                                                     │
│  ┌──────────────────────────────────────────────────────────────────────────────────┐   │
│  │                    Repository Ingestion Service                                  │   │
│  │                    (app/modules/resources/logic/repo_ingestion.py)               │   │
│  │                                                                                  │   │
│  │  ┌────────────────────────────────────────────────────────────────────────────┐  │   │
│  │  │ 1. Repository Access                                                       │  │   │
│  │  │    • Local directory: crawl_directory(path)                                │  │   │
│  │  │    • Git repository: clone_and_ingest(git_url)                             │  │   │
│  │  │    • Parse .gitignore with pathspec library                                │  │   │
│  │  │    • Detect binary files (null byte check)                                 │  │   │
│  │  └────────────────────────────────────────────────────────────────────────────┘  │   │
│  │                                   │                                              │   │
│  │                                   ▼                                              │   │
│  │  ┌────────────────────────────────────────────────────────────────────────────┐  │   │
│  │  │ 2. File Classification                                                     │  │   │
│  │  │    (app/modules/resources/logic/classification.py)                         │  │   │
│  │  │    • PRACTICE: Code files (.py, .js, .ts, .rs, .go, .java)                │  │   │
│  │  │    • THEORY: Academic docs (.pdf, .md with keywords)                       │  │   │
│  │  │    • GOVERNANCE: Config files (.eslintrc, CONTRIBUTING.md)                 │  │   │
│  │  └────────────────────────────────────────────────────────────────────────────┘  │   │
│  │                                   │                                              │   │
│  │                                   ▼                                              │   │
│  │  ┌────────────────────────────────────────────────────────────────────────────┐  │   │
│  │  │ 3. Resource Creation                                                       │  │   │
│  │  │    • Create Resource with metadata (repo_root, commit_hash, branch)        │  │   │
│  │  │    • Store file path and classification                                    │  │   │
│  │  │    • Emit resource.created event                                           │  │   │
│  │  └────────────────────────────────────────────────────────────────────────────┘  │   │
│  └──────────────────────────────────┬───────────────────────────────────────────────┘   │
│                                     │                                                   │
│                                     │ For code files                                    │
│                                     │                                                   │
│                                     ▼                                                   │
│  ┌──────────────────────────────────────────────────────────────────────────────────┐   │
│  │                    AST-Based Code Chunking Service                               │   │
│  │                    (app/modules/resources/logic/chunking.py)                     │   │
│  │                                                                                  │   │
│  │  ┌────────────────────────────────────────────────────────────────────────────┐  │   │
│  │  │ 1. Tree-Sitter Parsing                                                     │  │   │
│  │  │    • Initialize parser for language (Python, JS, TS, Rust, Go, Java)      │  │   │
│  │  │    • Parse code into Abstract Syntax Tree (AST)                            │  │   │
│  │  │    • Fallback to character-based chunking on parse errors                  │  │   │
│  │  └────────────────────────────────────────────────────────────────────────────┘  │   │
│  │                                   │                                              │   │
│  │                                   ▼                                              │   │
│  │  ┌────────────────────────────────────────────────────────────────────────────┐  │   │
│  │  │ 2. Logical Unit Extraction                                                 │  │   │
│  │  │    • Extract functions, classes, methods from AST                          │  │   │
│  │  │    • Capture function_name, class_name, start_line, end_line              │  │   │
│  │  │    • Store language and type (function/class/method) in metadata           │  │   │
│  │  └────────────────────────────────────────────────────────────────────────────┘  │   │
│  │                                   │                                              │   │
│  │                                   ▼                                              │   │
│  │  ┌────────────────────────────────────────────────────────────────────────────┐  │   │
│  │  │ 3. Chunk Creation                                                          │  │   │
│  │  │    • Create DocumentChunk with populated chunk_metadata JSON               │  │   │
│  │  │    • Generate embeddings for each chunk                                    │  │   │
│  │  │    • Emit resource.chunked event                                           │  │   │
│  │  └────────────────────────────────────────────────────────────────────────────┘  │   │
│  └──────────────────────────────────┬───────────────────────────────────────────────┘   │
│                                     │                                                   │
│                                     │ Triggers                                          │
│                                     │                                                   │
│                                     ▼                                                   │
│  ┌──────────────────────────────────────────────────────────────────────────────────┐   │
│  │                    Static Analysis Service                                       │   │
│  │                    (app/modules/graph/logic/static_analysis.py)                  │   │
│  │                                                                                  │   │
│  │  ┌────────────────────────────────────────────────────────────────────────────┐  │   │
│  │  │ 1. Import Extraction                                                       │  │   │
│  │  │    • Find import statements in AST                                         │  │   │
│  │  │    • Create IMPORTS relationships                                          │  │   │
│  │  │    • Metadata: source_file, target_module, line_number                     │  │   │
│  │  └────────────────────────────────────────────────────────────────────────────┘  │   │
│  │                                   │                                              │   │
│  │                                   ▼                                              │   │
│  │  ┌────────────────────────────────────────────────────────────────────────────┐  │   │
│  │  │ 2. Definition Extraction                                                   │  │   │
│  │  │    • Find function, class, variable definitions                            │  │   │
│  │  │    • Create DEFINES relationships                                          │  │   │
│  │  │    • Metadata: source_file, symbol_name, symbol_type, line_number         │  │   │
│  │  └────────────────────────────────────────────────────────────────────────────┘  │   │
│  │                                   │                                              │   │
│  │                                   ▼                                              │   │
│  │  ┌────────────────────────────────────────────────────────────────────────────┐  │   │
│  │  │ 3. Call Extraction                                                         │  │   │
│  │  │    • Detect function calls in AST                                          │  │   │
│  │  │    • Create CALLS relationships with confidence scoring                    │  │   │
│  │  │    • Metadata: source_function, target_function, line_number, confidence   │  │   │
│  │  └────────────────────────────────────────────────────────────────────────────┘  │   │
│  │                                   │                                              │   │
│  │                                   ▼                                              │   │
│  │  ┌────────────────────────────────────────────────────────────────────────────┐  │   │
│  │  │ 4. Graph Relationship Creation                                             │  │   │
│  │  │    • Store relationships in graph_relationships table                      │  │   │
│  │  │    • Link to source chunks via provenance                                  │  │   │
│  │  │    • Enable graph traversal and dependency analysis                        │  │   │
│  │  └────────────────────────────────────────────────────────────────────────────┘  │   │
│  └──────────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                         │
│  Performance Targets:                                                                   │
│  • AST Parsing: <2s per file (P95)                                                      │
│  • Static Analysis: <1s per file (P95)                                                  │
│  • Batch Processing: 50 files per transaction                                           │
│  • Concurrent Tasks: 3 per user                                                         │
│                                                                                         │
│  Supported Languages:                                                                   │
│  • Python (.py)                                                                         │
│  • JavaScript (.js)                                                                     │
│  • TypeScript (.ts)                                                                     │
│  • Rust (.rs)                                                                           │
│  • Go (.go)                                                                             │
│  • Java (.java)                                                                         │
│                                                                                         │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Current Modules

### Resources Module

**Domain:** Content management and ingestion

**Responsibilities:**
- Resource CRUD operations
- URL ingestion and content extraction
- AI-powered summarization and tagging
- Quality score computation
- Classification assignment
- **[Phase 18]** Code repository ingestion (local directories and Git repositories)
- **[Phase 18]** AST-based code chunking with Tree-Sitter
- **[Phase 18]** File classification (PRACTICE, THEORY, GOVERNANCE)
- **[Phase 18]** Binary file detection and exclusion
- **[Phase 18]** .gitignore parsing and compliance

**Services:**
- `ResourceService` - Core CRUD operations
- **[Phase 18]** `RepoIngestionService` - Repository crawling and Git cloning
- **[Phase 18]** `CodeChunkingStrategy` - AST-based code chunking
- **[Phase 18]** File classification logic

**Code Intelligence Features (Phase 18):**
- **Repository Ingestion**: Scan local directories or clone Git repositories
- **AST Parsing**: Tree-Sitter parsing for 6 languages (Python, JS, TS, Rust, Go, Java)
- **Logical Unit Extraction**: Chunk code by functions, classes, and methods
- **Chunk Metadata**: Includes function_name, class_name, start_line, end_line, language
- **Fallback Strategy**: Character-based chunking on parse errors
- **Performance**: <2s per file (P95) for AST parsing

**Supported Languages:**
- Python (.py)
- JavaScript (.js)
- TypeScript (.ts)
- Rust (.rs)
- Go (.go)
- Java (.java)

**Events Published:**
- `resource.created`
- `resource.updated`
- `resource.deleted`
- `resource.classified`
- **[Phase 18]** `resource.chunked` - When code is chunked into logical units

**Location:** `app/modules/resources/`

### Collections Module

**Domain:** Resource organization and curation

**Responsibilities:**
- Collection CRUD operations
- Hierarchical organization (parent-child)
- Resource membership management
- Aggregate embedding computation
- Collection-based recommendations

**Events Published:**
- `collection.created`
- `collection.updated`
- `collection.deleted`
- `collection.resource_added`
- `collection.resource_removed`

**Events Subscribed:**
- `resource.deleted` → Remove from collections

**Location:** `app/modules/collections/`

### Search Module

**Domain:** Discovery and retrieval

**Responsibilities:**
- Hybrid search (keyword + semantic)
- Three-way search with RRF fusion
- Faceted search results
- Search quality evaluation
- **[Phase 17.5]** Parent-child retrieval (chunk-level search with parent context)
- **[Phase 17.5]** GraphRAG retrieval (entity-based search with graph traversal)
- **[Phase 17.5]** Question-based retrieval (Reverse HyDE with synthetic questions)
- **[Phase 17.5]** Synthetic question generation for chunks

**Services:**
- `AdvancedSearchService` - Hybrid and vector search
- **[Phase 17.5]** `SyntheticQuestionService` - Generate questions for chunks
- **[Phase 17.5]** Parent-child retrieval methods
- **[Phase 17.5]** GraphRAG retrieval methods
- **[Phase 17.5]** Question-based retrieval methods

**Advanced RAG Features (Phase 17.5):**
- **Parent-Child Retrieval**: Search at chunk level, return parent resources with surrounding context
- **GraphRAG Retrieval**: Extract entities from query, traverse knowledge graph, retrieve chunks via provenance
- **Reverse HyDE**: Match user query against synthetic question embeddings, retrieve associated chunks
- **Hybrid Strategies**: Combine multiple retrieval methods with configurable weights
- **Context Window**: Include surrounding chunks for better context
- **Contradiction Discovery**: Find contradictory information in knowledge graph

**Events Published:**
- `search.executed`

**Events Subscribed:**
- `resource.created` → Update search index
- `resource.updated` → Update search index
- `resource.deleted` → Remove from index

**Location:** `app/modules/search/`

### Annotations Module

**Domain:** Text highlights, notes, and tags

**Responsibilities:**
- Create, update, delete annotations on resources
- Precise text range highlighting with character offsets
- Semantic search across annotation content and notes
- Tag-based organization and filtering
- Export annotations to Markdown and JSON formats
- Shared annotations for collaboration

**Services:**
- `AnnotationService` - Core CRUD operations and business logic
- Semantic search with embedding-based similarity
- Export service for multiple formats

**Events Published:**
- `annotation.created` - New annotation added to resource
- `annotation.updated` - Annotation content or metadata changed
- `annotation.deleted` - Annotation removed

**Events Subscribed:**
- `resource.deleted` → Delete all annotations on resource

**Location:** `app/modules/annotations/`

### Scholarly Module

**Domain:** Academic metadata extraction

**Responsibilities:**
- Extract academic metadata from resources (equations, tables, figures)
- Parse LaTeX equations and mathematical notation
- Extract structured table data
- Identify and catalog figures and diagrams
- Extract author information, abstracts, DOIs
- Support for academic paper formats

**Services:**
- `ScholarlyExtractor` - Main extraction service
- LaTeX parser for mathematical content
- Table extraction and structuring
- Metadata normalization

**Events Published:**
- `metadata.extracted` - Academic metadata parsed from resource
- `equations.parsed` - Mathematical equations found
- `tables.extracted` - Tables extracted from content

**Events Subscribed:**
- `resource.created` → Extract scholarly metadata

**Location:** `app/modules/scholarly/`

### Authority Module

**Domain:** Subject authority control

**Responsibilities:**
- Manage hierarchical subject authority trees
- Subject heading normalization
- Authority record management
- Cross-reference management

**Events Published:**
- None (passive module)

**Events Subscribed:**
- None

**Location:** `app/modules/authority/`

### Quality Module

**Domain:** Multi-dimensional quality assessment

**Responsibilities:**
- Compute quality scores across 5 dimensions (accuracy, completeness, consistency, timeliness, relevance)
- Monitor quality degradation over time
- Detect quality outliers using statistical methods
- Track quality metrics and trends
- Provide quality-based filtering and ranking

**Services:**
- `QualityService` - Quality computation and monitoring
- `ContentQualityAnalyzer` - Dimension-specific analysis
- Outlier detection with configurable thresholds

**Events Published:**
- `quality.computed` - Quality scores calculated for resource
- `quality.outlier_detected` - Anomalous quality detected
- `quality.degradation_detected` - Quality decreased over time

**Events Subscribed:**
- `resource.created` → Compute initial quality scores
- `resource.updated` → Recompute quality scores

**Location:** `app/modules/quality/`

### Graph Module

**Domain:** Knowledge graph and citation network

**Responsibilities:**
- Extract citations from resources
- Build and maintain citation network graph
- Graph traversal and path finding
- PageRank computation for resource importance
- Literature-Based Discovery (LBD) for hypothesis generation
- Semantic graph embeddings
- Citation context extraction
- **[Phase 17.5]** Semantic triple storage (entity-relationship-entity)
- **[Phase 17.5]** Entity extraction from document chunks
- **[Phase 17.5]** Relationship extraction with provenance tracking
- **[Phase 17.5]** GraphRAG retrieval with entity-based search
- **[Phase 18]** Static analysis for code relationships
- **[Phase 18]** Import/definition/call extraction from code

**Services:**
- `GraphService` - Graph operations and queries
- `CitationExtractor` - Citation parsing and extraction
- `LBDService` - Hypothesis discovery (ABC pattern)
- `GraphEmbeddingService` - Node embedding generation
- **[Phase 17.5]** `GraphExtractionService` - Entity and relationship extraction from chunks
- **[Phase 18]** `StaticAnalysisService` - Code relationship extraction

**Advanced RAG Features (Phase 17.5):**
- **Entity Extraction**: Extract named entities (Concept, Person, Organization, Method) from document chunks using NLP or LLM
- **Relationship Extraction**: Identify relationships between entities (CONTRADICTS, SUPPORTS, EXTENDS, CITES)
- **Provenance Tracking**: Link relationships back to source chunks for explainability
- **GraphRAG Retrieval**: Traverse knowledge graph to find related entities and retrieve associated chunks
- **Contradiction Discovery**: Find contradictory relationships in the knowledge graph
- **Code Support**: Relationship types include code-specific relations (CALLS, IMPORTS, DEFINES) for Phase 18

**Code Intelligence Features (Phase 18):**
- **Static Analysis**: AST-based relationship extraction without code execution
- **Import Extraction**: Detect module/file imports with source and target
- **Definition Extraction**: Find function, class, and variable definitions
- **Call Extraction**: Detect function calls with confidence scoring
- **Relationship Types**:
  - `IMPORTS`: Module/file imports another module/file
  - `DEFINES`: File defines a function, class, or variable
  - `CALLS`: Function calls another function
- **Metadata**: source_file, target_symbol, line_number, confidence
- **Performance**: <1s per file (P95) for static analysis

**Events Published:**
- `citation.extracted` - Citations parsed from resource
- `graph.updated` - Graph structure changed
- `hypothesis.discovered` - LBD found new connection
- **[Phase 17.5]** `graph.entity_extracted` - Entity extracted from chunk
- **[Phase 17.5]** `graph.relationship_extracted` - Relationship extracted from chunk

**Events Subscribed:**
- `resource.created` → Extract citations and update graph
- `resource.deleted` → Remove from graph
- **[Phase 17.5]** `resource.chunked` → Extract entities and relationships from chunks

**Location:** `app/modules/graph/`

### Monitoring Module

**Domain:** System health and observability

**Responsibilities:**
- Health check endpoints for all modules
- Event bus metrics tracking
- Performance monitoring and alerting
- System resource usage tracking
- API endpoint latency monitoring
- Database connection pool monitoring

**Services:**
- `MonitoringService` - Health checks and metrics aggregation
- Event bus statistics
- Performance metric collection

**Events Published:**
- None (observability module)

**Events Subscribed:**
- All events (for metrics tracking)

**Location:** `app/modules/monitoring/`

---

## Module Communication

Modules communicate through the event bus, not direct imports:

```
┌──────────────────────────────────────────────────────────────────────┐
│                    MODULE COMMUNICATION                              │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ❌ WRONG: Direct Import                                             │
│  ─────────────────────────                                           │
│  from app.modules.resources.service import get_resource              │
│                                                                      │
│  ✅ CORRECT: Event-Based Communication                               │
│  ─────────────────────────────────────                               │
│  event_bus.publish(Event(type="resource.deleted", payload={...}))    │
│                                                                      │
│  ✅ CORRECT: Shared Kernel                                           │
│  ─────────────────────────                                           │
│  from app.shared.database import get_db                              │
│  from app.shared.event_bus import event_bus                          │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Shared Kernel

Common infrastructure shared by all modules:

```
app/shared/
├── __init__.py
├── database.py      # Database session, engine
├── event_bus.py     # Event publishing/subscribing
└── base_model.py    # Base SQLAlchemy model with GUID
```

### Database Access

```python
from app.shared.database import get_db, SessionLocal

# In router
@router.get("/resources")
def list_resources(db: Session = Depends(get_db)):
    return service.list_resources(db)
```

### Event Bus

```python
from app.shared.event_bus import event_bus, Event

# Publishing
event_bus.publish(Event(
    type="resource.created",
    payload={"resource_id": str(resource.id)}
))

# Subscribing
event_bus.subscribe("resource.deleted", handle_resource_deleted)
```

### Base Model

```python
from app.shared.base_model import BaseModel

class Resource(BaseModel):
    __tablename__ = "resources"
    # Inherits: id (UUID), created_at, updated_at
    title = Column(String, nullable=False)
```

---

## Service Layer Architecture

The service layer implements business logic and orchestrates domain objects, database operations, and external services.

### ML Classification Service

```
┌────────────────────────────────────────────────────────────────────┐
│                    MLClassificationService                         │
├────────────────────────────────────────────────────────────────────┤
│ Attributes:                                                        │
│  • db: Session                                                     │
│  • model_name: str = "distilbert-base-uncased"                     │
│  • model: Optional[AutoModelForSequenceClassification]             │
│  • tokenizer: Optional[AutoTokenizer]                              │
│  • id_to_label: Dict[int, str]                                     │
│  • label_to_id: Dict[str, int]                                     │
│  • monitor: PredictionMonitor                                      │
│  • checkpoint_dir: Path                                            │
│  • device: torch.device                                            │
├────────────────────────────────────────────────────────────────────┤
│ Constants:                                                         │
│  • DEFAULT_MODEL_NAME = "distilbert-base-uncased"                  │
│  • MAX_TOKEN_LENGTH = 512                                          │
│  • DEFAULT_EPOCHS = 3                                              │
│  • DEFAULT_BATCH_SIZE = 16                                         │
│  • DEFAULT_LEARNING_RATE = 2e-5                                    │
│  • BINARY_PREDICTION_THRESHOLD = 0.5                               │
│  • HIGH_CONFIDENCE_THRESHOLD = 0.8                                 │
│  • DEFAULT_TOP_K = 5                                               │
├────────────────────────────────────────────────────────────────────┤
│ Public Methods:                                                    │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ Training & Fine-tuning                                       │  │ 
│  │  • fine_tune(labeled_data, ...) → Dict[str, float]           │  │
│  │  • semi_supervised_learning(...) → Dict[str, float]          │  │
│  └──────────────────────────────────────────────────────────────┘  │ 
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ Inference                                                    │  │
│  │  • predict(text, top_k) → ClassificationResult               │  │
│  │  • predict_batch(texts, top_k) → List[ClassificationResult]  │  │
│  └──────────────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ Active Learning                                              │  │
│  │  • active_learning_uncertainty_sampling(...)                 │  │
│  │  • get_model_metrics(window_minutes) → Dict                  │  │
│  └──────────────────────────────────────────────────────────────┘  │
├────────────────────────────────────────────────────────────────────┤
│ Private Methods (20+ helper methods):                              │
│  • _load_model(), _import_ml_libraries()                           │
│  • _tokenize_texts(), _create_datasets()                           │
│  • _compute_metrics(), _calculate_classification_metrics()         │
│  • _build_label_mapping(), _convert_to_multihot_encoding()         │
│  • _split_train_validation(), _initialize_model_for_training()     │
│  • _configure_trainer(), _train_model()                            │
│  • _perform_semi_supervised_learning()                             │
│  • _save_model_and_artifacts(), _extract_metrics()                 │
└────────────────────────────────────────────────────────────────────┘
```

### Quality Service

```
┌────────────────────────────────────────────────────────────────┐
│                 ContentQualityAnalyzer                         │
├────────────────────────────────────────────────────────────────┤
│ Attributes:                                                    │
│  • REQUIRED_KEYS: List[str] = ["title", "description",         │
│    "subject", "creator", "language", "type", "identifier"]     │
├────────────────────────────────────────────────────────────────┤
│ Constants:                                                     │
│  • METADATA_WEIGHT = 0.6                                       │
│  • READABILITY_WEIGHT = 0.4                                    │
│  • READING_EASE_MIN = 0.0                                      │
│  • READING_EASE_MAX = 100.0                                    │
│  • CREDIBILITY_HIGH = 0.9                                      │
│  • CREDIBILITY_MEDIUM = 0.7                                    │
│  • CREDIBILITY_DEFAULT = 0.6                                   │
│  • DEPTH_THRESHOLD_MINIMAL = 100                               │
│  • DEPTH_THRESHOLD_SHORT = 500                                 │
│  • DEPTH_THRESHOLD_MEDIUM = 2000                               │
├────────────────────────────────────────────────────────────────┤
│ Methods:                                                       │
│  • metadata_completeness(resource) → float                     │
│  • text_readability(text) → Dict[str, float]                   │
│  • overall_quality(resource, text) → float                     │
│  • quality_level(score) → str                                  │
│  • source_credibility(source) → float                          │
│  • content_depth(text) → float                                 │
└────────────────────────────────────────────────────────────────┘
                            │
                            │ used by
                            ▼
┌────────────────────────────────────────────────────────────────┐
│                      QualityService                            │
├────────────────────────────────────────────────────────────────┤
│ Attributes:                                                    │
│  • db: Session                                                 │
│  • quality_version: str = "v2.0"                               │
├────────────────────────────────────────────────────────────────┤
│ Constants:                                                     │
│  • HIGH_QUALITY_THRESHOLD = 0.8                                │
│  • MEDIUM_QUALITY_THRESHOLD = 0.5                              │
│  • DEFAULT_QUALITY_WEIGHTS = {...}                             │
│  • COMPLETENESS_FIELD_WEIGHT = 0.2                             │
│  • DEGRADATION_THRESHOLD = 0.2                                 │
│  • OUTLIER_MIN_RESOURCES = 10                                  │
│  • OUTLIER_CONTAMINATION = 0.1                                 │
│  • OUTLIER_THRESHOLD_LOW = 0.3                                 │
├────────────────────────────────────────────────────────────────┤
│ Public Methods:                                                │
│  • compute_quality(resource_id, weights) → QualityScore        │
│  • monitor_quality_degradation(days) → List[Dict]              │
│  • detect_quality_outliers(batch_size) → int                   │
├────────────────────────────────────────────────────────────────┤
│ Private Methods:                                               │
│  • _compute_accuracy_dimension(resource) → float               │
│  • _compute_completeness_dimension(resource) → float           │
│  • _compute_consistency_dimension(resource) → float            │
│  • _compute_timeliness_dimension(resource) → float             │
│  • _compute_relevance_dimension(resource) → float              │
│  • _update_resource_quality_fields(resource, ...) → None       │
│  • _identify_outlier_reasons(resource) → List[str]             │
└────────────────────────────────────────────────────────────────┘
```

### Search Service

```
┌────────────────────────────────────────────────────────────────┐
│                   AdvancedSearchService                        │
├────────────────────────────────────────────────────────────────┤
│ Public Methods:                                                │
│  • hybrid_search(db, query, weight) → (resources, total, ...)  │
│  • fts_search(db, query, filters, ...) → (resources, ...)      │
│  • vector_search(db, query_text, ...) → (resources, ...)       │
│  • parse_search_query(query: str) → str                        │
│  • generate_snippets(text, query, max_len) → str               │
│                                                                │
│ Private Methods:                                               │
│  • _analyze_query(query) → Dict[str, Any]                      │
│  • _search_sparse(db, query_text, limit) → List[Tuple]         │
│  • _fetch_resources_ordered(db, ids, filters) → List[Res]      │
│  • _compute_facets(db, query) → Facets                         │
└────────────────────────────────────────────────────────────────┘
                            │
                            │ uses
                            ▼
┌────────────────────────────────────────────────────────────────┐
│                     HybridSearchQuery                          │
├────────────────────────────────────────────────────────────────┤
│ Attributes:                                                    │
│  • db: Session                                                 │
│  • query: DomainSearchQuery                                    │
│  • enable_reranking: bool                                      │
│  • adaptive_weighting: bool                                    │
│  • _diagnostics: Dict[str, Any]                                │
├────────────────────────────────────────────────────────────────┤
│ Public Methods:                                                │
│  • execute() → Tuple[List[Resource], int, Facets, ...]         │
│  • get_diagnostic_info() → Dict[str, Any]                      │
├────────────────────────────────────────────────────────────────┤
│ Private Methods:                                               │
│  • _convert_to_schema_filters() → SearchFilters | None         │
│  • _ensure_tables_exist() → None                               │
│  • _check_services_available() → bool                          │
│  • _fallback_to_two_way_hybrid(start_time) → Tuple[...]        │
│  • _analyze_query() → Dict[str, Any]                           │
│  • _execute_retrieval_phase() → RetrievalCandidates            │
│  • _execute_fusion_phase(candidates) → FusedCandidates         │
│  • _execute_reranking_phase(fused) → List[Tuple[str, float]]   │
│  • _search_fts5() → List[Tuple[str, float]]                    │
│  • _search_dense() → List[Tuple[str, float]]                   │
│  • _search_sparse() → List[Tuple[str, float]]                  │
│  • _compute_weights() → List[float]                            │
│  • _compute_method_contributions(...) → Dict[str, int]         │
│  • _fetch_paginated_resources(fused) → List[Resource]          │
│  • _compute_facets(fused) → Facets                             │
│  • _generate_snippets(resources) → Dict[str, str]              │
└────────────────────────────────────────────────────────────────┘
```

### Search Pipeline Data Structures

```
┌────────────────────────────────────────────────────────────────┐
│                   RetrievalCandidates                          │
├────────────────────────────────────────────────────────────────┤
│ Attributes:                                                    │
│  • fts5_results: List[Tuple[str, float]]                       │
│  • dense_results: List[Tuple[str, float]]                      │
│  • sparse_results: List[Tuple[str, float]]                     │
│  • retrieval_time_ms: float                                    │
│  • method_times_ms: Dict[str, float]                           │
├────────────────────────────────────────────────────────────────┤
│ Methods:                                                       │
│  • get_all_candidate_ids() → set[str]                          │
│  • get_method_counts() → Dict[str, int]                        │
└────────────────────────────────────────────────────────────────┘
                            │
                            │ feeds into
                            ▼
┌────────────────────────────────────────────────────────────────┐
│                     FusedCandidates                            │
├────────────────────────────────────────────────────────────────┤
│ Attributes:                                                    │
│  • fused_results: List[Tuple[str, float]]                      │
│  • weights_used: List[float]                                   │
│  • fusion_time_ms: float                                       │
│  • method_contributions: Dict[str, int]                        │
├────────────────────────────────────────────────────────────────┤
│ Methods:                                                       │
│  • get_top_k(k: int) → List[Tuple[str, float]]                 │
│  • get_candidate_ids() → List[str]                             │
└────────────────────────────────────────────────────────────────┘
```

---

## Domain Layer Architecture (Phase 11)

```
┌─────────────────────────────────────────────────────────────────────────┐
│            DOMAIN-DRIVEN DESIGN (DDD) REFACTORING                       │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│                   ┌──────────────────────────┐                          │
│                   │  BaseDomainObject (ABC)  │                          │
│                   ├──────────────────────────┤                          │
│                   │ + to_dict()              │                          │
│                   │ + from_dict()            │                          │
│                   │ + to_json()              │                          │
│                   │ + from_json()            │                          │
│                   │ + validate() [abstract]  │                          │
│                   │ + __eq__()               │                          │
│                   │ + __repr__()             │                          │
│                   └────────┬─────────────────┘                          │
│                            │                                            │
│              ┌─────────────┴──────────────┐                             │
│              │                            │                             │
│    ┌─────────▼──────────┐      ┌──────────▼──────────┐                  │
│    │   ValueObject      │      │   DomainEntity      │                  │
│    │   (dataclass)      │      │                     │                  │
│    ├────────────────────┤      ├─────────────────────┤                  │
│    │ Immutable          │      │ • entity_id: str    │                  │
│    │ Defined by values  │      │ Identity-based      │                  │
│    │ No identity        │      │ Mutable             │                  │
│    └─────────┬──────────┘      └─────────────────────┘                  │
│              │                                                          │
│              │ subclasses                                               │
│              │                                                          │
│    ┌─────────┼─────────┬─────────────┬─────────────┬─────────────┐      │
│    │         │         │             │             │             │      │
│    ▼         ▼         ▼             ▼             ▼             ▼      │
│ ┌──────┐ ┌──────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐   │
│ │Class-│ │Class-│ │ Quality  │ │Recommend-│ │ Search   │ │ Search   │   │
│ │ifica-│ │ifica-│ │  Score   │ │  ation   │ │  Query   │ │ Result   │   │
│ │tion  │ │tion  │ │          │ │  Score   │ │          │ │          │   │
│ │Predic│ │Result│ │          │ │          │ │          │ │          │   │
│ │tion  │ │      │ │          │ │          │ │          │ │          │   │
│ └──────┘ └──────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Domain Objects


#### Classification Domain

```
┌──────────────────────────────────────────────────────────────┐
│         ClassificationPrediction (ValueObject)               │
├──────────────────────────────────────────────────────────────┤
│ Attributes:                                                  │
│  • taxonomy_id: str                                          │
│  • confidence: float (0.0-1.0)                               │
│  • rank: int (1-based)                                       │
├──────────────────────────────────────────────────────────────┤
│ Methods:                                                     │
│  • validate()                                                │
│  • is_high_confidence(threshold=0.8) → bool                  │
│  • is_low_confidence(threshold=0.5) → bool                   │
│  • is_medium_confidence(low, high) → bool                    │ 
└──────────────────────────────────────────────────────────────┘
                             │
                             │ contains multiple
                             ▼
┌──────────────────────────────────────────────────────────────┐
│         ClassificationResult (ValueObject)                   │
├──────────────────────────────────────────────────────────────┤
│ Attributes:                                                  │
│  • predictions: List[ClassificationPrediction]               │
│  • model_version: str                                        │
│  • inference_time_ms: float                                  │
│  • resource_id: Optional[str]                                │
├──────────────────────────────────────────────────────────────┤
│ Methods:                                                     │
│  • validate()                                                │
│  • get_high_confidence(threshold) → List[Prediction]         │
│  • get_top_k(k) → List[Prediction]                           │
│  • get_best_prediction() → Prediction                        │
│  • count_by_confidence_level() → Dict[str, int]              │
│  • to_dict() → Dict[str, Any]                                │
│  • from_dict(data) → ClassificationResult                    │
└──────────────────────────────────────────────────────────────┘
```

#### Quality Domain

```
┌──────────────────────────────────────────────────────────────┐
│              QualityScore (ValueObject)                      │
├──────────────────────────────────────────────────────────────┤
│ Attributes (5 Dimensions):                                   │
│  • accuracy: float (0.0-1.0)        Weight: 0.30             │
│  • completeness: float (0.0-1.0)    Weight: 0.25             │
│  • consistency: float (0.0-1.0)     Weight: 0.20             │
│  • timeliness: float (0.0-1.0)      Weight: 0.15             │
│  • relevance: float (0.0-1.0)       Weight: 0.15             │
├──────────────────────────────────────────────────────────────┤
│ Methods:                                                     │
│  • validate()                                                │
│  • overall_score() → float                                   │
│  • is_high_quality(threshold=0.7) → bool                     │
│  • is_low_quality(threshold=0.5) → bool                      │
│  • get_quality_level() → str ("high"/"medium"/"low")         │
│  • get_weakest_dimension() → str                             │
│  • get_strongest_dimension() → str                           │
│  • get_dimension_scores() → Dict[str, float]                 │
│  • has_dimension_below_threshold(t) → bool                   │
│  • count_dimensions_below_threshold(t) → int                 │
│  • to_dict() → Dict[str, Any]                                │
│  • from_dict(data) → QualityScore                            │
└──────────────────────────────────────────────────────────────┘
```

#### Search Domain

```
┌──────────────────────────────────────────────────────────────┐
│              SearchQuery (ValueObject)                       │
├──────────────────────────────────────────────────────────────┤
│ Attributes:                                                  │
│  • query_text: str                                           │
│  • limit: int = 20                                           │
│  • enable_reranking: bool = True                             │
│  • adaptive_weights: bool = True                             │
│  • search_method: str = "hybrid"                             │
├──────────────────────────────────────────────────────────────┤
│ Methods:                                                     │
│  • validate()                                                │
│  • is_short_query(threshold=3) → bool                        │
│  • is_long_query(threshold=10) → bool                        │
│  • is_medium_query(short, long) → bool                       │
│  • get_word_count() → int                                    │
│  • is_single_word() → bool                                   │
│  • get_query_length() → int                                  │
└──────────────────────────────────────────────────────────────┘
                             │
                             │ produces
                             ▼
┌──────────────────────────────────────────────────────────────┐
│              SearchResults (ValueObject)                     │
├──────────────────────────────────────────────────────────────┤
│ Attributes:                                                  │
│  • results: List[SearchResult]                               │
│  • query: SearchQuery                                        │
│  • total_results: int                                        │
│  • search_time_ms: float                                     │
│  • reranked: bool = False                                    │
├──────────────────────────────────────────────────────────────┤
│ Methods:                                                     │
│  • validate()                                                │
│  • get_top_k(k) → List[SearchResult]                         │
│  • get_by_score_threshold(t) → List[SearchResult]            │
│  • is_empty() → bool                                         │
│  • has_results() → bool                                      │
└──────────────────────────────────────────────────────────────┘
```

---

## Refactoring Framework Architecture (Phase 12)

The refactoring framework implements Fowler's refactoring patterns with automated code smell detection and validation.

### Refactoring Models

```
SmellType (Enum)
├── Values:
│   ├── DUPLICATED_CODE
│   ├── LONG_FUNCTION
│   ├── LARGE_CLASS
│   ├── GLOBAL_DATA
│   ├── FEATURE_ENVY
│   ├── DATA_CLUMPS
│   ├── PRIMITIVE_OBSESSION
│   ├── REPEATED_SWITCHES
│   ├── DATA_CLASS
│   └── LONG_PARAMETER_LIST

Severity (Enum)
├── Values:
│   ├── HIGH (blocks production)
│   ├── MEDIUM (technical debt)
│   └── LOW (minor improvement)

RefactoringTechnique (Enum)
├── Values:
│   ├── EXTRACT_FUNCTION
│   ├── EXTRACT_CLASS
│   ├── REPLACE_PRIMITIVE_WITH_OBJECT
│   ├── COMBINE_FUNCTIONS_INTO_CLASS
│   ├── SEPARATE_QUERY_FROM_MODIFIER
│   ├── ENCAPSULATE_COLLECTION
│   ├── SPLIT_PHASE
│   ├── REPLACE_CONDITIONAL_WITH_POLYMORPHISM
│   ├── MOVE_FUNCTION
│   └── INLINE_FUNCTION
```

### Refactoring Data Classes

```
Location (dataclass)
├── Attributes:
│   ├── file_path: Path
│   ├── start_line: int
│   ├── end_line: int
│   ├── function_name: Optional[str]
│   └── class_name: Optional[str]

CodeSmell (dataclass)
├── Attributes:
│   ├── smell_type: SmellType
│   ├── severity: Severity
│   ├── location: Location
│   ├── description: str
│   ├── suggested_technique: RefactoringTechnique
│   └── metrics: Dict[str, Any]

SmellReport (dataclass)
├── Attributes:
│   ├── file_path: Path
│   ├── smells: List[CodeSmell]
│   ├── total_lines: int
│   ├── complexity_score: float
│   └── timestamp: str
├── Methods:
│   ├── high_priority_smells() → List[CodeSmell]
│   ├── smells_by_type(smell_type) → List[CodeSmell]
│   └── summary() → str

RefactoringResult (dataclass)
├── Attributes:
│   ├── success: bool
│   ├── original_code: str
│   ├── refactored_code: str
│   ├── technique_applied: RefactoringTechnique
│   ├── changes_made: List[str]
│   └── test_results: Optional[TestResults]

TestResults (dataclass)
├── Attributes:
│   ├── total_tests: int
│   ├── passed: int
│   ├── failed: int
│   ├── errors: List[str]
│   ├── coverage_percentage: float
│   └── execution_time_seconds: float
├── Methods:
│   ├── all_passed() → bool
│   ├── coverage_acceptable(threshold=0.85) → bool
│   └── summary() → str
```

### Refactoring Detector

```
┌────────────────────────────────────────────────────────────────┐
│                    CodeSmellDetector                           │
├────────────────────────────────────────────────────────────────┤
│ Attributes:                                                    │
│  • function_checker: FunctionLengthChecker                     │
│  • class_checker: ClassSizeChecker                             │
│  • type_hint_checker: TypeHintCoverageChecker                  │
│  • duplication_detector: CodeDuplicationDetector               │
├────────────────────────────────────────────────────────────────┤
│ Public Methods:                                                │
│  • analyze_file(file_path: Path) → SmellReport                 │
│  • analyze_directory(dir_path: Path) → List[SmellReport]       │
│  • prioritize_smells(reports) → PrioritizedSmells              │
│  • generate_summary_report(reports) → str                      │
├────────────────────────────────────────────────────────────────┤
│ Private Methods:                                               │
│  • _detect_feature_envy(file_path) → List[CodeSmell]           │
│  • _detect_long_parameter_lists(file_path) → List[CodeSmell]   │
│  • _count_lines(file_path) → int                               │
│  • _calculate_complexity(file_path) → float                    │
└────────────────────────────────────────────────────────────────┘
```

### Refactoring Validators

```
FunctionLengthChecker
├── Constants: MAX_FUNCTION_LINES = 50
├── Methods:
│   ├── check_file(file_path: Path) → List[CodeSmell]
│   ├── _extract_functions(tree, source) → List[FunctionInfo]
│   └── _create_smell(file_path, func) → CodeSmell

ClassSizeChecker
├── Constants: MAX_CLASS_LINES = 200, MAX_METHODS = 10
├── Methods:
│   ├── check_file(file_path: Path) → List[CodeSmell]
│   ├── _extract_classes(tree, source) → List[ClassInfo]
│   └── _create_smell(file_path, cls) → CodeSmell

TypeHintCoverageChecker
├── Constants: MIN_TYPE_HINT_COVERAGE = 1.0
├── Methods:
│   ├── check_file(file_path: Path) → Tuple[float, List[CodeSmell]]
│   └── _has_complete_type_hints(node) → bool

CodeDuplicationDetector
├── Constants: DUPLICATION_SIMILARITY_THRESHOLD = 0.8
├── Methods:
│   ├── check_files(file_paths: List[Path]) → List[CodeSmell]
│   ├── _extract_function_bodies(tree, source) → List[Tuple]
│   └── _calculate_similarity(body1, body2) → float
```

---

## Router Layer Architecture

The router layer provides FastAPI endpoints for all services, implementing REST API patterns.

### Main Routers

```
Classification Router (/api/classification)
├── Endpoints:
│   ├── POST /classify
│   │   ├── Input: ClassifyRequest (text, top_k)
│   │   └── Output: ClassificationResult
│   ├── POST /fine-tune
│   │   ├── Input: FineTuneRequest (labeled_data, epochs, batch_size)
│   │   └── Output: TrainingMetrics
│   └── GET /metrics
│       └── Output: ModelMetrics

Quality Router (/api/quality)
├── Endpoints:
│   ├── POST /compute/{resource_id}
│   │   ├── Input: Optional[QualityWeights]
│   │   └── Output: QualityScore
│   ├── GET /monitor/degradation
│   │   ├── Query: time_window_days
│   │   └── Output: List[DegradationReport]
│   └── POST /detect/outliers
│       ├── Query: batch_size
│       └── Output: OutlierDetectionResult

Recommendation Router (/api/recommendations)
├── Endpoints:
│   ├── GET /user/{user_id}
│   │   ├── Query: limit, strategy
│   │   └── Output: List[Recommendation]
│   ├── GET /resource/{resource_id}
│   │   ├── Query: limit
│   │   └── Output: List[Recommendation]
│   └── GET /graph/{resource_id}
│       ├── Query: limit, graph_weight
│       └── Output: List[Recommendation]

Search Router (/api/search)
├── Endpoints:
│   ├── POST /hybrid
│   │   ├── Input: HybridSearchRequest
│   │   └── Output: SearchResults with facets
│   ├── GET /fts
│   │   ├── Query: q, filters, limit, offset
│   │   └── Output: SearchResults
│   └── GET /vector
│       ├── Query: q, limit, offset
│       └── Output: SearchResults
```

---

## Creating a New Module

1. Create module directory:
```bash
mkdir -p app/modules/new_module
```

2. Create module files:
```python
# __init__.py
from .router import router
from .service import create_item, get_item
from .schema import ItemCreate, ItemResponse
from .model import Item

__version__ = "1.0.0"
__domain__ = "new_module"
```

3. Register router in main.py:
```python
from app.modules.new_module import router as new_module_router
app.include_router(new_module_router, prefix="/new-module", tags=["new-module"])
```

4. Register event handlers:
```python
# In handlers.py
from app.shared.event_bus import event_bus

def register_handlers():
    event_bus.subscribe("some.event", handle_some_event)

# Call in __init__.py or main.py
register_handlers()
```

---

## Module Isolation Rules

1. **No cross-module imports** - Use events or shared kernel
2. **String-based relationships** - Avoid circular imports in models
3. **Independent testing** - Each module has its own tests
4. **Clear public interface** - Export only what's needed in `__init__.py`
5. **Self-contained migrations** - Module-specific schema changes

---

## Legacy Services Migration Status

Services being migrated to modules:

| Service | Target Module | Status |
|---------|---------------|--------|
| `resource_service.py` | Resources | ✅ Complete |
| `collection_service.py` | Collections | ✅ Complete |
| `search_service.py` | Search | ✅ Complete |
| `taxonomy_service.py` | Taxonomy | 🔄 Planned |
| `annotation_service.py` | Annotations | 🔄 Planned |
| `quality_service.py` | Quality | 🔄 Planned |
| `graph_service.py` | Graph | 🔄 Planned |
| `recommendation_service.py` | Recommendations | 🔄 Planned |

---

## Schema Layer Architecture

The schema layer defines Pydantic models for API request/response validation.

```
SearchQuery (Pydantic)
├── Attributes:
│   ├── text: str
│   ├── limit: int = 20
│   ├── offset: int = 0
│   ├── hybrid_weight: float = 0.5
│   ├── filters: Optional[SearchFilters]
│   └── sort_by: Optional[str]

SearchFilters (Pydantic)
├── Attributes:
│   ├── classification_code: Optional[List[str]]
│   ├── type: Optional[List[str]]
│   ├── language: Optional[List[str]]
│   ├── year_min: Optional[int]
│   └── year_max: Optional[int]

ResourceCreate (Pydantic)
├── Attributes:
│   ├── title: str
│   ├── description: Optional[str]
│   ├── creator: Optional[str]
│   ├── subject: Optional[List[str]]
│   ├── type: str
│   ├── language: str
│   └── identifier: str

ResourceUpdate (Pydantic)
├── Attributes:
│   ├── title: Optional[str]
│   ├── description: Optional[str]
│   ├── creator: Optional[str]
│   ├── subject: Optional[List[str]]
│   └── classification_code: Optional[str]

ClassifyRequest (Pydantic)
├── Attributes:
│   ├── text: str
│   └── top_k: int = 5

AnnotationCreate (Pydantic)
├── Attributes:
│   ├── resource_id: UUID
│   ├── content: str
│   ├── annotation_type: str
│   ├── start_position: Optional[int]
│   ├── end_position: Optional[int]
│   └── tags: Optional[List[str]]

RecommendationRequest (Pydantic)
├── Attributes:
│   ├── user_id: str
│   ├── limit: int = 10
│   └── strategy: str = "hybrid"
```

---

## Configuration Layer Architecture

The configuration layer manages application settings and environment variables.

```
Settings (Pydantic BaseSettings)
├── Attributes:
│   ├── DATABASE_URL: str
│   ├── SECRET_KEY: str
│   ├── API_VERSION: str = "v2.0"
│   ├── DEBUG: bool = False
│   ├── LOG_LEVEL: str = "INFO"
│   ├── CORS_ORIGINS: List[str]
│   ├── MAX_UPLOAD_SIZE: int
│   ├── EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"
│   ├── CLASSIFICATION_MODEL: str = "distilbert-base-uncased"
│   ├── ENABLE_GPU: bool = True
│   ├── CACHE_TTL: int = 3600
│   └── RATE_LIMIT: int = 100
├── Methods:
│   ├── get_database_url() → str
│   ├── is_production() → bool
│   └── validate_settings() → None

get_settings()
├── Returns: Settings (singleton)
└── Usage: settings = get_settings()
```

---

## Utility Layer Architecture

The utility layer provides helper functions and shared utilities across the application.

### Text Processing Utilities

```
text_processor module
├── Functions:
│   ├── readability_scores(text: str) -> Dict[str, float]
│   │   ├── Returns: flesch_reading_ease, flesch_kincaid_grade, etc.
│   │   └── Uses: textstat library
│   ├── extract_keywords(text: str, top_k: int) -> List[str]
│   │   ├── Returns: List of top keywords
│   │   └── Uses: TF-IDF or RAKE
│   ├── clean_text(text: str) -> str
│   │   ├── Removes: HTML tags, special characters
│   │   └── Returns: Cleaned text
│   ├── tokenize(text: str) -> List[str]
│   │   └── Returns: List of tokens
│   └── normalize_text(text: str) -> str
│       ├── Lowercases, removes punctuation
│       └── Returns: Normalized text

content_extractor module
├── Functions:
│   ├── extract_from_pdf(file_path: Path) -> str
│   │   └── Uses: PyPDF2 or pdfplumber
│   ├── extract_from_html(html: str) -> str
│   │   └── Uses: BeautifulSoup
│   ├── extract_metadata(file_path: Path) -> Dict[str, Any]
│   │   └── Returns: Title, author, date, etc.
│   └── extract_citations(text: str) -> List[str]
│       └── Returns: List of citation strings
```

### Performance Monitoring Utilities

```
performance_monitoring module
├── Classes:
│   └── PerformanceMonitor
│       ├── Attributes:
│       │   ├── metrics: Dict[str, List[float]]
│       │   └── start_times: Dict[str, float]
│       ├── Methods:
│       │   ├── start_timer(name: str) -> None
│       │   ├── stop_timer(name: str) -> float
│       │   ├── record_metric(name: str, value: float) -> None
│       │   ├── get_average(name: str) -> float
│       │   ├── get_percentile(name: str, percentile: float) -> float
│       │   └── get_summary() -> Dict[str, Any]
│
├── Decorators:
│   ├── @time_function
│   │   └── Measures function execution time
│   └── @log_performance
│       └── Logs performance metrics

recommendation_metrics module
├── Functions:
│   ├── precision_at_k(predictions, ground_truth, k) -> float
│   ├── recall_at_k(predictions, ground_truth, k) -> float
│   ├── ndcg_at_k(predictions, ground_truth, k) -> float
│   ├── mean_average_precision(predictions, ground_truth) -> float
│   └── hit_rate_at_k(predictions, ground_truth, k) -> float
```

---

## ML Monitoring Architecture

The ML monitoring layer provides observability for machine learning models and predictions.

```
PredictionMonitor
├── Attributes:
│   ├── predictions: List[Dict[str, Any]]
│   ├── metrics: Dict[str, float]
│   └── alert_thresholds: Dict[str, float]
├── Methods:
│   ├── __init__()
│   ├── log_prediction(model_name, input_data, prediction, confidence, latency_ms) -> None
│   ├── get_metrics(window_minutes: int) -> Dict[str, Any]
│   ├── get_prediction_distribution() -> Dict[str, int]
│   ├── get_average_confidence() -> float
│   ├── get_average_latency() -> float
│   ├── check_drift(baseline_distribution) -> bool
│   └── export_metrics() -> Dict[str, Any]

AlertManager
├── Attributes:
│   ├── alerts: List[Alert]
│   └── notification_channels: List[NotificationChannel]
├── Methods:
│   ├── __init__()
│   ├── create_alert(alert_type, severity, message, metadata) -> Alert
│   ├── check_thresholds(metrics: Dict[str, float]) -> List[Alert]
│   ├── send_notification(alert: Alert) -> None
│   └── get_active_alerts() -> List[Alert]

HealthCheck
├── Methods:
│   ├── check_model_health(model_name: str) -> Dict[str, Any]
│   ├── check_database_health() -> Dict[str, Any]
│   ├── check_service_health(service_name: str) -> Dict[str, Any]
│   └── get_system_health() -> Dict[str, Any]

JSONLogging
├── Functions:
│   ├── setup_json_logging(log_level: str) -> None
│   ├── log_structured(level, message, **kwargs) -> None
│   └── get_logger(name: str) -> logging.Logger
```

---

## Complete System Flow Diagrams

### Classification Flow

```
User Request
    ↓
FastAPI Router (POST /api/classification/classify)
    ↓
MLClassificationService.predict(text, top_k)
    ↓
    ├─→ _load_model() [if not loaded]
    │   ├─→ _import_ml_libraries()
    │   ├─→ _load_tokenizer()
    │   ├─→ _determine_checkpoint_path()
    │   ├─→ _load_model_from_checkpoint()
    │   └─→ _move_model_to_device()
    │
    ├─→ Tokenize input text
    ├─→ Model inference (forward pass)
    ├─→ Apply sigmoid activation
    ├─→ Sort by confidence
    ├─→ Take top_k predictions
    │
    └─→ Create ClassificationResult domain object
        ├─→ ClassificationPrediction objects
        └─→ Validate all predictions
    ↓
PredictionMonitor.log_prediction()
    ↓
Return ClassificationResult
    ↓
Convert to JSON response
    ↓
User receives predictions
```

### Quality Assessment Flow

```
User Request
    ↓
FastAPI Router (POST /api/quality/compute/{resource_id})
    ↓
QualityService.compute_quality(resource_id, weights)
    ↓
    ├─→ Validate weights
    ├─→ Query Resource from database
    │
    ├─→ _compute_accuracy_dimension(resource)
    ├─→ _compute_completeness_dimension(resource)
    ├─→ _compute_consistency_dimension(resource)
    ├─→ _compute_timeliness_dimension(resource)
    └─→ _compute_relevance_dimension(resource)
    ↓
Create QualityScore domain object
    ├─→ Validate all dimensions (0.0-1.0)
    └─→ Calculate overall_score()
    ↓
_update_resource_quality_fields(resource, ...)
    ↓
Database commit
    ↓
Return QualityScore
    ↓
Convert to JSON response
    ↓
User receives quality assessment
```

### Recommendation Flow

> **Removed in Phase 21.** The Recommendations module (NCF, strategy pattern, collaborative filtering) was physically removed because NCF is mathematically useless for N=1 users. See ADR-008.

### Search Flow (Three-Way Hybrid)

```
User Request
    ↓
FastAPI Router (POST /api/search/three-way)
    ↓
HybridSearchQuery(db, query, enable_reranking, adaptive_weights)
    ↓
execute()
    ↓
    ├─→ _ensure_tables_exist()
    ├─→ _check_services_available()
    ├─→ _analyze_query() → query characteristics
    │
    ├─→ PHASE 1: _execute_retrieval_phase()
    │   ├─→ _search_fts5() → FTS5 keyword results
    │   ├─→ _search_dense() → Dense vector results
    │   └─→ _search_sparse() → Sparse vector results
    │   └─→ Return RetrievalCandidates
    │
    ├─→ PHASE 2: _execute_fusion_phase(candidates)
    │   ├─→ _compute_weights() → adaptive RRF weights
    │   ├─→ ReciprocalRankFusionService.fuse_results()
    │   ├─→ _compute_method_contributions()
    │   └─→ Return FusedCandidates
    │
    ├─→ PHASE 3: _execute_reranking_phase(fused)
    │   ├─→ RerankingService.rerank() [if enabled]
    │   └─→ Return final ranked results
    │
    ├─→ _fetch_paginated_resources(results)
    ├─→ _compute_facets(results)
    └─→ _generate_snippets(resources)
    ↓
Return (resources, total, facets, snippets, metadata)
    ↓
Convert to JSON response
    ↓
User receives search results
```

### Refactoring Detection Flow

```
Developer runs CLI
    ↓
refactoring.cli.detect_smells(directory_path)
    ↓
CodeSmellDetector()
    ├─→ Initialize validators:
    │   ├─→ FunctionLengthChecker()
    │   ├─→ ClassSizeChecker()
    │   ├─→ TypeHintCoverageChecker()
    │   └─→ CodeDuplicationDetector()
    ↓
analyze_directory(dir_path)
    ↓
    For each Python file:
    ├─→ analyze_file(file_path)
    │   ├─→ FunctionLengthChecker.check_file()
    │   │   ├─→ Parse AST
    │   │   ├─→ _extract_functions()
    │   │   ├─→ _analyze_function()
    │   │   └─→ _create_smell() if violation
    │   │
    │   ├─→ ClassSizeChecker.check_file()
    │   │   ├─→ Parse AST
    │   │   ├─→ _extract_classes()
    │   │   ├─→ _analyze_class()
    │   │   └─→ _create_smell() if violation
    │   │
    │   ├─→ TypeHintCoverageChecker.check_file()
    │   │   ├─→ Parse AST
    │   │   ├─→ _has_complete_type_hints()
    │   │   └─→ _create_smell() if missing
    │   │
    │   ├─→ _detect_feature_envy()
    │   ├─→ _detect_long_parameter_lists()
    │   ├─→ _count_lines()
    │   └─→ _calculate_complexity()
    │   ↓
    │   Return SmellReport
    │
    └─→ CodeDuplicationDetector.check_files(all_files)
        ├─→ _extract_function_bodies()
        ├─→ Compare all pairs
        ├─→ _calculate_similarity()
        └─→ _create_smell() if duplicate
    ↓
prioritize_smells(reports)
    ├─→ Sort by severity (HIGH, MEDIUM, LOW)
    └─→ Return PrioritizedSmells
    ↓
generate_summary_report(reports)
    ↓
Display results to developer
```

---

## Related Documentation

- [Architecture Overview](overview.md) - System design
- [Event System](event-system.md) - Event-driven communication
- [Database](database.md) - Schema and models
- [Design Decisions](decisions.md) - ADRs
