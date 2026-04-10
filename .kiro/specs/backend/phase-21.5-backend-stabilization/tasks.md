# Phase 21.5: Backend Stabilization - Tasks

## Overview

This document provides a comprehensive task breakdown for fixing all 267 failing tests, resolving 22 open issues, and stabilizing the Pharos backend. Tasks are organized by priority and category.

## Task Organization

- **Week 1**: Security Hardening (Critical Priority)
- **Week 2**: Configuration Management
- **Week 3**: API Endpoint Registration & Phase 19 Fixes
- **Week 4**: Database & Model Fixes
- **Week 5**: Event System & Integration Tests
- **Week 6**: Performance Optimization & Final Validation

---

## Week 1: Security Hardening (Critical Priority)

### Task 1.1: Remove Hardcoded Secrets
- [x] Remove default value from JWT_SECRET_KEY in settings.py
- [x] Remove default value from POSTGRES_PASSWORD in settings.py
- [x] Add validator for JWT_SECRET_KEY (min 32 chars, not default)
- [x] Add startup validation for production environment
- [x] Update .env.example with required variables
- [x] Document required secrets in deployment.md
- [x] Test that app fails to start without secrets in production

**Estimated Time**: 4 hours
**Resolves**: ISSUE-2026-02-16-001

### Task 1.2: Eliminate Authentication Bypass
- [x] Remove all TEST_MODE checks from app/shared/security.py
- [x] Remove TEST_MODE checks from app/__init__.py
- [x] Create bypass_auth fixture in tests/conftest.py using dependency override
- [x] Update all tests using TEST_MODE to use bypass_auth fixture
- [x] Add environment validation preventing TEST_MODE in production
- [x] Test that authentication cannot be bypassed in production mode
- [x] Verify all auth tests still pass with new fixture

**Estimated Time**: 8 hours
**Resolves**: ISSUE-2026-02-16-002
**Fixes Tests**: 15+ authentication tests

### Task 1.3: Fix Open Redirect Vulnerability
- [x] Add ALLOWED_REDIRECT_URLS to settings.py
- [x] Add validator for HTTPS requirement in production
- [x] Implement validate_redirect_url function
- [x] Update OAuth2 callback to use HTTP-only cookies
- [x] Remove tokens from URL parameters
- [x] Add redirect URL validation to all OAuth2 callbacks
- [x] Update frontend documentation for cookie handling
- [x] Test redirect validation with various URLs

**Estimated Time**: 6 hours
**Resolves**: ISSUE-2026-02-16-003

### Task 1.4: Implement CSRF Protection
- [x] Create app/middleware/csrf.py
- [x] Implement CSRFMiddleware class
- [x] Add Origin/Referer validation
- [x] Register middleware in app/__init__.py
- [x] Add ALLOWED_ORIGINS to settings
- [x] Test CSRF protection on POST/PUT/DELETE endpoints
- [x] Document CSRF requirements for API clients

**Estimated Time**: 6 hours
**Resolves**: ISSUE-2026-02-16-010

### Task 1.5: Add Rate Limiting to Auth Endpoints
- [x] Implement check_auth_rate_limit in rate_limiter.py
- [x] Add rate limiting to /auth/login (5 per 15 min)
- [x] Add rate limiting to /auth/refresh (10 per hour)
- [x] Add rate limiting to /auth/register (endpoint doesn't exist - skipped)
- [x] Return 429 status code when limit exceeded
- [x] Add rate limit headers to responses
- [x] Test rate limiting with multiple requests
- [x] Document rate limits in API documentation

**Estimated Time**: 6 hours
**Resolves**: ISSUE-2026-02-16-007

### Task 1.6: Implement Repository URL Validation
- [x] Create app/utils/url_validator.py
- [x] Implement validate_repository_url function
- [x] Add ALLOWED_DOMAINS list (github.com, gitlab.com, etc.)
- [x] Add BLOCKED_IP_RANGES list (private IPs, metadata endpoints)
- [x] Add hostname resolution and IP checking
- [x] Apply validation to /ingest-repo endpoint
- [x] Apply validation to repo_ingestion.py
- [x] Test with various valid and invalid URLs
- [x] Test SSRF prevention with private IPs

**Estimated Time**: 8 hours
**Resolves**: ISSUE-2026-02-16-005, ISSUE-2026-02-16-008
**Fixes Tests**: test_valid_url_accepted, test_invalid_url_rejected, test_invalid_url_validation

### Task 1.7: Implement File Upload Validation
- [x] Add file extension allowlist to settings
- [x] Implement file content-type validation (magic numbers)
- [x] Add file size limit (50MB default)
- [x] Add file upload rate limiting
- [x] Strip metadata from uploaded files
- [x] Test with various file types
- [x] Test with oversized files
- [x] Document upload restrictions

**Estimated Time**: 6 hours
**Resolves**: ISSUE-2026-02-16-004

### Task 1.8: Fix Token Transmission
- [x] Update OAuth2 callbacks to use HTTP-only cookies
- [x] Remove tokens from URL parameters
- [x] Set Secure flag in production
- [x] Set SameSite=Lax attribute
- [x] Update token refresh to use cookies
- [x] Test cookie-based authentication
- [x] Document cookie requirements

**Estimated Time**: 4 hours
**Resolves**: ISSUE-2026-02-16-006

### Task 1.9: Implement Temporary File Cleanup
- [x] Remove ignore_errors=True from shutil.rmtree calls
- [x] Add explicit error handling for cleanup failures
- [x] Log cleanup failures for monitoring
- [x] Implement periodic cleanup job for orphaned temp dirs
- [x] Add disk space monitoring
- [x] Use context managers for automatic cleanup
- [x] Test cleanup with various error conditions

**Estimated Time**: 4 hours
**Resolves**: ISSUE-2026-02-16-009

**Week 1 Total**: 52 hours (~6.5 days)

---

## Week 2: Configuration Management

### Task 2.1: Fix Settings Mocking in Tests
- [x] Create mock_settings fixture in conftest.py
- [x] Use real Settings instance with test values
- [x] Implement override_get_settings autouse fixture
- [x] Remove manual Settings mocking from all test files
- [x] Test that all settings attributes are accessible
- [x] Verify Settings validation works in tests

**Estimated Time**: 8 hours
**Fixes Tests**: 50+ tests with Settings mocking issues

### Task 2.2: Create Requirements Files Split
- [x] Create requirements-base.txt with shared dependencies
- [x] Create requirements-cloud.txt (no GPU dependencies)
- [x] Create requirements-edge.txt (with GPU dependencies)
- [x] Update requirements.txt to point to base
- [x] Test installation with each requirements file
- [x] Document requirements file structure
- [x] Update CI/CD to use appropriate requirements file

**Estimated Time**: 4 hours
**Fixes Tests**: test_requirements_base_exists, test_requirements_cloud_exists, test_requirements_edge_exists, etc.

### Task 2.3: Implement Environment Variable Validation
- [x] Add MODE validator (must be CLOUD or EDGE)
- [x] Add QUEUE_SIZE validator (must be positive)
- [x] Add model_post_init for MODE-specific validation
- [x] Validate UPSTASH credentials in CLOUD mode
- [x] Validate QDRANT credentials in EDGE mode
- [x] Validate HTTPS requirement in CLOUD mode
- [x] Test validation with various configurations
- [x] Test that invalid configs raise errors

**Estimated Time**: 6 hours
**Fixes Tests**: test_missing_upstash_url_raises_error, test_invalid_mode_raises_error, etc.

### Task 2.4: Fix Configuration Defaults
- [x] Set QUEUE_SIZE default to 10
- [x] Set TASK_TTL default to 86400 (24 hours)
- [x] Set WORKER_POLL_INTERVAL default to 2 seconds
- [x] Set CHUNK_ON_RESOURCE_CREATE default to False
- [x] Set GRAPH_EXTRACTION_ENABLED default to True
- [x] Set SYNTHETIC_QUESTIONS_ENABLED default to False
- [x] Set DEFAULT_RETRIEVAL_STRATEGY default to "parent-child"
- [x] Test all defaults are set correctly

**Estimated Time**: 3 hours
**Fixes Tests**: test_default_queue_size, test_default_task_ttl, test_default_worker_poll_interval, etc.

### Task 2.5: Fix Database URL Construction
- [x] Implement get_database_url method in Settings
- [x] Handle SQLite URLs (return unchanged)
- [x] Handle PostgreSQL URL construction
- [x] Handle special characters in passwords (URL encoding)
- [x] Test with various database configurations
- [x] Test with special characters in password

**Estimated Time**: 4 hours
**Fixes Tests**: test_sqlite_url_unchanged, test_postgresql_url_construction, etc.

### Task 2.6: Fix JWT Configuration
- [x] Set JWT_ALGORITHM default to "HS256"
- [x] Set JWT_ACCESS_TOKEN_EXPIRE_MINUTES default to 30
- [x] Set JWT_REFRESH_TOKEN_EXPIRE_DAYS default to 7
- [x] Test JWT configuration from environment
- [x] Test JWT secret key validation

**Estimated Time**: 2 hours
**Fixes Tests**: test_jwt_algorithm_default, test_jwt_access_token_expire_minutes_default, etc.

### Task 2.7: Fix Rate Limiting Configuration
- [x] Set RATE_LIMIT_FREE_TIER default to 100
- [x] Set RATE_LIMIT_PREMIUM_TIER default to 1000
- [x] Set RATE_LIMIT_ADMIN_TIER default to 10000
- [x] Test rate limit configuration from environment
- [x] Test rate limit validation

**Estimated Time**: 2 hours
**Fixes Tests**: test_rate_limit_defaults, test_rate_limit_from_env

### Task 2.8: Fix Advanced RAG Configuration
- [x] Set chunking configuration defaults
- [x] Set graph extraction configuration defaults
- [x] Set synthetic questions configuration defaults
- [x] Set retrieval configuration defaults
- [x] Add validators for configuration values
- [x] Test configuration from environment

**Estimated Time**: 4 hours
**Fixes Tests**: test_chunking_config_defaults, test_graph_extraction_config_defaults, etc.

### Task 2.9: Fix Configuration Validation Errors
- [x] Fix graph weights validation (must sum to 1.0)
- [x] Fix JWT expire minutes validation (must be positive)
- [x] Fix rate limit validation (must be non-negative)
- [x] Fix Redis port validation (must be 1-65535)
- [x] Fix quality threshold validation (must be 0-1)
- [x] Fix hybrid search weight validation (must be 0-1)
- [x] Test all validation errors

**Estimated Time**: 4 hours
**Fixes Tests**: test_graph_weights_must_sum_to_one, test_jwt_access_token_expire_minutes_must_be_positive, etc.

**Week 2 Total**: 37 hours (~4.6 days)

---

## Week 2 Completed Summary

All Week 2 Configuration Management tasks have been completed:

### Task 2.1: Fix Settings Mocking in Tests ✅
- Created `mock_settings` fixture in conftest.py with real Settings instance
- Implemented `override_get_settings` autouse fixture for automatic dependency override
- Updated test files to use `test_settings` fixture instead of manual mocking
- Updated: `test_redirect_validation.py`, `test_rate_limiter.py`, `test_auth_endpoints.py`

### Task 2.2: Create Requirements Files Split ✅
- Created `requirements-base.txt` with shared dependencies
- Created `requirements-cloud.txt` (no GPU dependencies)
- Created `requirements-edge.txt` (with GPU dependencies)
- Updated `requirements.txt` to point to base

### Task 2.3: Implement Environment Variable Validation ✅
- Added MODE validator (must be CLOUD or EDGE)
- Added QUEUE_SIZE validator (must be positive)
- MODE-specific validation in model_post_init

### Task 2.4: Fix Configuration Defaults ✅
- QUEUE_SIZE default to 10 (with alias for MAX_QUEUE_SIZE)
- TASK_TTL default to 86400 (with alias for TASK_TTL_SECONDS)
- CHUNK_ON_RESOURCE_CREATE default to False
- RATE_LIMIT_ADMIN_TIER default to 10000

### Task 2.5: Fix Database URL Construction ✅
- Implemented URL encoding for special characters in passwords
- Updated get_database_url() to use urllib.parse.quote

### Task 2.6: Fix JWT Configuration ✅
- JWT_ALGORITHM default to "HS256" (already set)
- JWT_ACCESS_TOKEN_EXPIRE_MINUTES default to 30 (already set)
- JWT_REFRESH_TOKEN_EXPIRE_DAYS default to 7 (already set)

### Task 2.7: Fix Rate Limiting Configuration ✅
- RATE_LIMIT_FREE_TIER default to 100 (already set)
- RATE_LIMIT_PREMIUM_TIER default to 1000 (already set)
- RATE_LIMIT_ADMIN_TIER default to 10000 (updated from 0)

### Task 2.8: Fix Advanced RAG Configuration ✅
- All chunking, graph extraction, synthetic questions, and retrieval defaults set
- All validators in place

### Task 2.9: Fix Configuration Validation Errors ✅
- Graph weights validation (sum to 1.0)
- JWT expire minutes validation (positive)
- Rate limit validation (non-negative)
- Redis port validation (1-65535)
- Quality threshold validation (0-1)
- Hybrid search weight validation (0-1)

**Test Results**: 75/75 settings tests passing

---

## Week 3: API Endpoint Registration & Phase 19 Fixes

### Task 3.1: Register Missing API Endpoints
- [x] Register rag_evaluation_router in app/__init__.py
- [x] Register recommendations_router in app/__init__.py
- [x] Register advanced_search_router in app/__init__.py
- [x] Register chunking_router in app/__init__.py
- [x] Register document_intelligence_router in app/__init__.py
- [x] Register ai_planning_router in app/__init__.py
- [x] Register mcp_router in app/__init__.py
- [x] Register curation_router with correct prefix
- [ ] Test all endpoints are accessible (no 404s)
- [ ] Update OpenAPI spec generation

**Estimated Time**: 6 hours
**Fixes Tests**: 50+ tests with 404 errors

### Task 3.2: Implement Worker Process Function
- [ ] Create process_job function in deployment/worker.py
- [ ] Implement job data validation
- [x] Implement repository ingestion logic
- [x] Implement error handling and result storage
- [x] Implement worker main loop
- [ ] Test worker with sample jobs
- [x] Document worker deployment

**Estimated Time**: 8 hours
**Fixes Tests**: All tests importing process_job from worker

### Task 3.3: Fix Queue Service Configuration
- [x] Implement QueueService class
- [x] Add Redis connection logic for CLOUD mode (Upstash)
- [x] Add Redis connection logic for EDGE mode (local)
- [x] Implement submit_job method with queue size check
- [x] Implement get_job_status method
- [x] Implement get_job_history method
- [ ] Test queue service in both modes
- [ ] Test queue full scenario (429 response)

**Estimated Time**: 8 hours
**Fixes Tests**: test_429_when_queue_is_full, test_worker_status_returns_real_time_updates, test_job_history_endpoint

### Task 3.4: Fix Cloud API Integration Tests
- [ ] Fix task metadata TTL handling
- [ ] Fix worker status endpoint
- [ ] Fix job history endpoint
- [ ] Fix queue position tracking
- [ ] Test with real Redis connection
- [ ] Test error scenarios

**Estimated Time**: 6 hours
**Fixes Tests**: test_task_metadata_includes_ttl, test_worker_status_returns_real_time_updates, test_job_history_endpoint

### Task 3.5: Fix Code Pipeline E2E Tests
- [ ] Fix repository ingestion endpoint
- [ ] Fix port casting issue in Redis configuration
- [ ] Fix error handling for invalid repositories
- [ ] Test complete code pipeline
- [ ] Test error scenarios
- [ ] Test performance requirements

**Estimated Time**: 6 hours
**Fixes Tests**: test_code_pipeline_end_to_end, test_code_pipeline_with_errors, test_code_pipeline_performance

### Task 3.6: Fix Multi-Repository Processing
- [ ] Implement sequential processing logic
- [ ] Implement status updates for multiple repos
- [ ] Implement failure handling
- [ ] Implement embedding isolation
- [ ] Test with multiple repositories
- [ ] Test failure scenarios

**Estimated Time**: 6 hours
**Fixes Tests**: test_multi_repo_sequential_processing, test_multi_repo_status_updates, test_multi_repo_with_failures, etc.

### Task 3.7: Fix Error Recovery Tests
- [ ] Implement Redis connection failure handling
- [ ] Implement Qdrant upload retry logic
- [ ] Implement Git clone failure handling
- [ ] Implement timeout handling
- [ ] Implement cleanup on error
- [ ] Test all error scenarios

**Estimated Time**: 8 hours
**Fixes Tests**: test_redis_connection_failure_on_submit, test_qdrant_upload_retry_on_failure, test_git_clone_failure_handling, etc.

**Week 3 Total**: 48 hours (~6 days)

---


## Week 4: Database & Model Fixes

### Task 4.1: Fix Resource Model URL Parameter
- [ ] Add url field to Resource model
- [ ] Update Resource.__init__ to accept url parameter
- [ ] Create migration to add url column
- [ ] Update all Resource instantiations to use url
- [ ] Test Resource creation with url parameter
- [ ] Update API schemas to include url

**Estimated Time**: 4 hours
**Fixes Tests**: test_annotation_complete_workflow, test_search_complete_workflow

### Task 4.2: Fix Foreign Key Constraints
- [ ] Ensure sample_user fixture creates user before resources
- [ ] Update sample_resource fixture to use sample_user.id
- [ ] Fix all test fixtures to satisfy foreign key constraints
- [ ] Add cascade delete where appropriate
- [ ] Test foreign key constraint enforcement
- [ ] Document fixture dependencies

**Estimated Time**: 6 hours
**Fixes Tests**: test_user_item_matrix_construction, test_negative_sampling_for_training, test_train_with_insufficient_data, etc.

### Task 4.3: Fix List Parameter Binding
- [ ] Replace direct list binding with bindparam(expanding=True)
- [ ] Fix recommendations service list queries
- [ ] Fix search service list queries
- [ ] Fix content-based strategy queries
- [ ] Test with SQLite and PostgreSQL
- [ ] Document list parameter handling pattern

**Estimated Time**: 6 hours
**Fixes Tests**: test_content_based_strategy_generates_recommendations, test_content_based_user_profile_building, etc.

### Task 4.4: Fix Embedding Storage and Retrieval
- [ ] Ensure embedding column accepts NULL
- [ ] Fix embedding serialization/deserialization
- [ ] Fix embedding queries with NULL handling
- [ ] Test embedding storage
- [ ] Test embedding retrieval
- [ ] Test NULL embedding handling

**Estimated Time**: 4 hours
**Fixes Tests**: test_store_chunks_embedding_failure

### Task 4.5: Fix CircuitBreaker Integration
- [ ] Use @circuit decorator instead of CircuitBreaker instance
- [ ] Fix GoogleOAuth2Provider
- [ ] Fix GitHubOAuth2Provider
- [ ] Remove manual CircuitBreaker attribute access
- [ ] Test circuit breaker functionality
- [ ] Test failure scenarios

**Estimated Time**: 4 hours
**Fixes Tests**: test_exchange_code_for_token_success, test_exchange_code_for_token_failure, etc.

### Task 4.6: Fix Token Revocation
- [ ] Implement proper token revocation in Redis
- [ ] Fix revoke_token to return True on success
- [ ] Fix is_token_revoked to check Redis
- [ ] Implement token TTL calculation
- [ ] Test token revocation
- [ ] Test revoked token detection

**Estimated Time**: 4 hours
**Fixes Tests**: test_revoke_token_marks_as_revoked, test_revoke_token_with_custom_ttl, test_different_tokens_revoked_independently

### Task 4.7: Fix TokenData Validation
- [ ] Fix TokenData Pydantic model
- [ ] Add proper field definitions
- [ ] Add default values where appropriate
- [ ] Test TokenData creation
- [ ] Test TokenData validation

**Estimated Time**: 2 hours
**Fixes Tests**: test_token_data_creation, test_token_data_defaults

### Task 4.8: Fix Authentication Flow Tests
- [ ] Fix complete authentication flow test
- [ ] Fix refresh token flow test
- [ ] Ensure token revocation works in flow
- [ ] Test with real Redis connection
- [ ] Document authentication flow

**Estimated Time**: 4 hours
**Fixes Tests**: test_complete_authentication_flow, test_refresh_token_flow

### Task 4.9: Fix Qdrant Client Integration
- [ ] Fix qdrant_client.models imports
- [ ] Implement proper Qdrant collection creation
- [ ] Implement batch upload logic
- [ ] Implement retry logic
- [ ] Test with mock Qdrant client
- [ ] Document Qdrant integration

**Estimated Time**: 6 hours
**Fixes Tests**: test_batch_upload_to_qdrant, test_retry_logic_on_upload_failure, test_collection_creation, etc.

**Week 4 Total**: 40 hours (~5 days)

---

## Week 5: Event System & Integration Tests

### Task 5.1: Fix Resource Chunking Event Handler
- [ ] Implement handle_resource_created in resources/handlers.py
- [ ] Register handler with event_bus
- [ ] Check CHUNK_ON_RESOURCE_CREATE setting
- [ ] Call ChunkingService.chunk_resource
- [ ] Add error handling and logging
- [ ] Test event emission and handling
- [ ] Verify ChunkingService is called

**Estimated Time**: 4 hours
**Fixes Tests**: test_handle_resource_created_triggers_chunking

### Task 5.2: Fix Graph Extraction Event Handler
- [ ] Implement handle_resource_chunked in graph/handlers.py
- [ ] Register handler with event_bus
- [ ] Check GRAPH_EXTRACTION_ENABLED setting
- [ ] Call GraphExtractionService
- [ ] Add error handling and logging
- [ ] Test event emission and handling
- [ ] Verify extraction is triggered

**Estimated Time**: 4 hours
**Fixes Tests**: test_handle_resource_chunked_triggers_extraction

### Task 5.3: Fix Event Chain Propagation
- [ ] Ensure resource.created emits correctly
- [ ] Ensure resource.chunked emits after chunking
- [ ] Ensure graph extraction emits after extraction
- [ ] Test full event chain
- [ ] Test with extraction disabled
- [ ] Document event flow

**Estimated Time**: 4 hours
**Fixes Tests**: test_full_event_chain, test_event_chain_with_extraction_disabled

### Task 5.4: Fix Enhanced Search Tests
- [ ] Fix GraphRAG search response structure
- [ ] Add entities field to GraphRAG results
- [ ] Fix question-based retrieval
- [ ] Fix hybrid mode deduplication
- [ ] Test all search strategies
- [ ] Document search response formats

**Estimated Time**: 6 hours
**Fixes Tests**: test_graphrag_search_basic, test_question_search_hybrid_mode

### Task 5.5: Fix E2E Workflow Tests
- [ ] Fix annotation workflow (Resource url parameter)
- [ ] Fix search workflow (202 vs 201 status)
- [ ] Test complete workflows end-to-end
- [ ] Document workflow patterns

**Estimated Time**: 4 hours
**Fixes Tests**: test_annotation_complete_workflow, test_search_complete_workflow

### Task 5.6: Fix Phase 20 E2E Workflows
- [ ] Implement document intelligence endpoints
- [ ] Implement AI planning endpoints
- [ ] Implement MCP endpoints
- [ ] Test complete workflows
- [ ] Document Phase 20 features

**Estimated Time**: 8 hours
**Fixes Tests**: test_document_intelligence_complete_workflow, test_ai_planning_complete_workflow, test_mcp_complete_workflow

### Task 5.7: Fix Curation Review Workflow
- [ ] Fix review queue filtering endpoint
- [ ] Fix review queue pagination
- [ ] Fix low quality endpoint
- [ ] Test curation workflows
- [ ] Document curation API

**Estimated Time**: 4 hours
**Fixes Tests**: test_review_queue_filtering, test_review_queue_pagination, test_low_quality_endpoint

### Task 5.8: Fix Taxonomy Flow Tests
- [ ] Fix category creation endpoint
- [ ] Fix resource classification endpoint
- [ ] Test taxonomy workflows
- [ ] Document taxonomy API

**Estimated Time**: 4 hours
**Fixes Tests**: test_category_creation_flow, test_resource_classification_flow

**Week 5 Total**: 38 hours (~4.75 days)

---

## Week 6: Performance Optimization & Final Validation

### Task 6.1: Optimize Search Latency
- [ ] Implement parallel keyword and semantic search
- [ ] Add caching for embeddings
- [ ] Add caching for search results
- [ ] Optimize database queries
- [ ] Test search latency < 500ms
- [ ] Profile and optimize bottlenecks

**Estimated Time**: 8 hours
**Fixes Tests**: test_search_latency_target

### Task 6.2: Optimize Hover Response Time
- [ ] Add caching for hover info
- [ ] Optimize hover info queries
- [ ] Limit related chunks to top 5
- [ ] Use indexed queries
- [ ] Test hover response < 100ms
- [ ] Profile and optimize bottlenecks

**Estimated Time**: 6 hours
**Fixes Tests**: test_property_hover_response_time, test_property_hover_response_time_random_positions

### Task 6.3: Optimize Recommendation Performance
- [ ] Optimize signal fusion algorithm
- [ ] Optimize MMR calculation
- [ ] Optimize novelty boosting
- [ ] Add caching where appropriate
- [ ] Test performance targets
- [ ] Profile and optimize bottlenecks

**Estimated Time**: 8 hours
**Fixes Tests**: test_ranking_performance, test_mmr_performance, test_novelty_boost_performance, test_full_recommendation_pipeline

### Task 6.4: Optimize Parent-Child Retrieval
- [ ] Optimize parent-child query
- [ ] Add caching for parent chunks
- [ ] Optimize context window retrieval
- [ ] Test retrieval < 200ms
- [ ] Profile and optimize bottlenecks

**Estimated Time**: 6 hours
**Fixes Tests**: test_parent_child_retrieval_under_200ms, test_complete_rag_pipeline_performance

### Task 6.5: Fix GPU Utilization Tests
- [ ] Fix neural graph training (empty parameter list)
- [ ] Ensure GPU is used during training
- [ ] Test GPU utilization > 70%
- [ ] Fix embedding generation tests
- [ ] Fix repository processing throughput
- [ ] Document GPU requirements

**Estimated Time**: 8 hours
**Fixes Tests**: test_training_loss_logging_every_5_epochs, test_gpu_utilization_during_training, test_embedding_generation_100_files, etc.

### Task 6.6: Fix Rate Limiter Implementation
- [ ] Fix rate limit header setting
- [ ] Fix tier limit retrieval
- [ ] Fix rate limit exceeded detection
- [ ] Fix TTL setting with pipeline
- [ ] Test rate limiting functionality
- [ ] Document rate limiting behavior

**Estimated Time**: 6 hours
**Fixes Tests**: test_check_rate_limit_free_tier_first_request, test_check_rate_limit_premium_tier, test_check_rate_limit_exceeded, etc.

### Task 6.7: Fix Monitoring Service Tests
- [ ] Fix health check status calculation
- [ ] Fix database health check
- [ ] Fix module health checks
- [ ] Fix recommendation quality metrics
- [ ] Test health check scenarios
- [ ] Document health check behavior

**Estimated Time**: 4 hours
**Fixes Tests**: test_health_check_all_healthy, test_health_check_db_unhealthy, test_health_check_with_modules, etc.

### Task 6.8: Fix Property-Based Test Deadlines
- [ ] Increase deadline for slow tests to 300ms
- [ ] Optimize test execution where possible
- [ ] Use @settings(deadline=300) for slow tests
- [ ] Test property-based tests complete within deadline
- [ ] Document performance expectations

**Estimated Time**: 4 hours
**Fixes Tests**: test_property_foreign_key_integrity, test_property_graph_triple_validity, test_session_context_preservation, etc.

### Task 6.9: Fix Golden Data Files
- [ ] Create missing taxonomy_prediction.json
- [ ] Validate all golden data files
- [ ] Test golden data file loading
- [ ] Document golden data format

**Estimated Time**: 2 hours
**Fixes Tests**: test_golden_data_files_valid_json

### Task 6.10: Fix Performance Decorator
- [ ] Fix performance regression detection message
- [ ] Ensure "PERFORMANCE REGRESSION DETECTED" appears in output
- [ ] Test performance decorator
- [ ] Document performance testing

**Estimated Time**: 2 hours
**Fixes Tests**: test_performance_decorator_works

### Task 6.11: Fix Recommendation Router Tests
- [ ] Register recommendations router
- [ ] Fix all recommendation endpoint tests
- [ ] Test recommendation workflows
- [ ] Document recommendation API

**Estimated Time**: 4 hours
**Fixes Tests**: test_get_recommendations_simple_success, test_track_interaction_success, test_get_profile_success, etc.

### Task 6.12: Fix Advanced Search Endpoint Tests
- [ ] Register advanced search router
- [ ] Fix all advanced search endpoint tests
- [ ] Test all search strategies
- [ ] Document advanced search API

**Estimated Time**: 4 hours
**Fixes Tests**: test_advanced_search_parent_child_strategy, test_advanced_search_graphrag_strategy, test_advanced_search_hybrid_strategy, etc.

### Task 6.13: Fix RAG Evaluation Endpoint Tests
- [ ] Register RAG evaluation router
- [ ] Fix all RAG evaluation endpoint tests
- [ ] Test evaluation submission
- [ ] Test metrics retrieval
- [ ] Test evaluation history
- [ ] Document RAG evaluation API

**Estimated Time**: 4 hours
**Fixes Tests**: test_submit_evaluation_success, test_get_metrics_with_data, test_get_history_success, etc.

### Task 6.14: Fix Chunking Endpoint Tests
- [ ] Register chunking router
- [ ] Fix get chunk endpoint
- [ ] Test chunk retrieval
- [ ] Document chunking API

**Estimated Time**: 2 hours
**Fixes Tests**: test_get_chunk_success

### Task 6.15: Fix Code Intelligence Property Tests
- [ ] Fix directory crawling completeness
- [ ] Fix gitignore compliance
- [ ] Fix binary file exclusion
- [ ] Fix task state transitions
- [ ] Fix error tracking
- [ ] Document code intelligence behavior

**Estimated Time**: 6 hours
**Fixes Tests**: test_property_directory_crawling_completeness, test_property_gitignore_compliance, test_property_binary_file_exclusion, etc.

### Task 6.16: Fix Cloud API Property Tests
- [ ] Fix task queue round trip
- [ ] Fix URL validation
- [ ] Fix status endpoint
- [ ] Fix authentication requirement
- [ ] Test all cloud API properties
- [ ] Document cloud API behavior

**Estimated Time**: 4 hours
**Fixes Tests**: test_property_1_task_queue_round_trip, test_property_3_url_validation_rejects_invalid_input, test_property_4_status_endpoint_reflects_redis_state, etc.

### Task 6.17: Fix Worker Initialization Tests
- [ ] Fix get_embedding_service initialization check
- [ ] Test worker initialization
- [ ] Document worker setup

**Estimated Time**: 2 hours
**Fixes Tests**: test_get_embedding_service_not_initialized

### Task 6.18: Final Test Suite Validation
- [ ] Run complete test suite
- [ ] Verify 0 failures, 0 errors
- [ ] Check test coverage
- [ ] Generate test report
- [ ] Document test results

**Estimated Time**: 4 hours

### Task 6.19: Documentation Updates
- [ ] Update ISSUES.md (mark all issues resolved)
- [ ] Update deployment documentation
- [ ] Update API documentation
- [ ] Update configuration documentation
- [ ] Create migration guide for configuration changes

**Estimated Time**: 6 hours

### Task 6.20: Final Security Audit
- [ ] Verify all security issues resolved
- [ ] Run security scanners (bandit, safety)
- [ ] Review authentication flows
- [ ] Review input validation
- [ ] Document security improvements

**Estimated Time**: 4 hours

**Week 6 Total**: 94 hours (~11.75 days)

---

## Summary

### Total Estimated Time by Week
- Week 1 (Security): 52 hours (~6.5 days)
- Week 2 (Configuration): 37 hours (~4.6 days)
- Week 3 (API & Phase 19): 48 hours (~6 days)
- Week 4 (Database & Models): 40 hours (~5 days)
- Week 5 (Events & Integration): 38 hours (~4.75 days)
- Week 6 (Performance & Validation): 94 hours (~11.75 days)

**Total**: 309 hours (~38.6 working days or ~7.7 weeks at 40 hours/week)

### Critical Path
1. **Security Hardening** (Week 1) - Must be completed first
2. **Configuration Management** (Week 2) - Enables proper testing
3. **API Registration** (Week 3) - Fixes 404 errors
4. **Database Fixes** (Week 4) - Fixes foreign key issues
5. **Event System** (Week 5) - Fixes integration tests
6. **Performance & Validation** (Week 6) - Final polish

### Success Criteria
- [ ] All 267 failing tests passing
- [ ] 0 test errors
- [ ] All 22 open issues resolved
- [ ] All 5 critical security issues fixed
- [ ] All API endpoints registered and accessible
- [ ] All performance targets met
- [ ] Test coverage maintained or improved
- [ ] Documentation updated

### Risk Mitigation

**Risk**: Breaking existing functionality
**Mitigation**: Run full test suite after each task, fix incrementally

**Risk**: Security fixes breaking legitimate use cases
**Mitigation**: Provide proper escape hatches, document changes thoroughly

**Risk**: Performance optimizations causing regressions
**Mitigation**: Benchmark before and after, use profiling tools

**Risk**: Configuration changes breaking deployments
**Mitigation**: Provide migration guide, document all changes

## Related Documentation

- [Requirements](requirements.md)
- [Design](design.md)
- [ISSUES.md](../../../backend/docs/ISSUES.md)
- [Tech Stack](../../../.kiro/steering/tech.md)
- [Test Summary](../../../BACKEND_TEST_SUMMARY.md)

