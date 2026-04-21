"""
Hybrid AST Ingestion Pipeline — Phase 2

Ingests a GitHub repository without storing raw source code.

What gets stored in Postgres
────────────────────────────
• Resource row   – one per repository file (path, language, git metadata)
• DocumentChunk  – one per AST symbol (function/class/method) with:
    - github_uri      → raw.githubusercontent.com URL for the symbol
    - branch_reference → pinned commit SHA
    - start_line / end_line → line span in the file
    - ast_node_type / symbol_name → symbol identity
    - semantic_summary → signature + docstring (used for embeddings)
    - embedding        → vector stored on the Resource row

What does NOT get stored
────────────────────────
• Raw source code content
• Full file bodies
• Any binary artefacts

Embedding strategy
──────────────────
Rather than embedding full function bodies (expensive, bloats the DB),
we embed a lightweight semantic summary:

  [python] def authenticate_user(username: str, password: str) -> User:
      'Authenticate a user with credentials.'
      deps: [verify_password, db.query, User]

This is typically 2–5× smaller than the full body yet carries equal or
better semantic signal for retrieval.

Dependencies
────────────
  pip install gitpython pathspec sentence-transformers
  (httpx and redis are pulled in by the fetcher module)

Usage
─────
  pipeline = HybridIngestionPipeline(db)
  result   = await pipeline.ingest_github_repo(
      git_url="https://github.com/owner/repo",
      branch="main",
  )
"""

from __future__ import annotations

import ast
import logging
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import git
import pathspec
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import DocumentChunk, Resource
from app.modules.resources.logic.classification import classify_file

logger = logging.getLogger(__name__)


# ── Config ─────────────────────────────────────────────────────────────────────

# Languages that the pipeline can parse at AST level
_AST_SUPPORTED = {"python"}

# Extensions → language map (mirrors repo_ingestion.py)
_EXTENSION_LANGUAGE: dict[str, str] = {
    ".py": "python", ".js": "javascript", ".jsx": "javascript",
    ".ts": "typescript", ".tsx": "typescript", ".rs": "rust",
    ".go": "go", ".java": "java", ".cpp": "cpp", ".c": "c",
    ".rb": "ruby", ".php": "php", ".swift": "swift",
    ".kt": "kotlin", ".scala": "scala",
}

# Maximum characters of docstring to include in the semantic summary
_MAX_DOCSTRING_CHARS = 512

# Batch size for DB flushes
_BATCH_SIZE = 50


# ── Result dataclass ───────────────────────────────────────────────────────────

@dataclass
class IngestionResult:
    """Aggregate statistics returned after a repository is ingested."""
    repo_url: str
    branch: str
    commit_sha: str
    resources_created: int = 0
    chunks_created: int = 0
    files_skipped: int = 0
    files_failed: int = 0
    ingestion_time_seconds: float = 0.0
    # Estimate of DB storage saved vs naïve full-content approach
    estimated_storage_saved_bytes: int = 0
    errors: list[dict[str, str]] = field(default_factory=list)

    @property
    def storage_saved_mb(self) -> float:
        return self.estimated_storage_saved_bytes / (1024 * 1024)


# ── AST symbol extractor ───────────────────────────────────────────────────────

@dataclass
class SymbolInfo:
    """Represents a single AST-extracted code symbol."""
    name: str               # simple name, e.g. "authenticate_user"
    qualified_name: str     # module.ClassName.method_name
    node_type: str          # "function" | "class" | "method"
    start_line: int         # 1-based
    end_line: int           # 1-based
    signature: str          # reconstructed def/class line
    docstring: str          # first docstring, empty string if absent
    dependencies: list[str] # called names / imported names referenced


class PythonASTExtractor:
    """Extract symbols from a Python source file using the stdlib `ast` module."""

    def extract(self, source: str, module_path: str) -> list[SymbolInfo]:
        """
        Parse `source` and return one SymbolInfo per function / class / method.

        Args:
            source:      Full source text of the file.
            module_path: Dot-separated module path, e.g. "auth.oauth".
        """
        try:
            tree = ast.parse(source)
        except SyntaxError as exc:
            logger.warning("AST parse failed for %s: %s", module_path, exc)
            return []

        visitor = _SymbolVisitor(module_path=module_path)
        visitor.visit(tree)
        return visitor.symbols

    def build_semantic_summary(self, sym: SymbolInfo, language: str = "python") -> str:
        """
        Produce a compact, embedding-friendly text block for a symbol.

        Format:
            [{language}] {signature}
                {docstring truncated}
                deps: [{dep1}, {dep2}, …]
        """
        parts = [f"[{language}] {sym.signature}"]
        if sym.docstring:
            doc = sym.docstring[:_MAX_DOCSTRING_CHARS]
            if len(sym.docstring) > _MAX_DOCSTRING_CHARS:
                doc += "…"
            parts.append(f"    \"\"\"{doc}\"\"\"")
        if sym.dependencies:
            dep_str = ", ".join(sym.dependencies[:20])  # cap for summary length
            parts.append(f"    deps: [{dep_str}]")
        return "\n".join(parts)


class _SymbolVisitor(ast.NodeVisitor):
    """Walk the AST and collect SymbolInfo entries."""

    def __init__(self, module_path: str) -> None:
        self.module_path = module_path
        self.symbols: list[SymbolInfo] = []
        self._class_stack: list[str] = []

    # ── Helpers ────────────────────────────────────────────────────────────

    def _qualified(self, name: str) -> str:
        parts = [self.module_path] + self._class_stack + [name]
        return ".".join(filter(None, parts))

    @staticmethod
    def _get_docstring(node: ast.AST) -> str:
        try:
            doc = ast.get_docstring(node)
            return doc or ""
        except Exception:
            return ""

    @staticmethod
    def _extract_deps(node: ast.AST) -> list[str]:
        """Return names called or loaded within this node's subtree."""
        deps: list[str] = []
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                # func can be Name or Attribute
                if isinstance(child.func, ast.Name):
                    deps.append(child.func.id)
                elif isinstance(child.func, ast.Attribute):
                    deps.append(child.func.attr)
            elif isinstance(child, ast.Import):
                for alias in child.names:
                    deps.append(alias.asname or alias.name.split(".")[0])
            elif isinstance(child, ast.ImportFrom):
                if child.module:
                    deps.append(child.module.split(".")[0])
        # Deduplicate while preserving order
        seen: set[str] = set()
        unique: list[str] = []
        for d in deps:
            if d not in seen:
                seen.add(d)
                unique.append(d)
        return unique

    @staticmethod
    def _function_signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
        """Reconstruct a one-line signature from an AST function node."""
        args = []
        fn_args = node.args

        # positional args
        for i, arg in enumerate(fn_args.args):
            annotation = ""
            if arg.annotation:
                annotation = f": {ast.unparse(arg.annotation)}"
            args.append(f"{arg.arg}{annotation}")

        # *args
        if fn_args.vararg:
            args.append(f"*{fn_args.vararg.arg}")

        # **kwargs
        if fn_args.kwarg:
            args.append(f"**{fn_args.kwarg.arg}")

        return_ann = ""
        if node.returns:
            return_ann = f" -> {ast.unparse(node.returns)}"

        prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
        return f"{prefix} {node.name}({', '.join(args)}){return_ann}:"

    # ── Visitors ───────────────────────────────────────────────────────────

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        bases = ", ".join(ast.unparse(b) for b in node.bases) if node.bases else ""
        sig = f"class {node.name}({bases}):" if bases else f"class {node.name}:"

        self.symbols.append(SymbolInfo(
            name=node.name,
            qualified_name=self._qualified(node.name),
            node_type="class",
            start_line=node.lineno,
            end_line=node.end_lineno or node.lineno,
            signature=sig,
            docstring=self._get_docstring(node),
            dependencies=self._extract_deps(node),
        ))

        self._class_stack.append(node.name)
        self.generic_visit(node)
        self._class_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def _visit_function(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> None:
        node_type = "method" if self._class_stack else "function"
        self.symbols.append(SymbolInfo(
            name=node.name,
            qualified_name=self._qualified(node.name),
            node_type=node_type,
            start_line=node.lineno,
            end_line=node.end_lineno or node.lineno,
            signature=self._function_signature(node),
            docstring=self._get_docstring(node),
            dependencies=self._extract_deps(node),
        ))
        self.generic_visit(node)


# ── Generic (non-AST) chunker ──────────────────────────────────────────────────

def chunk_generic_file(
    content: str,
    chunk_size: int = 50,
    overlap: int = 5,
) -> list[tuple[int, int, str]]:
    """
    Split a non-Python file into overlapping line-range chunks.

    Returns a list of (start_line, end_line, summary_text) tuples.
    Summary text is the first non-empty line of the chunk (used for embedding).
    """
    lines = content.splitlines()
    chunks: list[tuple[int, int, str]] = []
    step = chunk_size - overlap
    for start in range(0, len(lines), step):
        end = min(start + chunk_size, len(lines))
        chunk_lines = lines[start:end]
        # Use first non-blank line as a summary proxy
        summary = next((line.strip() for line in chunk_lines if line.strip()), "")
        chunks.append((start + 1, end, summary[:512]))   # 1-based
        if end >= len(lines):
            break
    return chunks


# ── Main pipeline class ────────────────────────────────────────────────────────

class HybridIngestionPipeline:
    """
    Ingests a GitHub repository into Pharos without storing raw source code.

    Workflow
    ────────
    1. Shallow-clone the repository to a temp directory
    2. Walk code files, respecting .gitignore
    3. For Python files: extract AST symbols (functions, classes, methods)
       For other languages: create fixed-size line-range chunks
    4. Build a semantic summary per symbol/chunk (signature + docstring + deps)
    5. Generate vector embedding from the semantic summary
    6. Store Resource + DocumentChunk rows with github_uri pointers
    7. Return IngestionResult with storage/performance statistics

    The cloned repo is deleted after ingestion — nothing is persisted locally.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self._extractor = PythonASTExtractor()

    # ── Public entry point ─────────────────────────────────────────────────

    async def ingest_github_repo(
        self,
        git_url: str,
        branch: str = "main",
        file_extensions: tuple[str, ...] = (".py", ".js", ".ts", ".go", ".java"),
        batch_size: int = _BATCH_SIZE,
    ) -> IngestionResult:
        """
        Clone `git_url` and ingest all matching source files.

        Args:
            git_url:         HTTPS clone URL (validated for safety).
            branch:          Branch or tag to clone.
            file_extensions: Tuple of extensions to process.
            batch_size:      Number of chunks to flush per DB transaction.

        Returns:
            IngestionResult with detailed statistics.
        """
        import time
        if not git_url.startswith("https://"):
            raise ValueError("Only HTTPS clone URLs are accepted.")

        t0 = time.monotonic()
        temp_dir = tempfile.mkdtemp(prefix="pharos_ingest_")
        temp_path = Path(temp_dir)

        try:
            repo, commit_sha = self._clone_repo(git_url, branch, temp_path)
            result = IngestionResult(repo_url=git_url, branch=branch, commit_sha=commit_sha)

            gitignore_spec = self._load_gitignore(temp_path)
            pending_chunks: list[DocumentChunk] = []

            for file_path in self._iter_source_files(
                temp_path, gitignore_spec, file_extensions
            ):
                try:
                    new_chunks = await self._process_file(
                        file_path=file_path,
                        root_path=temp_path,
                        git_url=git_url,
                        commit_sha=commit_sha,
                        result=result,
                    )
                    pending_chunks.extend(new_chunks)

                    if len(pending_chunks) >= batch_size:
                        await self._flush(pending_chunks, result)
                        pending_chunks.clear()

                except Exception as exc:
                    rel = str(file_path.relative_to(temp_path))
                    logger.error("File failed: %s — %s", rel, exc, exc_info=True)
                    result.files_failed += 1
                    result.errors.append({"path": rel, "error": str(exc)})

            # Flush remaining
            if pending_chunks:
                await self._flush(pending_chunks, result)

        finally:
            try:
                shutil.rmtree(temp_path)
            except Exception as exc:
                logger.warning("Temp dir cleanup failed: %s", exc)

        result.ingestion_time_seconds = time.monotonic() - t0
        logger.info(
            "Ingested %s — %d resources, %d chunks in %.1fs "
            "(saved ~%.1f MB of raw code storage)",
            git_url,
            result.resources_created,
            result.chunks_created,
            result.ingestion_time_seconds,
            result.storage_saved_mb,
        )
        return result

    # ── Private helpers ────────────────────────────────────────────────────

    def _clone_repo(
        self, git_url: str, branch: str, dest: Path
    ) -> tuple[git.Repo, str]:
        """Shallow-clone and return (repo, commit_sha)."""
        try:
            repo = git.Repo.clone_from(
                git_url, dest,
                branch=branch,
                depth=1,
                # timeout parameter removed for Git < 2.47 compatibility
            )
        except git.GitCommandError as exc:
            raise RuntimeError(f"Clone failed for {git_url}: {exc}") from exc

        sha = repo.head.commit.hexsha
        logger.info("Cloned %s @ %s (branch=%s)", git_url, sha[:12], branch)
        return repo, sha

    @staticmethod
    def _load_gitignore(root: Path) -> pathspec.PathSpec | None:
        gi_path = root / ".gitignore"
        if not gi_path.exists():
            return None
        try:
            lines = [
                line.strip() for line in gi_path.read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.strip().startswith("#")
            ]
            return pathspec.PathSpec.from_lines("gitwildmatch", lines)
        except Exception as exc:
            logger.warning(".gitignore load failed: %s", exc)
            return None

    @staticmethod
    def _iter_source_files(
        root: Path,
        gitignore: pathspec.PathSpec | None,
        extensions: tuple[str, ...],
    ):
        """Yield source file Paths respecting .gitignore and extension filter."""
        for path in root.rglob("*"):
            if path.is_dir():
                continue
            if path.suffix.lower() not in extensions:
                continue
            if gitignore:
                rel = str(path.relative_to(root)).replace("\\", "/")
                if gitignore.match_file(rel):
                    continue
            # Quick binary check
            try:
                with open(path, "rb") as fh:
                    if b"\x00" in fh.read(4096):
                        continue
            except OSError:
                continue
            yield path

    async def _process_file(
        self,
        file_path: Path,
        root_path: Path,
        git_url: str,
        commit_sha: str,
        result: IngestionResult,
    ) -> list[DocumentChunk]:
        """
        Process one source file and return the DocumentChunk list.

        Reads the file only to extract AST metadata and compute embeddings —
        the content is then discarded without being written to the DB.
        """
        try:
            content = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = file_path.read_text(encoding="latin-1")

        rel_path = str(file_path.relative_to(root_path)).replace("\\", "/")
        language = _EXTENSION_LANGUAGE.get(file_path.suffix.lower(), "unknown")
        module_path = rel_path.replace("/", ".").removesuffix(".py")

        # Build GitHub raw URL for this file
        # e.g. https://raw.githubusercontent.com/owner/repo/SHA/path/file.py
        raw_base = _github_raw_base(git_url, commit_sha)
        file_github_uri = f"{raw_base}/{rel_path}"

        # Create Resource row (one per file) — no raw content stored
        classification = classify_file(file_path, content)
        resource = Resource(
            title=file_path.name,
            description=f"{language.title()} source — {rel_path}",
            source=git_url,
            identifier=rel_path,
            coverage=commit_sha,
            type="code_file",
            format=f"text/{language}",
            language=language,
            classification_code=classification,
            subject=[classification, language],
            relation=[
                f"classification:{classification}",
                f"language:{language}",
                f"git:commit:{commit_sha}",
                f"git:url:{git_url}",
            ],
        )
        self.db.add(resource)
        await self.db.flush()
        result.resources_created += 1

        # Extract symbols
        chunks: list[DocumentChunk] = []

        if language in _AST_SUPPORTED:
            symbols = self._extractor.extract(content, module_path)
            for idx, sym in enumerate(symbols):
                summary = self._extractor.build_semantic_summary(sym, language)
                embedding_vector = await _generate_embedding(summary)
                chunk = DocumentChunk(
                    resource_id=resource.id,
                    chunk_index=idx,
                    content=None,          # ← no raw code stored
                    is_remote=True,
                    github_uri=file_github_uri,
                    branch_reference=commit_sha,
                    start_line=sym.start_line,
                    end_line=sym.end_line,
                    ast_node_type=sym.node_type,
                    symbol_name=sym.qualified_name,
                    semantic_summary=summary,
                    chunk_metadata={
                        "language": language,
                        "dependencies": sym.dependencies[:30],
                    },
                )
                self.db.add(chunk)
                chunks.append(chunk)

                # Also store the embedding on the resource (for global search)
                if embedding_vector and resource.embedding is None:
                    resource.embedding = str(embedding_vector)

                # Estimate bytes saved: avg symbol body ≈ 800 chars
                result.estimated_storage_saved_bytes += 800

        else:
            # Generic chunking for non-Python files
            line_chunks = chunk_generic_file(content)
            for idx, (start, end, summary) in enumerate(line_chunks):
                embedding_vector = await _generate_embedding(summary)
                chunk = DocumentChunk(
                    resource_id=resource.id,
                    chunk_index=idx,
                    content=None,
                    is_remote=True,
                    github_uri=file_github_uri,
                    branch_reference=commit_sha,
                    start_line=start,
                    end_line=end,
                    ast_node_type="block",
                    symbol_name=f"{rel_path}:{start}-{end}",
                    semantic_summary=summary,
                    chunk_metadata={"language": language},
                )
                self.db.add(chunk)
                chunks.append(chunk)
                result.estimated_storage_saved_bytes += (end - start) * 40  # ~40 chars/line

        result.chunks_created += len(chunks)
        return chunks

    async def _flush(
        self, chunks: list[DocumentChunk], result: IngestionResult
    ) -> None:
        """Commit a batch of chunks to the database."""
        try:
            await self.db.commit()
            logger.debug("Flushed %d chunks", len(chunks))
        except Exception as exc:
            await self.db.rollback()
            logger.error("Batch commit failed: %s", exc, exc_info=True)
            result.files_failed += 1
            result.errors.append({"batch": "db_commit_error", "error": str(exc)})


# ── Utilities ──────────────────────────────────────────────────────────────────

def _github_raw_base(git_url: str, commit_sha: str) -> str:
    """
    Convert a GitHub clone URL + commit SHA → raw content base URL.

    https://github.com/owner/repo.git  →  https://raw.githubusercontent.com/owner/repo/SHA
    """
    url = git_url.rstrip("/").removesuffix(".git")
    # Replace github.com host with raw.githubusercontent.com
    url = url.replace("https://github.com/", "https://raw.githubusercontent.com/", 1)
    return f"{url}/{commit_sha}"


async def _generate_embedding(text: str) -> list[float] | None:
    """
    Generate a vector embedding for `text`.

    Uses sentence-transformers (all-MiniLM-L6-v2) when available.
    Falls back gracefully to None so ingestion continues even without a
    GPU / model download.
    """
    try:
        from sentence_transformers import SentenceTransformer
        # Module-level singleton — loaded once per process
        if not hasattr(_generate_embedding, "_model"):
            _generate_embedding._model = SentenceTransformer("all-MiniLM-L6-v2")
        model = _generate_embedding._model
        # Run in default executor to avoid blocking the event loop
        import asyncio
        loop = asyncio.get_event_loop()
        vector = await loop.run_in_executor(None, model.encode, text)
        return vector.tolist()
    except ImportError:
        logger.warning(
            "sentence-transformers not installed — embeddings skipped. "
            "Run: pip install sentence-transformers"
        )
        return None
    except Exception as exc:
        logger.warning("Embedding generation failed: %s", exc)
        return None
