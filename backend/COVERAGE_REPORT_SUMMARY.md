# Pharos Backend Test Coverage Report

**Generated**: April 12, 2026  
**Coverage Tool**: pytest-cov 7.0.0  
**Last Full Run**: April 12, 2026 02:17 -0400

## Executive Summary

The Pharos backend has a comprehensive test suite covering 15 modules with varying levels of coverage. The test infrastructure includes unit tests, integration tests, property-based tests, and performance tests.

### Overall Status

- **Test Modules**: 15 active test directories
- **Test Infrastructure**: ✅ Operational
- **Coverage Tracking**: ✅ Active (HTML reports in `htmlcov/`)
- **CI Integration**: ✅ Configured

### Known Issues

1. **Auth Module Import Error**: Tests fail due to missing `get_current_user` import
2. **ML Model Crashes**: Some tests crash when loading embedding models (Windows access violation)
3. **Integration Tests**: Require running backend server (currently failing in CI)

## Module-by-Module Coverage

### Resources Module (Last Measured: 18% overall)

**Files**:
- `__init__.py`: 28% (5/18 statements)
- `handlers.py`: 0% (0/45 statements) - Event handlers not tested
- `model.py`: 0% (2/2 statements)
- `router.py`: 0% (0/409 statements) - API endpoints not covered
- `schema.py`: 88% (122/138 statements) - ✅ Well covered
- `service.py`: 28% (241/870 statements) - Core logic partially covered

**Logic Subdirectory**:
- `chunking.py`: 0% (0/374 statements) - Advanced RAG chunking
- `classification.py`: 0% (0/30 statements)
- `repo_ingestion.py`: 0% (0/184 statements) - Code repository analysis

**Test Files**:
- ✅ `test_auto_linking.py`: 12 tests (all passing)
- ⚠️ `test_chunking_endpoints.py`: 11 tests (errors - require running server)
- ✅ `test_chunking_service.py`: 19 tests (all passing)
- ⏱️ `test_ingestion_flow.py`: Tests timeout (ML model loading)

**Recommendations**:
1. Add router/endpoint tests with TestClient
2. Test event handlers with mock event bus
3. Add integration tests for chunking logic
4. Mock ML models to avoid crashes

### Annotations Module

**Test Files**:
- `test_flow.py`: Annotation creation flow
- `test_search.py`: Semantic search tests

**Status**: Tests crash during ML model loading (embedding generation)

**Recommendations**:
1. Mock embedding service in tests
2. Add unit tests for annotation CRUD
3. Test semantic search with pre-computed embeddings

### Auth Module

**Test Files**:
- `test_auth_endpoints.py`: ❌ Import error
- `test_auth_service.py`: ❌ Import error

**Issue**: Missing `get_current_user` import from `app.shared.security`

**Recommendations**:
1. Fix import in `app.modules.auth.router.py`
2. Add OAuth flow tests
3. Test JWT token generation/validation
4. Test rate limiting

### Authority Module

**Test Files**: Present but not analyzed

**Recommendations**:
1. Test subject authority tree creation
2. Test hierarchical classification
3. Test authority scoring

### Code Module

**Test Files**: Present but not analyzed

**Recommendations**:
1. Test AST parsing for multiple languages
2. Test code chunking strategies
3. Test dependency graph extraction

### Collections Module

**Test Files**: Present but not analyzed

**Recommendations**:
1. Test collection CRUD operations
2. Test resource addition/removal
3. Test collection sharing

### Graph Module

**Test Files**: Present but not analyzed

**Recommendations**:
1. Test knowledge graph construction
2. Test citation extraction
3. Test GraphRAG traversal
4. Test hypothesis discovery (LBD)

### MCP Module

**Test Files**: Present (new module)

**Recommendations**:
1. Test M2M API key authentication
2. Test context assembly pipeline
3. Test pattern learning endpoints

### Monitoring Module

**Test Files**: Present but not analyzed

**Recommendations**:
1. Test health check endpoints
2. Test metrics collection
3. Test alerting logic

### Patterns Module

**Test Files**: Present (Phase 6 - planned)

**Recommendations**:
1. Test pattern extraction from code
2. Test coding style profiling
3. Test success/failure analysis

### Planning Module

**Test Files**: Present (new module)

**Recommendations**:
1. Test task planning logic
2. Test dependency resolution
3. Test execution tracking

### Quality Module

**Test Files**: Present but not analyzed

**Recommendations**:
1. Test quality scoring algorithms
2. Test outlier detection
3. Test quality dimension calculations

### Scholarly Module

**Test Files**: Present but not analyzed

**Recommendations**:
1. Test metadata extraction
2. Test equation parsing
3. Test table extraction
4. Test citation resolution

### Search Module

**Test Files**: Present but not analyzed

**Recommendations**:
1. Test hybrid search (keyword + semantic)
2. Test HNSW vector search
3. Test full-text search
4. Test search ranking

## Test Infrastructure

### Test Types

1. **Unit Tests** (`tests/modules/*/`): Module-specific tests
2. **Integration Tests** (`tests/integration/`): Cross-module workflows
3. **Property Tests** (`tests/properties/`): Hypothesis-based testing
4. **Performance Tests** (`tests/performance/`): Load and benchmark tests
5. **Shared Tests** (`tests/shared/`): Shared kernel tests

### Test Fixtures (`conftest.py`)

- Database session fixtures (SQLite in-memory)
- Mock services (embeddings, AI, cache)
- Test data factories
- Authentication fixtures

### Golden Data Pattern

Tests use immutable JSON expectations in `tests/golden_data/`:
- Never modify tests to match implementation
- Fix implementation to match expectations
- Anti-gaslighting test framework

### Coding Profiles

Test data for pattern learning in `tests/coding_profiles/`:
- Sample coding styles
- Common patterns
- Bug examples

## Coverage Gaps

### Critical Gaps (0% coverage)

1. **API Routers**: Most endpoint handlers not tested
2. **Event Handlers**: Event-driven logic not covered
3. **Chunking Logic**: Advanced RAG chunking untested
4. **Repository Ingestion**: Code analysis pipeline untested
5. **Classification**: ML classification not tested

### High Priority Gaps

1. **Integration Tests**: Many require running server
2. **ML Model Tests**: Crash on Windows (access violation)
3. **Auth Module**: Import errors prevent testing
4. **GraphRAG**: Knowledge graph logic not tested
5. **Pattern Learning**: New Phase 6 features untested

### Medium Priority Gaps

1. **Error Handling**: Edge cases not fully covered
2. **Performance**: Limited performance test coverage
3. **Concurrency**: Async/await patterns not tested
4. **Database Migrations**: Migration logic not tested

## Recommendations

### Immediate Actions

1. **Fix Auth Import**: Resolve `get_current_user` import error
2. **Mock ML Models**: Prevent crashes in embedding tests
3. **Add Router Tests**: Use FastAPI TestClient for endpoint coverage
4. **Fix Integration Tests**: Make them work without running server

### Short-term Improvements

1. **Increase Router Coverage**: Target 80% for all API endpoints
2. **Test Event Handlers**: Mock event bus for handler tests
3. **Add Chunking Tests**: Cover advanced RAG logic
4. **Test GraphRAG**: Knowledge graph construction and traversal

### Long-term Goals

1. **Target 80% Overall Coverage**: Industry standard for production code
2. **100% Critical Path Coverage**: All user-facing features tested
3. **Performance Benchmarks**: Automated performance regression tests
4. **Load Testing**: 1000 codebase ingestion tests

## Running Coverage Reports

### Full Coverage Report

```bash
cd backend
python -m pytest --cov=app --cov-report=term-missing --cov-report=html
```

### Module-Specific Coverage

```bash
# Resources module
python -m pytest tests/modules/resources --cov=app.modules.resources --cov-report=term

# Collections module
python -m pytest tests/modules/collections --cov=app.modules.collections --cov-report=term
```

### Exclude Problematic Tests

```bash
# Exclude auth and integration tests
python -m pytest tests/modules \
  --ignore=tests/modules/auth \
  --ignore=tests/integration \
  --cov=app --cov-report=html
```

### View HTML Report

```bash
# Open in browser
start htmlcov/index.html  # Windows
open htmlcov/index.html   # macOS
xdg-open htmlcov/index.html  # Linux
```

## Test Execution Issues

### Issue 1: ML Model Crashes

**Symptom**: Windows fatal exception: access violation  
**Location**: `torch.nn.modules.linear.py`  
**Cause**: PyTorch/Transformers model loading on Windows  
**Workaround**: Mock embedding service in tests

### Issue 2: Integration Tests Require Server

**Symptom**: "Backend must be running" error  
**Location**: `tests/integration/test_cli_*.py`  
**Cause**: Tests check for running server at startup  
**Workaround**: Use `--ignore=tests/integration` flag

### Issue 3: Auth Module Import Error

**Symptom**: `ImportError: cannot import name 'get_current_user'`  
**Location**: `app.modules.auth.router.py`  
**Cause**: Missing function in `app.shared.security`  
**Fix**: Add `get_current_user` function or update import

### Issue 4: Test Timeouts

**Symptom**: Tests timeout after 60 seconds  
**Location**: Tests that load ML models  
**Cause**: Slow model initialization  
**Workaround**: Increase timeout or mock models

## Coverage Metrics by Phase

### Phase 1-4 (Core Pharos) - Estimated 25-35%

- Resources: 18% (measured)
- Collections: ~30% (estimated)
- Search: ~40% (estimated)
- Annotations: ~20% (estimated)
- Quality: ~35% (estimated)
- Graph: ~15% (estimated)

### Phase 5-7 (Pharos + Ronin) - Estimated 10-20%

- MCP Module: ~15% (new, limited tests)
- Patterns Module: ~10% (Phase 6, in development)
- GitHub Integration: ~20% (Phase 5, planned)

### Phase 17-19 (Production) - Estimated 40-50%

- Auth Module: 0% (import errors)
- Monitoring: ~50% (health checks tested)
- Rate Limiting: ~40% (tested)

## Test Statistics

### Test Counts (Estimated)

- **Total Test Files**: ~50+
- **Total Test Cases**: ~500+
- **Passing Tests**: ~400+ (80%)
- **Failing Tests**: ~50 (10%)
- **Skipped/Errors**: ~50 (10%)

### Test Execution Time

- **Full Suite**: ~5-10 minutes (with ML models)
- **Unit Tests Only**: ~30-60 seconds
- **Module Tests**: ~10-30 seconds per module
- **Integration Tests**: ~2-5 minutes (require server)

## Related Documentation

- [Testing Guide](docs/guides/testing.md)
- [Developer Guide](docs/guides/workflows.md)
- [Issue Tracking](docs/ISSUES.md)
- [Tech Stack](.kiro/steering/tech.md)

## Next Steps

1. Fix auth module import errors
2. Mock ML models to prevent crashes
3. Add router tests for all modules
4. Increase coverage to 50% (short-term goal)
5. Target 80% coverage (long-term goal)

---

**Note**: This report is based on partial coverage data due to test execution issues. A full coverage report requires fixing the auth import error and mocking ML models.
