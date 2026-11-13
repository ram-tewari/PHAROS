"""
Anti-Gaslighting Protocol Module

Provides assertion helpers that enforce the Golden Data pattern.
All test expectations are loaded from immutable JSON files.
"""

from pathlib import Path
from typing import Any, Dict
import json


GOLDEN_DATA_DIR = Path(__file__).parent / "golden_data"


class GoldenDataError(AssertionError):
    """Raised when actual data does not match Golden Data expectations."""

    pass


def load_golden_data(module: str) -> Dict[str, Any]:
    """
    Load Golden Data JSON file for a module.

    Args:
        module: Module name (e.g., "quality_scoring", "search_ranking")

    Returns:
        Dictionary containing all test cases for the module

    Raises:
        FileNotFoundError: If Golden Data file does not exist
    """
    file_path = GOLDEN_DATA_DIR / f"{module}.json"
    if not file_path.exists():
        raise FileNotFoundError(
            f"Golden Data file not found: {file_path}\n"
            f"Create the file with expected test values."
        )

    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def assert_against_golden(module: str, case_id: str, actual_data: Any) -> None:
    """
    Assert actual data matches Golden Data expectations.

    This is the core anti-gaslighting assertion. It loads expected values
    from an immutable JSON file and compares against actual implementation output.

    Args:
        module: Module name (e.g., "quality_scoring")
        case_id: Test case identifier within the module
        actual_data: Actual data from implementation to verify

    Raises:
        GoldenDataError: If actual data does not match expected data
    """
    golden_data = load_golden_data(module)

    if case_id not in golden_data:
        raise GoldenDataError(
            f"IMPLEMENTATION FAILURE: Test case '{case_id}' not found in Golden Data.\n"
            f"DO NOT UPDATE THE TEST - Add the test case to golden_data/{module}.json\n"
            f"Available cases: {list(golden_data.keys())}"
        )

    expected_data = golden_data[case_id]

    if actual_data != expected_data:
        raise GoldenDataError(
            f"IMPLEMENTATION FAILURE: Actual data does not match Golden Data.\n"
            f"DO NOT UPDATE THE TEST - Fix the implementation instead.\n"
            f"\n"
            f"Golden Data File: golden_data/{module}.json\n"
            f"Test Case ID: {case_id}\n"
            f"\n"
            f"Expected (from Golden Data):\n{json.dumps(expected_data, indent=2)}\n"
            f"\n"
            f"Actual (from implementation):\n{json.dumps(actual_data, indent=2)}\n"
        )


def assert_score_against_golden(
    module: str, case_id: str, actual_score: float, tolerance: float = 0.001
) -> None:
    """
    Assert a numeric score matches Golden Data with tolerance.

    Args:
        module: Module name
        case_id: Test case identifier
        actual_score: Actual score from implementation
        tolerance: Acceptable difference (default: 0.001)

    Raises:
        GoldenDataError: If score differs by more than tolerance
    """
    golden_data = load_golden_data(module)

    if case_id not in golden_data:
        raise GoldenDataError(
            f"IMPLEMENTATION FAILURE: Test case '{case_id}' not found.\n"
            f"DO NOT UPDATE THE TEST - Add case to golden_data/{module}.json"
        )

    expected = golden_data[case_id]
    expected_score = expected.get("score") if isinstance(expected, dict) else expected

    if abs(actual_score - expected_score) > tolerance:
        raise GoldenDataError(
            f"IMPLEMENTATION FAILURE: Score mismatch.\n"
            f"DO NOT UPDATE THE TEST - Fix the implementation instead.\n"
            f"\n"
            f"Golden Data File: golden_data/{module}.json\n"
            f"Test Case ID: {case_id}\n"
            f"\n"
            f"Expected score: {expected_score}\n"
            f"Actual score: {actual_score}\n"
            f"Difference: {abs(actual_score - expected_score)} (tolerance: {tolerance})"
        )


def assert_ranking_against_golden(
    module: str, case_id: str, actual_ids: list, check_order: bool = True
) -> None:
    """
    Assert a ranking matches Golden Data expectations.

    Args:
        module: Module name
        case_id: Test case identifier
        actual_ids: Actual ranked IDs from implementation
        check_order: Whether order matters (True) or just membership (False)

    Raises:
        GoldenDataError: If ranking does not match
    """
    golden_data = load_golden_data(module)

    if case_id not in golden_data:
        raise GoldenDataError(
            f"IMPLEMENTATION FAILURE: Test case '{case_id}' not found.\n"
            f"DO NOT UPDATE THE TEST - Add case to golden_data/{module}.json"
        )

    expected = golden_data[case_id]
    expected_ids = expected.get("ranked_ids", expected)

    if check_order:
        if actual_ids != expected_ids:
            raise GoldenDataError(
                f"IMPLEMENTATION FAILURE: Ranking order mismatch.\n"
                f"DO NOT UPDATE THE TEST - Fix the implementation instead.\n"
                f"\n"
                f"Golden Data File: golden_data/{module}.json\n"
                f"Test Case ID: {case_id}\n"
                f"\n"
                f"Expected order: {expected_ids}\n"
                f"Actual order: {actual_ids}"
            )
    else:
        if set(actual_ids) != set(expected_ids):
            raise GoldenDataError(
                f"IMPLEMENTATION FAILURE: Ranking membership mismatch.\n"
                f"DO NOT UPDATE THE TEST - Fix the implementation instead.\n"
                f"\n"
                f"Expected IDs: {set(expected_ids)}\n"
                f"Actual IDs: {set(actual_ids)}"
            )
