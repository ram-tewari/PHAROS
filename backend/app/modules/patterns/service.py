"""
Pattern Learning Engine — Service Layer

Orchestrates AST parsing and Git history analysis to produce a DeveloperProfile.
Handles repository cloning for remote URIs and persists results to the database.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from .logic.ast_analyzer import ASTAnalyzer
from .logic.git_analyzer import GitAnalyzer
from .model import DeveloperProfileRecord
from .schema import DeveloperProfile, LearnRequest, LearnResponse

logger = logging.getLogger(__name__)


# ============================================================================
# Repository Resolution
# ============================================================================


def _resolve_repo(uri: str) -> tuple[Path, bool, str]:
    """
    Resolve a repository URI to a local path.

    Returns:
        (repo_path, is_temp, repo_name)
        is_temp=True means the caller must clean up the directory.
    """
    path = Path(uri)

    # Local path
    if path.exists() and (path / ".git").exists():
        return path, False, path.name

    if path.exists() and not (path / ".git").exists():
        # Directory exists but isn't a git repo — analyze it anyway
        return path, False, path.name

    # Remote URL — clone to temp directory
    if uri.startswith(("http://", "https://", "git@", "ssh://")):
        return _clone_remote(uri)

    raise ValueError(
        f"Cannot resolve repository URI: {uri}. "
        "Provide a local path to a git repo or a remote Git URL."
    )


def _clone_remote(url: str) -> tuple[Path, bool, str]:
    """Clone a remote repo to a temp directory (shallow clone for speed)."""
    tmpdir = Path(tempfile.mkdtemp(prefix="pharos_patterns_"))
    repo_name = url.rstrip("/").split("/")[-1].replace(".git", "")

    logger.info("Cloning %s to %s", url, tmpdir)
    try:
        subprocess.run(
            ["git", "clone", "--depth", "200", "--single-branch", url, str(tmpdir / repo_name)],
            capture_output=True,
            text=True,
            timeout=120,
            check=True,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        shutil.rmtree(tmpdir, ignore_errors=True)
        raise ValueError(f"Failed to clone repository: {exc}") from exc

    return tmpdir / repo_name, True, repo_name


# ============================================================================
# Main Service Functions
# ============================================================================


def learn_patterns(request: LearnRequest) -> LearnResponse:
    """
    Orchestrate AST parsing and Git analysis for a repository.

    This is the core entry point called by the API endpoint.
    """
    warnings: List[str] = []
    repo_path: Optional[Path] = None
    is_temp = False

    try:
        repo_path, is_temp, repo_name = _resolve_repo(request.repository_uri)

        # Phase 1: AST Analysis
        logger.info("Starting AST analysis for %s", repo_path)
        ast_analyzer = ASTAnalyzer(repo_path)
        arch_profile, style_profile, fingerprints, file_count, total_lines = (
            ast_analyzer.analyze()
        )

        if file_count == 0:
            warnings.append("No Python files found in repository.")

        # Phase 2: Git History Analysis
        git_profile = None
        if (repo_path / ".git").exists():
            logger.info("Starting Git history analysis for %s", repo_path)
            git_analyzer = GitAnalyzer(
                repo_path,
                max_commits=request.max_commits,
                branch=request.branch,
            )
            git_profile = git_analyzer.analyze()
        else:
            warnings.append(
                "No .git directory found — skipping Git history analysis."
            )

        # Phase 3: Detect languages
        languages = _detect_languages(repo_path)

        # Phase 4: Build summary
        summary = _build_summary(arch_profile, style_profile, git_profile)

        # Assemble profile
        profile = DeveloperProfile(
            repository_url=request.repository_uri,
            repository_name=repo_name,
            total_files_analyzed=file_count,
            total_lines_analyzed=total_lines,
            languages_detected=languages,
            architecture=arch_profile,
            style=style_profile,
            git_analysis=git_profile,
            summary=summary,
        )

        return LearnResponse(
            status="success",
            profile=profile,
            warnings=warnings,
        )

    except ValueError as exc:
        logger.error("Validation error: %s", exc)
        raise
    except Exception as exc:
        logger.error("Pattern learning failed: %s", exc, exc_info=True)
        raise ValueError(f"Pattern learning failed: {exc}") from exc
    finally:
        if is_temp and repo_path:
            shutil.rmtree(repo_path.parent, ignore_errors=True)


def persist_profile(
    db: Session,
    user_id: UUID,
    response: LearnResponse,
) -> DeveloperProfileRecord:
    """Persist a DeveloperProfile to the database, upserting by user+repo."""
    profile = response.profile

    # Check for existing record
    existing = (
        db.query(DeveloperProfileRecord)
        .filter(
            DeveloperProfileRecord.user_id == user_id,
            DeveloperProfileRecord.repository_url == profile.repository_url,
        )
        .first()
    )

    profile_json = json.loads(profile.model_dump_json())

    if existing:
        existing.profile_data = profile_json
        existing.total_files_analyzed = profile.total_files_analyzed
        existing.total_commits_analyzed = (
            profile.git_analysis.total_commits_analyzed
            if profile.git_analysis
            else 0
        )
        existing.languages_detected = json.dumps(profile.languages_detected)
        existing.repository_name = profile.repository_name
        db.commit()
        db.refresh(existing)
        return existing

    record = DeveloperProfileRecord(
        user_id=user_id,
        repository_url=profile.repository_url,
        repository_name=profile.repository_name,
        profile_data=profile_json,
        total_files_analyzed=profile.total_files_analyzed,
        total_commits_analyzed=(
            profile.git_analysis.total_commits_analyzed
            if profile.git_analysis
            else 0
        ),
        languages_detected=json.dumps(profile.languages_detected),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


# ============================================================================
# Helpers
# ============================================================================


def _detect_languages(repo_path: Path) -> List[str]:
    """Detect programming languages present in the repository."""
    extensions = {
        ".py": "Python",
        ".js": "JavaScript",
        ".ts": "TypeScript",
        ".tsx": "TypeScript (React)",
        ".jsx": "JavaScript (React)",
        ".c": "C",
        ".cpp": "C++",
        ".h": "C/C++ Header",
        ".go": "Go",
        ".rs": "Rust",
        ".java": "Java",
        ".rb": "Ruby",
    }
    found = set()

    excludes = {
        ".git", "node_modules", ".venv", "venv", "env",
        "__pycache__", "dist", "build", ".tox",
    }

    for filepath in repo_path.rglob("*"):
        if filepath.is_file():
            parts = set(filepath.relative_to(repo_path).parts)
            if parts.intersection(excludes):
                continue
            suffix = filepath.suffix.lower()
            if suffix in extensions:
                found.add(extensions[suffix])

    return sorted(found)


def _build_summary(arch_profile, style_profile, git_profile) -> dict:
    """Build a human-readable summary dict of key findings."""
    summary = {}

    # Architecture
    if arch_profile.framework.framework:
        summary["framework"] = arch_profile.framework.framework
    if arch_profile.orm.orm_detected:
        summary["orm"] = arch_profile.orm.orm_detected
    if arch_profile.dependency_injection.uses_di:
        summary["dependency_injection"] = arch_profile.dependency_injection.di_style
    if arch_profile.detected_patterns:
        summary["architectural_patterns"] = arch_profile.detected_patterns

    # Style
    summary["async_density"] = f"{style_profile.async_patterns.async_density:.0%}"
    summary["type_hint_coverage"] = f"{style_profile.naming.type_hint_density:.0%}"
    summary["avg_function_length"] = f"{style_profile.avg_function_length:.0f} lines"

    if style_profile.error_handling.exception_logging_style:
        summary["error_logging_style"] = (
            style_profile.error_handling.exception_logging_style
        )

    # Git
    if git_profile:
        summary["kept_patterns_count"] = len(git_profile.kept_patterns)
        summary["abandoned_patterns_count"] = len(git_profile.abandoned_patterns)
        summary["commits_analyzed"] = git_profile.total_commits_analyzed

    return summary
