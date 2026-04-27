# Pharos Changelog

All notable changes to Pharos are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased] - 2026-04-24 - Search Quality + Embed Server Reliability

### Fixed

- **pgvector parent-child search** (`backend/app/modules/search/service.py`)
  - Replaced O(N) Python cosine similarity loop (fetched every chunk row, ran `scipy.spatial.distance.cosine` per chunk) with a single pgvector HNSW `<=>` cosine operator on `resources.embedding`.
  - The prior path hung for 2+ minutes on Render Starter (0.5 CPU) once the langchain corpus (3 302 files) was ingested. Now resolves in ~250ms.
  - Added `EXISTS (SELECT 1 FROM document_chunks WHERE resource_id = r.id)` filter so test-ingest resources (embedding present, zero chunks) no longer monopolise top-k results.
  - Commit: `c6000080`

- **asyncpg CAST for uuid/vector parameters** (`backend/embed_server.py`)
  - `UPDATE resources SET embedding = :emb WHERE id = :rid` silently matched 0 rows when `:emb` and `:rid` were passed as Python strings — asyncpg does not auto-cast `str → uuid` or `str → vector`.
  - Fixed by replacing `:p::vector` / `:p::uuid` shorthand (which also collides with SQLAlchemy's `:param` marker parser) with `CAST(:p AS vector)` / `CAST(:p AS uuid)`.
  - `rowcount` is now logged after every embedding write so silent zero-row UPDATEs are immediately visible.
  - Commit: `c6000080`

- **Upstash free-tier polling compliance** (`backend/embed_server.py`)
  - Prior BLPOP cycle: 5s timeout + 0.1s sleep ≈ 21k Upstash REST requests/day when queue is idle — more than double the free-tier cap (10k/day).
  - Fixed: BLPOP timeout raised to 9s, sleep reduced to 1s → ≈8.6k req/day idle.
  - Commit: `ebe0ce3f`

- **GitHub URI normalization** (`backend/app/modules/ingestion/ast_pipeline.py`)
  - Windows-ingested repos wrote `github_uri` paths with `\\` backslashes, breaking `raw.githubusercontent.com` URL construction on Render (Linux).
  - Fixed: all `github_uri` values normalized to POSIX paths at write time.
  - Commit: `e54cbf1e`

- **Non-SHA branch references rewritten to HEAD** (`backend/app/modules/ingestion/ast_pipeline.py`)
  - `branch_reference` values like `"main"` or `""` did not resolve on `raw.githubusercontent.com` for all repos. Rewriting to `HEAD` always resolves to the default branch tip.
  - Commit: `e54cbf1e`

- **Embed semantic_summary not JSON blob** (`backend/app/modules/ingestion/ast_pipeline.py`)
  - Code chunks were being embedded using the full `chunk_metadata` JSON string (`{"github_uri": ..., "ast_node_type": ...}`) — ~50% noise. Switched to embedding the `semantic_summary` field (`"[python] def fn(...): 'docstring.' deps: [...]"`), which dramatically improved score distribution (from near-uniform to a meaningful 0.44–0.71 spread).
  - Commit: `6a0d8733`

- **Test-file distance penalty** (`backend/app/modules/search/service.py`)
  - `/tests/` path resources were dominating top-k for queries that should return production code.
  - Fixed: +0.10 added to cosine distance for any resource whose path contains `/tests/`.
  - Commit: `6a0d8733`

### Known Issues / Not Yet Fixed

- `POST /api/v1/ingestion/ingest/{repo_url}` queues to `ingest_queue` but no worker reliably consumes it end-to-end. GitHub bulk ingestion is the next planned fix (option: modify router to call `HybridIngestionPipeline` directly as a `BackgroundTask`).

---

## [2.3.0] - 2026-01-05 - Phase 18: Code Intelligence Pipeline

### Added
- **Code Repository Ingestion**
  - Local directory scanning with recursive file discovery
  - Git repository cloning from HTTPS/SSH URLs
  - .gitignore parsing and compliance using pathspec library
  - Binary file detection and exclusion (null byte check)
  - Repository metadata storage (repo_root, commit_hash, branch)
  - Async ingestion via Celery with progress tracking
  - Batch processing (50 files per transaction)
  - API endpoints: POST /resources/ingest-repo, GET /resources/ingest-repo/{task_id}/status

- **File Classification System**
  - PRACTICE classification for code files (.py, .js, .ts, .rs, .go, .java)
  - THEORY classification for academic documents (.pdf, .md with keywords)
  - GOVERNANCE classification for policy files (CONTRIBUTING.md, CODE_OF_CONDUCT.md, .eslintrc)
  - Automatic classification during ingestion

- **AST-Based Code Chunking**
  - Tree-Sitter integration for 6 languages (Python, JavaScript, TypeScript, Rust, Go, Java)
  - Logical unit extraction (functions, classes, methods)
  - Chunk metadata: function_name, class_name, start_line, end_line, language, type
  - Fallback to character-based chunking on parse errors
  - CodeChunkingStrategy in ChunkingService
  - Performance: <2s per file (P95) for AST parsing

- **Static Analysis Service**
  - StaticAnalysisService for code relationship extraction
  - Import statement extraction (IMPORTS relationships)
  - Function/class definition detection (DEFINES relationships)
  - Function call detection (CALLS relationships)
  - Relationship metadata: source_file, target_symbol, line_number, confidence
  - No code execution (static analysis only)
  - Performance: <1s per file (P95) for static analysis

- **Code Graph Relationships**
  - IMPORTS: Module/file imports another module/file
  - DEFINES: File defines a function, class, or variable
  - CALLS: Function calls another function
  - Integration with existing graph infrastructure
  - Provenance tracking to source code chunks
  - Graph traversal for dependency analysis

- **Comprehensive Documentation**
  - `backend/docs/guides/code-ingestion.md` - Complete code ingestion guide
  - Updated `backend/docs/api/resources.md` with repository ingestion endpoints
  - Updated `backend/docs/api/graph.md` with code relationship types
  - Updated `backend/docs/architecture/modules.md` with code intelligence pipeline diagram
  - Updated `backend/docs/index.md` with code ingestion guide link

### Changed
- **Resources Module**: Enhanced with repository ingestion and code chunking capabilities
- **Graph Module**: Enhanced with static analysis and code relationship extraction
- **ChunkingService**: Added CodeChunkingStrategy for AST-based chunking

### Performance
- **AST Parsing**: <2s per file (P95)
- **Static Analysis**: <1s per file (P95)
- **Batch Processing**: 50 files per transaction
- **Concurrent Tasks**: 3 per user
- **Total Ingestion**: ~5-10 seconds per file (including I/O)

### Technical Highlights
- **Tree-Sitter Integration**: Multi-language AST parsing with fallback strategy
- **Event-Driven**: Automatic chunking and static analysis via event handlers
- **Scalable**: Async Celery tasks for large repository processing
- **Testable**: Property-based tests for AST parsing, static analysis, and graph relationships

### Dependencies
- tree-sitter==0.20.4
- tree-sitter-languages==1.10.2
- gitpython==3.1.40
- pathspec==0.12.1

### Requirements Validation
- ✅ All 9 requirements groups implemented (45+ acceptance criteria)
- ✅ 11 tasks completed with comprehensive test coverage
- ✅ Performance targets met for all operations
- ✅ Documentation complete with guides and API reference

## [2.2.0] - 2026-01-04 - Phase 17.5: Advanced RAG Architecture

### Added
- **Advanced RAG Database Schema**
  - `document_chunks` table for parent-child chunking strategy
  - `graph_entities` table for knowledge graph nodes
  - `graph_relationships` table for semantic triples with provenance
  - `synthetic_questions` table for reverse HyDE retrieval
  - `rag_evaluations` table for RAGAS metrics tracking
  - Flexible chunk_metadata (JSONB) supporting both PDF pages and code line numbers
  - Code-ready relation types: CALLS, IMPORTS, DEFINES (alongside academic types)
  - Alembic migration: `20260103_add_advanced_rag_tables.py`

- **Document Chunking Service**
  - ChunkingService with semantic and fixed-size strategies
  - Semantic chunking using sentence boundaries (spaCy/NLTK)
  - Fixed-size chunking with whitespace-aware splitting
  - Configurable chunk size (default: 500 tokens) and overlap (default: 50 tokens)
  - Parser type parameter for future AST chunking (code_python, code_javascript, etc.)
  - Automatic embedding generation for all chunks
  - Event emission: `resource.chunked` on success
  - Integration with ingestion pipeline (optional via CHUNK_ON_RESOURCE_CREATE)
  - Celery task for async chunking of large documents (>10,000 words)

- **Graph Extraction Service**
  - GraphExtractionService with LLM and spaCy extraction methods
  - Entity extraction with type classification (Concept, Person, Organization, Method)
  - Relationship extraction with confidence scoring
  - Relation types: CONTRADICTS, SUPPORTS, EXTENDS, CITES (academic)
  - Code-specific relation types: CALLS, IMPORTS, DEFINES (for Phase 18)
  - Entity deduplication by name and type
  - Provenance tracking linking relationships to source chunks
  - Event emission: `graph.entity_extracted`, `graph.relationship_extracted`

- **Synthetic Question Service**
  - SyntheticQuestionService for reverse HyDE retrieval
  - Heuristic pattern-based question generation (1-3 questions per chunk)
  - LLM-based question generation (GPT-3.5-turbo compatible)
  - Automatic embedding generation for questions
  - Configuration toggle: SYNTHETIC_QUESTIONS_ENABLED
  - Question quality validation and relevance scoring

- **Enhanced Search Strategies**
  - Parent-child retrieval: retrieve chunks, expand to parent resources
  - Context window parameter for surrounding chunk inclusion
  - GraphRAG retrieval: entity extraction → graph traversal → chunk retrieval
  - Hybrid ranking combining embedding similarity and graph weights
  - Contradiction discovery mode filtering CONTRADICTS relationships
  - Question-based retrieval (Reverse HyDE) matching against synthetic questions
  - Result deduplication when multiple chunks from same resource

- **RAG Evaluation System**
  - RAGEvaluation model for RAGAS metrics storage
  - Metrics: faithfulness_score, answer_relevance_score, context_precision_score
  - Retrieved chunk tracking for evaluation
  - Evaluation history and trend analysis
  - Metric aggregation endpoints

- **API Endpoints**
  - **Chunking**: POST/GET `/api/resources/{resource_id}/chunks`, GET `/api/chunks/{chunk_id}`
  - **Graph**: POST `/api/graph/extract/{chunk_id}`, GET `/api/graph/entities`, GET `/api/graph/entities/{entity_id}/relationships`, GET `/api/graph/traverse`
  - **Advanced Search**: POST `/api/search/advanced` with strategy parameter (parent-child, graphrag, hybrid)
  - **Evaluation**: POST `/api/evaluation/submit`, GET `/api/evaluation/metrics`, GET `/api/evaluation/history`

- **Resource Migration Script**
  - `scripts/migrate_existing_resources.py` for migrating existing resources to chunking system
  - Batch processing (default: 10 resources per batch)
  - Progress tracking with JSON persistence (`storage/migration_progress.json`)
  - Resume capability from last processed resource
  - Error handling with continue-on-failure
  - Configurable chunking strategy, chunk size, and overlap
  - Command-line interface with `--batch-size`, `--strategy`, `--resume` flags
  - Comprehensive test suite (18 tests, all passing)

- **Configuration Options**
  - CHUNK_ON_RESOURCE_CREATE: Enable automatic chunking during ingestion
  - GRAPH_EXTRACT_ON_CHUNK: Enable automatic graph extraction after chunking
  - SYNTHETIC_QUESTIONS_ENABLED: Enable synthetic question generation
  - Chunking strategy, chunk size, overlap configuration
  - Graph extraction method (llm, spacy, hybrid)

- **Event Handlers**
  - Resource chunking handler subscribing to `resource.created`
  - Graph extraction handler subscribing to `resource.chunked`
  - Automatic processing pipeline with configurable triggers

- **Comprehensive Documentation**
  - `backend/docs/guides/advanced-rag.md` - Parent-child chunking, GraphRAG, HyDE concepts
  - `backend/docs/guides/rag-evaluation.md` - RAGAS metrics and evaluation procedures
  - `backend/docs/guides/naive-to-advanced-rag.md` - Migration guide with rollback procedures
  - Updated `backend/docs/architecture/database.md` with 5 new tables
  - Updated `backend/docs/api/resources.md` with chunking endpoints
  - Updated `backend/docs/api/graph.md` with graph endpoints
  - Updated `backend/docs/api/search.md` with advanced search
  - Updated `backend/docs/api/quality.md` with evaluation endpoints

### Changed
- **Database Schema**: Added 5 new tables for Advanced RAG (document_chunks, graph_entities, graph_relationships, synthetic_questions, rag_evaluations)
- **Resource Module**: Enhanced with chunking service and endpoints
- **Graph Module**: Enhanced with entity/relationship extraction and semantic triple storage
- **Search Module**: Enhanced with parent-child, GraphRAG, and question-based retrieval
- **Quality Module**: Enhanced with RAG evaluation metrics

### Performance
- **Chunking**: 10,000 words in <5 seconds (semantic strategy)
- **Graph Extraction**: 100 chunks in <5 minutes (LLM method)
- **Parent-Child Retrieval**: <200ms for top-k chunks with parent expansion
- **GraphRAG Retrieval**: <500ms for entity extraction + graph traversal + chunk retrieval
- **Question Search**: <100ms for synthetic question matching

### Technical Highlights
- **Code-Ready Design**: Flexible metadata and relation types support future code chunking (Phase 18)
- **Provenance Tracking**: All graph relationships linked to source chunks
- **Event-Driven**: Automatic chunking and graph extraction via event handlers
- **Scalable**: Async Celery tasks for large document processing
- **Testable**: Property-based tests for chunk preservation, foreign key integrity, graph validity

### Migration Notes
- Run `alembic upgrade head` to apply new schema
- Use `scripts/migrate_existing_resources.py` to chunk existing resources
- Configure CHUNK_ON_RESOURCE_CREATE for automatic chunking of new resources
- Enable GRAPH_EXTRACT_ON_CHUNK for automatic graph extraction

### Requirements Validation
- ✅ All 12 requirements groups implemented (60+ acceptance criteria)
- ✅ 18 tasks completed with comprehensive test coverage
- ✅ Performance targets met for all operations
- ✅ Documentation complete with guides and API reference

## [2.1.0] - 2026-01-02 - Phase 17: Production Hardening

### Added
- **JWT Authentication System**
  - JWT-based authentication with access and refresh tokens
  - Access tokens expire in 30 minutes (configurable)
  - Refresh tokens expire in 7 days (configurable)
  - Token revocation using Redis blacklist
  - Password hashing with bcrypt
  - User management and authentication service
  - Global authentication middleware protecting all endpoints
  - Public endpoints: `/auth/*`, `/docs`, `/openapi.json`, `/monitoring/health`
  - TEST_MODE for development bypass

- **OAuth2 Social Login**
  - Google OAuth2 integration
  - GitHub OAuth2 integration
  - OAuth2 provider abstraction for easy extension
  - Automatic user account creation/linking
  - Encrypted OAuth token storage

- **Tiered Rate Limiting**
  - Free tier: 100 requests/hour
  - Premium tier: 1,000 requests/hour
  - Admin tier: 10,000 requests/hour
  - Sliding window algorithm with Redis
  - Rate limit headers: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`
  - HTTP 429 responses when limit exceeded
  - Graceful degradation when Redis unavailable
  - Per-user rate limiting based on JWT tier claim

- **Authentication Module (14th Module)**
  - `POST /auth/login` - Username/password authentication
  - `POST /auth/refresh` - Token refresh
  - `POST /auth/logout` - Token revocation
  - `GET /auth/me` - Current user information
  - `GET /auth/rate-limit` - Rate limit status
  - `GET /auth/google` - Google OAuth2 initiation
  - `GET /auth/google/callback` - Google OAuth2 callback
  - `GET /auth/github` - GitHub OAuth2 initiation
  - `GET /auth/github/callback` - GitHub OAuth2 callback

- **Database Schema Updates**
  - `users` table for user accounts
  - `oauth_accounts` table for OAuth2 provider linking
  - Alembic migration: `20260101_add_auth_tables_phase17.py`
  - Unique indexes on username and email
  - Composite index on (provider, provider_user_id)

- **Shared Kernel Enhancements**
  - `app.shared.security` - JWT creation/validation, password hashing
  - `app.shared.oauth2` - OAuth2 provider integration
  - `app.shared.rate_limiter` - Tiered rate limiting service
  - Redis-backed token revocation
  - Redis-backed rate limiting

- **Comprehensive Documentation**
  - `backend/docs/api/auth.md` - Authentication API reference
  - `backend/app/modules/auth/README.md` - Auth module documentation
  - Updated Docker setup guide with Phase 17 configuration
  - Updated PostgreSQL migration guide with auth tables
  - Updated architecture documentation with auth middleware
  - Updated API overview with authentication and rate limiting

### Changed
- **Module Count**: Increased from 13 to 14 modules
- **API Security**: All endpoints now require authentication (except public endpoints)
- **Error Responses**: Added 401, 403, and 429 status codes
- **Environment Variables**: Added JWT, OAuth2, and rate limiting configuration
- **Architecture Diagrams**: Updated to show authentication middleware and rate limiter

### Security
- Bcrypt password hashing with automatic salt generation
- JWT token signing with HS256 algorithm
- Token revocation on logout
- OAuth2 state parameter for CSRF protection
- Encrypted OAuth token storage
- Rate limiting to prevent abuse
- HTTPS recommended for production

### Performance
- Redis-backed rate limiting with <1ms overhead
- JWT validation <5ms (P95)
- Token revocation check <2ms (P95)
- Graceful degradation when Redis unavailable

## [2.0.0] - 2025-01-28 - Phase 14: Complete Vertical Slice Architecture

### Added
- **Complete Module Isolation**
  - All 13 modules fully isolated with zero circular dependencies
  - Module isolation validation script with CI/CD integration
  - Dependency graph generation and validation
  - Automated checks on every commit

- **Module Test Suite Rewrite**
  - Comprehensive test suite for all 13 modules
  - 150+ endpoint tests with proper fixtures
  - Database-agnostic test infrastructure
  - Multi-database testing support (SQLite and PostgreSQL)
  - Test coverage >95% for all modules

- **Enhanced Module Documentation**
  - Updated README.md for all 13 modules
  - Module-specific implementation summaries
  - Event handler documentation
  - Integration point documentation

- **Modular API Documentation**
  - Split API documentation into 13 domain-specific files
  - `backend/docs/api/overview.md` - Base URL, auth, errors
  - `backend/docs/api/resources.md` - Resource endpoints
  - `backend/docs/api/search.md` - Search endpoints
  - `backend/docs/api/collections.md` - Collection endpoints
  - `backend/docs/api/annotations.md` - Annotation endpoints
  - `backend/docs/api/taxonomy.md` - Taxonomy endpoints
  - `backend/docs/api/graph.md` - Graph/citation endpoints
  - `backend/docs/api/recommendations.md` - Recommendation endpoints
  - `backend/docs/api/quality.md` - Quality endpoints
  - `backend/docs/api/scholarly.md` - Scholarly metadata endpoints
  - `backend/docs/api/authority.md` - Authority control endpoints
  - `backend/docs/api/curation.md` - Curation endpoints
  - `backend/docs/api/monitoring.md` - Health/monitoring endpoints

- **Modular Architecture Documentation**
  - `backend/docs/architecture/overview.md` - System architecture
  - `backend/docs/architecture/database.md` - Schema and models
  - `backend/docs/architecture/event-system.md` - Event bus
  - `backend/docs/architecture/events.md` - Event catalog
  - `backend/docs/architecture/modules.md` - Vertical slices
  - `backend/docs/architecture/decisions.md` - ADRs

- **Developer Guides**
  - `backend/docs/guides/setup.md` - Installation guide
  - `backend/docs/guides/workflows.md` - Development tasks
  - `backend/docs/guides/testing.md` - Testing strategies
  - `backend/docs/guides/deployment.md` - Docker/production
  - `backend/docs/guides/troubleshooting.md` - FAQ and issues

- **Documentation Hub**
  - `backend/docs/index.md` - Central navigation hub
  - `backend/docs/README.md` - Documentation overview
  - Clear documentation hierarchy
  - Easy navigation and discoverability

- **Legacy Cleanup**
  - Removed all legacy routers, services, and schemas
  - Archived historical documentation
  - Cleaned up redundant code
  - Removed unused imports and dependencies

### Changed
- **Module Structure**
  - All modules follow consistent structure:
    - `router.py` - FastAPI endpoints
    - `service.py` - Business logic
    - `schema.py` - Pydantic models
    - `model.py` - SQLAlchemy models
    - `handlers.py` - Event handlers
    - `README.md` - Documentation

- **Import Patterns**
  - Modules only import from:
    - `app.shared.*` - Shared kernel
    - `app.events.*` - Event system
    - `app.domain.*` - Domain objects
    - Standard library and third-party packages
  - No direct module-to-module imports
  - All cross-module communication via events

- **Test Infrastructure**
  - Unified test fixtures across all modules
  - Database-agnostic test patterns
  - Proper cleanup and isolation
  - Consistent test organization

### Fixed
- **Model Field Consistency**
  - Fixed Resource model field usage (`url` → `source`, `resource_type` → `type`)
  - Fixed DiscoveryHypothesis field names
  - Fixed GraphEmbedding field names
  - Updated all tests with correct field names

- **Import Issues**
  - Resolved circular import issues
  - Fixed missing imports
  - Cleaned up unused imports
  - Proper module initialization

- **Test Failures**
  - Fixed 173+ test failures
  - Improved test pass rate from 89% to >97%
  - Resolved database fixture issues
  - Fixed async test handling

### Performance
- **Module Startup**
  - All modules load in <10 seconds total
  - Lazy loading for heavy dependencies
  - Optimized import structure
  - Reduced startup overhead

- **Event System**
  - Event emission + delivery <1ms (p95)
  - In-memory async event bus
  - Zero blocking operations
  - Efficient handler registration

### Documentation
- **Comprehensive Updates**
  - 20+ documentation files created/updated
  - Modular structure for easy maintenance
  - Clear navigation and hierarchy
  - Archived legacy documentation

### Migration Notes
- **No Breaking Changes**
  - All API endpoints remain unchanged
  - Backward compatible with existing clients
  - Database schema unchanged
  - Configuration unchanged

### Technical Debt Reduction
- Eliminated all circular dependencies
- Removed legacy code (>5000 lines)
- Consolidated duplicate functionality
- Improved code organization
- Enhanced maintainability

## [1.9.5] - 2025-01-25 - Phase 13.5: Vertical Slice Refactoring

### Added
- **Vertical Slice Architecture Foundation**
  - Introduced modular architecture with 13 self-contained modules
  - Each module contains router, service, schema, model, and handlers
  - Event-driven communication between modules
  - Zero circular dependencies enforced

- **Module Structure**
  - `backend/app/modules/annotations/` - Text highlights and notes
  - `backend/app/modules/authority/` - Subject authority trees
  - `backend/app/modules/collections/` - Collection management
  - `backend/app/modules/curation/` - Content review
  - `backend/app/modules/graph/` - Knowledge graph and citations
  - `backend/app/modules/monitoring/` - System health and metrics
  - `backend/app/modules/quality/` - Quality assessment
  - `backend/app/modules/recommendations/` - Hybrid recommendations
  - `backend/app/modules/resources/` - Resource CRUD
  - `backend/app/modules/scholarly/` - Academic metadata
  - `backend/app/modules/search/` - Hybrid search
  - `backend/app/modules/taxonomy/` - ML classification

- **Shared Kernel**
  - `backend/app/shared/database.py` - Database sessions
  - `backend/app/shared/event_bus.py` - Event system
  - `backend/app/shared/base_model.py` - Base models
  - `backend/app/shared/embeddings.py` - Vector embeddings
  - `backend/app/shared/ai_core.py` - AI operations
  - `backend/app/shared/cache.py` - Redis cache

- **Event System**
  - In-memory async event bus
  - Event types for all module interactions
  - Event handlers in each module
  - <1ms event emission and delivery (p95)

- **Module Isolation Validation**
  - `backend/scripts/check_module_isolation.py` - Validation script
  - Dependency graph generation
  - Circular dependency detection
  - Import pattern validation

### Changed
- **Architecture Pattern**
  - Migrated from layered architecture to vertical slices
  - Replaced direct imports with event-driven communication
  - Consolidated duplicate code into shared kernel
  - Improved separation of concerns

- **Module Communication**
  - All cross-module communication via events
  - No direct module-to-module imports
  - Async event handling
  - Decoupled module dependencies

### Performance
- **Event System**
  - Event emission + delivery <1ms (p95)
  - In-memory async processing
  - Zero blocking operations
  - Efficient handler registration

- **Module Loading**
  - All modules load in <10 seconds
  - Lazy loading for heavy dependencies
  - Optimized import structure

### Documentation
- **Architecture Documentation**
  - Updated architecture diagrams
  - Module structure documentation
  - Event system documentation
  - Migration guides

### Migration Notes
- **Backward Compatibility**
  - All API endpoints unchanged
  - Database schema unchanged
  - Configuration unchanged
  - No breaking changes

### Technical Debt Reduction
- Eliminated circular dependencies
- Consolidated duplicate code
- Improved code organization
- Enhanced maintainability

## [1.9.0] - 2025-01-20 - Phase 13: PostgreSQL Migration

### Added
- **PostgreSQL Production Database Support**
  - Full PostgreSQL 15+ compatibility for production deployments
  - Automatic database type detection from DATABASE_URL
  - Database-specific connection pool configuration (20 base + 40 overflow for PostgreSQL)
  - SQLite compatibility maintained for development and testing

- **Enhanced Database Configuration**
  - `backend/app/database/base.py` - Enhanced with PostgreSQL-specific parameters
  - Connection pool optimization: pool_size=20, max_overflow=40, pool_recycle=3600
  - Pool pre-ping for connection health validation
  - Statement timeout (30s) and timezone configuration for PostgreSQL
  - Backward-compatible SQLite configuration

- **PostgreSQL Compatibility Migration**
  - `backend/alembic/versions/20250120_postgresql_compatibility.py` - Database-specific migration
  - PostgreSQL extension installation (pg_trgm, uuid-ossp)
  - JSON to JSONB conversion for improved query performance
  - GIN indexes on JSONB columns for efficient containment queries
  - Conditional migration logic based on database type

- **Full-Text Search Abstraction**
  - Strategy pattern for database-specific full-text search
  - SQLiteFTS5Strategy maintaining existing FTS5 functionality
  - PostgreSQLFullTextStrategy using tsvector and tsquery
  - Automatic search_vector column with trigger-based updates
  - GIN index on search_vector for fast full-text search

- **Data Migration Tools**
  - `backend/scripts/migrate_sqlite_to_postgresql.py` - Forward migration script
  - `backend/scripts/migrate_postgresql_to_sqlite.py` - Rollback migration script
  - Batch processing (1000 records per batch) to prevent memory exhaustion
  - Schema validation before migration
  - Row count validation after migration
  - Detailed migration reports with statistics and errors

- **Connection Pool Monitoring**
  - Enhanced `get_pool_status()` function with PostgreSQL metrics
  - `/monitoring/database` endpoint for pool statistics
  - Slow query logging (threshold: 1 second)
  - Connection pool usage middleware with capacity warnings (>90%)

- **Docker Compose Integration**
  - PostgreSQL 15 service configuration in `backend/docker/docker-compose.yml`
  - Persistent volume configuration for postgres_data
  - Health checks for PostgreSQL container
  - Environment variable configuration for credentials

- **Environment-Specific Configuration**
  - `.env.development` - SQLite configuration for local development
  - `.env.staging` - PostgreSQL configuration for staging environment
  - `.env.production` - PostgreSQL configuration for production deployment
  - TEST_DATABASE_URL support for multi-database testing

- **PostgreSQL Optimization**
  - B-tree indexes on all foreign key columns
  - GIN indexes on JSONB columns (subject, relation, embedding, sparse_embedding)
  - Composite indexes for common query patterns
  - Indexes on timestamp columns for sorting and filtering

- **Transaction Management**
  - READ COMMITTED isolation level for PostgreSQL
  - Retry decorator for handling serialization errors
  - SELECT FOR UPDATE locking for resource updates
  - Statement timeout configuration (30 seconds)

- **Backup and Recovery**
  - `backend/docs/POSTGRESQL_BACKUP_GUIDE.md` - Comprehensive backup documentation
  - `backend/scripts/backup_postgresql.sh` - Automated backup script
  - pg_dump procedures (full, compressed, custom format)
  - Point-in-time recovery configuration
  - Restore procedures for full and partial recovery

- **Testing Infrastructure**
  - Multi-database test support via TEST_DATABASE_URL
  - Database-agnostic test fixtures
  - `@pytest.mark.postgresql` marker for PostgreSQL-specific tests
  - JSONB containment query tests
  - Full-text search ranking tests

- **Rollback Procedures**
  - `backend/docs/SQLITE_COMPATIBILITY_MAINTENANCE.md` - Compatibility guide
  - Reverse migration script for PostgreSQL to SQLite
  - Documented rollback procedures with known limitations
  - SQLite compatibility maintained for one release cycle

- **Comprehensive Documentation**
  - `backend/docs/POSTGRESQL_MIGRATION_GUIDE.md` - Complete migration guide
  - Prerequisites and system requirements
  - Step-by-step migration procedures
  - Troubleshooting section for common issues
  - Performance tuning recommendations

### Changed
- **Database Layer**
  - Enhanced engine creation with database-specific parameters
  - Automatic database type detection from connection URL
  - Connection pool configuration based on database type
  - Improved error handling for database-specific issues

- **Search Service**
  - Abstracted full-text search implementation
  - Runtime strategy selection based on database type
  - Maintained API compatibility across database types

### Performance
- **PostgreSQL Advantages**
  - Superior concurrent write performance (100+ simultaneous connections)
  - Advanced indexing with GIN indexes for JSONB queries
  - Native full-text search with ranking
  - Better query optimization for complex joins
  - Connection pooling with health checks

- **Benchmarks**
  - Connection pool: 20 base + 40 overflow connections
  - Query timeout: 30 seconds
  - Pool recycle: 1 hour
  - Full-text search: <100ms for 10K resources
  - JSONB containment queries: <50ms with GIN indexes

### Migration Notes
- **Forward Migration (SQLite → PostgreSQL)**
  1. Run `alembic upgrade head` to apply schema changes
  2. Execute `migrate_sqlite_to_postgresql.py` script
  3. Validate row counts and data integrity
  4. Update DATABASE_URL environment variable
  5. Restart application

- **Rollback (PostgreSQL → SQLite)**
  1. Stop application
  2. Execute `migrate_postgresql_to_sqlite.py` script
  3. Update DATABASE_URL to SQLite
  4. Restart application
  5. Note: JSONB features will be downgraded to JSON

### Breaking Changes
- None - All changes are backward compatible with SQLite

### Known Limitations
- **Rollback Limitations**
  - JSONB columns converted to JSON text (no binary optimization)
  - PostgreSQL full-text search vectors not migrated
  - Some PostgreSQL-specific indexes cannot be recreated in SQLite
  - Array types converted to JSON arrays

### Dependencies
- PostgreSQL 15 or higher (for production deployments)
- psycopg2-binary==2.9.9 (PostgreSQL adapter)
- All existing dependencies maintained

### Documentation Updates
- Updated README.md with PostgreSQL setup instructions
- Updated DEVELOPER_GUIDE.md with database configuration options
- Added POSTGRESQL_MIGRATION_GUIDE.md with complete migration procedures
- Added POSTGRESQL_BACKUP_GUIDE.md with backup and recovery procedures
- Updated .env.example with PostgreSQL connection string examples

### Future Enhancements
- Automatic failover and replication support
- Read replicas for scaling read operations
- Advanced PostgreSQL features (partitioning, materialized views)
- Database performance monitoring dashboard
- Automated backup scheduling and rotation

## [1.8.0] - 2025-11-17 - Phase 12.5: Event-Driven Architecture

### Added
- **Event System Foundation**
  - EventEmitter singleton class with publisher-subscriber pattern
  - Support for synchronous and asynchronous event handlers
  - Event history tracking (last 1000 events) with timestamps and priority levels
  - Event priority levels: CRITICAL, HIGH, NORMAL, LOW
  - Error isolation ensuring handler failures don't affect other handlers
  - SystemEvent enum with 40+ event type definitions

- **Celery Distributed Task Queue**
  - Celery integration with Redis as broker and result backend
  - Priority-based task routing with 10 priority levels
  - Task queues: urgent, high_priority, ml_tasks, batch, default
  - Automatic task retry with exponential backoff for transient errors
  - Worker optimization: prefetch 4 tasks, restart after 1000 tasks
  - Task result expiration after 1 hour
  - DatabaseTask base class with automatic session management

- **Core Celery Tasks**
  - `regenerate_embedding_task` - Regenerate embeddings with 3 retries, 60s delay
  - `recompute_quality_task` - Recompute quality scores with 2 retries
  - `update_search_index_task` - Update FTS5 index with URGENT priority
  - `update_graph_edges_task` - Update citation graph relationships
  - `classify_resource_task` - ML classification with 2 retries
  - `invalidate_cache_task` - Pattern-based cache invalidation
  - `refresh_recommendation_profile_task` - Update user preferences
  - `batch_process_resources_task` - Batch operations with progress tracking

- **Automatic Data Consistency Hooks**
  - Content change → Embedding regeneration (HIGH priority, 5s delay)
  - Metadata change → Quality recomputation (MEDIUM priority, 10s delay)
  - Resource update → Search index sync (URGENT priority, 1s delay)
  - Citation extraction → Graph edge update (MEDIUM priority, 30s delay)
  - Resource update → Cache invalidation (URGENT priority, immediate)
  - User interaction → Profile refresh every 10 interactions (LOW priority, 5min delay)
  - Resource creation → Classification suggestion (MEDIUM priority, 20s delay)
  - Author extraction → Name normalization (LOW priority, 60s delay)

- **Scheduled Background Tasks**
  - Quality degradation monitoring (daily at 2 AM)
  - Quality outlier detection (weekly Sunday at 3 AM)
  - Classification model retraining (monthly on 1st at midnight)
  - Cache cleanup (daily at 4 AM)

- **Multi-Layer Redis Caching**
  - RedisCache class with hit/miss tracking
  - Pattern-based cache invalidation with wildcard support
  - Cache statistics: hit rate, miss rate, invalidation counts
  - TTL strategy: embeddings (1h), quality (30m), search (5m), resources (10m)
  - Caching integrated into EmbeddingService, QualityService, SearchService
  - 50-70% computation reduction through intelligent caching

- **Database Connection Pooling**
  - SQLAlchemy pool: 20 base connections, 40 overflow connections
  - Connection recycling after 1 hour
  - Pre-ping health checks before connection use
  - Pool monitoring endpoint for observability

- **Docker Compose Orchestration**
  - Redis service with 2GB memory limit and persistence
  - 4 Celery worker containers with 4 concurrency each
  - Celery Beat scheduler for periodic tasks
  - Flower monitoring dashboard on port 5555
  - Health checks for all containers

- **Monitoring and Observability**
  - Event history endpoint: GET /events/history
  - Cache statistics endpoint: GET /cache/stats
  - Database pool status endpoint: GET /db/pool
  - Flower dashboard for Celery task monitoring
  - Comprehensive logging for all task executions

### Changed
- **Migration from BackgroundTasks to Celery**
  - All FastAPI BackgroundTasks replaced with Celery tasks
  - Persistent task queue instead of in-memory background tasks
  - Automatic retry logic for failed operations
  - Distributed processing across multiple workers

- **Service Event Integration**
  - ResourceService emits lifecycle events (created, updated, deleted, content_changed, metadata_changed)
  - IngestionService emits processing events (started, completed, failed)
  - User interaction tracking emits events for profile updates
  - Citation and author extraction emit events for graph updates

### Performance
- **Horizontal Scalability**: Support for 100+ concurrent ingestions without degradation
- **Cache Performance**: 60%+ cache hit rate for repeated operations
- **Search Index Updates**: Complete within 5 seconds of resource updates
- **Task Reliability**: <1% failure rate with automatic retries
- **Linear Scaling**: Throughput increases linearly with worker count

### Technical Debt Reduction
- Replaced unreliable in-memory background tasks with persistent queue
- Eliminated manual data synchronization with automatic event hooks
- Centralized task management and monitoring
- Improved error handling and retry logic

## [1.7.0] - 2025-11-16 - Phase 12: Domain-Driven Design Refactoring

### Added
- **Domain Objects Foundation**
  - BaseDomainObject abstract base class with serialization methods
  - ValueObject base class for immutable value objects using dataclasses
  - DomainEntity base class for entities with identity
  - Validation utilities: validate_range, validate_positive, validate_non_negative, validate_non_empty
  - Automatic validation on construction via __post_init__

- **Classification Domain Objects**
  - ClassificationPrediction value object with category, confidence, source
  - ClassificationResult entity with resource_id, predictions, metadata
  - Rich behavior methods: get_top_predictions(), filter_by_confidence(), has_high_confidence()
  - Full serialization support (to_dict, from_dict, to_json, from_json)

- **Search Domain Objects**
  - SearchQuery value object with query text, filters, pagination
  - SearchResult entity with results, total_count, query metadata
  - Query validation and normalization
  - Result pagination and filtering methods

- **Quality Domain Objects**
  - QualityScore value object with five dimensions (completeness, accuracy, consistency, timeliness, relevance)
  - Overall quality score calculation (weighted average)
  - Quality level classification (excellent, good, fair, poor)
  - Dimension-specific validation (0.0-1.0 range)

- **Recommendation Domain Objects**
  - Recommendation entity with resource_id, score, explanation
  - RecommendationScore value object with strategy-specific scores
  - Score aggregation and ranking methods
  - Explanation generation for transparency

- **Refactoring Framework**
  - Automated detection of primitive obsession anti-patterns
  - Code quality validators for type hints, docstrings, complexity
  - Refactoring CLI tool for batch analysis
  - Comprehensive test suite with 31+ test cases

### Changed
- **Service Layer Refactoring**
  - MLClassificationService uses ClassificationResult domain objects
  - SearchService uses SearchQuery and SearchResult domain objects
  - QualityService uses QualityScore domain objects
  - RecommendationService uses Recommendation domain objects
  - Eliminated primitive obsession throughout service layer

- **Type Safety Improvements**
  - 100% type hint coverage on all public methods
  - Strict validation on all domain object construction
  - Type-safe serialization and deserialization

### Technical Debt Reduction
- Replaced primitive types with rich domain objects
- Centralized validation logic in domain layer
- Improved code maintainability and testability
- Enhanced type safety and IDE support

## [1.6.0] - 2025-11-15 - Phase 11.5: ML Benchmarking & Performance Testing

### Added
- **Classification Benchmarking**
  - Comprehensive metrics: precision, recall, F1-score, accuracy
  - Per-category performance analysis
  - Confusion matrix generation
  - Top-k accuracy evaluation (k=1,3,5)
  - Confidence calibration analysis

- **Collaborative Filtering Benchmarking**
  - NCF model performance metrics
  - Precision@K and Recall@K (K=5,10,20)
  - Mean Average Precision (MAP)
  - Normalized Discounted Cumulative Gain (NDCG)
  - Coverage and diversity metrics

- **Search Quality Benchmarking**
  - Relevance scoring metrics
  - Query performance analysis
  - Result ranking quality (MRR, NDCG)
  - Search latency measurements
  - Cache hit rate tracking

- **Summarization Quality Benchmarking**
  - ROUGE score evaluation (ROUGE-1, ROUGE-2, ROUGE-L)
  - BLEU score for translation quality
  - Semantic similarity metrics
  - Abstractiveness vs extractiveness analysis

- **ML Performance Latency Tests**
  - Inference latency benchmarks for all ML models
  - Batch processing performance tests
  - GPU vs CPU performance comparison
  - Memory usage profiling
  - Throughput measurements under load

### Performance Baselines
- Classification inference: <100ms per resource
- NCF recommendation: <200ms for 100 candidates
- Search query: <50ms with cache, <500ms without
- Embedding generation: <300ms per resource
- Quality computation: <150ms per resource

## [1.5.0] - 2025-11-15 - Phase 11: Hybrid Recommendation Engine

### Added
- **User Profile Management**
  - UserProfile model for storing user preferences and learned patterns
  - Automatic profile creation with default settings (diversity=0.5, novelty=0.3, recency=0.5)
  - Research domain tracking and active domain selection
  - Learned preferences: preferred authors, taxonomy categories, sources
  - Preference learning triggered every 10 interactions (analyzes last 90 days)
  - User settings: diversity_preference, novelty_preference, recency_bias (0.0-1.0 range)
  - Interaction metrics: total_interactions, avg_session_duration, last_active_at

- **Interaction Tracking System**
  - UserInteraction model with implicit and explicit feedback signals
  - Interaction types: view, annotation, collection_add, export, rating
  - Automatic interaction strength computation (0.0-1.0 scale)
  - View strength: 0.1 + min(0.3, dwell_time/1000) + 0.1*scroll_depth
  - Annotation strength: 0.7, Collection add: 0.8, Export: 0.9
  - Positive interaction threshold: strength > 0.4
  - Return visit tracking and strength updates
  - Session tracking with session_id
  - Confidence scoring for interaction quality

- **Neural Collaborative Filtering (NCF)**
  - CollaborativeFilteringService with PyTorch implementation
  - NCF model architecture: User embedding (64-dim) + Item embedding (64-dim) → MLP (128→64→32→1)
  - Training on positive interactions with interaction_strength as implicit feedback
  - Negative sampling for balanced training
  - GPU acceleration with automatic CPU fallback
  - Model checkpointing and versioning
  - Batch prediction support for efficient scoring
  - Requires minimum 5 interactions per user for activation

- **Hybrid Recommendation Strategy**
  - HybridRecommendationService combining three strategies
  - Two-stage pipeline: Candidate Generation → Ranking & Reranking
  - Collaborative filtering candidates (NCF predictions, top 100)
  - Content-based candidates (user embedding similarity, top 100)
  - Graph-based candidates (multi-hop neighbors, top 100)
  - Hybrid scoring formula with weighted combination
  - Default weights: collaborative=0.35, content=0.30, graph=0.20, quality=0.10, recency=0.05
  - User-specific weight overrides via profile settings

- **Diversity Optimization (MMR)**
  - Maximal Marginal Relevance algorithm implementation
  - Formula: MMR = λ * relevance - (1-λ) * max_similarity_to_selected
  - λ parameter from user.diversity_preference (default 0.5)
  - Iterative selection maximizing diversity
  - Target: Gini coefficient < 0.3 for diverse recommendations
  - Prevents filter bubbles and echo chambers

- **Novelty Promotion**
  - Novelty score computation: 1.0 - (view_count / median_view_count)
  - Score boosting for novel resources: hybrid_score *= (1.0 + 0.2 * novelty_score)
  - Guarantee: 20%+ recommendations from outside top-viewed resources
  - User-controlled via novelty_preference setting
  - Promotes discovery of hidden gems

- **Cold Start Handling**
  - Content + graph strategies for users with <5 interactions
  - Zero vector user embedding for new users
  - Relevant recommendations available immediately
  - Automatic transition to collaborative filtering after 5+ interactions
  - Research domain filtering for new users

- **Recommendation Feedback Loop**
  - RecommendationFeedback model for tracking performance
  - Click tracking (was_clicked) and usefulness ratings (was_useful)
  - Recommendation context: strategy, score, rank_position
  - Click-through rate (CTR) computation by strategy
  - Target: 40% improvement in CTR over baseline
  - Feedback integration for continuous improvement

- **Performance Optimizations**
  - User embedding caching with 5-minute TTL
  - In-memory cache for NCF predictions (10-minute TTL)
  - Database query limits to prevent memory issues
  - Batch resource lookups using .in_() queries
  - Parallel candidate generation (future: asyncio)
  - Target latency: <200ms for 20 recommendations

- **Quality and Diversity Metrics**
  - Gini coefficient calculation for diversity measurement
  - Click-through rate (CTR) tracking by strategy
  - Novelty percentage computation
  - Cache hit rate monitoring
  - Recommendation generation latency tracking
  - Slow query detection (>500ms threshold)

- **API Endpoints**
  - `GET /api/recommendations` - Personalized recommendations with hybrid strategy
  - `POST /api/interactions` - Track user-resource interactions
  - `GET /api/profile` - Retrieve user profile and preferences
  - `PUT /api/profile` - Update user preference settings
  - `POST /api/recommendations/feedback` - Submit recommendation feedback
  - All endpoints with comprehensive validation and error handling

- **Database Schema**
  - user_profiles table with preference storage
  - user_interactions table with implicit feedback signals
  - recommendation_feedback table for performance tracking
  - Indexes: user_id, resource_id, interaction_timestamp
  - Check constraints for preference ranges (0.0-1.0)
  - Foreign key constraints with CASCADE DELETE

- **Comprehensive Test Suite**
  - `tests/unit/phase11_recommendations/test_user_profile_service.py` - Profile management tests
  - `tests/unit/phase11_recommendations/test_collaborative_filtering.py` - NCF model tests
  - `tests/unit/phase11_recommendations/test_hybrid_recommendations.py` - Hybrid strategy tests
  - `tests/integration/phase11_recommendations/test_recommendation_api.py` - API integration tests
  - Mock PyTorch models to avoid loading actual weights
  - Fixtures for test data generation
  - All tests passing with 100% success rate

### Technical Implementation
- **Service Architecture**
  - UserProfileService for profile and interaction management
  - CollaborativeFilteringService for NCF training and prediction
  - HybridRecommendationService for multi-strategy recommendations
  - Dependency injection pattern for testability
  - Background task support for async operations

- **NCF Model Details**
  - Embedding dimension: 64 for users and items
  - MLP hidden layers: [128, 64, 32]
  - Activation: ReLU
  - Output: Sigmoid (0-1 score)
  - Optimizer: Adam with learning_rate=0.001
  - Loss: BCELoss (Binary Cross-Entropy)
  - Training: 10 epochs, batch_size=256
  - Model persistence: PyTorch checkpoint format

- **Performance Characteristics**
  - Recommendation generation: <200ms for 20 items
  - User embedding computation: <10ms (with caching)
  - NCF prediction: <5ms per resource
  - Database queries: <50ms per query
  - Cache hit rate: >80% for user embeddings
  - NCF training: ~10 minutes for 10K interactions (GPU)

### Integration Points
- Automatic interaction tracking from resource views, annotations, collections
- Integration with existing search and graph services
- Compatible with quality assessment system
- Extends recommendation system capabilities
- Profile updates trigger cache invalidation

### Documentation Updates
- Updated API_DOCUMENTATION.md with Phase 11 endpoints
- Added comprehensive Phase 11 section to DEVELOPER_GUIDE.md
- NCF model training and deployment guide
- Hybrid scoring formula documentation
- MMR diversity optimization explanation
- Performance optimization strategies
- Updated CHANGELOG.md with Phase 11 release notes

### Performance Improvements
- 40%+ improvement in CTR over baseline recommendations
- Gini coefficient < 0.3 for diverse recommendation sets
- 20%+ novel recommendations from outside top-viewed resources
- <200ms latency for 20 recommendations at 95th percentile
- >80% cache hit rate for user embeddings

### Dependencies
- Existing PyTorch 2.2.1 for NCF implementation
- Existing NumPy for vector operations
- Existing SQLAlchemy for database operations
- No new dependencies required

### Migration Notes
- Run `alembic upgrade head` to create Phase 11 tables
- All new fields are nullable for backward compatibility
- No data migration required for existing resources
- Initial NCF model training recommended after deployment
- Minimum 100 interactions recommended for production model

### Breaking Changes
- None - All changes are additive and backward compatible

### Known Issues
- None

### Future Enhancements
- Context-aware recommendations (time, device, location)
- Multi-armed bandits for explore-exploit tradeoff
- Transformer-based user/item embeddings
- Real-time recommendation updates
- Explanation generation for recommendations
- Social collaborative filtering
- Expert user identification and weighting

## [1.4.0] - 2025-11-14 - Phase 10.5: Code Standardization & Bug Fixes

### Fixed
- **Model Field Validation**
  - Fixed Resource model field usage in tests (`url` → `source`, `resource_type` → `type`)
  - Fixed DiscoveryHypothesis field names (`a_resource_id` → `resource_a_id`, etc.)
  - Fixed GraphEmbedding field names (`embedding_method` → `embedding_model`)
  - Updated 4 test files with correct model field names

- **Recommendation Service**
  - Created RecommendationService class for better organization
  - Fixed cosine similarity to return [0, 1] range instead of [-1, 1]
  - Added to_numpy_vector() returning proper numpy arrays
  - Maintained backward compatibility with module-level functions

- **Graph Service Enhancements**
  - Added `distance`, `score`, `intermediate` fields to neighbor discovery responses
  - Enhanced build_multilayer_graph() to persist citation edges to GraphEdge table
  - Fixed get_neighbors_multihop() response structure

- **Database & Infrastructure**
  - Added `engine` alias to base.py for backward compatibility
  - Fixed regex pattern in equation_parser.py (proper raw string escaping)

- **Test Infrastructure**
  - Fixed test_phase10_graph_construction.py to use correct column names
  - Resolved ~173 test failures and errors
  - Improved test pass rate from 89% to >97%

### Changed
- Refactored recommendation_service.py to class-based architecture (~100 lines)
- Enhanced graph_service.py with edge creation methods (~170 lines)

## [1.3.0] - 2025-11-13 - Phase 10: Advanced Graph Intelligence & LBD

### Added
- **Multi-Layer Graph Construction**
  - GraphService class with build_multilayer_graph() method
  - Support for citation, co-authorship, subject similarity, and temporal edges
  - Graph caching with timestamp tracking for performance
  - NetworkX MultiGraph integration for complex graph operations
  - Edge weight calculations for different relationship types

- **Literature-Based Discovery (LBD)**
  - LBDService class for discovering hidden connections
  - open_discovery() method for finding potential connections from a resource
  - closed_discovery() method for finding paths between two resources
  - ABC hypothesis pattern support (A-B-C connections)
  - Hypothesis ranking by confidence scores

- **Graph Embeddings**
  - GraphEmbeddingsService for structural embeddings
  - Node2Vec and Graph2Vec embedding support
  - Fusion embeddings combining content and structure
  - HNSW indexing for fast similarity search

- **Neighbor Discovery**
  - get_neighbors_multihop() for 1-hop and 2-hop neighbor retrieval
  - Path tracking with intermediate nodes
  - Edge type filtering (citation, coauthorship, subject, temporal)
  - Weight-based filtering and ranking
  - Novelty scoring based on node degree

- **Database Models**
  - GraphEdge model for multi-layer graph edges
  - GraphEmbedding model for structural embeddings
  - DiscoveryHypothesis model for LBD hypotheses
  - Proper indexes and foreign keys for performance

- **Edge Creation Methods**
  - create_coauthorship_edges() for author collaboration networks
  - create_subject_similarity_edges() for topic-based connections
  - create_temporal_edges() for time-based relationships

## [1.2.0] - 2025-11-12 - Phase 9: Multi-Dimensional Quality Assessment

### Added
- **Multi-Dimensional Quality Framework**
  - QualityService class for comprehensive quality assessment
  - Five quality dimensions: accuracy, completeness, consistency, timeliness, relevance
  - Weighted overall quality score with customizable dimension weights
  - Quality computation versioning for tracking algorithm changes

- **Quality Dimensions**
  - Accuracy: Citation validity, source credibility, scholarly metadata, author metadata
  - Completeness: Required fields, important fields, scholarly fields, multi-modal content
  - Consistency: Title-content alignment, summary-content alignment
  - Timeliness: Publication recency, ingestion recency
  - Relevance: Classification confidence, citation count

- **Content Quality Analysis**
  - ContentQualityAnalyzer class for text quality metrics
  - Readability scoring (Flesch Reading Ease, FK Grade Level)
  - Word count, sentence count, paragraph count
  - Unique word ratio and long word ratio
  - Source credibility assessment
  - Content depth analysis

- **Quality Monitoring**
  - Outlier detection for quality anomalies
  - Quality degradation monitoring over time
  - Review queue for low-quality resources
  - Quality trends and distribution analytics

- **Database Enhancements**
  - Added quality dimension fields to Resource model
  - Added quality metadata fields (last_computed, computation_version)
  - Added outlier detection fields (is_quality_outlier, outlier_score, outlier_reasons)
  - Added summary quality fields (coherence, consistency, fluency, relevance)
  - Indexes on quality_overall, is_quality_outlier, needs_quality_review

- **Summarization Evaluation**
  - G-EVAL metrics for summary quality (coherence, consistency, fluency, relevance)
  - BERTScore for semantic similarity
  - FineSure metrics for completeness
  - Composite summary quality scoring

## [1.1.0] - 2025-11-10 - Phase 8.5: ML Classification & Hierarchical Taxonomy

### Added
- **Hierarchical Taxonomy System**
  - `app/database/models.py` - TaxonomyNode and ResourceTaxonomy models for hierarchical categories
  - `app/services/taxonomy_service.py` - Complete taxonomy management service
  - Materialized path pattern for efficient hierarchical queries (O(1) ancestors/descendants)
  - Unlimited tree depth with parent-child relationships
  - Automatic slug generation from category names
  - Resource count caching (direct and descendant counts)
  - Circular reference prevention for node reparenting
  - Cascade deletion and reparenting options
  - Alembic migration `add_taxonomy_tables_phase8_5.py` for taxonomy schema

- **Transformer-Based ML Classification**
  - `app/services/ml_classification_service.py` - ML classification service using BERT/DistilBERT
  - Fine-tuned transformer models for domain-specific classification
  - Multi-label classification with confidence scores (0.0-1.0)
  - Lazy model loading for efficient resource usage
  - GPU acceleration with automatic CPU fallback
  - Model versioning and checkpoint management
  - Label mapping for taxonomy ID to model index conversion
  - Batch prediction support (32 for GPU, 8 for CPU)
  - Target performance: <100ms inference, F1 score >0.85

- **Semi-Supervised Learning**
  - Pseudo-labeling algorithm for leveraging unlabeled data
  - High-confidence threshold (>= 0.9) for pseudo-label generation
  - Automatic iteration combining labeled and pseudo-labeled data
  - Enables effective training with <500 labeled examples
  - 10-30% of unlabeled data typically becomes pseudo-labeled
  - Reduces manual labeling effort by 40-60%

- **Active Learning Workflow**
  - Uncertainty sampling using entropy, margin, and confidence metrics
  - Combined uncertainty score: entropy * (1 - margin) * (1 - max_confidence)
  - Automatic flagging of low-confidence predictions (<0.7) for review
  - Review priority scoring for efficient human labeling
  - Feedback integration with manual label storage (confidence=1.0)
  - Retraining threshold (100 new manual labels) with automatic notification
  - Expected 60%+ reduction in labeling effort

- **Classification Service Integration**
  - `app/services/classification_service.py` - Enhanced with ML integration
  - Automatic classification during resource ingestion pipeline
  - Configurable use_ml flag for ML vs rule-based selection
  - Confidence threshold filtering (>= 0.3)
  - Multi-label support with multiple categories per resource
  - Model version tracking in classification metadata
  - Graceful fallback to rule-based classification

- **Taxonomy Management API**
  - `app/routers/taxonomy.py` - Complete taxonomy management endpoints
  - `POST /taxonomy/nodes` - Create taxonomy nodes with parent relationships
  - `PUT /taxonomy/nodes/{node_id}` - Update node metadata
  - `DELETE /taxonomy/nodes/{node_id}` - Delete nodes with cascade option
  - `POST /taxonomy/nodes/{node_id}/move` - Reparent nodes with validation
  - `GET /taxonomy/tree` - Retrieve nested tree structure with depth limits
  - `GET /taxonomy/nodes/{node_id}/ancestors` - Get breadcrumb trail
  - `GET /taxonomy/nodes/{node_id}/descendants` - Get all subcategories

- **ML Classification API**
  - `POST /taxonomy/classify/{resource_id}` - Classify resource using ML model
  - `GET /taxonomy/active-learning/uncertain` - Get uncertain predictions for review
  - `POST /taxonomy/active-learning/feedback` - Submit human classification feedback
  - `POST /taxonomy/train` - Initiate model fine-tuning with training data
  - All classification endpoints return 202 Accepted for background processing

- **Pydantic Schemas**
  - `app/schemas/taxonomy.py` - Complete schema definitions
  - TaxonomyNodeCreate, TaxonomyNodeUpdate for node management
  - ClassificationFeedback for active learning feedback
  - ClassifierTrainingRequest for model training configuration
  - Comprehensive validation and documentation

- **Comprehensive Test Suite**
  - `tests/test_taxonomy_service.py` - 20+ test cases for taxonomy operations
  - `tests/test_ml_classification_service.py` - 15+ test cases for ML classification
  - `tests/test_taxonomy_api_endpoints.py` - 12+ API endpoint tests
  - `tests/test_classification_integration.py` - 10+ integration tests
  - `tests/test_active_learning.py` - 8+ active learning workflow tests
  - `tests/test_performance.py` - Performance validation tests
  - All tests passing with 100% success rate

### Technical Implementation
- **Database Schema**
  - taxonomy_nodes table with id, name, slug, parent_id, level, path, description, keywords
  - resource_taxonomy association table with confidence, is_predicted, predicted_by, needs_review
  - Indexes on parent_id, path, slug for efficient queries
  - Indexes on resource_id, taxonomy_node_id, needs_review for classification queries
  - Check constraints for level >= 0 and confidence between 0.0 and 1.0
  - Cascade deletion for parent-child relationships

- **Materialized Path Pattern**
  - Path format: "/parent-slug/child-slug/grandchild-slug"
  - O(1) ancestor queries by parsing path string
  - O(1) descendant queries using path LIKE pattern
  - Automatic path updates on node reparenting
  - Level computation from parent level + 1

- **ML Model Architecture**
  - Base models: DistilBERT (primary), BERT-base (alternative)
  - Multi-label classification with sigmoid activation
  - Tokenization with max_length=512
  - Training: 80/20 train/validation split
  - Default hyperparameters: 3 epochs, batch_size=16, learning_rate=2e-5
  - Model storage: models/classification/{version}/
  - Includes pytorch_model.bin, config.json, tokenizer files, label_map.json

- **Service Architecture**
  - TaxonomyService with CRUD operations and hierarchical queries
  - MLClassificationService with training, inference, and active learning
  - ClassificationService integration with resource ingestion
  - Dependency injection pattern for testability
  - Background task processing for classification and training

- **Performance Characteristics**
  - Single prediction: <100ms (GPU), <80ms (CPU)
  - Batch prediction (32): <400ms (GPU), <2.5s (CPU)
  - Training (500 examples): ~10 minutes (GPU), ~45 minutes (CPU)
  - Ancestor query: <10ms using materialized path
  - Descendant query: <10ms using path pattern matching
  - Tree retrieval (depth 5): <50ms

### Changed
- **Resource Ingestion Pipeline**
  - Added ML classification step after embedding generation
  - Classification runs as background task (non-blocking)
  - Automatic flagging of low-confidence predictions
  - Resource count updates for taxonomy nodes

- **Classification System**
  - Enhanced ClassificationService with ML integration
  - Configurable ML vs rule-based classification
  - Confidence score filtering (>= 0.3 threshold)
  - Multi-label support with multiple categories

### Documentation
- **README.md**
  - Added Phase 8.5 overview in development phases
  - Added ML classification feature description
  - Added taxonomy management endpoints
  - Added ML classification examples

- **API_DOCUMENTATION.md**
  - Complete documentation for all taxonomy management endpoints
  - Complete documentation for all ML classification endpoints
  - Request/response examples for all new endpoints
  - Performance characteristics and usage guidelines

- **ml_classification_usage_guide.md** (New)
  - Comprehensive usage guide for ML classification system
  - Model training workflow with code examples
  - Semi-supervised learning setup and best practices
  - Active learning workflow with Python client examples
  - Troubleshooting guide for common issues
  - Performance optimization tips

- **DEVELOPER_GUIDE.md**
  - Added taxonomy service architecture section
  - Added ML classification service architecture section
  - Materialized path pattern explanation
  - Integration points with resource ingestion
  - Troubleshooting guide for ML issues

### Dependencies
- **New ML Dependencies**
  - transformers==4.38.2 - Hugging Face transformers library
  - torch==2.2.1 - PyTorch deep learning framework
  - scikit-learn==1.4.0 - Machine learning utilities
  - All dependencies added to requirements.txt

### Performance Improvements
- **Lazy Model Loading**
  - Models loaded on first prediction request (~2s initial load)
  - Subsequent predictions use cached model (<100ms)
  - Reduces memory usage when ML not actively used

- **Batch Processing**
  - Batch prediction for multiple resources
  - GPU batch size: 32 (6x faster than sequential)
  - CPU batch size: 8 (3x faster than sequential)

- **Efficient Hierarchical Queries**
  - Materialized path for O(1) ancestor/descendant queries
  - Indexed path column for fast pattern matching
  - No recursive CTEs needed

### Migration Notes
- **Database Migration**
  - Run `alembic upgrade head` to create taxonomy tables
  - All new fields are nullable for backward compatibility
  - No data migration required for existing resources

- **Model Training**
  - Initial model training required before classification
  - Minimum 100 labeled examples recommended
  - 500+ labeled examples for production-ready model
  - GPU recommended for training (5-6x faster)

### Breaking Changes
- None - All changes are additive and backward compatible

### Known Issues
- None

### Future Enhancements
- Hierarchical classification constraints (parent implies child)
- Multi-model ensemble for improved accuracy
- Automatic hyperparameter tuning
- Real-time model retraining
- Classification explanation/interpretability

## [1.0.0] - 2025-11-10 - Phase 8: Three-Way Hybrid Search with Sparse Vectors & Reranking

### Added
- **Sparse Vector Embeddings**
  - `app/database/models.py` - Extended Resource model with sparse_embedding, sparse_embedding_model, and sparse_embedding_updated_at fields
  - `app/services/sparse_embedding_service.py` - Sparse embedding generation and search using BGE-M3 model
  - Alembic migration `add_sparse_embeddings_phase8.py` for sparse vector storage
  - Learned keyword representations with 50-200 non-zero dimensions per resource
  - ReLU + log transformation and top-K selection for sparse vectors
  - Normalization to [0, 1] range for consistent scoring

- **Three-Way Retrieval System**
  - Parallel execution of FTS5, dense vector, and sparse vector search
  - Target latency: <150ms for all three retrieval methods combined
  - Configurable result limits (up to 100 candidates per method)
  - Graceful fallback when individual methods fail
  - GPU acceleration for sparse embedding generation (5-10x speedup)

- **Reciprocal Rank Fusion (RRF)**
  - `app/services/reciprocal_rank_fusion_service.py` - RRF algorithm implementation
  - Score-agnostic result merging with formula: weight_i / (k + rank_i)
  - Weighted fusion with custom weights per retrieval method
  - Default k=60 for balanced rank contribution
  - Handles empty result lists and missing documents gracefully

- **Query-Adaptive Weighting**
  - Automatic weight adjustment based on query characteristics
  - Short queries (1-3 words): Boost FTS5 by 50%
  - Long queries (>10 words): Boost dense vectors by 50%
  - Technical queries (code, math): Boost sparse vectors by 50%
  - Question queries (who/what/when/where/why/how): Boost dense vectors by 30%
  - Weight normalization to sum to 1.0

- **ColBERT-Style Reranking**
  - `app/services/reranking_service.py` - Cross-encoder reranking implementation
  - Reranks top 100 candidates using ms-marco-MiniLM-L-6-v2 model
  - Query-document pair scoring with title + first 500 chars
  - Batch processing for efficiency (>100 docs/second)
  - Optional caching with TTL for repeated queries
  - GPU acceleration when available

- **Search Metrics Service**
  - `app/services/search_metrics_service.py` - Information retrieval metrics computation
  - nDCG@K (Normalized Discounted Cumulative Gain) for ranking quality
  - Recall@K for retrieval completeness
  - Precision@K for retrieval accuracy
  - MRR (Mean Reciprocal Rank) for first relevant result position
  - Baseline comparison for measuring improvements

- **Enhanced Search Service**
  - `app/services/search_service.py` - Extended AdvancedSearchService with three-way hybrid search
  - `search_three_way_hybrid()` method combining all retrieval methods
  - Query analysis for adaptive weighting
  - Performance monitoring with latency tracking
  - Method contribution logging (FTS5, dense, sparse counts)
  - Slow query detection (>500ms threshold)

- **API Endpoints**
  - `GET /search/three-way-hybrid` - Three-way hybrid search with RRF and reranking
  - `GET /search/compare-methods` - Compare all search methods side-by-side
  - `POST /search/evaluate` - Evaluate search quality with IR metrics
  - `POST /admin/sparse-embeddings/generate` - Batch generate sparse embeddings

- **Comprehensive Test Suite**
  - `tests/test_sparse_embedding_service.py` - 15+ test cases for sparse embeddings
  - `tests/test_reciprocal_rank_fusion_service.py` - 12+ test cases for RRF
  - `tests/test_reranking_service.py` - 10+ test cases for reranking
  - `tests/test_search_metrics_service.py` - 8+ test cases for metrics
  - `tests/test_three_way_hybrid_search_integration.py` - 15+ integration tests
  - `tests/test_phase8_api_endpoints.py` - 12+ API endpoint tests
  - `tests/test_phase8_quality_validation.py` - Quality improvement validation
  - All tests passing with 100% success rate

### Technical Implementation
- **Database Schema**
  - sparse_embedding field (Text/JSON) for token-weight mappings
  - sparse_embedding_model field (String) for model version tracking
  - sparse_embedding_updated_at field (DateTime) for batch processing
  - Index on sparse_embedding_updated_at for efficient queries
  - Backward compatible (all fields nullable)

- **Service Architecture**
  - SparseEmbeddingService with lazy model loading
  - ReciprocalRankFusionService with configurable k parameter
  - RerankingService with caching support
  - SearchMetricsService with standard IR metrics
  - Dependency injection pattern for testability

- **Performance Optimizations**
  - Parallel retrieval execution using asyncio
  - GPU acceleration for embedding generation and reranking
  - Batch processing for sparse embeddings (32 resources per batch)
  - In-memory caching for reranking results
  - Efficient sparse dot product computation
  - Database indexes for fast queries

### Integration Points
- Automatic sparse embedding generation during resource ingestion
- Background task support for batch sparse embedding generation
- Integration with existing search infrastructure
- Compatible with faceted search and filtering
- Extends recommendation system capabilities

### Performance Characteristics
- Three-way hybrid search: <200ms at 95th percentile
- Sparse embedding generation: <1 second per resource
- Reranking throughput: >100 documents/second
- nDCG improvement: 30%+ over two-way hybrid baseline
- Batch sparse embedding: <1 hour for 10,000 resources

### Dependencies
- Added `transformers>=4.35.0` for BGE-M3 model
- Added `torch>=2.0.0` for neural network inference
- Added `sentence-transformers>=2.2.0` for cross-encoder reranking
- Leverages existing `numpy>=2.0.0` for vector operations

### Documentation Updates
- Updated README.md with Phase 8 features and examples
- Added comprehensive Phase 8 endpoint documentation to API_DOCUMENTATION.md
- Updated DEVELOPER_GUIDE.md with Phase 8 architecture details
- Added EXAMPLES.md with Phase 8 usage examples
- Updated CHANGELOG.md with Phase 8 release notes

### Quality Improvements
- 30%+ improvement in nDCG@20 over two-way hybrid baseline
- Better handling of technical queries with sparse vectors
- Improved precision with ColBERT reranking
- Query-adaptive weighting improves results across query types
- Comprehensive metrics for measuring search quality

## [0.9.5] - 2025-11-10 - Phase 7.5: Annotation & Active Reading System

### Added
- **Annotation CRUD Operations**
  - `app/database/models.py` - Annotation model with text offsets, notes, tags, and embeddings
  - `app/services/annotation_service.py` - Core annotation management service
  - `app/routers/annotations.py` - REST API endpoints for annotations
  - `app/schemas/annotation.py` - Pydantic schemas for validation
  - Alembic migration `e5b9f2c3d4e5_add_annotations_table_phase7_5.py`

- **Text Highlighting Features**
  - Character-offset-based text selection for precise positioning
  - Automatic context extraction (50 characters before/after highlight)
  - Support for any text format (HTML, PDF, plain text)
  - Validation of offsets (start < end, non-negative, within bounds)
  - Zero-length highlight rejection

- **Note-Taking and Organization**
  - Rich annotation notes with automatic semantic embedding generation
  - Tag-based categorization (up to 20 tags per annotation)
  - Color-coding for visual organization (hex color values)
  - Collection association for project-based organization
  - Privacy controls (private by default, optional sharing)

- **Search Capabilities**
  - Full-text search across notes and highlighted text (<100ms for 10K annotations)
  - Semantic search using cosine similarity (<500ms for 1K annotations)
  - Tag-based search with ANY/ALL matching modes
  - Search results ordered by relevance or similarity

- **Export Functionality**
  - Markdown export with resource grouping (<2s for 1K annotations)
  - JSON export with complete metadata
  - Resource-specific or all-annotations export
  - Compatible with external note-taking tools (Obsidian, Notion, etc.)

- **API Endpoints**
  - `POST /resources/{resource_id}/annotations` - Create annotation
  - `GET /resources/{resource_id}/annotations` - List resource annotations
  - `GET /annotations` - List user annotations with pagination
  - `GET /annotations/{id}` - Retrieve specific annotation
  - `PUT /annotations/{id}` - Update annotation note, tags, or color
  - `DELETE /annotations/{id}` - Delete annotation
  - `GET /annotations/search/fulltext` - Full-text search
  - `GET /annotations/search/semantic` - Semantic search with similarity scores
  - `GET /annotations/search/tags` - Tag-based search
  - `GET /annotations/export/markdown` - Export to Markdown
  - `GET /annotations/export/json` - Export to JSON

- **Comprehensive Test Suite**
  - `tests/test_phase7_5_annotations.py` - 50+ test cases covering all functionality
  - Annotation CRUD operations with validation
  - Retrieval and filtering tests
  - Search functionality tests (full-text, semantic, tag-based)
  - Export tests (Markdown and JSON)
  - Integration tests with resources, search, and recommendations
  - Performance benchmarks
  - Edge case handling
  - All tests passing with 100% success rate

### Technical Implementation
- **Database Schema**
  - Annotations table with text offsets, notes, tags, embeddings, and context fields
  - Foreign key to resources with CASCADE DELETE
  - Indexes on resource_id, user_id, created_at for query optimization
  - Check constraints for offset validation (start < end, non-negative)
  - JSON storage for tags, collection_ids, and embeddings

- **Service Architecture**
  - AnnotationService with dependency injection pattern
  - Async embedding generation using background tasks
  - NumPy-based cosine similarity for semantic search
  - Context extraction with boundary handling
  - Graceful error handling and validation

- **Performance Optimizations**
  - Database indexes on frequently queried fields
  - Async embedding generation (doesn't block creation)
  - Efficient JSON queries for tag filtering
  - Batch operations for export
  - In-memory similarity computation for <1K annotations

### Integration Points
- Automatic annotation deletion when resources are deleted (CASCADE)
- Integration with embedding service for semantic search
- Compatible with collection system for organization
- Search service integration for annotation-aware search
- Recommendation service integration for annotation-based recommendations

### Performance Characteristics
- Annotation creation: <50ms (excluding embedding generation)
- Embedding generation: <500ms (async, doesn't block)
- Full-text search: <100ms for 10,000 annotations
- Semantic search: <500ms for 1,000 annotations
- Export: <2s for 1,000 annotations
- Context extraction: <10ms per annotation

### Dependencies
- Added `numpy>=2.0.0` for vector operations and cosine similarity
- Leverages existing `sentence-transformers` for embedding generation
- Uses existing database and ORM infrastructure

### Documentation Updates
- Updated README.md with Phase 7.5 features and examples
- Added comprehensive annotation endpoint documentation to API_DOCUMENTATION.md
- Updated DEVELOPER_GUIDE.md with "Working with Annotations" section
- Added EXAMPLES_PHASE7_5.md with practical usage examples
- Updated CHANGELOG.md with Phase 7.5 release notes

## [0.9.0] - 2025-11-09 - Phase 7: Collection Management

### Added
- **Collection CRUD Operations**
  - `app/database/models.py` - Collection and CollectionResource models with relationships
  - `app/services/collection_service.py` - Core collection management service
  - `app/routers/collections.py` - REST API endpoints for collections
  - `app/schemas/collection.py` - Pydantic schemas for validation
  - Alembic migration `d4a8e9f1b2c3_add_collections_tables_phase7.py`

- **Collection Features**
  - Create, read, update, and delete collections with metadata
  - Hierarchical organization with parent/child relationships
  - Visibility controls (private, shared, public) for access management
  - Owner-based permissions with automatic authorization checks
  - Resource membership management with batch operations (up to 100 resources)
  - Automatic collection updates when resources are deleted

- **Aggregate Embedding System**
  - Automatic embedding computation from member resource embeddings
  - Mean vector calculation with L2 normalization
  - Recomputation triggered on membership changes
  - Null embedding handling for collections without resources
  - Performance: <1 second for collections with 1000 resources

- **Collection Recommendations**
  - Semantic similarity search for related resources
  - Collection-to-collection recommendations
  - Cosine similarity-based ranking
  - Exclusion of source collection and member resources
  - Access control filtering for collection recommendations
  - Configurable result limits (1-50 items)

- **Hierarchy Validation**
  - Circular reference detection and prevention
  - Maximum depth limit (10 levels)
  - Parent existence and ownership validation
  - Cascade deletion for parent-child relationships

- **API Endpoints**
  - `POST /collections` - Create new collection
  - `GET /collections/{id}` - Retrieve collection with member resources
  - `PUT /collections/{id}` - Update collection metadata
  - `DELETE /collections/{id}` - Delete collection and subcollections
  - `GET /collections` - List collections with filtering and pagination
  - `POST /collections/{id}/resources` - Add resources to collection (batch)
  - `DELETE /collections/{id}/resources` - Remove resources from collection (batch)
  - `GET /collections/{id}/recommendations` - Get similar resources and collections
  - `GET /collections/{id}/embedding` - Retrieve aggregate embedding vector

- **Comprehensive Test Suite**
  - `tests/test_phase7_collections.py` - 50+ test cases covering all functionality
  - Collection model creation and relationships
  - CRUD operations with authorization
  - Resource membership management
  - Aggregate embedding computation
  - Hierarchy validation and circular reference prevention
  - Recommendation algorithm testing
  - API endpoint integration tests
  - Performance benchmarks
  - All tests passing with 100% success rate

### Technical Implementation
- **Database Schema**
  - Collections table with owner_id, visibility, parent_id, embedding fields
  - CollectionResource association table with composite primary key
  - Indexes on owner_id, visibility, parent_id for query optimization
  - CASCADE DELETE constraints for parent-child and association cleanup
  - Self-referential foreign key for hierarchical relationships

- **Service Architecture**
  - CollectionService with dependency injection pattern
  - Batch operations using bulk_insert_mappings for performance
  - NumPy-based vector operations for embedding computation
  - Graceful error handling and validation
  - Transaction-safe database operations

- **Performance Optimizations**
  - Database indexes on frequently queried fields
  - Batch operations for resource membership (up to 100 per request)
  - Efficient JSON queries for embedding operations
  - Single embedding recomputation per batch operation
  - Pagination support for large result sets

### Integration Points
- Automatic collection cleanup when resources are deleted
- Integration with existing embedding infrastructure
- Compatible with search and recommendation systems
- Extends knowledge graph capabilities

### Performance Characteristics
- Collection retrieval: <500ms for collections with 1000 resources
- Embedding computation: <1s for collections with 1000 resources
- Batch resource operations: <2s for 100 resources
- Recommendation queries: <1s for typical collections
- Hierarchy validation: <100ms for depth 10

### Documentation Updates
- Updated README.md with Phase 7 features and use cases
- Added comprehensive collection endpoint documentation to API_DOCUMENTATION.md
- Updated DEVELOPER_GUIDE.md with collection service architecture
- Added EXAMPLES_PHASE7.md with practical usage examples
- Updated CHANGELOG.md with Phase 7 release notes

## [0.8.5] - 2025-11-09 - Phase 6.5: Advanced Metadata Extraction & Scholarly Processing

### Added
- **Scholarly Metadata Fields**
  - Extended Resource model with 25+ scholarly fields
  - Author and attribution fields (authors, affiliations)
  - Academic identifiers (DOI, PMID, arXiv ID, ISBN)
  - Publication details (journal, conference, volume, issue, pages, year)
  - Funding sources and acknowledgments
  - Content structure counts (equations, tables, figures, references)
  - Structured content storage (JSON fields for equations, tables, figures)
  - Metadata quality metrics (completeness score, extraction confidence)
  - OCR metadata (processing status, confidence, corrections)

- **Database Migration**
  - Alembic migration `c15f564b1ccd_add_scholarly_metadata_fields_phase6_5.py`
  - All scholarly columns added as nullable (backward compatible)
  - Indexes on doi, pmid, arxiv_id, publication_year for fast lookups
  - Default values for count fields (0) and boolean flags

- **Metadata Extractor Service**
  - `app/services/metadata_extractor.py` - Core scholarly metadata extraction
  - DOI extraction with regex pattern matching
  - arXiv ID extraction from multiple formats
  - Publication year extraction with validation
  - Author and journal name extraction (heuristic-based)
  - Equation extraction from LaTeX-style markup
  - Table detection and caption extraction
  - Metadata completeness and confidence scoring
  - Automatic flagging for manual review (confidence < 0.7)

- **Equation Parser Utility**
  - `app/utils/equation_parser.py` - LaTeX equation processing
  - Extract inline math ($...$) and display math ($$...$$)
  - Support for LaTeX environments (equation, align)
  - LaTeX syntax validation with balanced delimiter checking
  - LaTeX normalization for consistency
  - MathML conversion support (optional)

- **Table Extractor Utility**
  - `app/utils/table_extractor.py` - Multi-strategy table extraction
  - PDF table extraction with camelot-py (lattice and stream modes)
  - PDF table extraction with tabula-py (fallback)
  - HTML table parsing with BeautifulSoup
  - Table structure validation and confidence scoring
  - Caption extraction from surrounding text

- **Scholarly API Endpoints**
  - `app/routers/scholarly.py` - REST API for scholarly metadata
  - `GET /scholarly/resources/{id}/metadata` - Get complete scholarly metadata
  - `GET /scholarly/resources/{id}/equations` - Get equations (LaTeX or MathML)
  - `GET /scholarly/resources/{id}/tables` - Get tables with optional data
  - `POST /scholarly/resources/{id}/metadata/extract` - Trigger extraction
  - `GET /scholarly/metadata/completeness-stats` - Aggregate statistics

- **Pydantic Schemas**
  - `app/schemas/scholarly.py` - Request/response models
  - Author, Equation, TableData, Figure schemas
  - ScholarlyMetadataResponse with all fields
  - MetadataExtractionRequest/Response
  - MetadataCompletenessStats for analytics

### Technical Implementation
- **Dependencies**
  - Added `camelot-py[base]==0.11.0` for PDF table extraction
  - Added `tabula-py==2.9.0` for PDF table extraction (fallback)
  - Added `pytesseract==0.3.10` for OCR processing
  - Added `pdf2image==1.17.0` for PDF to image conversion
  - Added `Pillow==10.4.0` for image processing
  - Added `sympy==1.12` for LaTeX validation
  - Added `nltk==3.8.1` for text processing
  - Added `python-Levenshtein==0.25.0` for OCR error correction

### Enhanced
- Resource model with comprehensive scholarly metadata support
- Database schema with indexed academic identifiers
- API surface area with specialized scholarly endpoints

## [0.8.0] - 2025-11-09 - Phase 6: Citation Network & Link Intelligence

### Added
- **Citation Model and Database Schema**
  - `app/database/models.py` - Citation model with source/target relationships
  - Alembic migration `23fa08826047_add_citation_table_phase6.py`
  - Foreign key constraints with CASCADE/SET NULL behavior
  - Indexes on source_resource_id, target_resource_id, and target_url
  - Check constraint for citation_type validation

- **Citation Service**
  - `app/services/citation_service.py` - Core citation extraction and graph operations
  - Multi-format citation extraction (HTML, PDF, Markdown)
  - Internal citation resolution with URL normalization
  - PageRank-style importance scoring using NetworkX
  - Citation graph construction with configurable depth
  - Smart citation type classification (reference, dataset, code, general)

- **Citation API Endpoints**
  - `app/routers/citations.py` - REST API for citation management
  - `GET /citations/resources/{id}/citations` - Retrieve resource citations
  - `GET /citations/graph/citations` - Get citation network for visualization
  - `POST /citations/resources/{id}/citations/extract` - Trigger extraction
  - `POST /citations/resolve` - Resolve internal citations
  - `POST /citations/importance/compute` - Compute PageRank scores

- **Pydantic Schemas**
  - `app/schemas/citation.py` - Request/response models for citation endpoints
  - CitationResponse, CitationWithResource, ResourceCitationsResponse
  - CitationGraphResponse with nodes and edges
  - Task status responses for background operations

- **Comprehensive Test Suite**
  - `tests/test_phase6_citations.py` - 10 test cases covering all functionality
  - Citation model creation and relationships
  - Citation service methods (extraction, resolution, graph)
  - API endpoint integration tests
  - All tests passing with 100% success rate

### Technical Implementation
- **Dependencies**
  - Added `pdfplumber==0.11.0` for PDF citation extraction
  - Added `networkx==3.2.1` for PageRank computation
  - Leveraged existing `beautifulsoup4` for HTML parsing

- **Citation Extraction Features**
  - HTML: Extracts `<a href>` links and `<cite>` tags with context
  - PDF: Uses pdfplumber for hyperlinks and regex for text URLs
  - Markdown: Parses `[text](url)` syntax with context capture
  - Limit: 50 citations per resource for performance
  - Context snippets: 50 characters before/after citation

- **Citation Resolution**
  - URL normalization (fragments, trailing slashes, case)
  - Batch processing (100 citations per batch)
  - Bulk database operations for efficiency
  - Incremental resolution (only unresolved citations)

- **PageRank Computation**
  - Damping factor: 0.85
  - Max iterations: 100
  - Convergence threshold: 1e-6
  - Score normalization to [0, 1] range
  - Sparse matrix representation for large graphs

- **Citation Graph Construction**
  - BFS traversal with configurable depth (max 2)
  - Node limit: 100 for visualization performance
  - Bidirectional edges (inbound and outbound citations)
  - Node type classification (source, cited, citing)

### Performance Characteristics
- Citation extraction: <500ms (HTML), <2s (PDF), <200ms (Markdown)
- Citation resolution: <100ms per 100 citations
- PageRank computation: <1s (<100 nodes), <5s (100-1000 nodes), <30s (1000+ nodes)
- Graph queries: <500ms for typical resources

### Integration Points
- Automatic citation extraction during resource ingestion
- Citation resolution after new resource creation
- Integration with knowledge graph service (future)
- Background task support for all expensive operations

### Documentation Updates
- Updated README.md with Phase 6 features and endpoints
- Added comprehensive citation endpoint documentation to API_DOCUMENTATION.md
- Updated CHANGELOG.md with Phase 6 release notes
- Added citation extraction details and performance characteristics

## [0.7.1] - 2025-01-15 - Phase 5.5: Personalized Recommendation Engine

### Added
- **Personalized Recommendation System**
  - `app/services/recommendation_service.py` - Core recommendation engine with user profile generation
  - `app/schemas/recommendation.py` - Pydantic models for recommendation responses
  - `app/routers/recommendation.py` - REST API endpoint for recommendations
  - `tests/test_phase55_recommendations.py` - Comprehensive test suite with 31 test cases

- **User Profile Generation**
  - Automatic user profile vector creation from top-quality library resources
  - Configurable profile size (default: 50 resources)
  - Embedding averaging for preference learning
  - Graceful handling of empty or insufficient libraries

- **External Content Discovery**
  - Pluggable search provider architecture (default: DuckDuckGo Search)
  - Configurable keyword extraction from authority subjects
  - Candidate sourcing with deduplication and caching
  - Timeout and error handling for external services

- **Recommendation Scoring**
  - Cosine similarity-based relevance scoring
  - Lightweight in-memory processing
  - Explainable recommendation reasoning
  - Relevance score validation (0.0-1.0 range)

- **Configuration System**
  - `RECOMMENDATION_PROFILE_SIZE` - Number of top resources for profile (default: 50)
  - `RECOMMENDATION_KEYWORD_COUNT` - Number of seed keywords (default: 5)
  - `RECOMMENDATION_CANDIDATES_PER_KEYWORD` - Candidates per keyword (default: 10)
  - `SEARCH_PROVIDER` - External search provider (default: "ddgs")
  - `SEARCH_TIMEOUT` - Search timeout in seconds (default: 10)

### Technical Implementation
- **Dependencies**
  - Added `duckduckgo-search==5.3.1` for external content discovery
  - Updated `numpy>=2.0.0` for vector operations and cosine similarity
  - Maintained compatibility with existing AI and search infrastructure

- **Performance Optimizations**
  - In-memory caching for search results (5-minute TTL)
  - Efficient vector operations using NumPy
  - Batch candidate processing with early termination
  - Graceful degradation on external service failures

- **Testing Infrastructure**
  - Comprehensive test coverage with unit, integration, and API tests
  - Mocked external dependencies for reliable testing
  - Performance benchmarking and edge case validation
  - Custom test markers for organized test execution

### API Changes
- **New Endpoint**
  - `GET /recommendations?limit=N` - Retrieve personalized content recommendations
  - Query parameter validation (limit: 1-100, default: 10)
  - Structured JSON response with relevance scores and reasoning

### Documentation
- **Updated Documentation**
  - Comprehensive API reference with recommendation examples
  - Developer guide with architecture and setup instructions
  - Practical examples and tutorials in multiple programming languages
  - Professional-grade documentation following API documentation standards

## [0.7.0] - 2025-01-15 - Phase 5: Hybrid Knowledge Graph

### Added
- **Hybrid Knowledge Graph System**
  - `app/services/graph_service.py` - Core graph computation service with multi-signal scoring
  - `app/schemas/graph.py` - Pydantic models for graph data structures
  - `app/routers/graph.py` - REST API endpoints for graph functionality
  - `tests/test_phase5_graph_api.py` - Comprehensive test suite for graph functionality

- **Graph Scoring Algorithms**
  - NumPy-based cosine similarity computation with fallback for zero vectors
  - Tag overlap scoring with diminishing returns heuristic
  - Binary classification code matching for exact code matches
  - Hybrid weight fusion combining vector (60%), tag (30%), and classification (10%) signals

- **Mind-Map Neighbor Discovery**
  - `GET /graph/resource/{id}/neighbors` endpoint for resource-centric exploration
  - Configurable neighbor limits (default: 7, range: 1-20)
  - Multi-signal candidate gathering from vector similarity, shared subjects, and classification matches
  - Transparent edge details explaining connection reasoning

- **Global Overview Analysis**
  - `GET /graph/overview` endpoint for system-wide relationship analysis
  - Configurable edge limits (default: 50, range: 10-100)
  - Vector similarity threshold filtering for candidate pruning (default: 0.85)
  - Combines high vector similarity pairs and significant tag overlap pairs

### Technical Implementation
- **Database Integration**
  - Leverages existing `embedding` JSON column for vector similarity
  - Uses `subject` JSON array for tag overlap analysis
  - Utilizes `classification_code` for exact matching
  - No additional database schema changes required

- **Performance Optimizations**
  - Efficient JSON queries for subject overlap detection
  - Candidate pre-filtering by vector threshold for global overview
  - Optimized NumPy operations for similarity computation
  - Configurable limits to prevent performance issues

### Configuration
- **Graph Settings**
  - `GRAPH_WEIGHT_VECTOR` - Vector similarity weight (default: 0.6)
  - `GRAPH_WEIGHT_TAGS` - Tag overlap weight (default: 0.3)
  - `GRAPH_WEIGHT_CLASSIFICATION` - Classification match weight (default: 0.1)
  - `GRAPH_VECTOR_MIN_SIM_THRESHOLD` - Minimum similarity threshold (default: 0.85)
  - `DEFAULT_GRAPH_NEIGHBORS` - Default neighbor limit (default: 7)
  - `GRAPH_OVERVIEW_MAX_EDGES` - Default overview edge limit (default: 50)

## [0.6.0] - 2025-01-12 - Phase 4: Vector & Hybrid Search

### Added
- **Vector Embeddings and Semantic Search**
  - `app/services/ai_core.py` - Enhanced with vector embedding generation using `nomic-ai/nomic-embed-text-v1`
  - `app/services/hybrid_search_methods.py` - Vector similarity computation and score fusion
  - `app/services/search_service.py` - Enhanced with hybrid search capabilities
  - Database migration for vector embeddings storage

- **Hybrid Search Fusion**
  - Weighted combination of keyword (FTS5) and semantic (vector) search
  - User-controllable hybrid weight parameter (0.0-1.0)
  - Score normalization using min-max scaling for fair combination
  - Transparent integration with existing search endpoint

- **Search Modes**
  - Pure keyword search (`hybrid_weight=0.0`) - Traditional FTS5 search
  - Pure semantic search (`hybrid_weight=1.0`) - Vector similarity search
  - Balanced hybrid search (`hybrid_weight=0.5`) - Default balanced approach

### Technical Implementation
- **Embedding Generation**
  - Automatic embedding creation during resource ingestion
  - Composite text generation from title, description, and subjects
  - Cross-database storage using JSON columns for portability
  - Model caching for performance optimization

- **Vector Operations**
  - NumPy-based cosine similarity computation
  - Efficient vector storage and retrieval
  - Fallback handling for missing embeddings
  - Performance optimizations for large datasets

### Configuration
- **Search Settings**
  - `EMBEDDING_MODEL_NAME` - Embedding model (default: "nomic-ai/nomic-embed-text-v1")
  - `DEFAULT_HYBRID_SEARCH_WEIGHT` - Default fusion weight (default: 0.5)
  - `EMBEDDING_CACHE_SIZE` - Model cache size (default: 1000)

### Dependencies
- Added `sentence-transformers` for embedding generation
- Updated `numpy` for vector operations
- Enhanced AI core with embedding capabilities

## [0.5.0] - 2025-01-11 - Phase 3.5: AI-Powered Asynchronous Ingestion

### Added
- **Real AI Processing**
  - `app/services/ai_core.py` - AI processing service with Hugging Face transformers
  - Intelligent summarization using `facebook/bart-large-cnn`
  - Zero-shot tagging using `facebook/bart-large-mnli`
  - Graceful fallback when AI models are unavailable

- **Asynchronous Ingestion Pipeline**
  - `POST /resources` returns immediately with `202 Accepted` status
  - Background processing using FastAPI BackgroundTasks
  - `GET /resources/{id}/status` for real-time status monitoring
  - Comprehensive error handling and recovery mechanisms

- **Enhanced Content Extraction**
  - Multi-format support for HTML, PDF, and plain text
  - Primary PDF extraction via PyMuPDF with pdfminer.six fallback
  - Content type detection based on headers, URLs, and file signatures
  - Robust error handling for network errors and timeouts

### Technical Implementation
- **AI Model Integration**
  - Lazy model loading to minimize startup time
  - CPU-only PyTorch configuration for broad compatibility
  - Model caching for performance optimization
  - Fallback logic for production reliability

- **Background Processing**
  - FastAPI BackgroundTasks for in-process async processing
  - Status tracking with timestamps and error reporting
  - Transaction-safe database updates
  - Comprehensive logging and monitoring

### Configuration
- **AI Model Settings**
  - `SUMMARIZER_MODEL` - Summarization model (default: "facebook/bart-large-cnn")
  - `TAGGER_MODEL` - Tagging model (default: "facebook/bart-large-mnli")
  - Configurable via environment variables or code injection

### Dependencies
- Added `transformers` and `torch` for AI processing
- Added `PyMuPDF` and `pdfminer.six` for PDF processing
- Enhanced content extraction capabilities

## [0.4.0] - 2025-01-10 - Phase 3: Advanced Search & Discovery

### Added
- **Full-Text Search with FTS5**
  - SQLite FTS5 contentless virtual table implementation
  - Automatic trigger synchronization with resources table
  - Search result snippets and highlighting
  - Graceful fallback to LIKE search if FTS5 unavailable

- **Faceted Search Capabilities**
  - Advanced filtering by classification, type, language, and subjects
  - Facet counts computed over filtered pre-paginated sets
  - Support for multiple filter types (any, all, range, exact)
  - Transparent integration with existing search infrastructure

- **Authority Control System**
  - `app/services/authority_service.py` - Subject normalization and canonical forms
  - `app/routers/authority.py` - Authority control endpoints
  - Built-in synonyms and smart formatting (e.g., "ML" → "Machine Learning")
  - Usage tracking and variant management

- **Personal Classification System**
  - `app/services/classification_service.py` - UDC-inspired classification system
  - `app/routers/classification.py` - Classification management endpoints
  - Rule-based keyword matching with weighted scoring
  - Hierarchical classification tree with parent-child relationships

- **Enhanced Quality Control**
  - `app/services/quality_service.py` - Multi-factor quality assessment
  - Source credibility evaluation using domain reputation
  - Content depth analysis and vocabulary richness assessment
  - Quality level classification (HIGH ≥0.8, MEDIUM ≥0.5, LOW <0.5)

### Technical Implementation
- **Database Enhancements**
  - New authority tables for subject and creator normalization
  - Classification code tables with hierarchical relationships
  - FTS5 virtual table with automatic synchronization
  - Enhanced resource model with quality scoring

- **Search Infrastructure**
  - Portable FTS5 implementation with fallback support
  - Efficient facet computation using SQL aggregation
  - Query optimization for large datasets
  - Comprehensive error handling and validation

### Configuration
- **Search Settings**
  - Configurable search limits and pagination
  - Customizable facet computation
  - FTS5 availability detection and fallback
  - Performance tuning parameters

## [0.3.0] - 2025-01-09 - Phase 2: CRUD & Curation

### Added
- **Resource Management**
  - Complete CRUD operations for resources
  - `GET /resources` with filtering, sorting, and pagination
  - `PUT /resources/{id}` for partial updates
  - `DELETE /resources/{id}` for resource removal

- **Curation Workflows**
  - `GET /curation/review-queue` for low-quality item review
  - `POST /curation/batch-update` for bulk operations
  - Quality-based filtering and sorting
  - Batch processing with transaction safety

- **Enhanced Resource Model**
  - Dublin Core metadata compliance
  - Custom fields for classification and quality
  - Audit fields with automatic timestamps
  - Cross-database compatibility

### Technical Implementation
- **Database Schema**
  - Enhanced resource table with additional fields
  - Proper indexing for performance
  - Migration system with Alembic
  - Cross-database type compatibility

- **API Design**
  - RESTful endpoint design
  - Comprehensive query parameter support
  - Structured error responses
  - OpenAPI documentation generation

## [0.2.0] - 2025-01-08 - Phase 1: Content Ingestion

### Added
- **URL Ingestion System**
  - `POST /resources` endpoint for URL submission
  - Content fetching and extraction
  - Local content archiving
  - Basic metadata extraction

- **Content Processing**
  - HTML content extraction using readability-lxml
  - Text cleaning and processing
  - Metadata extraction and validation
  - Local storage with organized archive structure

- **Database Foundation**
  - SQLAlchemy ORM setup
  - Resource model definition
  - Database session management
  - Migration system initialization

### Technical Implementation
- **Content Extraction**
  - HTTP client with timeout handling
  - HTML parsing and text extraction
  - Content type detection
  - Error handling and recovery

- **Storage System**
  - Organized archive structure by date and domain
  - Raw HTML and processed text storage
  - Metadata persistence
  - File system organization

## [0.1.0] - 2025-01-07 - Phase 0: Foundation

### Added
- **Project Foundation**
  - FastAPI application setup
  - SQLAlchemy database configuration
  - Pydantic settings management
  - Basic project structure

- **Database Models**
  - Resource model with Dublin Core fields
  - Database migrations with Alembic
  - Cross-database compatibility
  - Proper indexing and constraints

- **Configuration System**
  - Environment-based configuration
  - Pydantic settings validation
  - Database URL configuration
  - Development and production settings

### Technical Implementation
- **Architecture**
  - Clean separation of concerns
  - Dependency injection pattern
  - Modular service architecture
  - Comprehensive error handling

- **Development Tools**
  - Testing framework setup
  - Code quality tools
  - Documentation generation
  - Development server configuration

---

## Breaking Changes

### Version 0.7.1
- No breaking changes

### Version 0.7.0
- No breaking changes

### Version 0.6.0
- No breaking changes

### Version 0.5.0
- `POST /resources` now returns `202 Accepted` instead of `200 OK` for async processing
- Added `ingestion_status` field to resource model

### Version 0.4.0
- Enhanced search endpoint with new filter parameters
- Added new database tables for authority control and classification

### Version 0.3.0
- Enhanced resource model with additional fields
- Updated API response formats

### Version 0.2.0
- Initial API implementation
- No breaking changes from previous versions

### Version 0.1.0
- Initial release
- No breaking changes

## Migration Guide

### Upgrading to 0.7.1
1. Install new dependencies: `pip install -r requirements.txt`
2. Run database migrations: `alembic upgrade head`
3. No additional configuration required

### Upgrading to 0.7.0
1. Run database migrations: `alembic upgrade head`
2. No additional configuration required

### Upgrading to 0.6.0
1. Install new dependencies: `pip install sentence-transformers numpy`
2. Run database migrations: `alembic upgrade head`
3. Existing resources will generate embeddings on next update

### Upgrading to 0.5.0
1. Install AI dependencies: `pip install transformers torch`
2. Run database migrations: `alembic upgrade head`
3. Update client code to handle `202 Accepted` responses for ingestion

### Upgrading to 0.4.0
1. Run database migrations: `alembic upgrade head`
2. Update search queries to use new filter parameters
3. No breaking changes to existing functionality

## Deprecation Notices

- No current deprecations

## Security Updates

- All versions include input validation and sanitization
- SQL injection protection through SQLAlchemy ORM
- XSS protection through proper content handling
- Rate limiting planned for future releases

## Performance Improvements

### Version 0.7.1
- In-memory caching for recommendation search results
- Optimized vector operations using NumPy
- Efficient candidate processing with early termination

### Version 0.7.0
- Optimized graph computation with efficient JSON queries
- Candidate pre-filtering for performance
- Configurable limits to prevent resource exhaustion

### Version 0.6.0
- Model caching for embedding generation
- Optimized vector similarity computation
- Efficient storage and retrieval of embeddings

### Version 0.5.0
- Lazy model loading for faster startup
- Background processing for non-blocking ingestion
- Optimized content extraction pipeline

## Known Issues

### Version 0.7.1
- External search provider may be rate-limited
- Large libraries may require tuning of recommendation parameters

### Version 0.7.0
- Graph computation may be slow for very large libraries
- Memory usage increases with library size

### Version 0.6.0
- Embedding generation requires significant memory
- First-time model loading may be slow

### Version 0.5.0
- AI models require substantial memory and CPU resources
- Background processing is in-process (not distributed)

## Future Roadmap

### Version 1.0.0 (Planned)
- API key authentication and rate limiting
- Advanced analytics and reporting
- Multi-user support and permissions
- Real-time collaboration features
- Mobile API optimizations
- Advanced caching strategies
- Performance monitoring and metrics
- Production-ready deployment options
- Enterprise-grade security features
- Scalable cloud deployment
- Integration with popular knowledge management tools