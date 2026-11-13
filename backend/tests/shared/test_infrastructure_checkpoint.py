"""
Checkpoint test to verify infrastructure components.

This test file verifies that all infrastructure created in Tasks 1-3 works correctly.
"""

import pytest
import json
import re
from pathlib import Path


def test_performance_decorator_import():
    """Verify performance decorator can be imported."""
    from tests.performance import performance_limit, PerformanceRegressionError

    assert callable(performance_limit)
    assert issubclass(PerformanceRegressionError, AssertionError)


def test_mock_ml_inference_fixture(mock_ml_inference):
    """Verify mock_ml_inference fixture loads without errors."""
    assert mock_ml_inference is not None
    assert "sentence_transformer" in mock_ml_inference
    assert "pipeline" in mock_ml_inference

    # Verify mocks are callable
    assert callable(mock_ml_inference["sentence_transformer"].encode)
    assert callable(mock_ml_inference["pipeline"])


def test_factory_fixtures_exist(create_test_annotation, mock_embedding_service):
    """Verify the factory fixtures are available."""
    assert callable(create_test_annotation)
    assert mock_embedding_service is not None


def test_factory_create_annotation(db_session, create_test_annotation):
    """Verify create_test_annotation fixture creates test data correctly."""
    annotation = create_test_annotation(highlighted_text="Test text")

    assert annotation.id is not None
    assert annotation.highlighted_text == "Test text"
    assert annotation.resource_id is not None


def test_golden_data_files_valid_json():
    """Every golden file a test loads exists, and every golden file is a non-empty JSON object."""
    tests_dir = Path(__file__).parent.parent
    golden_data_dir = tests_dir / "golden_data"

    referenced = set()
    for test_file in tests_dir.rglob("*.py"):
        referenced |= set(re.findall(r"load_golden_data\(\s*[\"']([a-z_]+)[\"']", test_file.read_text(errors="ignore")))
    assert referenced, "expected some tests to use golden data"
    missing = sorted(name for name in referenced if not (golden_data_dir / f"{name}.json").exists())
    assert not missing, f"Golden data files missing: {missing}"

    for filepath in sorted(golden_data_dir.glob("*.json")):
        data = json.loads(filepath.read_text())
        assert isinstance(data, dict) and data, f"{filepath.name} should be a non-empty JSON object"


def test_performance_decorator_works(monkeypatch):
    """Verify performance decorator enforces time limits."""
    # Pin PERF_SCALE so assertions are deterministic regardless of env overrides.
    monkeypatch.setenv("PERF_SCALE", "1")

    from tests.performance import performance_limit, PerformanceRegressionError
    import time

    # Test that fast function passes
    @performance_limit(max_ms=1000)
    def fast_function():
        time.sleep(0.01)  # 10ms
        return "success"

    result = fast_function()
    assert result == "success"

    # Test that slow function raises error
    @performance_limit(max_ms=10)
    def slow_function():
        time.sleep(0.05)  # 50ms
        return "should not reach here"

    with pytest.raises(PerformanceRegressionError) as exc_info:
        slow_function()

    error_message = str(exc_info.value)
    assert "slow_function" in error_message
