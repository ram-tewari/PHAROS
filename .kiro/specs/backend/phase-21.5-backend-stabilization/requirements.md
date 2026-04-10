# Phase 21.5: Backend Stabilization - Requirements

## Overview

Comprehensive backend stabilization phase to fix all 267 failing tests, resolve all 22 open issues from ISSUES.md, and establish a production-ready, secure, and reliable backend system. This phase focuses on test suite stabilization, security hardening, configuration management, and technical debt resolution.

## Problem Statement

The Pharos backend currently has:
- **267 failing tests** across integration, unit, performance, and property-based test suites
- **22 open issues** including 5 critical security vulnerabilities
- **Configuration management problems** with hardcoded secrets and missing validation
- **Test infrastructure issues** with mocking, fixtures, and performance thresholds
- **Missing API endpoints** and incomplete feature implementations
- **Platform compatibility issues** between SQLite and PostgreSQL

This phase will systematically address all issues to achieve a stable, secure, production-ready backend.

## User Stories

### As a DevOps Engineer
- I want all tests to pass reliably so I can trust the CI/CD pipeline
- I want secure configuration management so production deployments are safe
- I want proper error handling so I can diagnose issues quickly
- I want performance benchmarks to meet targets so the system scales

### As a Security Engineer
- I want all authentication bypasses closed so the system is secure
- I want secrets properly managed so credentials aren't leaked
- I want input validation on all endpoints so attacks are prevented
- I want CSRF protection so users are protected from attacks

### As a Backend Developer
- I want consistent test fixtures so tests are maintainable
- I want clear error messages so debugging is efficient
- I want proper mocking so tests run fast and reliably
- I want documentation so I understand system behavior

## Functional Requirements

### 1. Test Suite Stabilization

**FR-1.1**: Fix all 267 failing tests across all test categories
**FR-1.2**: Establish consistent test fixtures and factories
**FR-1.3**: Fix mocking issues with Settings and configuration
**FR-1.4**: Update performance thresholds to realistic values
**FR-1.5**: Fix property-based test deadline violations
**FR-1.6**: Resolve foreign key constraint failures in tests
**FR-1.7**: Fix golden data file issues and test infrastructure

### 2. Security Hardening

**FR-2.1**: Remove hardcoded default secrets from configuration
**FR-2.2**: Eliminate authentication bypass in TEST_MODE
**FR-2.3**: Fix open redirect vulnerability in OAuth2 callback
**FR-2.4**: Implement proper CSRF protection
**FR-2.5**: Add rate limiting to authentication endpoints
**FR-2.6**: Validate and sanitize all repository URLs (SSRF prevention)
**FR-2.7**: Implement file upload validation and size limits
**FR-2.8**: Use HTTP-only cookies for token transmission
**FR-2.9**: Add URL allowlisting for external requests
**FR-2.10**: Implement proper temporary file cleanup

### 3. Configuration Management

**FR-3.1**: Fix Settings mocking in tests
**FR-3.2**: Implement proper environment variable validation
**FR-3.3**: Create requirements-base.txt, requirements-cloud.txt, requirements-edge.txt
**FR-3.4**: Add configuration validation at startup
**FR-3.5**: Implement proper default values for all settings
**FR-3.6**: Fix MODE configuration and validation
**FR-3.7**: Add Upstash Redis configuration validation
**FR-3.8**: Implement proper database URL construction

### 4. API Endpoint Completeness

**FR-4.1**: Register all missing API endpoints (RAG evaluation, recommendations, taxonomy, advanced search)
**FR-4.2**: Fix 404 errors for implemented but unregistered endpoints
**FR-4.3**: Implement missing chunking endpoints
**FR-4.4**: Complete Phase 20 endpoints (document intelligence, AI planning, MCP)
**FR-4.5**: Fix collection review queue endpoints

### 5. Phase 19 Cloud/Edge Architecture

**FR-5.1**: Fix cloud API integration tests (429, worker status, job history)
**FR-5.2**: Implement proper queue service configuration
**FR-5.3**: Fix worker.py imports and process_job function
**FR-5.4**: Implement proper Redis connection handling
**FR-5.5**: Fix Qdrant client integration
**FR-5.6**: Implement proper error recovery and retry logic
**FR-5.7**: Fix multi-repository processing

### 6. Database and Model Fixes

**FR-6.1**: Fix Resource model constructor to accept 'url' parameter
**FR-6.2**: Fix foreign key constraints in recommendations tests
**FR-6.3**: Fix embedding storage and retrieval
**FR-6.4**: Fix list parameter binding in SQLite queries
**FR-6.5**: Implement proper NULL handling for embeddings
**FR-6.6**: Fix CircuitBreaker attribute access issues

### 7. Performance Optimization

**FR-7.1**: Fix search latency to meet <500ms target
**FR-7.2**: Optimize hover response time to <100ms
**FR-7.3**: Fix recommendation ranking performance
**FR-7.4**: Optimize parent-child retrieval to <200ms
**FR-7.5**: Fix GPU utilization and training performance
**FR-7.6**: Optimize three-way hybrid search

### 8. Event System Fixes

**FR-8.1**: Fix resource chunking event handler
**FR-8.2**: Fix graph extraction event handler
**FR-8.3**: Implement proper event chain propagation
**FR-8.4**: Fix event emission and subscription

### 9. OAuth2 and Authentication

**FR-9.1**: Fix CircuitBreaker integration in OAuth2 providers
**FR-9.2**: Implement proper token revocation
**FR-9.3**: Fix TokenData validation
**FR-9.4**: Implement complete authentication flow tests
**FR-9.5**: Fix refresh token flow

### 10. Rate Limiting

**FR-10.1**: Fix rate limiter Redis integration
**FR-10.2**: Implement proper rate limit headers
**FR-10.3**: Fix tier limit retrieval
**FR-10.4**: Implement proper TTL setting
**FR-10.5**: Fix rate limit exceeded detection

## Non-Functional Requirements

### Performance

**NFR-1**: All performance tests must pass with realistic thresholds
**NFR-2**: Search latency P95 < 500ms
**NFR-3**: API response time P95 < 200ms
**NFR-4**: Hover response time < 100ms
**NFR-5**: Property-based tests complete within 200ms deadline

### Security

**NFR-6**: No hardcoded secrets in production code
**NFR-7**: All authentication bypasses removed
**NFR-8**: CSRF protection on all state-changing endpoints
**NFR-9**: Rate limiting on authentication endpoints
**NFR-10**: Input validation on all user-provided data
**NFR-11**: Secure token transmission (HTTP-only cookies)
**NFR-12**: URL allowlisting for external requests

### Reliability

**NFR-13**: 100% test pass rate (0 failures, 0 errors)
**NFR-14**: All API endpoints registered and accessible
**NFR-15**: Proper error handling with informative messages
**NFR-16**: Graceful degradation for optional dependencies
**NFR-17**: Proper resource cleanup (temp files, connections)

### Maintainability

**NFR-18**: Consistent test fixtures across all test files
**NFR-19**: Proper mocking patterns for external dependencies
**NFR-20**: Clear documentation for configuration
**NFR-21**: All TODOs tracked and prioritized
**NFR-22**: Golden data files present and valid

## Acceptance Criteria

### AC-1: Test Suite Health
- [ ] All 267 failing tests fixed and passing
- [ ] 0 test errors
- [ ] 0 test failures
- [ ] All property-based tests complete within deadline
- [ ] All performance tests meet thresholds
- [ ] Test coverage maintained or improved

### AC-2: Security Posture
- [ ] All 5 critical security issues resolved
- [ ] No hardcoded secrets in code
- [ ] Authentication bypass removed
- [ ] CSRF protection implemented
- [ ] Rate limiting on auth endpoints
- [ ] Input validation on all endpoints
- [ ] Security audit passes

### AC-3: Configuration Management
- [ ] Settings properly mocked in all tests
- [ ] Environment variable validation implemented
- [ ] Requirements files split (base, cloud, edge)
- [ ] Configuration defaults set correctly
- [ ] Startup validation prevents invalid config
- [ ] Documentation updated

### AC-4: API Completeness
- [ ] All endpoints registered and accessible
- [ ] No 404 errors for implemented features
- [ ] RAG evaluation endpoints working
- [ ] Recommendation endpoints working
- [ ] Taxonomy endpoints working
- [ ] Advanced search endpoints working
- [ ] Phase 20 endpoints implemented

### AC-5: Phase 19 Integration
- [ ] Cloud API tests passing
- [ ] Worker process functioning
- [ ] Queue service configured
- [ ] Redis integration working
- [ ] Qdrant integration working
- [ ] Multi-repo processing working
- [ ] Error recovery implemented

### AC-6: Database Integrity
- [ ] All foreign key constraints satisfied
- [ ] Resource model accepts all valid parameters
- [ ] Embedding storage/retrieval working
- [ ] List parameters handled correctly
- [ ] NULL handling correct
- [ ] Migrations complete and tested

### AC-7: Performance Targets
- [ ] Search latency < 500ms (P95)
- [ ] Hover response < 100ms
- [ ] Recommendation ranking < 50ms
- [ ] Parent-child retrieval < 200ms
- [ ] GPU utilization > 70% during training
- [ ] All performance tests passing

### AC-8: Event System
- [ ] Resource chunking events working
- [ ] Graph extraction events working
- [ ] Event chain propagation working
- [ ] Event handlers registered
- [ ] Event emission reliable

## Out of Scope

- ❌ New features or functionality
- ❌ Frontend changes
- ❌ Database schema changes (unless required for fixes)
- ❌ Performance optimizations beyond test requirements
- ❌ Refactoring for code quality (unless required for fixes)
- ❌ Documentation updates (except configuration)

## Success Metrics

- **Test Pass Rate**: 100% (0 failures, 0 errors)
- **Security Issues**: 0 critical, 0 high
- **Configuration Issues**: 0 open
- **API Completeness**: 100% endpoints registered
- **Performance Compliance**: 100% tests meeting thresholds
- **Code Coverage**: Maintained or improved from current baseline

## Dependencies

- Existing Pharos backend codebase
- Test suite infrastructure
- PostgreSQL and SQLite databases
- Redis (Upstash) for queue and rate limiting
- Qdrant for vector storage
- Python 3.8+ ecosystem

## Timeline Estimate

- **Week 1**: Security hardening (5 critical issues)
- **Week 2**: Configuration management and Settings fixes
- **Week 3**: API endpoint registration and Phase 19 fixes
- **Week 4**: Database and model fixes
- **Week 5**: Event system and integration tests
- **Week 6**: Performance optimization and final validation

**Total**: 6 weeks (1.5 months)

## Risk Mitigation

**Risk**: Breaking existing functionality while fixing tests
**Mitigation**: Fix tests incrementally, run full suite after each change

**Risk**: Security fixes breaking legitimate use cases
**Mitigation**: Implement security with proper escape hatches, document changes

**Risk**: Performance optimizations causing regressions
**Mitigation**: Benchmark before and after, use profiling tools

**Risk**: Configuration changes breaking deployments
**Mitigation**: Document all configuration changes, provide migration guide

## Related Documentation

- [ISSUES.md](../../../backend/docs/ISSUES.md) - Complete issue log
- [Tech Stack](../../../.kiro/steering/tech.md) - Technology constraints
- [Test Summary](../../../BACKEND_TEST_SUMMARY.md) - Current test status
- [Architecture](../../../backend/docs/architecture/overview.md) - System architecture

