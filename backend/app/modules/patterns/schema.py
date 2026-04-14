"""
Pattern Learning Engine — Pydantic Schemas

Defines the DeveloperProfile and all sub-schemas that capture a developer's
architectural standards, syntax habits, and historical success/failure patterns.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ============================================================================
# Architecture Detection Schemas
# ============================================================================


class DependencyInjectionProfile(BaseModel):
    """Captures DI usage patterns (FastAPI Depends, manual injection, etc.)."""

    uses_di: bool = False
    di_style: Optional[str] = Field(
        None, description="'fastapi_depends', 'constructor', 'manual', 'none'"
    )
    di_density: float = Field(
        0.0, description="Ratio of functions using DI to total functions"
    )
    examples: List[str] = Field(default_factory=list)


class ORMProfile(BaseModel):
    """ORM vs raw SQL preferences."""

    orm_detected: Optional[str] = Field(
        None, description="'sqlalchemy', 'django_orm', 'tortoise', 'peewee', None"
    )
    uses_raw_sql: bool = False
    raw_sql_density: float = Field(
        0.0, description="Ratio of raw SQL usage to total DB calls"
    )
    session_style: Optional[str] = Field(
        None, description="'sync', 'async', 'mixed'"
    )
    model_style: Optional[str] = Field(
        None, description="'declarative', 'imperative', 'dataclass'"
    )


class RepositoryPatternProfile(BaseModel):
    """Whether the codebase uses the repository/service/router layered pattern."""

    uses_repository_pattern: bool = False
    uses_service_layer: bool = False
    layer_separation: Optional[str] = Field(
        None, description="'strict' (no cross-layer calls), 'loose', 'none'"
    )
    detected_layers: List[str] = Field(default_factory=list)


class FrameworkProfile(BaseModel):
    """Detected web framework and patterns."""

    framework: Optional[str] = Field(
        None, description="'fastapi', 'flask', 'django', 'starlette', None"
    )
    framework_version: Optional[str] = None
    uses_blueprints: bool = False
    uses_routers: bool = False
    middleware_count: int = 0


class ArchitectureProfile(BaseModel):
    """Aggregated architectural detection results."""

    dependency_injection: DependencyInjectionProfile = Field(
        default_factory=DependencyInjectionProfile
    )
    orm: ORMProfile = Field(default_factory=ORMProfile)
    repository_pattern: RepositoryPatternProfile = Field(
        default_factory=RepositoryPatternProfile
    )
    framework: FrameworkProfile = Field(default_factory=FrameworkProfile)
    detected_patterns: List[str] = Field(
        default_factory=list,
        description="Named patterns found: 'factory', 'singleton', 'observer', etc.",
    )


# ============================================================================
# Style Extraction Schemas
# ============================================================================


class AsyncProfile(BaseModel):
    """Async/await usage density and patterns."""

    async_function_count: int = 0
    sync_function_count: int = 0
    async_density: float = Field(
        0.0, description="async functions / total functions"
    )
    uses_asyncio_gather: bool = False
    uses_asyncio_create_task: bool = False
    uses_async_generators: bool = False
    uses_async_context_managers: bool = False


class ErrorHandlingProfile(BaseModel):
    """Try/except patterns and logging behavior."""

    total_try_blocks: int = 0
    bare_except_count: int = 0
    typed_except_count: int = 0
    exception_logging_style: Optional[str] = Field(
        None,
        description="'logger.error', 'logger.exception', 'print', 'raise', 'silent'",
    )
    uses_custom_exceptions: bool = False
    custom_exception_count: int = 0
    reraise_ratio: float = Field(
        0.0, description="Ratio of except blocks that re-raise"
    )
    common_caught_exceptions: List[str] = Field(default_factory=list)


class NamingConventions(BaseModel):
    """Detected casing and naming conventions."""

    function_casing: str = Field(
        "snake_case",
        description="'snake_case', 'camelCase', 'PascalCase', 'mixed'",
    )
    class_casing: str = Field("PascalCase")
    variable_casing: str = Field("snake_case")
    constant_casing: str = Field(
        "UPPER_SNAKE", description="'UPPER_SNAKE', 'snake_case', 'mixed'"
    )
    private_prefix: str = Field(
        "_", description="'_', '__', 'none'"
    )
    uses_type_hints: bool = False
    type_hint_density: float = Field(
        0.0, description="Ratio of annotated params to total params"
    )


class ImportProfile(BaseModel):
    """Import organization habits."""

    uses_absolute_imports: bool = True
    uses_relative_imports: bool = False
    groups_imports: bool = False
    average_imports_per_file: float = 0.0
    top_packages: List[str] = Field(default_factory=list)


class DocstringProfile(BaseModel):
    """Documentation habits."""

    docstring_density: float = Field(
        0.0, description="Ratio of documented functions to total"
    )
    docstring_style: Optional[str] = Field(
        None, description="'google', 'numpy', 'sphinx', 'plain', 'none'"
    )
    uses_inline_comments: bool = False
    avg_comment_density: float = Field(
        0.0, description="Comment lines / total lines"
    )


class StyleProfile(BaseModel):
    """Aggregated code style extraction."""

    async_patterns: AsyncProfile = Field(default_factory=AsyncProfile)
    error_handling: ErrorHandlingProfile = Field(default_factory=ErrorHandlingProfile)
    naming: NamingConventions = Field(default_factory=NamingConventions)
    imports: ImportProfile = Field(default_factory=ImportProfile)
    docstrings: DocstringProfile = Field(default_factory=DocstringProfile)
    avg_function_length: float = Field(0.0, description="Average lines per function")
    avg_class_length: float = Field(0.0, description="Average lines per class")
    max_nesting_depth: int = 0


# ============================================================================
# Git History / Success-Failure Schemas
# ============================================================================


class StructuralFingerprint(BaseModel):
    """AST-level structural pattern fingerprint."""

    fingerprint_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    pattern_type: str = Field(
        ..., description="'error_handler', 'decorator_stack', 'class_structure', etc."
    )
    signature: str = Field(
        ..., description="Normalized AST signature, e.g. 'try>except(ValueError)>logger.error'"
    )
    source_file: str
    first_seen_commit: str
    first_seen_date: Optional[datetime] = None


class PatternLifecycle(BaseModel):
    """Tracks a structural pattern from introduction through modifications."""

    fingerprint: StructuralFingerprint
    status: str = Field(
        ..., description="'kept', 'abandoned', 'evolving'"
    )
    introduction_commit: str
    last_modified_commit: Optional[str] = None
    removal_commit: Optional[str] = None
    survival_commits: int = Field(
        0, description="Number of commits the pattern survived"
    )
    replication_count: int = Field(
        0, description="Number of files where this pattern was replicated"
    )
    modified_in_bugfix: bool = False
    confidence: float = Field(
        0.0, ge=0.0, le=1.0, description="Confidence in classification"
    )
    reasoning: str = Field(
        "", description="Why this was classified as kept/abandoned"
    )


class GitAnalysisProfile(BaseModel):
    """Results of Git history behavioral analysis."""

    total_commits_analyzed: int = 0
    feature_commits: int = 0
    bugfix_commits: int = 0
    refactor_commits: int = 0
    formatting_commits_skipped: int = 0
    kept_patterns: List[PatternLifecycle] = Field(default_factory=list)
    abandoned_patterns: List[PatternLifecycle] = Field(default_factory=list)
    evolving_patterns: List[PatternLifecycle] = Field(default_factory=list)
    analysis_window: Optional[str] = Field(
        None, description="Git log range analyzed, e.g. 'HEAD~100..HEAD'"
    )


# ============================================================================
# Aggregated Developer Profile
# ============================================================================


class DeveloperProfile(BaseModel):
    """
    Complete developer coding psychology profile.

    Aggregates architectural standards, syntax habits, and historical
    success/failure patterns into a single JSON-serializable profile.
    """

    profile_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    repository_url: str
    repository_name: str = ""
    analyzed_at: datetime = Field(default_factory=datetime.utcnow)
    total_files_analyzed: int = 0
    total_lines_analyzed: int = 0
    languages_detected: List[str] = Field(default_factory=list)

    # Core profile sections
    architecture: ArchitectureProfile = Field(default_factory=ArchitectureProfile)
    style: StyleProfile = Field(default_factory=StyleProfile)
    git_analysis: Optional[GitAnalysisProfile] = None

    # Summary
    summary: Dict[str, Any] = Field(
        default_factory=dict,
        description="Human-readable summary of key findings",
    )


# ============================================================================
# API Request/Response Schemas
# ============================================================================


class LearnRequest(BaseModel):
    """Request body for /api/patterns/learn."""

    repository_uri: str = Field(
        ..., description="Local path or remote Git URL to analyze"
    )
    max_commits: int = Field(
        200, ge=10, le=1000, description="Max commits to analyze for Git history"
    )
    branch: Optional[str] = Field(
        None, description="Branch to analyze (default: current/main)"
    )


class LearnResponse(BaseModel):
    """Response from /api/patterns/learn."""

    status: str = "success"
    profile: DeveloperProfile
    warnings: List[str] = Field(default_factory=list)


# ============================================================================
# Phase 6: Proposed Rule Schemas (Feedback Loop)
# ============================================================================


class CodingProfileCreate(BaseModel):
    """Request body for creating a new CodingProfile."""

    id: str = Field(..., min_length=1, max_length=128, description="Unique profile slug, e.g. 'sys_hacker'")
    name: str = Field(..., min_length=1, max_length=255, description="Human-readable name")
    description: str = Field(..., min_length=1, description="2-4 sentence description of the coding philosophy")
    best_suited_for: Dict[str, Any] = Field(
        default_factory=dict,
        description="JSON with 'languages' and 'tasks' arrays",
    )


class CodingProfileResponse(BaseModel):
    """A coding profile as returned by the API."""

    id: str
    name: str
    description: str
    best_suited_for: Dict[str, Any]
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ProposeRuleRequest(BaseModel):
    """Payload posted by the local extraction worker."""

    repository: str = Field(..., description="owner/repo identifier")
    commit_sha: str = Field(..., min_length=7, max_length=40)
    file_path: str
    diff_payload: str

    rule_name: str = Field(..., min_length=1, max_length=255)
    rule_description: str
    rule_schema: Dict[str, Any] = Field(
        ..., description="Structured JSON schema of the extracted rule"
    )
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    profile_id: Optional[str] = Field(
        None, description="CodingProfile ID to link this rule to (NULL = personal baseline)"
    )


class ProposeRuleResponse(BaseModel):
    """Acknowledgement returned to the local worker."""

    id: str
    status: str
    message: str


class RuleReviewItem(BaseModel):
    """A single proposed rule as seen in the triage inbox."""

    id: str
    repository: str
    commit_sha: str
    file_path: str
    diff_payload: str
    rule_name: str
    rule_description: str
    rule_schema: Dict[str, Any]
    confidence: float
    status: str
    created_at: Optional[datetime] = None
