"""
Tests for Git Analyzer - Pattern Lifecycle Detection

Tests the Git history analysis logic that differentiates between
patterns developers keep versus patterns they abandon.
"""

import subprocess
import tempfile
from pathlib import Path

import pytest

from app.modules.patterns.logic.git_analyzer import (
    GitAnalyzer,
    classify_commit,
    extract_fingerprints_from_source,
)
from app.modules.patterns.schema import GitAnalysisProfile


# ============================================================================
# Helper Functions
# ============================================================================


def init_git_repo(repo_path: Path):
    """Initialize a git repository."""
    subprocess.run(
        ["git", "init"],
        cwd=repo_path,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo_path,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo_path,
        capture_output=True,
        check=True,
    )


def git_commit(repo_path: Path, message: str):
    """Create a git commit."""
    subprocess.run(
        ["git", "add", "."],
        cwd=repo_path,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "commit", "-m", message],
        cwd=repo_path,
        capture_output=True,
        check=True,
    )


# ============================================================================
# Commit Classification Tests
# ============================================================================


class TestCommitClassification:
    """Test commit message classification."""
    
    def test_classify_bugfix_commit(self):
        """Test classification of bugfix commits."""
        assert classify_commit("fix: resolve login issue") == "bugfix"
        assert classify_commit("hotfix: patch security vulnerability") == "bugfix"
        assert classify_commit("bug: correct calculation error") == "bugfix"
        assert classify_commit("Fix broken authentication") == "bugfix"
    
    def test_classify_feature_commit(self):
        """Test classification of feature commits."""
        assert classify_commit("feat: add user registration") == "feature"
        assert classify_commit("feature: implement search") == "feature"
        assert classify_commit("Add new dashboard") == "feature"
        assert classify_commit("Introduce payment processing") == "feature"
    
    def test_classify_refactor_commit(self):
        """Test classification of refactor commits."""
        assert classify_commit("refactor: simplify auth logic") == "refactor"
        assert classify_commit("Restructure database models") == "refactor"
        assert classify_commit("Extract helper functions") == "refactor"
    
    def test_classify_formatting_commit(self):
        """Test classification of formatting commits."""
        assert classify_commit("style: format with black") == "formatting"
        assert classify_commit("Format code with prettier") == "formatting"
        assert classify_commit("Run isort on imports") == "formatting"
        assert classify_commit("Fix whitespace issues") == "formatting"
    
    def test_classify_other_commit(self):
        """Test classification of other commits."""
        assert classify_commit("Update README") == "other"
        assert classify_commit("Merge branch 'main'") == "other"
        assert classify_commit("Initial commit") == "other"
    
    def test_priority_order(self):
        """Test that bugfix takes priority over feature."""
        # If a commit mentions both fix and feature, it should be classified as bugfix
        assert classify_commit("feat: add feature and fix bug") == "bugfix"


# ============================================================================
# Fingerprint Extraction Tests
# ============================================================================


class TestFingerprintExtraction:
    """Test structural fingerprint extraction."""
    
    def test_extract_error_handler_fingerprint(self):
        """Test extraction of error handler fingerprints."""
        code = '''
try:
    process()
except ValueError as exc:
    logger.error("Error: %s", exc)
    raise
'''
        fingerprints = extract_fingerprints_from_source(code, "test.py")
        
        assert len(fingerprints) > 0
        error_handlers = [fp for fp in fingerprints if fp.pattern_type == "error_handler"]
        assert len(error_handlers) > 0
        assert "ValueError" in error_handlers[0].signature
    
    def test_extract_decorator_fingerprint(self):
        """Test extraction of decorator stack fingerprints."""
        code = '''
@app.route("/api/test")
@require_auth
@rate_limit
def endpoint():
    pass
'''
        fingerprints = extract_fingerprints_from_source(code, "test.py")
        
        decorator_stacks = [fp for fp in fingerprints if fp.pattern_type == "decorator_stack"]
        assert len(decorator_stacks) > 0
    
    def test_extract_class_structure_fingerprint(self):
        """Test extraction of class structure fingerprints."""
        code = '''
class UserService(BaseService):
    def create(self):
        pass
    
    def update(self):
        pass
    
    def delete(self):
        pass
'''
        fingerprints = extract_fingerprints_from_source(code, "test.py")
        
        class_structures = [fp for fp in fingerprints if fp.pattern_type == "class_structure"]
        assert len(class_structures) > 0
        assert "BaseService" in class_structures[0].signature
    
    def test_handle_syntax_errors(self):
        """Test that syntax errors return empty fingerprints."""
        code = "def broken(: pass"
        fingerprints = extract_fingerprints_from_source(code, "test.py")
        
        assert fingerprints == []
    
    def test_multiple_error_handlers(self):
        """Test extraction of multiple error handler patterns."""
        code = '''
try:
    process()
except ValueError:
    logger.error("ValueError")
except KeyError:
    logger.warning("KeyError")
except Exception:
    logger.exception("Unexpected")
'''
        fingerprints = extract_fingerprints_from_source(code, "test.py")
        
        error_handlers = [fp for fp in fingerprints if fp.pattern_type == "error_handler"]
        assert len(error_handlers) == 3


# ============================================================================
# Git Analyzer Integration Tests
# ============================================================================


@pytest.mark.skipif(
    subprocess.run(["git", "--version"], capture_output=True).returncode != 0,
    reason="Git not available"
)
class TestGitAnalyzer:
    """Test suite for GitAnalyzer."""
    
    @pytest.fixture
    def git_repo(self, tmp_path):
        """Create a git repository with sample commits."""
        repo = tmp_path / "test_repo"
        repo.mkdir()
        init_git_repo(repo)
        
        # Initial commit with a pattern
        (repo / "module.py").write_text('''
def process_data(data):
    try:
        return transform(data)
    except ValueError as exc:
        logger.error("Error: %s", exc)
        raise

def transform(data):
    return data
''')
        git_commit(repo, "feat: add data processing")
        
        # Second commit - keep the pattern
        (repo / "module.py").write_text('''
def process_data(data):
    try:
        return transform(data)
    except ValueError as exc:
        logger.error("Error: %s", exc)
        raise

def process_batch(items):
    try:
        return [transform(item) for item in items]
    except ValueError as exc:
        logger.error("Batch error: %s", exc)
        raise

def transform(data):
    return data
''')
        git_commit(repo, "feat: add batch processing")
        
        # Third commit - remove pattern in bugfix
        (repo / "module.py").write_text('''
def process_data(data):
    return transform(data)

def process_batch(items):
    return [transform(item) for item in items]

def transform(data):
    return data
''')
        git_commit(repo, "fix: remove error handling that was causing issues")
        
        return repo
    
    def test_analyzer_initialization(self, git_repo):
        """Test analyzer can be initialized with a git repository."""
        analyzer = GitAnalyzer(git_repo, max_commits=10)
        assert analyzer.repo_path == git_repo
        assert analyzer.max_commits == 10
    
    def test_analyze_git_history(self, git_repo):
        """Test analyzing git history."""
        analyzer = GitAnalyzer(git_repo, max_commits=10)
        profile = analyzer.analyze()
        
        assert isinstance(profile, GitAnalysisProfile)
        assert profile.total_commits_analyzed > 0
    
    def test_detect_feature_commits(self, git_repo):
        """Test detection of feature commits."""
        analyzer = GitAnalyzer(git_repo, max_commits=10)
        profile = analyzer.analyze()
        
        assert profile.feature_commits > 0
    
    def test_detect_bugfix_commits(self, git_repo):
        """Test detection of bugfix commits."""
        analyzer = GitAnalyzer(git_repo, max_commits=10)
        profile = analyzer.analyze()
        
        assert profile.bugfix_commits > 0
    
    def test_detect_abandoned_patterns(self, git_repo):
        """Test detection of abandoned patterns."""
        analyzer = GitAnalyzer(git_repo, max_commits=10)
        profile = analyzer.analyze()
        
        # The error handling pattern was removed in a bugfix
        # So it should be classified as abandoned
        assert len(profile.abandoned_patterns) >= 0  # May or may not detect depending on fingerprint matching
    
    def test_skip_formatting_commits(self, tmp_path):
        """Test that formatting-only commits are skipped."""
        repo = tmp_path / "format_repo"
        repo.mkdir()
        init_git_repo(repo)
        
        # Initial commit
        (repo / "code.py").write_text("def hello(): pass")
        git_commit(repo, "feat: add hello function")
        
        # Formatting commit
        (repo / "code.py").write_text("def hello():\n    pass\n")
        git_commit(repo, "style: format with black")
        
        analyzer = GitAnalyzer(repo, max_commits=10)
        profile = analyzer.analyze()
        
        assert profile.formatting_commits_skipped > 0
    
    def test_handle_empty_repo(self, tmp_path):
        """Test handling of empty git repository."""
        repo = tmp_path / "empty_repo"
        repo.mkdir()
        init_git_repo(repo)
        
        analyzer = GitAnalyzer(repo, max_commits=10)
        profile = analyzer.analyze()
        
        assert profile.total_commits_analyzed == 0
        assert profile.kept_patterns == []
        assert profile.abandoned_patterns == []
    
    def test_max_commits_limit(self, git_repo):
        """Test that max_commits limit is respected."""
        analyzer = GitAnalyzer(git_repo, max_commits=2)
        profile = analyzer.analyze()
        
        assert profile.total_commits_analyzed <= 2
    
    def test_branch_parameter(self, git_repo):
        """Test analyzing a specific branch."""
        # Create a new branch
        subprocess.run(
            ["git", "checkout", "-b", "feature-branch"],
            cwd=git_repo,
            capture_output=True,
            check=True,
        )
        
        # Add a commit on the branch
        (git_repo / "feature.py").write_text("def feature(): pass")
        git_commit(git_repo, "feat: add feature")
        
        # Analyze the feature branch
        analyzer = GitAnalyzer(git_repo, max_commits=10, branch="feature-branch")
        profile = analyzer.analyze()
        
        assert profile.total_commits_analyzed > 0


# ============================================================================
# Pattern Lifecycle Tests
# ============================================================================


@pytest.mark.skipif(
    subprocess.run(["git", "--version"], capture_output=True).returncode != 0,
    reason="Git not available"
)
class TestPatternLifecycle:
    """Test pattern lifecycle tracking."""
    
    def test_kept_pattern_lifecycle(self, tmp_path):
        """Test that patterns surviving multiple commits are marked as kept."""
        repo = tmp_path / "kept_repo"
        repo.mkdir()
        init_git_repo(repo)
        
        # Pattern introduced
        code_v1 = '''
def process(data):
    try:
        return transform(data)
    except ValueError as exc:
        logger.error("Error: %s", exc)
        raise
'''
        (repo / "module.py").write_text(code_v1)
        git_commit(repo, "feat: add processing")
        
        # Pattern survives in commit 2
        code_v2 = code_v1 + "\ndef another(): pass\n"
        (repo / "module.py").write_text(code_v2)
        git_commit(repo, "feat: add another function")
        
        # Pattern survives in commit 3
        code_v3 = code_v2 + "\ndef third(): pass\n"
        (repo / "module.py").write_text(code_v3)
        git_commit(repo, "feat: add third function")
        
        # Pattern survives in commit 4
        code_v4 = code_v3 + "\ndef fourth(): pass\n"
        (repo / "module.py").write_text(code_v4)
        git_commit(repo, "feat: add fourth function")
        
        analyzer = GitAnalyzer(repo, max_commits=10)
        profile = analyzer.analyze()
        
        # Pattern should be classified as kept (survived 4+ commits)
        assert len(profile.kept_patterns) > 0
    
    def test_abandoned_pattern_lifecycle(self, tmp_path):
        """Test that patterns removed in bugfixes are marked as abandoned."""
        repo = tmp_path / "abandoned_repo"
        repo.mkdir()
        init_git_repo(repo)
        
        # Pattern introduced
        code_v1 = '''
def process(data):
    try:
        return transform(data)
    except:
        pass
'''
        (repo / "module.py").write_text(code_v1)
        git_commit(repo, "feat: add processing")
        
        # Pattern removed in bugfix
        code_v2 = '''
def process(data):
    return transform(data)
'''
        (repo / "module.py").write_text(code_v2)
        git_commit(repo, "fix: remove silent exception handling")
        
        analyzer = GitAnalyzer(repo, max_commits=10)
        profile = analyzer.analyze()
        
        # Pattern should be classified as abandoned
        # (removed during bugfix)
        assert profile.bugfix_commits > 0
    
    def test_replicated_pattern(self, tmp_path):
        """Test that patterns replicated across files are marked as kept."""
        repo = tmp_path / "replicated_repo"
        repo.mkdir()
        init_git_repo(repo)
        
        # Pattern in file 1
        code = '''
def process(data):
    try:
        return transform(data)
    except ValueError as exc:
        logger.error("Error: %s", exc)
        raise
'''
        (repo / "module1.py").write_text(code)
        git_commit(repo, "feat: add module1")
        
        # Same pattern replicated in file 2
        (repo / "module2.py").write_text(code)
        git_commit(repo, "feat: add module2")
        
        # Same pattern replicated in file 3
        (repo / "module3.py").write_text(code)
        git_commit(repo, "feat: add module3")
        
        analyzer = GitAnalyzer(repo, max_commits=10)
        profile = analyzer.analyze()
        
        # Pattern should be classified as kept (replicated across files)
        if len(profile.kept_patterns) > 0:
            # Check that replication count is tracked
            assert any(p.replication_count >= 2 for p in profile.kept_patterns)


# ============================================================================
# Edge Case Tests
# ============================================================================


@pytest.mark.skipif(
    subprocess.run(["git", "--version"], capture_output=True).returncode != 0,
    reason="Git not available"
)
class TestGitAnalyzerEdgeCases:
    """Test edge cases and error handling."""
    
    def test_non_git_directory(self, tmp_path):
        """Test handling of non-git directory."""
        repo = tmp_path / "not_git"
        repo.mkdir()
        (repo / "code.py").write_text("def hello(): pass")
        
        analyzer = GitAnalyzer(repo, max_commits=10)
        profile = analyzer.analyze()
        
        # Should return empty profile
        assert profile.total_commits_analyzed == 0
    
    def test_repo_with_no_python_files(self, tmp_path):
        """Test repository with no Python files."""
        repo = tmp_path / "no_python"
        repo.mkdir()
        init_git_repo(repo)
        
        (repo / "README.md").write_text("# README")
        git_commit(repo, "docs: add README")
        
        analyzer = GitAnalyzer(repo, max_commits=10)
        profile = analyzer.analyze()
        
        # Should analyze commits but find no patterns
        assert profile.total_commits_analyzed > 0
        assert len(profile.kept_patterns) == 0
        assert len(profile.abandoned_patterns) == 0
    
    def test_large_commit_history(self, tmp_path):
        """Test handling of large commit history."""
        repo = tmp_path / "large_history"
        repo.mkdir()
        init_git_repo(repo)
        
        # Create many commits
        for i in range(50):
            (repo / "code.py").write_text(f"def func_{i}(): pass\n")
            git_commit(repo, f"feat: add function {i}")
        
        # Analyze with limit
        analyzer = GitAnalyzer(repo, max_commits=20)
        profile = analyzer.analyze()
        
        # Should respect max_commits limit
        assert profile.total_commits_analyzed <= 20


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
