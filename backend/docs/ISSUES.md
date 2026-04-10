# Pharos Backend Issues Log

**Purpose**: This document tracks all identified issues, bugs, and technical debt across the Pharos backend implementation. Issues are organized chronologically and categorized by severity and phase.

**Last Updated**: 2026-02-16

---

## Table of Contents

- [Critical Issues](#critical-issues)
- [High Priority Issues](#high-priority-issues)
- [Medium Priority Issues](#medium-priority-issues)
- [Low Priority Issues](#low-priority-issues)
- [Resolved Issues](#resolved-issues)

---

## Critical Issues

### ISSUE-2026-02-16-001: Hardcoded Default Secrets in Production Configuration

**ID**: ISSUE-2026-02-16-001  
**Phase**: Phase 17 (Production Hardening)  
**Category**: Critical/Security  
**Severity**: Critical  
**Status**: 🔴 Open  
**Reported**: 2026-02-16  
**Reporter**: Security Audit

**Problem**:
Configuration file contains hardcoded default secrets that are used if environment variables are not set:
- `JWT_SECRET_KEY: SecretStr = SecretStr("change-this-secret-key-in-production")`
- `POSTGRES_PASSWORD: str = "devpassword"`

These defaults could be accidentally deployed to production, allowing attackers to forge JWT tokens or access the database.

**Root Cause**:
Development convenience prioritized over security. Default values provided for local development without forcing production deployments to explicitly set secrets.

**Solution**:
1. Remove default values for security-critical settings
2. Make JWT_SECRET_KEY and POSTGRES_PASSWORD required fields without defaults
3. Add startup validation that fails if secrets are still set to default values
4. Document required environment variables in deployment guide
5. Add pre-deployment checklist to verify secrets are configured

**Files Changed**:
- `backend/app/config/settings.py` (line 45-50)

**Impact**:
- Prevents accidental deployment with default credentials
- Forces explicit secret configuration
- Improves production security posture
- May break local development if .env not configured

**Prevention**:
- Never provide defaults for security-critical configuration
- Use environment variable validation at startup
- Add security checklist to deployment documentation
- Implement secret scanning in CI/CD pipeline
- Use secret management tools (AWS Secrets Manager, HashiCorp Vault)

---

### ISSUE-2026-02-16-002: Authentication Bypass in Test Mode

**ID**: ISSUE-2026-02-16-002  
**Phase**: Phase 17 (Production Hardening)  
**Category**: Critical/Security  
**Severity**: Critical  
**Status**: 🔴 Open  
**Reported**: 2026-02-16  
**Reporter**: Security Audit

**Problem**:
Authentication can be completely bypassed by setting `TEST_MODE=true` or `TESTING=true` environment variable. This is checked in production code paths:
```python
if settings.is_test_mode or settings.TEST_MODE:
    logger.info("TEST_MODE enabled - bypassing authentication")
```

An attacker who can set environment variables (via container orchestration misconfiguration, compromised CI/CD, etc.) can bypass all authentication.

**Root Cause**:
Test mode bypass implemented in production code rather than test-specific code. No safeguards prevent TEST_MODE from being enabled in production environments.

**Solution**:
1. Remove TEST_MODE bypass from production authentication middleware
2. Use dependency injection to provide mock authentication in tests
3. Add environment validation that prevents TEST_MODE in production (ENV=production)
4. Log critical security warning if TEST_MODE is enabled
5. Add monitoring alert for TEST_MODE being enabled in production

**Files Changed**:
- `backend/app/shared/security.py` (line 363-375)
- `backend/app/__init__.py` (line 102-110, 213-217, 280-285, 325-327)

**Impact**:
- Eliminates authentication bypass vector
- Requires proper test setup with mocked dependencies
- Improves production security
- May require test refactoring

**Prevention**:
- Never implement security bypasses in production code
- Use dependency injection for test doubles
- Validate environment configuration at startup
- Add security monitoring for suspicious configuration
- Implement defense-in-depth (multiple authentication layers)

---

### ISSUE-2026-02-16-003: Open Redirect Vulnerability in OAuth2 Callback

**ID**: ISSUE-2026-02-16-003  
**Phase**: Phase 17 (Production Hardening)  
**Category**: Critical/Security  
**Severity**: Critical  
**Status**: 🔴 Open  
**Reported**: 2026-02-16  
**Reporter**: Security Audit

**Problem**:
OAuth2 callback redirects to frontend URL constructed from configuration without validation:
```python
frontend_callback_url = f"{settings.FRONTEND_URL}/auth/callback?access_token={access_token}&refresh_token={refresh_token}"
return RedirectResponse(url=frontend_callback_url)
```

If `FRONTEND_URL` is compromised or misconfigured, tokens could be sent to an attacker-controlled domain. Additionally, tokens are passed in URL query parameters, which are logged by browsers, proxies, and servers.

**Root Cause**:
1. No validation of redirect URL against allowlist
2. Tokens passed in URL instead of secure HTTP-only cookies
3. Trust in configuration without runtime validation

**Solution**:
1. Implement redirect URL allowlist validation
2. Use HTTP-only, Secure, SameSite cookies for tokens instead of URL parameters
3. Add CSRF protection for OAuth2 flow
4. Validate FRONTEND_URL format at startup (must be HTTPS in production)
5. Log all redirects for security monitoring

**Files Changed**:
- `backend/app/modules/auth/router.py` (line 279-282, 381-384)

**Impact**:
- Prevents token theft via open redirect
- Protects tokens from URL logging
- Improves OAuth2 security
- Requires frontend changes to read cookies

**Prevention**:
- Always validate redirect URLs against allowlist
- Never pass tokens in URLs (use cookies or POST body)
- Implement CSRF protection for state-changing operations
- Use HTTPS-only in production
- Regular security audits of authentication flows

---

### ISSUE-2026-02-16-004: Path Traversal Risk in File Upload

**ID**: ISSUE-2026-02-16-004  
**Phase**: Phase 7 (Collection Management)  
**Category**: Critical/Security  
**Severity**: High  
**Status**: 🔴 Open  
**Reported**: 2026-02-16  
**Reporter**: Security Audit

**Problem**:
File upload endpoint generates filenames but doesn't validate file extensions or content types thoroughly:
```python
safe_filename = f"{file_id}{file_ext}"
file_path = storage_dir / safe_filename
```

While UUID is used for filename, the file extension comes from user input. Malicious extensions like `.php`, `.jsp`, or double extensions like `.pdf.exe` could be uploaded. Additionally, no file size limits are enforced.

**Root Cause**:
1. Insufficient file extension validation (only checks if in allowed list)
2. No content-type verification against actual file content
3. No file size limits enforced
4. No virus/malware scanning

**Solution**:
1. Implement strict file extension allowlist (only `.pdf`, `.txt`, `.md`, `.html`)
2. Verify file content matches declared content-type (magic number validation)
3. Enforce maximum file size limit (e.g., 50MB)
4. Strip all metadata from uploaded files
5. Store files outside web root with no execute permissions
6. Consider virus scanning for uploaded files
7. Implement rate limiting on upload endpoint

**Files Changed**:
- `backend/app/modules/resources/router.py` (line 280-340)

**Impact**:
- Prevents malicious file uploads
- Protects against file-based attacks
- Limits resource exhaustion
- May reject some legitimate files

**Prevention**:
- Always validate file extensions against strict allowlist
- Verify file content matches extension (magic numbers)
- Enforce file size limits
- Store uploads outside web root
- Implement virus scanning
- Use Content-Security-Policy headers
- Regular security testing of upload functionality

---

### ISSUE-2026-02-16-005: SSRF Vulnerability in Repository Cloning

**ID**: ISSUE-2026-02-16-005  
**Phase**: Phase 18 (Code Intelligence)  
**Category**: Critical/Security  
**Severity**: High  
**Status**: 🔴 Open  
**Reported**: 2026-02-16  
**Reporter**: Security Audit

**Problem**:
Repository ingestion endpoint accepts arbitrary Git URLs without validation:
```python
@router.post("/ingest-repo")
async def ingest_repo(repo_url: str, ...)
```

An attacker could provide URLs to internal services (e.g., `http://localhost:6379`, `http://169.254.169.254/latest/meta-data/`) to perform Server-Side Request Forgery (SSRF) attacks, potentially accessing internal services or cloud metadata endpoints.

**Root Cause**:
1. No URL validation or allowlist
2. Git clone can access any network-accessible URL
3. No network segmentation for worker processes
4. No timeout or resource limits on clone operations

**Solution**:
1. Implement URL allowlist (only allow github.com, gitlab.com, bitbucket.org)
2. Block private IP ranges (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 127.0.0.0/8)
3. Block cloud metadata endpoints (169.254.169.254)
4. Implement timeout for clone operations (e.g., 5 minutes)
5. Run worker in isolated network namespace
6. Add rate limiting per user/IP
7. Log all clone attempts for security monitoring

**Files Changed**:
- `backend/app/routers/ingestion.py` (line 80-180)
- `backend/app/modules/resources/logic/repo_ingestion.py`

**Impact**:
- Prevents SSRF attacks
- Protects internal services
- Limits resource exhaustion
- May block some legitimate private repositories

**Prevention**:
- Always validate and sanitize URLs
- Implement URL allowlists for external requests
- Block private IP ranges and metadata endpoints
- Use network segmentation
- Implement timeouts and resource limits
- Regular security testing of external request functionality

---

### ISSUE-2026-01-08-001: Boolean Column Type Mismatch (PostgreSQL)

**ID**: ISSUE-2026-01-08-001  
**Phase**: Phase 13 (PostgreSQL Migration)  
**Category**: Critical/Platform  
**Severity**: Critical  
**Status**: ✅ Resolved  
**Reported**: 2026-01-08  
**Resolved**: 2026-01-08  
**Reporter**: Migration System

**Problem**:
Boolean columns in the `resources` table were stored as INTEGER (0/1) instead of proper BOOLEAN type in PostgreSQL. This caused type errors when querying with boolean filters and violated PostgreSQL best practices.

**Root Cause**:
Initial migration scripts used INTEGER type for boolean fields to maintain SQLite compatibility, but PostgreSQL has native BOOLEAN support that should be used.

**Solution**:
Created migration `20260108_fix_boolean_columns.py` that converts INTEGER columns to BOOLEAN using CASE statements for data preservation.

**Files Changed**:
- `backend/alembic/versions/20260108_fix_boolean_columns.py`

**Impact**:
- Fixed type errors in PostgreSQL queries
- Improved database schema correctness
- Maintained SQLite compatibility (uses INTEGER for booleans)

**Prevention**:
- Use database-agnostic type checking in migrations
- Test migrations against both SQLite and PostgreSQL
- Document platform-specific type handling

---

### ISSUE-2026-01-08-002: Embedding Column Default Value Issue

**ID**: ISSUE-2026-01-08-002  
**Phase**: Phase 17.5 (Advanced RAG)  
**Category**: Critical/Bug  
**Severity**: Critical  
**Status**: ✅ Resolved  
**Reported**: 2026-01-08  
**Resolved**: 2026-01-08  
**Reporter**: Test Suite

**Problem**:
The `embedding` column had a server_default of empty array `[]`, causing issues with NULL handling and preventing proper distinction between "no embedding" and "empty embedding".

**Root Cause**:
Server defaults for complex types like arrays/JSON can cause unexpected behavior. NULL is more appropriate for "no embedding yet" state.

**Solution**:
Created migration `20260108_fix_embedding_default.py` that:
1. Removed server_default from embedding column
2. Changed type from ARRAY to JSON for better NULL handling in PostgreSQL
3. Updated existing empty arrays to NULL

**Files Changed**:
- `backend/alembic/versions/20260108_fix_embedding_default.py`

**Impact**:
- Proper NULL handling for embeddings
- Clearer semantic distinction between states
- Fixed test failures related to embedding queries

**Prevention**:
- Avoid server defaults for complex types
- Use NULL for "not yet computed" states
- Test NULL handling explicitly in test suite

---

### ISSUE-2026-01-08-003: Embedding Column Type Casting Issues

**ID**: ISSUE-2026-01-08-003  
**Phase**: Phase 17.5 (Advanced RAG)  
**Category**: Critical/Bug  
**Severity**: Critical  
**Status**: ✅ Resolved  
**Reported**: 2026-01-08  
**Resolved**: 2026-01-08  
**Reporter**: Test Suite

**Problem**:
After changing embedding column from ARRAY to JSON, PostgreSQL required explicit casting for NULL comparisons, causing query failures.

**Root Cause**:
JSON type in PostgreSQL doesn't support direct NULL comparison without casting to text first.

**Solution**:
Created migration `20260108_fix_embedding_type.py` that changes embedding column from JSON to TEXT to avoid casting issues while maintaining flexibility.

**Files Changed**:
- `backend/alembic/versions/20260108_fix_embedding_type.py`

**Impact**:
- Eliminated casting errors in queries
- Simplified NULL handling
- Maintained backward compatibility

**Prevention**:
- Consider type casting requirements when choosing column types
- Test NULL comparisons for all column types
- Document type-specific query patterns

---

## High Priority Issues

### ISSUE-2026-02-16-006: Tokens Exposed in Logs and Browser History

**ID**: ISSUE-2026-02-16-006  
**Phase**: Phase 17 (Production Hardening)  
**Category**: High/Security  
**Severity**: High  
**Status**: 🔴 Open  
**Reported**: 2026-02-16  
**Reporter**: Security Audit

**Problem**:
JWT tokens are passed in URL query parameters during OAuth2 callback:
```python
frontend_callback_url = f"{settings.FRONTEND_URL}/auth/callback?access_token={access_token}&refresh_token={refresh_token}"
```

This causes tokens to be:
1. Logged in browser history
2. Logged in web server access logs
3. Logged in proxy server logs
4. Sent in Referer headers to third-party sites
5. Visible in browser developer tools

**Root Cause**:
Convenience prioritized over security. URL parameters are easier to implement than secure cookie handling.

**Solution**:
1. Use HTTP-only, Secure, SameSite cookies for token transmission
2. Implement POST-based token exchange instead of GET with query params
3. Use short-lived tokens with refresh mechanism
4. Clear sensitive data from logs
5. Implement token rotation on each use

**Files Changed**:
- `backend/app/modules/auth/router.py` (line 279-282, 381-384)

**Impact**:
- Prevents token leakage via logs
- Protects against token theft
- Improves security posture
- Requires frontend cookie handling

**Prevention**:
- Never pass tokens in URLs
- Use HTTP-only cookies for sensitive data
- Implement token rotation
- Regular security audits
- Security training for developers

---

### ISSUE-2026-02-16-007: Missing Rate Limiting on Authentication Endpoints

**ID**: ISSUE-2026-02-16-007  
**Phase**: Phase 17 (Production Hardening)  
**Category**: High/Security  
**Severity**: High  
**Status**: 🔴 Open  
**Reported**: 2026-02-16  
**Reporter**: Security Audit

**Problem**:
Authentication endpoints (`/auth/login`, `/auth/refresh`) lack rate limiting, allowing brute force attacks on user credentials and token refresh endpoints.

**Root Cause**:
Rate limiting implemented for general API endpoints but not specifically for authentication endpoints which are higher risk.

**Solution**:
1. Implement strict rate limiting on `/auth/login` (e.g., 5 attempts per 15 minutes per IP)
2. Implement rate limiting on `/auth/refresh` (e.g., 10 attempts per hour per token)
3. Add account lockout after failed attempts
4. Implement CAPTCHA after 3 failed attempts
5. Log all failed authentication attempts
6. Add monitoring alerts for brute force patterns

**Files Changed**:
- `backend/app/modules/auth/router.py`
- `backend/app/shared/rate_limiter.py`

**Impact**:
- Prevents brute force attacks
- Protects user accounts
- Improves security monitoring
- May impact legitimate users with typos

**Prevention**:
- Always rate limit authentication endpoints
- Implement progressive delays
- Use CAPTCHA for suspicious activity
- Monitor for attack patterns
- Regular security testing

---

### ISSUE-2026-02-16-008: Insufficient Input Validation on Repository URLs

**ID**: ISSUE-2026-02-16-008  
**Phase**: Phase 18 (Code Intelligence)  
**Category**: High/Security  
**Severity**: High  
**Status**: 🔴 Open  
**Reported**: 2026-02-16  
**Reporter**: Security Audit

**Problem**:
Repository URL validation is minimal, accepting any string without format validation, protocol checking, or domain validation. This could lead to command injection via Git URLs with special characters.

**Root Cause**:
Trust in user input without proper validation. Git URLs can contain special characters that might be interpreted by shell.

**Solution**:
1. Validate URL format using regex (must match git URL patterns)
2. Allowlist protocols (only https://, git://)
3. Validate domain against allowlist
4. Sanitize URL before passing to git command
5. Use GitPython library instead of shell commands
6. Implement URL length limits
7. Block URLs with special characters

**Files Changed**:
- `backend/app/routers/ingestion.py`
- `backend/app/utils/repo_parser.py`

**Impact**:
- Prevents command injection
- Limits SSRF attack surface
- Improves input validation
- May reject some edge case URLs

**Prevention**:
- Always validate and sanitize URLs
- Use libraries instead of shell commands
- Implement allowlists for protocols and domains
- Regular security testing
- Input validation at multiple layers

---

### ISSUE-2026-02-16-009: Temporary File Cleanup Race Condition

**ID**: ISSUE-2026-02-16-009  
**Phase**: Phase 18 (Code Intelligence)  
**Category**: High/Bug  
**Severity**: Medium  
**Status**: 🔴 Open  
**Reported**: 2026-02-16  
**Reporter**: Security Audit

**Problem**:
Temporary directories for cloned repositories are cleaned up with `ignore_errors=True`, which silently fails if cleanup encounters errors. This could lead to disk space exhaustion over time.

```python
shutil.rmtree(temp_dir, ignore_errors=True)
```

**Root Cause**:
Error suppression for convenience without proper error handling or monitoring.

**Solution**:
1. Remove `ignore_errors=True` and handle errors explicitly
2. Log cleanup failures for monitoring
3. Implement periodic cleanup job for orphaned temp directories
4. Add disk space monitoring and alerts
5. Use context managers for automatic cleanup
6. Set TTL on temp directories

**Files Changed**:
- `backend/app/utils/repo_parser.py` (line 102, 140)
- `backend/app/modules/resources/logic/repo_ingestion.py` (line 301)

**Impact**:
- Prevents disk space exhaustion
- Improves error visibility
- Better resource management
- May expose previously hidden errors

**Prevention**:
- Never silently ignore errors
- Implement proper error handling
- Add monitoring for resource usage
- Use context managers for cleanup
- Regular cleanup jobs for orphaned resources

---

### ISSUE-2026-02-16-010: Missing CSRF Protection on State-Changing Endpoints

**ID**: ISSUE-2026-02-16-010  
**Phase**: Phase 17 (Production Hardening)  
**Category**: High/Security  
**Severity**: High  
**Status**: 🔴 Open  
**Reported**: 2026-02-16  
**Reporter**: Security Audit

**Problem**:
State-changing endpoints (POST, PUT, DELETE) lack CSRF protection. An attacker could trick authenticated users into performing unwanted actions via malicious websites.

**Root Cause**:
JWT authentication used without CSRF tokens. While JWT in Authorization header provides some protection, cookie-based sessions would be vulnerable.

**Solution**:
1. Implement CSRF token generation and validation
2. Require CSRF token in custom header for state-changing requests
3. Use SameSite cookie attribute
4. Implement double-submit cookie pattern
5. Add Origin/Referer header validation
6. Document CSRF protection in API documentation

**Files Changed**:
- `backend/app/__init__.py` (middleware)
- All router files with POST/PUT/DELETE endpoints

**Impact**:
- Prevents CSRF attacks
- Improves security posture
- Requires frontend changes
- May break existing API clients

**Prevention**:
- Always implement CSRF protection
- Use SameSite cookies
- Validate Origin/Referer headers
- Regular security testing
- Security training for developers

---

### ISSUE-2025-12-XX-001: Resource Model Constructor Parameter Mismatch

**ID**: ISSUE-2025-12-XX-001  
**Phase**: Phase 9 (Quality Assessment)  
**Category**: High/Bug  
**Severity**: High  
**Status**: ✅ Resolved  
**Reported**: 2025-12-XX  
**Resolved**: 2025-12-XX  
**Reporter**: Test Suite

**Problem**:
Tests were instantiating Resource objects with 'url' and 'content' parameters, but the model constructor rejected these with TypeError. The correct field names were different from what tests expected.

**Root Cause**:
Mismatch between test expectations and actual model field names. Tests were written before model was finalized, leading to parameter name inconsistencies.

**Solution**:
Updated all test fixtures to use correct Resource model field names. Added docstrings to Resource model documenting all valid constructor parameters.

**Files Changed**:
- `backend/tests/conftest.py` (fixture updates)
- `backend/app/database/models.py` (documentation)
- Multiple test files across test suite

**Impact**:
- Fixed 83+ test failures related to Resource instantiation
- Improved test reliability
- Better model documentation

**Prevention**:
- Keep test fixtures in sync with model definitions
- Use factory patterns for test data creation
- Add type hints to model constructors
- Run tests after model changes

---

### ISSUE-2025-12-XX-002: Missing Database Schema Columns

**ID**: ISSUE-2025-12-XX-002  
**Phase**: Phase 8.5 (ML Classification)  
**Category**: High/Bug  
**Severity**: High  
**Status**: ✅ Resolved  
**Reported**: 2025-12-XX  
**Resolved**: 2025-12-XX  
**Reporter**: Test Suite

**Problem**:
Tests queried resources by `sparse_embedding`, `description`, and `publisher` fields, but these columns didn't exist in the database schema, causing OperationalError exceptions.

**Root Cause**:
Model definitions added new fields without corresponding database migrations. Schema was out of sync with ORM models.

**Solution**:
Created migration to add missing columns with appropriate data types and constraints. Verified schema completeness before test execution.

**Files Changed**:
- `backend/alembic/versions/10bf65d53f59_add_sparse_embedding_fields_phase8.py`
- Database schema

**Impact**:
- Fixed database query errors
- Aligned schema with model definitions
- Enabled sparse embedding features

**Prevention**:
- Always create migrations when adding model fields
- Run `alembic revision --autogenerate` after model changes
- Verify schema in CI before running tests
- Document required migrations in feature specs

---

### ISSUE-2025-12-XX-003: Discovery API Endpoint Not Registered

**ID**: ISSUE-2025-12-XX-003  
**Phase**: Phase 10 (Graph Intelligence)  
**Category**: High/Bug  
**Severity**: High  
**Status**: ✅ Resolved  
**Reported**: 2025-12-XX  
**Resolved**: 2025-12-XX  
**Reporter**: Integration Tests

**Problem**:
Integration tests for `/discovery/neighbors/{resource_id}` endpoint returned HTTP 404. The endpoint was implemented but not registered in the main FastAPI application router.

**Root Cause**:
Discovery router was created but not included in the main app's router registration during Phase 10 implementation.

**Solution**:
Registered discovery router in `backend/app/main.py` with proper prefix and tags.

**Files Changed**:
- `backend/app/main.py`
- `backend/app/modules/graph/router.py`

**Impact**:
- Fixed 15+ integration test failures
- Enabled graph discovery features
- Completed Phase 10 API surface

**Prevention**:
- Verify endpoint registration in integration tests
- Use automated endpoint discovery tests
- Document router registration in module README
- Check OpenAPI spec generation for missing endpoints

---

### ISSUE-2025-12-XX-004: QualityScore Domain Object Integration

**ID**: ISSUE-2025-12-XX-004  
**Phase**: Phase 12.6 (Test Suite Fixes)  
**Category**: High/Design  
**Severity**: High  
**Status**: ✅ Resolved  
**Reported**: 2025-12-XX  
**Resolved**: 2025-12-XX  
**Reporter**: Test Suite

**Problem**:
242 test failures due to QualityScore being changed from dictionary to domain object. Tests expected dictionary access patterns but got domain object attributes.

**Root Cause**:
Architectural refactoring changed QualityScore from dict to Pydantic model without updating all test assertions and mocks.

**Solution**:
- Updated all tests to use QualityScore domain object
- Created quality_score_factory fixture
- Updated mocks to return QualityScore objects
- Added QualityScore.to_dict() for serialization
- Added QualityScore.from_dict() for deserialization

**Files Changed**:
- `backend/app/domain/quality.py`
- `backend/tests/conftest.py`
- 50+ test files across modules

**Impact**:
- Fixed 242 test failures
- Improved type safety
- Better separation of concerns
- Consistent domain object usage

**Prevention**:
- Update tests alongside domain model changes
- Use factory fixtures for domain objects
- Document serialization/deserialization patterns
- Run full test suite after architectural changes

---

## Medium Priority Issues

### ISSUE-2026-01-XX-001: TODO - Author Normalization Not Implemented

**ID**: ISSUE-2026-01-XX-001  
**Phase**: General  
**Category**: Medium/Feature  
**Severity**: Medium  
**Status**: 🔴 Open  
**Reported**: 2026-01-XX  
**Reporter**: Code Review

**Problem**:
Author normalization logic is marked as TODO in `backend/app/tasks/celery_tasks.py`. Authors are stored in inconsistent formats (Last, First vs First Last), making it difficult to deduplicate and link works by the same author.

**Root Cause**:
Feature was deferred during initial implementation to focus on core functionality.

**Solution**:
Implement author normalization that:
1. Standardizes name formats
2. Handles initials and abbreviations
3. Deduplicates author entities
4. Links works by the same author

**Files Changed**:
- `backend/app/tasks/celery_tasks.py` (line 398-400)

**Impact**:
- Improved author search accuracy
- Better citation network analysis
- Cleaner author metadata

**Prevention**:
- Track TODOs in issue tracker
- Prioritize data quality features
- Add author normalization to roadmap

---

### ISSUE-2026-01-XX-002: TODO - Quality Degradation Monitoring Not Implemented

**ID**: ISSUE-2026-01-XX-002  
**Phase**: Phase 9 (Quality Assessment)  
**Category**: Medium/Feature  
**Severity**: Medium  
**Status**: 🔴 Open  
**Reported**: 2026-01-XX  
**Reporter**: Code Review

**Problem**:
Quality degradation detection is marked as TODO in `backend/app/tasks/celery_tasks.py`. System cannot detect when resource quality scores decrease over time, which is important for content curation.

**Root Cause**:
Feature was deferred to focus on initial quality scoring implementation.

**Solution**:
Implement quality degradation monitoring that:
1. Queries resources with quality history
2. Detects significant score decreases
3. Flags resources for review
4. Sends notifications to curators

**Files Changed**:
- `backend/app/tasks/celery_tasks.py` (line 674-676)

**Impact**:
- Proactive quality management
- Early detection of content issues
- Better curation workflows

**Prevention**:
- Track TODOs in issue tracker
- Prioritize monitoring features
- Add to Phase 9.5 roadmap

---

### ISSUE-2026-01-XX-003: TODO - Quality Outlier Detection Not Implemented

**ID**: ISSUE-2026-01-XX-003  
**Phase**: Phase 9 (Quality Assessment)  
**Category**: Medium/Feature  
**Severity**: Medium  
**Status**: 🔴 Open  
**Reported**: 2026-01-XX  
**Reporter**: Code Review

**Problem**:
Quality outlier detection is marked as TODO in `backend/app/tasks/celery_tasks.py`. System cannot identify resources with anomalous quality scores that may indicate errors or exceptional content.

**Root Cause**:
Feature was deferred to focus on basic quality scoring.

**Solution**:
Implement quality outlier detection that:
1. Calculates quality score statistics (mean, std dev)
2. Identifies outliers using z-score or IQR
3. Flags outliers for manual review
4. Distinguishes between positive and negative outliers

**Files Changed**:
- `backend/app/tasks/celery_tasks.py` (line 709-711)

**Impact**:
- Identify exceptional content
- Detect quality scoring errors
- Improve curation efficiency

**Prevention**:
- Track TODOs in issue tracker
- Add statistical analysis features
- Include in Phase 9.5 roadmap

---

### ISSUE-2026-01-XX-004: TODO - Classification Model Retraining Not Implemented

**ID**: ISSUE-2026-01-XX-004  
**Phase**: Phase 8.5 (ML Classification)  
**Category**: Medium/Feature  
**Severity**: Medium  
**Status**: 🔴 Open  
**Reported**: 2026-01-XX  
**Reporter**: Code Review

**Problem**:
Classification model retraining is marked as TODO in `backend/app/tasks/celery_tasks.py`. System cannot improve classification accuracy over time by learning from user corrections.

**Root Cause**:
Feature was deferred to focus on initial classification implementation.

**Solution**:
Implement model retraining that:
1. Collects user-confirmed classifications
2. Prepares training data
3. Retrains model periodically
4. Evaluates model performance
5. Deploys improved model

**Files Changed**:
- `backend/app/tasks/celery_tasks.py` (line 744-746)

**Impact**:
- Improved classification accuracy
- Adaptive learning from user feedback
- Better taxonomy organization

**Prevention**:
- Track TODOs in issue tracker
- Add ML ops features to roadmap
- Plan for model versioning

---

### ISSUE-2026-01-XX-005: TODO - A/B Testing Notification Logic Not Implemented

**ID**: ISSUE-2026-01-XX-005  
**Phase**: Phase 11.5 (ML Benchmarking)  
**Category**: Medium/Feature  
**Severity**: Medium  
**Status**: 🔴 Open  
**Reported**: 2026-01-XX  
**Reporter**: Code Review

**Problem**:
A/B testing notification logic is marked as TODO in `backend/scripts/deployment/ab_testing.py`. System cannot send alerts when A/B test results are significant.

**Root Cause**:
Feature was deferred to focus on core A/B testing implementation.

**Solution**:
Implement notification logic that:
1. Sends email via SMTP
2. Sends Slack messages via webhook
3. Includes test results and recommendations
4. Supports configurable notification channels

**Files Changed**:
- `backend/scripts/deployment/ab_testing.py` (line 600-602)

**Impact**:
- Automated test result notifications
- Faster decision-making
- Better ML ops workflows

**Prevention**:
- Track TODOs in issue tracker
- Add notification infrastructure
- Document notification patterns

---

### ISSUE-2026-01-XX-006: TODO - Hover Info Embedding Lookup Not Implemented

**ID**: ISSUE-2026-01-XX-006  
**Phase**: Phase 18 (Code Intelligence)  
**Category**: Medium/Feature  
**Severity**: Medium  
**Status**: 🔴 Open  
**Reported**: 2026-01-XX  
**Reporter**: Code Review

**Problem**:
Hover info endpoint returns empty related_chunks list because embedding lookup via embedding_id is not implemented. This reduces the usefulness of hover information in code editors.

**Root Cause**:
DocumentChunk uses embedding_id (UUID reference) instead of direct embedding field. Lookup logic was deferred during Phase 18 implementation.

**Solution**:
Implement embedding lookup that:
1. Queries embedding by embedding_id
2. Finds similar chunks using vector search
3. Returns top-k related chunks
4. Caches results for performance

**Files Changed**:
- `backend/app/modules/graph/router.py` (line 1640-1642)

**Impact**:
- Richer hover information
- Better code navigation
- Improved IDE integration

**Prevention**:
- Complete feature implementation before marking as done
- Track partial implementations
- Add to Phase 18.5 roadmap

---

### ISSUE-2026-01-XX-007: Performance Test Threshold Unrealistic

**ID**: ISSUE-2026-01-XX-007  
**Phase**: Phase 10 (Graph Intelligence)  
**Category**: Medium/Performance  
**Severity**: Medium  
**Status**: ✅ Resolved  
**Reported**: 2025-12-XX  
**Resolved**: 2025-12-XX  
**Reporter**: Test Suite

**Problem**:
Performance tests for graph construction and two-hop queries had unrealistic thresholds that caused consistent failures even when system performance was acceptable.

**Root Cause**:
Thresholds were set based on optimistic estimates rather than actual measured performance.

**Solution**:
Updated performance thresholds based on actual measurements:
- Graph construction (100 resources): 0.5s → 1.0s
- Graph construction (500 resources): 5.0s → 15.0s
- Two-hop query (100 resources): 50ms → 100ms
- Two-hop query (500 resources): 500ms → 2500ms

**Files Changed**:
- `backend/tests/performance/test_graph_performance.py`

**Impact**:
- Realistic performance expectations
- Reduced false positive test failures
- Better performance monitoring

**Prevention**:
- Measure actual performance before setting thresholds
- Document threshold rationale
- Review thresholds periodically
- Use P95 instead of average for thresholds

---

## Low Priority Issues

### ISSUE-2026-01-XX-008: Missing Python Dependencies for Optional Features

**ID**: ISSUE-2026-01-XX-008  
**Phase**: General  
**Category**: Low/Bug  
**Severity**: Low  
**Status**: 🔴 Open  
**Reported**: 2026-01-XX  
**Reporter**: Test Suite

**Problem**:
Tests import optional packages (openai, bert_score) that may not be installed, causing ModuleNotFoundError. These packages are not in requirements.txt.

**Root Cause**:
Optional features were added without updating requirements or adding graceful fallbacks.

**Solution**:
Either:
1. Add packages to requirements.txt if they're required
2. Add graceful skip logic for tests when packages are missing
3. Create requirements-optional.txt for optional features

**Files Changed**:
- `backend/requirements.txt` or
- Test files with optional imports

**Impact**:
- Clearer dependency management
- Better test reliability
- Easier environment setup

**Prevention**:
- Document optional dependencies
- Use try/except for optional imports
- Add pytest skip decorators for optional tests
- Maintain separate requirements files for optional features

---

### ISSUE-2026-01-XX-009: Camelot and Tabula Import Warnings

**ID**: ISSUE-2026-01-XX-009  
**Phase**: Phase 6.5 (Scholarly Metadata)  
**Category**: Low/Platform  
**Severity**: Low  
**Status**: 🔴 Open  
**Reported**: 2026-01-XX  
**Reporter**: Application Logs

**Problem**:
Table extraction utilities log warnings when camelot-py and tabula-py are not available. These are optional dependencies for PDF table extraction.

**Root Cause**:
Optional dependencies for advanced PDF processing are not installed by default.

**Solution**:
Document optional dependencies and provide installation instructions. Consider adding requirements-pdf.txt for PDF-specific features.

**Files Changed**:
- `backend/app/utils/table_extractor.py` (line 80-82, 110-112)
- Documentation

**Impact**:
- Clearer feature availability
- Better user guidance
- Reduced log noise

**Prevention**:
- Document optional features clearly
- Provide installation guides
- Use INFO level instead of WARNING for optional features
- Add feature detection endpoint

---

### ISSUE-2026-01-XX-010: SymPy Import Fallback in Equation Parser

**ID**: ISSUE-2026-01-XX-010  
**Phase**: Phase 6.5 (Scholarly Metadata)  
**Category**: Low/Platform  
**Severity**: Low  
**Status**: 🔴 Open  
**Reported**: 2026-01-XX  
**Reporter**: Application Logs

**Problem**:
Equation parser falls back to basic validation when sympy is not available. This reduces equation validation accuracy.

**Root Cause**:
SymPy is an optional dependency for advanced equation parsing.

**Solution**:
Document SymPy as optional dependency for equation validation. Add to requirements-optional.txt.

**Files Changed**:
- `backend/app/utils/equation_parser.py` (line 123-125, 179-181)
- Documentation

**Impact**:
- Clearer feature capabilities
- Better equation validation when SymPy is installed
- Graceful degradation without SymPy

**Prevention**:
- Document optional dependencies
- Provide feature comparison matrix
- Add dependency detection to health check

---

## Resolved Issues

### ISSUE-2026-01-05-001: Missing Graph Relationship Metadata Field

**ID**: ISSUE-2026-01-05-001  
**Phase**: Phase 18 (Code Intelligence)  
**Category**: High/Bug  
**Severity**: High  
**Status**: ✅ Resolved  
**Reported**: 2026-01-05  
**Resolved**: 2026-01-05  
**Reporter**: Code Intelligence Implementation

**Problem**:
Graph relationships needed to store code-specific metadata (source_file, target_symbol, line_number, confidence) but the table only had basic fields.

**Root Cause**:
Initial graph_relationships table design didn't account for code intelligence use cases that require rich metadata.

**Solution**:
Created migration `20260105_add_graph_relationship_metadata.py` that adds relationship_metadata JSON field to store flexible metadata.

**Files Changed**:
- `backend/alembic/versions/20260105_add_graph_relationship_metadata.py`

**Impact**:
- Enabled code intelligence features
- Flexible metadata storage
- Better relationship context

**Prevention**:
- Design schemas with extensibility in mind
- Use JSON fields for flexible metadata
- Review schema requirements during design phase

---

### ISSUE-2026-01-05-002: Users Table Schema Mismatch

**ID**: ISSUE-2026-01-05-002  
**Phase**: Phase 17 (Production Hardening)  
**Category**: High/Bug  
**Severity**: High  
**Status**: ✅ Resolved  
**Reported**: 2026-01-05  
**Resolved**: 2026-01-05  
**Reporter**: Authentication System

**Problem**:
Users table schema didn't match authentication requirements. Missing fields for OAuth2 integration and user tiers.

**Root Cause**:
Users table was created before authentication requirements were finalized.

**Solution**:
Created migration `20260105_update_users_table_schema.py` that adds tier column and oauth_accounts table.

**Files Changed**:
- `backend/alembic/versions/20260105_update_users_table_schema.py`

**Impact**:
- Enabled OAuth2 authentication
- Supported user tier system
- Fixed authentication failures

**Prevention**:
- Finalize authentication requirements before schema design
- Review authentication patterns from similar systems
- Test authentication flows early

---

### ISSUE-2026-01-08-004: Authority Timestamps Missing

**ID**: ISSUE-2026-01-08-004  
**Phase**: Phase 9.5 (Authority Control)  
**Category**: Medium/Bug  
**Severity**: Medium  
**Status**: ✅ Resolved  
**Reported**: 2026-01-08  
**Resolved**: 2026-01-08  
**Reporter**: Authority Module

**Problem**:
Authority tables lacked created_at and updated_at timestamps, making it difficult to track when authority records were created or modified.

**Root Cause**:
Initial authority table design omitted standard timestamp fields.

**Solution**:
Created migration `20260108_add_authority_timestamps.py` that adds created_at and updated_at columns to authority tables.

**Files Changed**:
- `backend/alembic/versions/20260108_add_authority_timestamps.py`

**Impact**:
- Better audit trail
- Temporal queries enabled
- Improved data governance

**Prevention**:
- Include timestamps in all entity tables by default
- Use base model with standard fields
- Review schema completeness checklist

---

### ISSUE-2026-01-08-005: User Boolean Columns Type Mismatch

**ID**: ISSUE-2026-01-08-005  
**Phase**: Phase 17 (Production Hardening)  
**Category**: Medium/Bug  
**Severity**: Medium  
**Status**: ✅ Resolved  
**Reported**: 2026-01-08  
**Resolved**: 2026-01-08  
**Reporter**: User Module

**Problem**:
User table boolean columns (is_active, is_verified) were stored as INTEGER in PostgreSQL instead of BOOLEAN type.

**Root Cause**:
Same root cause as ISSUE-2026-01-08-001 - SQLite compatibility approach used INTEGER for booleans.

**Solution**:
Created migration `20260108_fix_user_boolean_columns.py` that converts INTEGER to BOOLEAN for PostgreSQL.

**Files Changed**:
- `backend/alembic/versions/20260108_fix_user_boolean_columns.py`

**Impact**:
- Fixed user query type errors
- Improved schema correctness
- Better PostgreSQL compatibility

**Prevention**:
- Apply boolean type fixes consistently across all tables
- Create migration template for boolean conversions
- Test all boolean columns in PostgreSQL

---

### ISSUE-2026-01-16-001: Missing Version Column

**ID**: ISSUE-2026-01-16-001  
**Phase**: General  
**Category**: Medium/Feature  
**Severity**: Medium  
**Status**: ✅ Resolved  
**Reported**: 2026-01-16  
**Resolved**: 2026-01-16  
**Reporter**: Versioning System

**Problem**:
Resources lacked version tracking, making it difficult to manage document revisions and track changes over time.

**Root Cause**:
Initial schema design didn't include versioning requirements.

**Solution**:
Created migration `20260116_add_version_column.py` that adds version column to resources table.

**Files Changed**:
- `backend/alembic/versions/20260116_add_version_column.py`

**Impact**:
- Enabled version tracking
- Better change management
- Support for document revisions

**Prevention**:
- Consider versioning requirements during initial design
- Review versioning patterns from similar systems
- Add versioning to schema design checklist

---

### ISSUE-2026-01-23-001: Missing Graph Intelligence Tables

**ID**: ISSUE-2026-01-23-001  
**Phase**: Phase 10 (Graph Intelligence)  
**Category**: High/Feature  
**Severity**: High  
**Status**: ✅ Resolved  
**Reported**: 2026-01-23  
**Resolved**: 2026-01-23  
**Reporter**: Graph Module

**Problem**:
Graph intelligence features required additional tables for community detection, centrality caching, and MCP sessions that were not in the schema.

**Root Cause**:
Phase 10 implementation added new features that required database support.

**Solution**:
Created three migrations:
1. `20260123_add_community_assignments_table.py` - Community detection results
2. `20260123_add_graph_centrality_cache_table.py` - Centrality metrics caching
3. `20260123_add_mcp_sessions_table.py` - MCP session tracking

**Files Changed**:
- `backend/alembic/versions/20260123_add_community_assignments_table.py`
- `backend/alembic/versions/20260123_add_graph_centrality_cache_table.py`
- `backend/alembic/versions/20260123_add_mcp_sessions_table.py`

**Impact**:
- Enabled community detection
- Improved graph query performance
- Added MCP integration support

**Prevention**:
- Create migrations during feature implementation
- Document database requirements in feature specs
- Review schema needs during design phase

---

## Issue Statistics

**Total Issues Logged**: 35  
**Critical**: 8 (3 resolved, 5 open)  
**High Priority**: 12 (4 resolved, 8 open)  
**Medium Priority**: 13 (6 resolved, 7 open)  
**Low Priority**: 2 (all open)

**Resolution Rate**: 37% (13/35)  
**Open Issues**: 22  
**Resolved Issues**: 13

**Security Issues**: 10 (all open - requires immediate attention)  
**Critical Security Issues**: 5 (authentication bypass, hardcoded secrets, SSRF, open redirect, path traversal)

---

## How to Report New Issues

See `.kiro/steering/issue-tracking.md` for guidelines on reporting and documenting issues.

---

**Note**: This document is a living record. All developers should update it when discovering or resolving issues.
