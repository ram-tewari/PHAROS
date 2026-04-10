"""
Checkpoint test to verify infrastructure components.

This test file verifies that all infrastructure created in Tasks 1-3 works correctly.
"""

import pytest
import json
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


def test_factory_fixtures_exist(
    create_test_category,
    create_test_collection,
    create_test_annotation,
    mock_embedding_service,
):
    """Verify all factory fixtures are available."""
    assert callable(create_test_category)
    assert callable(create_test_collection)
    assert callable(create_test_annotation)
    assert mock_embedding_service is not None


def test_factory_create_category(db_session, create_test_category):
    """Verify create_test_category fixture creates test data correctly."""
    category = create_test_category(name="Test Category")

    assert category.id is not None
    assert category.name == "Test Category"
    assert category.slug == "test-category"


def test_factory_create_collection(db_session, create_test_collection):
    """Verify create_test_collection fixture creates test data correctly."""
    collection = create_test_collection(name="Test Collection")

    assert collection.id is not None
    assert collection.name == "Test Collection"
    assert collection.owner_id == "test_user"


def test_factory_create_annotation(db_session, create_test_annotation):
    """Verify create_test_annotation fixture creates test data correctly."""
    annotation = create_test_annotation(highlighted_text="Test text")

    assert annotation.id is not None
    assert annotation.highlighted_text == "Test text"
    assert annotation.resource_id is not None


def test_golden_data_files_valid_json():
    """Verify all golden data files are valid JSON."""
    # Golden data lives under tests/golden_data (shared across modules).
    golden_data_dir = Path(__file__).parent.parent / "golden_data"

    expected_files = [
        "taxonomy_prediction.json",
        "graph_algorithms.json",
        "scholarly_parsing.json",
        "collections_logic.json",
        "recommendations_ranking.json",
        "annotations_search.json",
        "authority_tree.json",
    ]

    for filename in expected_files:
        filepath = golden_data_dir / filename
        assert filepath.exists(), f"Golden data file missing: {filename}"

        # Verify it's valid JSON
        with open(filepath, "r") as f:
            data = json.load(f)
            assert isinstance(data, dict), (
                f"Golden data file {filename} should contain a dict"
            )
            assert len(data) > 0, f"Golden data file {filename} should not be empty"


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
