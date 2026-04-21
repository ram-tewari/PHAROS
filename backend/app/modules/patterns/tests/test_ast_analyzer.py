"""
Unit tests for the AST Analyzer.

Tests structural extraction from Python source code including
architecture detection, style analysis, and fingerprint generation.
"""

import ast
import textwrap


from app.modules.patterns.logic.ast_analyzer import (
    ASTAnalyzer,
    _FileVisitor,
    _classify_casing,
    _safe_parse,
)


# ============================================================================
# Casing classification
# ============================================================================


class TestClassifyCasing:
    def test_snake_case(self):
        assert _classify_casing("my_function") == "snake_case"

    def test_pascal_case(self):
        assert _classify_casing("MyClass") == "PascalCase"

    def test_camel_case(self):
        assert _classify_casing("myFunction") == "camelCase"

    def test_upper_snake(self):
        assert _classify_casing("MAX_RETRIES") == "UPPER_SNAKE"


# ============================================================================
# Safe parsing
# ============================================================================


class TestSafeParse:
    def test_valid_source(self):
        tree = _safe_parse("x = 1")
        assert isinstance(tree, ast.Module)

    def test_invalid_source(self):
        tree = _safe_parse("def (invalid")
        assert tree is None


# ============================================================================
# FileVisitor — DI detection
# ============================================================================


class TestDIDetection:
    def test_fastapi_depends(self):
        source = textwrap.dedent("""\
            from fastapi import Depends

            def get_db():
                pass

            async def handler(db = Depends(get_db)):
                pass
        """)
        tree = _safe_parse(source)
        visitor = _FileVisitor(source.splitlines(), "test.py")
        visitor.visit(tree)
        assert visitor.di_depends_count == 1

    def test_no_di(self):
        source = "def handler(x, y):\n    pass\n"
        tree = _safe_parse(source)
        visitor = _FileVisitor(source.splitlines(), "test.py")
        visitor.visit(tree)
        assert visitor.di_depends_count == 0


# ============================================================================
# FileVisitor — Error handling
# ============================================================================


class TestErrorHandling:
    def test_try_except_with_logging(self):
        source = textwrap.dedent("""\
            import logging
            logger = logging.getLogger(__name__)

            def risky():
                try:
                    do_something()
                except ValueError as e:
                    logger.error(f"Failed: {e}")
                except Exception:
                    logger.exception("Unexpected")
                    raise
        """)
        tree = _safe_parse(source)
        visitor = _FileVisitor(source.splitlines(), "test.py")
        visitor.visit(tree)

        assert visitor.try_blocks == 1
        assert visitor.typed_excepts == 2
        assert visitor.bare_excepts == 0
        assert visitor.reraise_count == 1
        assert "ValueError" in visitor.caught_exceptions
        assert "Exception" in visitor.caught_exceptions
        assert len(visitor.fingerprints) == 2  # Two except handlers

    def test_bare_except(self):
        source = textwrap.dedent("""\
            try:
                pass
            except:
                pass
        """)
        tree = _safe_parse(source)
        visitor = _FileVisitor(source.splitlines(), "test.py")
        visitor.visit(tree)
        assert visitor.bare_excepts == 1


# ============================================================================
# FileVisitor — Async detection
# ============================================================================


class TestAsyncDetection:
    def test_async_functions(self):
        source = textwrap.dedent("""\
            async def handler():
                pass

            def sync_func():
                pass

            async def another():
                pass
        """)
        tree = _safe_parse(source)
        visitor = _FileVisitor(source.splitlines(), "test.py")
        visitor.visit(tree)
        assert visitor.async_functions == 2
        assert visitor.sync_functions == 1


# ============================================================================
# FileVisitor — ORM detection
# ============================================================================


class TestORMDetection:
    def test_sqlalchemy_model(self):
        source = textwrap.dedent("""\
            from sqlalchemy.orm import mapped_column, Mapped
            from sqlalchemy import String

            class User(Base):
                __tablename__ = "users"
                name: Mapped[str] = mapped_column(String)
        """)
        tree = _safe_parse(source)
        visitor = _FileVisitor(source.splitlines(), "test.py")
        visitor.visit(tree)
        assert visitor.orm_indicators["sqlalchemy"] > 0

    def test_raw_sql(self):
        source = textwrap.dedent('''\
            query = "SELECT * FROM users WHERE id = ?"
        ''')
        tree = _safe_parse(source)
        visitor = _FileVisitor(source.splitlines(), "test.py")
        visitor.visit(tree)
        assert visitor.raw_sql_count == 1


# ============================================================================
# FileVisitor — Framework detection
# ============================================================================


class TestFrameworkDetection:
    def test_fastapi_imports(self):
        source = textwrap.dedent("""\
            from fastapi import APIRouter, Depends
            from fastapi.responses import JSONResponse
        """)
        tree = _safe_parse(source)
        visitor = _FileVisitor(source.splitlines(), "test.py")
        visitor.visit(tree)
        assert visitor.framework_indicators["fastapi"] == 2


# ============================================================================
# FileVisitor — Type hints and docstrings
# ============================================================================


class TestTypeHintsAndDocstrings:
    def test_type_hints(self):
        source = textwrap.dedent("""\
            def add(x: int, y: int) -> int:
                return x + y

            def untyped(a, b):
                return a + b
        """)
        tree = _safe_parse(source)
        visitor = _FileVisitor(source.splitlines(), "test.py")
        visitor.visit(tree)
        # add: x, y, return = 3 annotated, 3 total
        # untyped: a, b = 0 annotated, 2 total
        assert visitor.annotated_params == 3
        assert visitor.total_params == 5

    def test_google_docstring(self):
        source = textwrap.dedent('''\
            def func():
                """Do something.

                Args:
                    x: The input.

                Returns:
                    The output.
                """
                pass
        ''')
        tree = _safe_parse(source)
        visitor = _FileVisitor(source.splitlines(), "test.py")
        visitor.visit(tree)
        assert visitor.documented_functions == 1
        assert "google" in visitor.docstring_styles


# ============================================================================
# Fingerprint generation
# ============================================================================


class TestFingerprints:
    def test_error_handler_fingerprint(self):
        source = textwrap.dedent("""\
            try:
                risky()
            except ValueError:
                logger.error("bad")
                raise
        """)
        tree = _safe_parse(source)
        visitor = _FileVisitor(source.splitlines(), "test.py")
        visitor.visit(tree)

        assert len(visitor.fingerprints) == 1
        fp = visitor.fingerprints[0]
        assert fp.pattern_type == "error_handler"
        assert "ValueError" in fp.signature
        assert "raise" in fp.signature


# ============================================================================
# Full repository analysis (using temp directory)
# ============================================================================


class TestASTAnalyzerIntegration:
    def test_analyze_single_file_repo(self, tmp_path):
        """Create a minimal repo and analyze it."""
        (tmp_path / "app.py").write_text(textwrap.dedent("""\
            from fastapi import FastAPI, Depends
            from sqlalchemy.orm import Session

            app = FastAPI()

            def get_db():
                pass

            @app.get("/")
            async def root(db: Session = Depends(get_db)):
                try:
                    return {"status": "ok"}
                except Exception as e:
                    logger.error(f"Error: {e}")
                    raise
        """))

        analyzer = ASTAnalyzer(tmp_path)
        arch, style, fps, file_count, lines = analyzer.analyze()

        assert file_count == 1
        assert lines > 0

        # Architecture checks
        assert arch.framework.framework == "fastapi"
        assert arch.dependency_injection.uses_di is True
        assert arch.orm.orm_detected == "sqlalchemy"

        # Style checks
        assert style.async_patterns.async_function_count >= 1
        assert style.error_handling.total_try_blocks >= 1

    def test_analyze_empty_repo(self, tmp_path):
        """Empty repo should produce default profiles without errors."""
        analyzer = ASTAnalyzer(tmp_path)
        arch, style, fps, file_count, lines = analyzer.analyze()
        assert file_count == 0
        assert lines == 0
