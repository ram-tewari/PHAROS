"""
Git History Behavioral Analyzer

Interfaces with Git history to differentiate patterns a developer keeps
versus patterns they abandon. Uses AST-level structural fingerprints to
survive formatting changes and produce meaningful pattern lifecycle data.

Edge-case handling:
- Formatting-only commits (>80% whitespace changes) are skipped.
- Merge commits are skipped (no single-author signal).
- Commits are classified by message heuristics, not just diff content.
- Pattern fingerprints are compared at AST level, not text level.
"""

from __future__ import annotations

import ast
import logging
import re
import subprocess
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from ..schema import (
    GitAnalysisProfile,
    PatternLifecycle,
    StructuralFingerprint,
)

logger = logging.getLogger(__name__)


# ============================================================================
# Commit Classification
# ============================================================================

# Patterns for classifying commits by message
_BUGFIX_PATTERNS = re.compile(
    r"\b(fix|bug|hotfix|patch|resolve|correct|repair|broken|crash|error|issue)\b",
    re.IGNORECASE,
)
_FEATURE_PATTERNS = re.compile(
    r"\b(feat|add|implement|introduce|create|new|support|enable)\b",
    re.IGNORECASE,
)
_REFACTOR_PATTERNS = re.compile(
    r"\b(refactor|restructure|reorganize|simplify|clean|extract|move|rename|improve)\b",
    re.IGNORECASE,
)
_FORMATTING_PATTERNS = re.compile(
    r"\b(style|format|lint|prettier|black|isort|whitespace|indent|pep8|ruff)\b",
    re.IGNORECASE,
)


def classify_commit(message: str) -> str:
    """
    Classify a commit message into a category.

    Returns one of: 'bugfix', 'feature', 'refactor', 'formatting', 'other'.
    Priority order matters — a 'fix' in a feature commit still counts as bugfix.
    """
    first_line = message.strip().split("\n")[0]

    if _FORMATTING_PATTERNS.search(first_line):
        return "formatting"
    if _BUGFIX_PATTERNS.search(first_line):
        return "bugfix"
    if _FEATURE_PATTERNS.search(first_line):
        return "feature"
    if _REFACTOR_PATTERNS.search(first_line):
        return "refactor"
    return "other"


# ============================================================================
# Git Interface
# ============================================================================


class _GitInterface:
    """Thin wrapper around git CLI for repository interrogation."""

    def __init__(self, repo_path: Path):
        self.repo_path = repo_path

    def _run(self, *args: str, timeout: int = 30) -> str:
        """Run a git command and return stdout."""
        cmd = ["git", "-C", str(self.repo_path)] + list(args)
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding="utf-8",
                errors="replace",
            )
            if result.returncode != 0:
                logger.debug("git %s failed: %s", " ".join(args[:3]), result.stderr[:200])
                return ""
            return result.stdout
        except subprocess.TimeoutExpired:
            logger.warning("git command timed out: %s", " ".join(args[:3]))
            return ""
        except FileNotFoundError:
            logger.error("git executable not found")
            return ""

    def log(
        self,
        max_count: int = 200,
        branch: Optional[str] = None,
        format_str: str = "%H|%ae|%aI|%s",
    ) -> List[Dict[str, str]]:
        """
        Get commit log as list of dicts.

        Returns dicts with keys: hash, author, date, message.
        Excludes merge commits.
        """
        args = [
            "log",
            "--no-merges",
            f"--max-count={max_count}",
            f"--format={format_str}",
        ]
        if branch:
            args.append(branch)

        output = self._run(*args)
        if not output:
            return []

        commits = []
        for line in output.strip().split("\n"):
            if not line:
                continue
            parts = line.split("|", 3)
            if len(parts) >= 4:
                commits.append({
                    "hash": parts[0],
                    "author": parts[1],
                    "date": parts[2],
                    "message": parts[3],
                })
        return commits

    def diff_stat(self, commit_hash: str) -> Dict[str, int]:
        """
        Get diff statistics for a commit.

        Returns dict with 'insertions', 'deletions', 'files_changed'.
        """
        output = self._run("diff", "--shortstat", f"{commit_hash}~1", commit_hash)
        if not output:
            return {"insertions": 0, "deletions": 0, "files_changed": 0}

        stats = {"insertions": 0, "deletions": 0, "files_changed": 0}

        files_match = re.search(r"(\d+) files? changed", output)
        ins_match = re.search(r"(\d+) insertions?", output)
        del_match = re.search(r"(\d+) deletions?", output)

        if files_match:
            stats["files_changed"] = int(files_match.group(1))
        if ins_match:
            stats["insertions"] = int(ins_match.group(1))
        if del_match:
            stats["deletions"] = int(del_match.group(1))

        return stats

    def diff_files(self, commit_hash: str) -> List[str]:
        """Get list of files changed in a commit."""
        output = self._run("diff-tree", "--no-commit-id", "-r", "--name-only", commit_hash)
        if not output:
            return []
        return [f for f in output.strip().split("\n") if f.endswith(".py")]

    def show_file_at_commit(self, commit_hash: str, filepath: str) -> str:
        """Get file content at a specific commit."""
        return self._run("show", f"{commit_hash}:{filepath}", timeout=10)

    def show_file_before_commit(self, commit_hash: str, filepath: str) -> str:
        """Get file content before a specific commit."""
        return self._run("show", f"{commit_hash}~1:{filepath}", timeout=10)

    def diff_patch(self, commit_hash: str, filepath: str) -> str:
        """Get unified diff for a specific file in a commit."""
        return self._run("diff", f"{commit_hash}~1", commit_hash, "--", filepath)

    def is_formatting_only(self, commit_hash: str) -> bool:
        """
        Heuristic: check if a commit is primarily formatting changes.

        A commit is formatting-only if >80% of changed lines are whitespace-only
        or import-reordering changes.
        """
        output = self._run("diff", f"{commit_hash}~1", commit_hash, "-U0")
        if not output:
            return False

        total_changes = 0
        whitespace_changes = 0

        for line in output.split("\n"):
            if line.startswith("+") and not line.startswith("+++"):
                total_changes += 1
                stripped = line[1:].strip()
                if not stripped or stripped.startswith(("import ", "from ")):
                    whitespace_changes += 1
            elif line.startswith("-") and not line.startswith("---"):
                total_changes += 1
                stripped = line[1:].strip()
                if not stripped or stripped.startswith(("import ", "from ")):
                    whitespace_changes += 1

        if total_changes == 0:
            return True
        return (whitespace_changes / total_changes) > 0.8


# ============================================================================
# AST Fingerprint Extraction from Source
# ============================================================================


def extract_fingerprints_from_source(
    source: str, filename: str
) -> List[StructuralFingerprint]:
    """
    Extract structural fingerprints from Python source code.

    Focuses on error handling patterns, decorator stacks, and class structures
    that can be tracked across commits.
    """
    try:
        tree = ast.parse(source, filename)
    except SyntaxError:
        return []

    fingerprints: List[StructuralFingerprint] = []

    for node in ast.walk(tree):
        # Error handler fingerprints
        if isinstance(node, ast.Try):
            for handler in node.handlers:
                if handler.type is not None:
                    exc_name = _get_name(handler.type) or "Unknown"
                    body_sig = _fingerprint_body(handler.body)
                    fingerprints.append(
                        StructuralFingerprint(
                            pattern_type="error_handler",
                            signature=f"try>except({exc_name})>{body_sig}",
                            source_file=filename,
                            first_seen_commit="",
                        )
                    )

        # Decorated function fingerprints
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.decorator_list:
                dec_names = [_get_name(d) or "?" for d in node.decorator_list]
                prefix = "async_" if isinstance(node, ast.AsyncFunctionDef) else ""
                fingerprints.append(
                    StructuralFingerprint(
                        pattern_type="decorator_stack",
                        signature=f"{prefix}def>{'+'.join(dec_names)}",
                        source_file=filename,
                        first_seen_commit="",
                    )
                )

        # Class inheritance fingerprints
        if isinstance(node, ast.ClassDef) and node.bases:
            base_names = [_get_name(b) or "?" for b in node.bases]
            method_names = [
                n.name for n in node.body
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            ][:5]
            fingerprints.append(
                StructuralFingerprint(
                    pattern_type="class_structure",
                    signature=f"class({'+'.join(base_names)})>methods[{','.join(method_names)}]",
                    source_file=filename,
                    first_seen_commit="",
                )
            )

    return fingerprints


def _get_name(node: ast.AST) -> Optional[str]:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        val = _get_name(node.value)
        return f"{val}.{node.attr}" if val else node.attr
    if isinstance(node, ast.Call):
        return _get_name(node.func)
    return None


def _fingerprint_body(body: List[ast.stmt]) -> str:
    parts = []
    for stmt in body[:3]:
        if isinstance(stmt, ast.Raise):
            parts.append("raise")
        elif isinstance(stmt, ast.Return):
            parts.append("return")
        elif isinstance(stmt, ast.Pass):
            parts.append("pass")
        elif isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
            name = _get_name(stmt.value.func)
            parts.append(name or "call")
        elif isinstance(stmt, ast.Assign):
            parts.append("assign")
    return "+".join(parts) if parts else "empty"


# ============================================================================
# Pattern Lifecycle Tracker
# ============================================================================


class _PatternTracker:
    """
    Tracks structural fingerprints across commits to determine
    whether patterns are kept, abandoned, or evolving.
    """

    def __init__(self):
        # signature -> PatternLifecycle
        self.patterns: Dict[str, PatternLifecycle] = {}
        # signature -> set of files where it appears
        self.file_occurrences: Dict[str, Set[str]] = defaultdict(set)

    def record_pattern(
        self,
        fingerprint: StructuralFingerprint,
        commit_hash: str,
        commit_date: Optional[str] = None,
        commit_type: str = "other",
    ) -> None:
        """Record that a fingerprint was observed in a commit."""
        sig = fingerprint.signature

        if sig not in self.patterns:
            # New pattern
            fp = fingerprint.model_copy()
            fp.first_seen_commit = commit_hash
            if commit_date:
                try:
                    fp.first_seen_date = datetime.fromisoformat(commit_date)
                except (ValueError, TypeError):
                    pass

            self.patterns[sig] = PatternLifecycle(
                fingerprint=fp,
                status="kept",  # Default, refined later
                introduction_commit=commit_hash,
                survival_commits=1,
            )
        else:
            lifecycle = self.patterns[sig]
            lifecycle.survival_commits += 1
            lifecycle.last_modified_commit = commit_hash

        self.file_occurrences[sig].add(fingerprint.source_file)

    def record_removal(
        self, signature: str, commit_hash: str, commit_type: str
    ) -> None:
        """Record that a fingerprint was removed in a commit."""
        if signature in self.patterns:
            lifecycle = self.patterns[signature]
            lifecycle.removal_commit = commit_hash
            if commit_type == "bugfix":
                lifecycle.modified_in_bugfix = True

    def finalize(self) -> Tuple[List[PatternLifecycle], List[PatternLifecycle], List[PatternLifecycle]]:
        """
        Classify all patterns into kept, abandoned, or evolving.

        Classification rules:
        - ABANDONED: Pattern has a removal_commit AND was removed during a bugfix,
          OR survived fewer than 3 commits and was removed.
        - EVOLVING: Pattern was modified in a bugfix but not removed
          (suggests it's being refined, not discarded).
        - KEPT: Pattern survived 3+ commits OR was replicated across 2+ files.
        """
        kept = []
        abandoned = []
        evolving = []

        for sig, lifecycle in self.patterns.items():
            lifecycle.replication_count = len(self.file_occurrences.get(sig, set()))

            if lifecycle.removal_commit:
                if lifecycle.modified_in_bugfix:
                    lifecycle.status = "abandoned"
                    lifecycle.confidence = min(
                        0.5 + (0.1 * lifecycle.survival_commits), 0.95
                    )
                    lifecycle.reasoning = (
                        f"Introduced in {lifecycle.introduction_commit[:8]}, "
                        f"removed during bugfix in {lifecycle.removal_commit[:8]} "
                        f"after surviving {lifecycle.survival_commits} commits."
                    )
                    abandoned.append(lifecycle)
                elif lifecycle.survival_commits < 3:
                    lifecycle.status = "abandoned"
                    lifecycle.confidence = 0.4 + (0.1 * lifecycle.survival_commits)
                    lifecycle.reasoning = (
                        f"Short-lived pattern (survived {lifecycle.survival_commits} commits), "
                        f"removed in {lifecycle.removal_commit[:8]}."
                    )
                    abandoned.append(lifecycle)
                else:
                    # Survived many commits then removed — could be an evolution
                    lifecycle.status = "evolving"
                    lifecycle.confidence = 0.6
                    lifecycle.reasoning = (
                        f"Survived {lifecycle.survival_commits} commits before "
                        f"removal in {lifecycle.removal_commit[:8]}."
                    )
                    evolving.append(lifecycle)
            elif lifecycle.modified_in_bugfix and lifecycle.survival_commits < 5:
                lifecycle.status = "evolving"
                lifecycle.confidence = 0.5
                lifecycle.reasoning = (
                    f"Pattern was modified during a bugfix but retained. "
                    f"May be evolving toward a stable form."
                )
                evolving.append(lifecycle)
            else:
                lifecycle.status = "kept"
                base_conf = 0.5
                if lifecycle.survival_commits >= 5:
                    base_conf += 0.2
                if lifecycle.replication_count >= 2:
                    base_conf += 0.2
                lifecycle.confidence = min(base_conf, 0.95)
                lifecycle.reasoning = (
                    f"Stable pattern: survived {lifecycle.survival_commits} commits, "
                    f"replicated across {lifecycle.replication_count} files."
                )
                kept.append(lifecycle)

        return kept, abandoned, evolving


# ============================================================================
# Main Git Analyzer
# ============================================================================


class GitAnalyzer:
    """
    Analyzes Git history to detect kept vs abandoned coding patterns.

    Workflow:
    1. Fetch commit log (excluding merges).
    2. Classify each commit (feature, bugfix, refactor, formatting).
    3. Skip formatting-only commits.
    4. For each relevant commit, extract AST fingerprints from changed .py files.
    5. Compare before/after fingerprints to detect introductions and removals.
    6. Track pattern lifecycles and classify as kept/abandoned/evolving.
    """

    def __init__(self, repo_path: Path, max_commits: int = 200, branch: Optional[str] = None):
        self.repo_path = repo_path
        self.max_commits = max_commits
        self.branch = branch
        self._git = _GitInterface(repo_path)
        self._tracker = _PatternTracker()

    def analyze(self) -> GitAnalysisProfile:
        """Run the full Git history analysis."""
        commits = self._git.log(max_count=self.max_commits, branch=self.branch)
        if not commits:
            logger.warning("No commits found in %s", self.repo_path)
            return GitAnalysisProfile()

        logger.info("Analyzing %d commits in %s", len(commits), self.repo_path)

        feature_count = 0
        bugfix_count = 0
        refactor_count = 0
        formatting_skipped = 0

        # Process commits from oldest to newest for correct lifecycle tracking
        for commit in reversed(commits):
            commit_hash = commit["hash"]
            commit_type = classify_commit(commit["message"])

            # Skip formatting commits
            if commit_type == "formatting":
                formatting_skipped += 1
                continue

            # Double-check with diff analysis for non-formatting-classified commits
            if self._git.is_formatting_only(commit_hash):
                formatting_skipped += 1
                continue

            if commit_type == "feature":
                feature_count += 1
            elif commit_type == "bugfix":
                bugfix_count += 1
            elif commit_type == "refactor":
                refactor_count += 1

            # Analyze changed Python files
            changed_files = self._git.diff_files(commit_hash)
            if not changed_files:
                continue

            # Limit files per commit to avoid excessive processing
            for filepath in changed_files[:20]:
                self._analyze_file_change(
                    commit_hash, filepath, commit["date"], commit_type
                )

        # Finalize pattern classifications
        kept, abandoned, evolving = self._tracker.finalize()

        return GitAnalysisProfile(
            total_commits_analyzed=len(commits),
            feature_commits=feature_count,
            bugfix_commits=bugfix_count,
            refactor_commits=refactor_count,
            formatting_commits_skipped=formatting_skipped,
            kept_patterns=kept,
            abandoned_patterns=abandoned,
            evolving_patterns=evolving,
            analysis_window=f"last {len(commits)} commits",
        )

    def _analyze_file_change(
        self,
        commit_hash: str,
        filepath: str,
        commit_date: str,
        commit_type: str,
    ) -> None:
        """
        Compare AST fingerprints before and after a commit for a single file.

        Detects:
        - New fingerprints (introductions)
        - Missing fingerprints (removals)
        - Persistent fingerprints (survivals)
        """
        after_source = self._git.show_file_at_commit(commit_hash, filepath)
        before_source = self._git.show_file_before_commit(commit_hash, filepath)

        after_fps = extract_fingerprints_from_source(after_source, filepath) if after_source else []
        before_fps = extract_fingerprints_from_source(before_source, filepath) if before_source else []

        after_sigs = {fp.signature for fp in after_fps}
        before_sigs = {fp.signature for fp in before_fps}

        # New patterns introduced in this commit
        for fp in after_fps:
            if fp.signature not in before_sigs:
                self._tracker.record_pattern(fp, commit_hash, commit_date, commit_type)
            else:
                # Pattern survived
                self._tracker.record_pattern(fp, commit_hash, commit_date, commit_type)

        # Patterns removed in this commit
        removed_sigs = before_sigs - after_sigs
        for sig in removed_sigs:
            self._tracker.record_removal(sig, commit_hash, commit_type)
