# Pattern Learning Engine Test Suite

Comprehensive test suite for Phase 3: The Pattern Learning Engine.

## Test Coverage

### Test Files

1. **test_ast_analyzer.py** (23 tests)
   - AST parsing and code analysis
   - Architecture pattern detection (DI, ORM, Repository, Framework)
   - Style extraction (async, error handling, naming, docstrings)
   - Structural fingerprint extraction
   - Edge cases (syntax errors, empty files, Unicode, deep nesting)

2. **test_git_analyzer.py** (26 tests)
   - Commit classification (bugfix, feature, refactor, formatting)
   - Structural fingerprint extraction from source
   - Git history analysis
   - Pattern lifecycle tracking (kept, abandoned, evolving)
   - Edge cases (non-git directories, empty repos, large histories)

3. **test_service.py** (24 tests)
   - Repository resolution (local, remote, invalid)
   - Language detection (Python, JavaScript, TypeScript, etc.)
   - Summary building
   - Complete pattern learning pipeline
   - Integration tests

4. **test_router.py** (18 tests, 14 skipped)
   - API endpoint testing
   - Profile management endpoints
   - End-to-end integration tests
   - Performance tests
   - Note: Most tests skipped due to auth middleware requirements

5. **test_functional.py** (16 tests)
   - Real-world project analysis (FastAPI, Django, Flask)
   - Cross-project comparison
   - Accuracy verification
   - Factual correctness of pattern detection

## Test Results

```
93 passed, 14 skipped
```

### Passing Tests: 93
- AST Analyzer: 23/23 ✅
- Git Analyzer: 26/26 ✅
- Service Layer: 24/24 ✅
- Functional Tests: 16/16 ✅
- Router Tests: 4/18 (14 skipped due to auth requirements)

### Skipped Tests: 14
- Router endpoint tests requiring full app initialization with auth middleware
- These tests verify the API layer but need proper authentication setup

## Running Tests

### Run All Tests
```bash
cd backend
python -m pytest tests/modules/patterns/ -v
```

### Run Specific Test File
```bash
python -m pytest tests/modules/patterns/test_ast_analyzer.py -v
python -m pytest tests/modules/patterns/test_git_analyzer.py -v
python -m pytest tests/modules/patterns/test_service.py -v
python -m pytest tests/modules/patterns/test_functional.py -v
```

### Run Specific Test Class
```bash
python -m pytest tests/modules/patterns/test_ast_analyzer.py::TestASTAnalyzer -v
python -m pytest tests/modules/patterns/test_git_analyzer.py::TestGitAnalyzer -v
```

### Run Specific Test
```bash
python -m pytest tests/modules/patterns/test_ast_analyzer.py::TestASTAnalyzer::test_detect_fastapi_framework -v
```

### Run with Coverage
```bash
python -m pytest tests/modules/patterns/ --cov=app.modules.patterns --cov-report=html
```

## Test Categories

### Unit Tests
- AST parsing logic
- Git commit classification
- Fingerprint extraction
- Repository resolution
- Language detection

### Integration Tests
- Complete pattern learning pipeline
- AST + Git analysis orchestration
- Database persistence
- Summary generation

### Functional Tests
- Real-world project analysis
- Framework detection accuracy
- Pattern detection correctness
- Cross-project comparison

### Performance Tests
- Large repository handling
- Commit limit enforcement
- Timeout behavior

## Key Test Scenarios

### Architecture Detection
- ✅ FastAPI framework with DI
- ✅ Django framework with ORM
- ✅ Flask framework with blueprints
- ✅ SQLAlchemy ORM patterns
- ✅ Repository/Service layer patterns
- ✅ Factory pattern detection

### Style Detection
- ✅ Async/await density
- ✅ Error handling patterns
- ✅ Logging styles
- ✅ Type hint coverage
- ✅ Naming conventions
- ✅ Docstring styles

### Git Analysis
- ✅ Commit classification
- ✅ Pattern lifecycle tracking
- ✅ Kept vs abandoned patterns
- ✅ Pattern replication detection
- ✅ Formatting commit filtering

### Edge Cases
- ✅ Empty repositories
- ✅ Non-git directories
- ✅ Syntax errors in code
- ✅ Unicode content
- ✅ Very long files
- ✅ Deeply nested code

## Test Data

Tests use:
- Temporary directories (`tmp_path` fixture)
- In-memory git repositories
- Synthetic code samples
- Realistic project structures

## Dependencies

- pytest
- pytest-asyncio
- Git (for git analyzer tests)
- FastAPI test client
- SQLAlchemy test fixtures

## Notes

### Git Requirement
Tests that analyze git history require git to be installed and available in PATH. These tests are automatically skipped if git is not available.

### Authentication Tests
Router tests that require authentication are currently skipped. To enable them, the test client needs proper authentication middleware setup.

### Test Isolation
All tests use function-scoped fixtures to ensure complete isolation. Each test gets:
- Fresh temporary directory
- Clean git repository
- Independent database session

### Performance
Full test suite runs in approximately 60 seconds on a typical development machine.

## Continuous Integration

Tests are designed to run in CI/CD pipelines:
- No external dependencies (except git)
- Deterministic results
- Proper cleanup of temporary files
- Clear failure messages

## Future Improvements

1. Enable router tests with proper auth setup
2. Add property-based tests with Hypothesis
3. Add mutation testing
4. Add performance benchmarks
5. Add integration tests with real repositories

## Related Documentation

- [Pattern Learning Engine](../../../app/modules/patterns/README.md)
- [AST Analyzer](../../../app/modules/patterns/logic/ast_analyzer.py)
- [Git Analyzer](../../../app/modules/patterns/logic/git_analyzer.py)
- [Service Layer](../../../app/modules/patterns/service.py)
- [API Router](../../../app/modules/patterns/router.py)
