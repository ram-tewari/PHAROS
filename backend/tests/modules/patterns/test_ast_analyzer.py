"""
Tests for AST Analyzer - Architecture and Style Detection

Tests the AST parsing logic that extracts architectural patterns,
style conventions, and structural fingerprints from Python code.
"""

import tempfile
from pathlib import Path

import pytest

from app.modules.patterns.logic.ast_analyzer import ASTAnalyzer
from app.modules.patterns.schema import (
    ArchitectureProfile,
    StyleProfile,
)


# ============================================================================
# Test Fixtures - Sample Python Code
# ============================================================================


@pytest.fixture
def sample_fastapi_code():
    """Sample FastAPI code with DI, async, and error handling."""
    return '''
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

def get_db():
    """Database dependency."""
    pass

@router.get("/items/{item_id}")
async def get_item(
    item_id: int,
    db: Session = Depends(get_db)
) -> dict:
    """
    Get an item by ID.
    
    Args:
        item_id: The item identifier
        db: Database session
        
    Returns:
        Item data
    """
    try:
        result = await fetch_item(item_id, db)
        return {"item": result}
    except ValueError as exc:
        logger.error("Invalid item ID: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception("Unexpected error fetching item")
        raise

async def fetch_item(item_id: int, db: Session):
    """Fetch item from database."""
    return {"id": item_id, "name": "Test"}

class ItemService:
    """Service for item operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    async def create_item(self, data: dict) -> dict:
        """Create a new item."""
        return data
'''


@pytest.fixture
def sample_orm_code():
    """Sample SQLAlchemy ORM code."""
    return '''
from sqlalchemy import Column, Integer, String, Boolean
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    def __repr__(self):
        return f"<User(email={self.email!r})>"

class CustomUserException(Exception):
    """Custom exception for user operations."""
    pass
'''


@pytest.fixture
def sample_error_handling_code():
    """Sample code with various error handling patterns."""
    return '''
import logging

logger = logging.getLogger(__name__)

def pattern_a(data):
    """Error handler pattern A: log and reraise."""
    try:
        process(data)
    except ValueError as exc:
        logger.error("Processing failed: %s", exc)
        raise

def pattern_b(data):
    """Error handler pattern B: log and return None."""
    try:
        process(data)
    except ValueError as exc:
        logger.exception("Processing failed")
        return None

def pattern_c(data):
    """Error handler pattern C: silent catch."""
    try:
        process(data)
    except:
        pass

def process(data):
    """Process data."""
    return data
'''


@pytest.fixture
def temp_repo(tmp_path):
    """Create a temporary repository with sample Python files."""
    repo_path = tmp_path / "test_repo"
    repo_path.mkdir()
    
    # Create a simple module structure
    (repo_path / "module1.py").write_text('''
def hello():
    """Say hello."""
    return "Hello"

async def async_hello():
    """Async hello."""
    return "Async Hello"
''')
    
    (repo_path / "module2.py").write_text('''
class MyClass:
    """A sample class."""
    
    def method_one(self):
        """Method one."""
        pass
    
    def _private_method(self):
        """Private method."""
        pass
''')
    
    return repo_path


# ============================================================================
# AST Analyzer Tests
# ============================================================================


class TestASTAnalyzer:
    """Test suite for ASTAnalyzer."""
    
    def test_analyzer_initialization(self, temp_repo):
        """Test analyzer can be initialized with a repository path."""
        analyzer = ASTAnalyzer(temp_repo)
        assert analyzer.repo_path == temp_repo
        assert analyzer._file_count == 0
        assert analyzer._total_lines == 0
    
    def test_analyze_empty_repo(self, tmp_path):
        """Test analyzing an empty repository."""
        empty_repo = tmp_path / "empty"
        empty_repo.mkdir()
        
        analyzer = ASTAnalyzer(empty_repo)
        arch, style, fingerprints, file_count, total_lines = analyzer.analyze()
        
        assert file_count == 0
        assert total_lines == 0
        assert isinstance(arch, ArchitectureProfile)
        assert isinstance(style, StyleProfile)
        assert fingerprints == []
    
    def test_analyze_basic_repo(self, temp_repo):
        """Test analyzing a basic repository."""
        analyzer = ASTAnalyzer(temp_repo)
        arch, style, fingerprints, file_count, total_lines = analyzer.analyze()
        
        assert file_count == 2
        assert total_lines > 0
        assert isinstance(arch, ArchitectureProfile)
        assert isinstance(style, StyleProfile)
    
    def test_detect_async_patterns(self, tmp_path, sample_fastapi_code):
        """Test detection of async/await patterns."""
        repo = tmp_path / "async_repo"
        repo.mkdir()
        (repo / "async_code.py").write_text(sample_fastapi_code)
        
        analyzer = ASTAnalyzer(repo)
        arch, style, fingerprints, file_count, total_lines = analyzer.analyze()
        
        # Should detect async functions
        assert style.async_patterns.async_function_count > 0
        assert style.async_patterns.async_density > 0
    
    def test_detect_fastapi_framework(self, tmp_path, sample_fastapi_code):
        """Test detection of FastAPI framework."""
        repo = tmp_path / "fastapi_repo"
        repo.mkdir()
        (repo / "api.py").write_text(sample_fastapi_code)
        
        analyzer = ASTAnalyzer(repo)
        arch, style, fingerprints, file_count, total_lines = analyzer.analyze()
        
        # Should detect FastAPI
        assert arch.framework.framework == "fastapi"
        assert arch.framework.uses_routers is True
    
    def test_detect_dependency_injection(self, tmp_path, sample_fastapi_code):
        """Test detection of dependency injection patterns."""
        repo = tmp_path / "di_repo"
        repo.mkdir()
        (repo / "di_code.py").write_text(sample_fastapi_code)
        
        analyzer = ASTAnalyzer(repo)
        arch, style, fingerprints, file_count, total_lines = analyzer.analyze()
        
        # Should detect DI usage
        assert arch.dependency_injection.uses_di is True
        assert arch.dependency_injection.di_style == "fastapi_depends"
        assert arch.dependency_injection.di_density > 0
    
    def test_detect_orm_patterns(self, tmp_path, sample_orm_code):
        """Test detection of ORM patterns."""
        repo = tmp_path / "orm_repo"
        repo.mkdir()
        (repo / "models.py").write_text(sample_orm_code)
        
        analyzer = ASTAnalyzer(repo)
        arch, style, fingerprints, file_count, total_lines = analyzer.analyze()
        
        # Should detect SQLAlchemy
        assert arch.orm.orm_detected == "sqlalchemy"
        assert arch.orm.model_style == "declarative"
    
    def test_detect_error_handling_patterns(self, tmp_path, sample_error_handling_code):
        """Test detection of error handling patterns."""
        repo = tmp_path / "error_repo"
        repo.mkdir()
        (repo / "errors.py").write_text(sample_error_handling_code)
        
        analyzer = ASTAnalyzer(repo)
        arch, style, fingerprints, file_count, total_lines = analyzer.analyze()
        
        # Should detect try/except blocks
        assert style.error_handling.total_try_blocks > 0
        assert style.error_handling.typed_except_count > 0
        assert style.error_handling.bare_except_count > 0
        assert "ValueError" in style.error_handling.common_caught_exceptions
    
    def test_detect_logging_style(self, tmp_path, sample_error_handling_code):
        """Test detection of logging style in error handlers."""
        repo = tmp_path / "logging_repo"
        repo.mkdir()
        (repo / "logging_code.py").write_text(sample_error_handling_code)
        
        analyzer = ASTAnalyzer(repo)
        arch, style, fingerprints, file_count, total_lines = analyzer.analyze()
        
        # Should detect logger.error or logger.exception
        assert style.error_handling.exception_logging_style in [
            "logger.error",
            "logger.exception",
        ]
    
    def test_detect_type_hints(self, tmp_path, sample_fastapi_code):
        """Test detection of type hint usage."""
        repo = tmp_path / "typed_repo"
        repo.mkdir()
        (repo / "typed.py").write_text(sample_fastapi_code)
        
        analyzer = ASTAnalyzer(repo)
        arch, style, fingerprints, file_count, total_lines = analyzer.analyze()
        
        # Should detect type hints
        assert style.naming.uses_type_hints is True
        assert style.naming.type_hint_density > 0
    
    def test_detect_naming_conventions(self, tmp_path):
        """Test detection of naming conventions."""
        code = '''
def snake_case_function():
    pass

class PascalCaseClass:
    pass

CONSTANT_VALUE = 42
variable_name = "test"
'''
        repo = tmp_path / "naming_repo"
        repo.mkdir()
        (repo / "naming.py").write_text(code)
        
        analyzer = ASTAnalyzer(repo)
        arch, style, fingerprints, file_count, total_lines = analyzer.analyze()
        
        # Should detect naming conventions
        assert style.naming.function_casing == "snake_case"
        assert style.naming.class_casing == "PascalCase"
        assert style.naming.constant_casing == "UPPER_SNAKE"
    
    def test_detect_custom_exceptions(self, tmp_path, sample_orm_code):
        """Test detection of custom exception classes."""
        repo = tmp_path / "exc_repo"
        repo.mkdir()
        (repo / "exceptions.py").write_text(sample_orm_code)
        
        analyzer = ASTAnalyzer(repo)
        arch, style, fingerprints, file_count, total_lines = analyzer.analyze()
        
        # Should detect custom exceptions
        assert style.error_handling.uses_custom_exceptions is True
        assert style.error_handling.custom_exception_count > 0
    
    def test_detect_docstrings(self, tmp_path, sample_fastapi_code):
        """Test detection of docstring usage."""
        repo = tmp_path / "doc_repo"
        repo.mkdir()
        (repo / "documented.py").write_text(sample_fastapi_code)
        
        analyzer = ASTAnalyzer(repo)
        arch, style, fingerprints, file_count, total_lines = analyzer.analyze()
        
        # Should detect docstrings
        assert style.docstrings.docstring_density > 0
        assert style.docstrings.docstring_style in ["google", "plain"]
    
    def test_structural_fingerprints(self, tmp_path, sample_error_handling_code):
        """Test extraction of structural fingerprints."""
        repo = tmp_path / "fingerprint_repo"
        repo.mkdir()
        (repo / "patterns.py").write_text(sample_error_handling_code)
        
        analyzer = ASTAnalyzer(repo)
        arch, style, fingerprints, file_count, total_lines = analyzer.analyze()
        
        # Should extract fingerprints
        assert len(fingerprints) > 0
        assert any(fp.pattern_type == "error_handler" for fp in fingerprints)
    
    def test_exclude_common_directories(self, tmp_path):
        """Test that common non-source directories are excluded."""
        repo = tmp_path / "exclude_repo"
        repo.mkdir()
        
        # Create files in excluded directories
        (repo / ".git").mkdir()
        (repo / ".git" / "config.py").write_text("# Git config")
        
        (repo / "__pycache__").mkdir()
        (repo / "__pycache__" / "cache.py").write_text("# Cache")
        
        (repo / "venv").mkdir()
        (repo / "venv" / "lib.py").write_text("# Venv")
        
        # Create a valid source file
        (repo / "source.py").write_text("def main(): pass")
        
        analyzer = ASTAnalyzer(repo)
        arch, style, fingerprints, file_count, total_lines = analyzer.analyze()
        
        # Should only analyze source.py
        assert file_count == 1
    
    def test_handle_syntax_errors_gracefully(self, tmp_path):
        """Test that syntax errors in files don't crash the analyzer."""
        repo = tmp_path / "syntax_error_repo"
        repo.mkdir()
        
        # Create a file with syntax error
        (repo / "broken.py").write_text("def broken(: pass")
        
        # Create a valid file
        (repo / "valid.py").write_text("def valid(): pass")
        
        analyzer = ASTAnalyzer(repo)
        arch, style, fingerprints, file_count, total_lines = analyzer.analyze()
        
        # Should analyze only the valid file
        assert file_count == 1
    
    def test_detect_repository_pattern(self, tmp_path):
        """Test detection of repository/service layer pattern."""
        repo = tmp_path / "layers_repo"
        repo.mkdir()
        
        (repo / "router.py").write_text("# Router layer")
        (repo / "service.py").write_text("# Service layer")
        (repo / "repository.py").write_text("# Repository layer")
        (repo / "schema.py").write_text("# Schema layer")
        
        analyzer = ASTAnalyzer(repo)
        arch, style, fingerprints, file_count, total_lines = analyzer.analyze()
        
        # Should detect layered architecture
        assert arch.repository_pattern.uses_repository_pattern is True
        assert arch.repository_pattern.uses_service_layer is True
        assert "repository" in arch.repository_pattern.detected_layers
        assert "service" in arch.repository_pattern.detected_layers
    
    def test_detect_factory_pattern(self, tmp_path):
        """Test detection of factory pattern."""
        code = '''
def create_user(data):
    """Factory for creating users."""
    return User(**data)

def create_admin(data):
    """Factory for creating admins."""
    return Admin(**data)

def make_connection():
    """Factory for connections."""
    return Connection()
'''
        repo = tmp_path / "factory_repo"
        repo.mkdir()
        (repo / "factories.py").write_text(code)
        
        analyzer = ASTAnalyzer(repo)
        arch, style, fingerprints, file_count, total_lines = analyzer.analyze()
        
        # Should detect factory pattern
        assert "factory" in arch.detected_patterns


# ============================================================================
# Edge Case Tests
# ============================================================================


class TestASTAnalyzerEdgeCases:
    """Test edge cases and error handling."""
    
    def test_empty_file(self, tmp_path):
        """Test analyzing an empty Python file."""
        repo = tmp_path / "empty_file_repo"
        repo.mkdir()
        (repo / "empty.py").write_text("")
        
        analyzer = ASTAnalyzer(repo)
        arch, style, fingerprints, file_count, total_lines = analyzer.analyze()
        
        assert file_count == 1
        assert total_lines == 0
    
    def test_file_with_only_comments(self, tmp_path):
        """Test analyzing a file with only comments."""
        repo = tmp_path / "comments_repo"
        repo.mkdir()
        (repo / "comments.py").write_text("""
# This is a comment
# Another comment
# More comments
""")
        
        analyzer = ASTAnalyzer(repo)
        arch, style, fingerprints, file_count, total_lines = analyzer.analyze()
        
        assert file_count == 1
        assert style.docstrings.uses_inline_comments is True
    
    def test_unicode_content(self, tmp_path):
        """Test analyzing files with Unicode content."""
        code = '''
def greet():
    """Say hello in multiple languages."""
    return "Hello 你好 مرحبا"
'''
        repo = tmp_path / "unicode_repo"
        repo.mkdir()
        (repo / "unicode.py").write_text(code, encoding="utf-8")
        
        analyzer = ASTAnalyzer(repo)
        arch, style, fingerprints, file_count, total_lines = analyzer.analyze()
        
        assert file_count == 1
    
    def test_very_long_file(self, tmp_path):
        """Test analyzing a very long file."""
        # Generate a file with many functions
        functions = "\n".join([
            f"def function_{i}():\n    pass\n"
            for i in range(1000)
        ])
        
        repo = tmp_path / "long_file_repo"
        repo.mkdir()
        (repo / "long.py").write_text(functions)
        
        analyzer = ASTAnalyzer(repo)
        arch, style, fingerprints, file_count, total_lines = analyzer.analyze()
        
        assert file_count == 1
        assert total_lines > 2000
    
    def test_deeply_nested_code(self, tmp_path):
        """Test analyzing deeply nested code."""
        code = '''
def outer():
    if True:
        if True:
            if True:
                if True:
                    if True:
                        return "deep"
'''
        repo = tmp_path / "nested_repo"
        repo.mkdir()
        (repo / "nested.py").write_text(code)
        
        analyzer = ASTAnalyzer(repo)
        arch, style, fingerprints, file_count, total_lines = analyzer.analyze()
        
        assert style.max_nesting_depth >= 5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
