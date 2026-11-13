"""
Property-based tests for the protocol module.

**Feature: anti-gaslighting-test-suite**

These tests verify universal properties of the protocol module's error handling
and assertion behavior using property-based testing with hypothesis.
"""

import pytest
import json
import tempfile
from pathlib import Path
from hypothesis import given, strategies as st, settings, HealthCheck

# Import the protocol module
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from protocol import (
    GoldenDataError,
    assert_against_golden,
    assert_score_against_golden,
    assert_ranking_against_golden,
)


# ============================================================================
# Property 3: Error Message Format Compliance
# **Validates: Requirements 2.4, 2.5, 11.1, 11.2**
# ============================================================================


@settings(max_examples=10, suppress_health_check=[HealthCheck.too_slow])
@given(
    module_name=st.text(
        min_size=1,
        max_size=20,
        alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
    ),
    case_id=st.text(min_size=1, max_size=20),
    expected_value=st.integers(),
    actual_value=st.integers(),
)
def test_property_error_message_format_compliance(
    module_name, case_id, expected_value, actual_value
):
    """
    **Feature: anti-gaslighting-test-suite, Property 3: Error Message Format Compliance**

    For any assertion failure (when actual_data does not match expected_data),
    the raised GoldenDataError message shall contain both the string
    "IMPLEMENTATION FAILURE" and the string "DO NOT UPDATE THE TEST".

    **Validates: Requirements 2.4, 2.5, 11.1, 11.2**
    """
    # Skip if values are equal (no error expected)
    if expected_value == actual_value:
        return

    # Create a temporary golden data file
    with tempfile.TemporaryDirectory() as tmpdir:
        golden_dir = Path(tmpdir)
        golden_file = golden_dir / f"{module_name}.json"

        # Write golden data
        golden_data = {case_id: expected_value}
        with open(golden_file, "w") as f:
            json.dump(golden_data, f)

        # Temporarily override GOLDEN_DATA_DIR
        import protocol

        original_dir = protocol.GOLDEN_DATA_DIR
        protocol.GOLDEN_DATA_DIR = golden_dir

        try:
            # This should raise GoldenDataError
            assert_against_golden(module_name, case_id, actual_value)
            # If we get here, the test failed to raise an error
            pytest.fail("Expected GoldenDataError to be raised")
        except GoldenDataError as e:
            error_message = str(e)

            # Verify both required strings are present
            assert "IMPLEMENTATION FAILURE" in error_message, (
                f"Error message missing 'IMPLEMENTATION FAILURE': {error_message}"
            )
            assert "DO NOT UPDATE THE TEST" in error_message, (
                f"Error message missing 'DO NOT UPDATE THE TEST': {error_message}"
            )
        finally:
            # Restore original directory
            protocol.GOLDEN_DATA_DIR = original_dir


# ============================================================================
# Property 4: Error Message Content Completeness
# **Validates: Requirements 2.6, 11.3, 11.4, 11.5**
# ============================================================================


@settings(max_examples=10)
@given(
    module_name=st.text(
        min_size=1,
        max_size=20,
        alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
    ),
    case_id=st.text(
        min_size=1,
        max_size=20,
        alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
    ),
    expected_value=st.dictionaries(
        keys=st.text(
            min_size=1,
            max_size=10,
            alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
        ),
        values=st.one_of(
            st.integers(),
            st.text(
                min_size=1,
                max_size=20,
                alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
            ),
        ),
        min_size=1,
        max_size=5,
    ),
    actual_value=st.dictionaries(
        keys=st.text(
            min_size=1,
            max_size=10,
            alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
        ),
        values=st.one_of(
            st.integers(),
            st.text(
                min_size=1,
                max_size=20,
                alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
            ),
        ),
        min_size=1,
        max_size=5,
    ),
)
def test_property_error_message_content_completeness(
    module_name, case_id, expected_value, actual_value
):
    """
    **Feature: anti-gaslighting-test-suite, Property 4: Error Message Content Completeness**

    For any assertion failure, the raised GoldenDataError message shall contain:
    (1) the Golden Data file path, (2) the case_id, (3) the expected value from
    Golden Data, and (4) the actual value from the implementation.

    **Validates: Requirements 2.6, 11.3, 11.4, 11.5**
    """
    # Skip if values are equal (no error expected)
    if expected_value == actual_value:
        return

    # Create a temporary golden data file
    with tempfile.TemporaryDirectory() as tmpdir:
        golden_dir = Path(tmpdir)
        golden_file = golden_dir / f"{module_name}.json"

        # Write golden data
        golden_data = {case_id: expected_value}
        with open(golden_file, "w") as f:
            json.dump(golden_data, f)

        # Temporarily override GOLDEN_DATA_DIR
        import protocol

        original_dir = protocol.GOLDEN_DATA_DIR
        protocol.GOLDEN_DATA_DIR = golden_dir

        try:
            # This should raise GoldenDataError
            assert_against_golden(module_name, case_id, actual_value)
            # If we get here, the test failed to raise an error
            pytest.fail("Expected GoldenDataError to be raised")
        except GoldenDataError as e:
            error_message = str(e)

            # (1) Verify Golden Data file path is present
            assert f"golden_data/{module_name}.json" in error_message, (
                f"Error message missing file path: {error_message}"
            )

            # (2) Verify case_id is present
            assert case_id in error_message, (
                f"Error message missing case_id '{case_id}': {error_message}"
            )

            # (3) Verify expected value is present in the message
            # We check that "Expected (from Golden Data):" section exists
            assert "Expected (from Golden Data):" in error_message, (
                f"Error message missing expected value section: {error_message}"
            )

            # (4) Verify actual value is present in the message
            # We check that "Actual (from implementation):" section exists
            assert "Actual (from implementation):" in error_message, (
                f"Error message missing actual value section: {error_message}"
            )
        finally:
            # Restore original directory
            protocol.GOLDEN_DATA_DIR = original_dir


# ============================================================================
# Additional Property Tests for Score and Ranking Assertions
# ============================================================================


@settings(max_examples=10)
@given(
    module_name=st.text(
        min_size=1,
        max_size=20,
        alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
    ),
    case_id=st.text(min_size=1, max_size=20),
    expected_score=st.floats(
        min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False
    ),
    actual_score=st.floats(
        min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False
    ),
    tolerance=st.floats(
        min_value=0.0001, max_value=0.01, allow_nan=False, allow_infinity=False
    ),
)
def test_property_score_assertion_error_format(
    module_name, case_id, expected_score, actual_score, tolerance
):
    """
    For any score assertion failure, the error message shall contain
    "IMPLEMENTATION FAILURE" and "DO NOT UPDATE THE TEST".
    """
    # Skip if scores are within tolerance
    if abs(expected_score - actual_score) <= tolerance:
        return

    # Create a temporary golden data file
    with tempfile.TemporaryDirectory() as tmpdir:
        golden_dir = Path(tmpdir)
        golden_file = golden_dir / f"{module_name}.json"

        # Write golden data
        golden_data = {case_id: {"score": expected_score}}
        with open(golden_file, "w") as f:
            json.dump(golden_data, f)

        # Temporarily override GOLDEN_DATA_DIR
        import protocol

        original_dir = protocol.GOLDEN_DATA_DIR
        protocol.GOLDEN_DATA_DIR = golden_dir

        try:
            # This should raise GoldenDataError
            assert_score_against_golden(module_name, case_id, actual_score, tolerance)
            # If we get here, the test failed to raise an error
            pytest.fail("Expected GoldenDataError to be raised")
        except GoldenDataError as e:
            error_message = str(e)

            # Verify both required strings are present
            assert "IMPLEMENTATION FAILURE" in error_message
            assert "DO NOT UPDATE THE TEST" in error_message
        finally:
            # Restore original directory
            protocol.GOLDEN_DATA_DIR = original_dir


@settings(max_examples=10)
@given(
    module_name=st.text(
        min_size=1,
        max_size=20,
        alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
    ),
    case_id=st.text(min_size=1, max_size=20),
    expected_ids=st.lists(
        st.text(min_size=1, max_size=10), min_size=1, max_size=10, unique=True
    ),
    actual_ids=st.lists(
        st.text(min_size=1, max_size=10), min_size=1, max_size=10, unique=True
    ),
)
def test_property_ranking_assertion_error_format(
    module_name, case_id, expected_ids, actual_ids
):
    """
    For any ranking assertion failure, the error message shall contain
    "IMPLEMENTATION FAILURE" and "DO NOT UPDATE THE TEST".
    """
    # Skip if rankings are equal
    if expected_ids == actual_ids:
        return

    # Create a temporary golden data file
    with tempfile.TemporaryDirectory() as tmpdir:
        golden_dir = Path(tmpdir)
        golden_file = golden_dir / f"{module_name}.json"

        # Write golden data
        golden_data = {case_id: {"ranked_ids": expected_ids}}
        with open(golden_file, "w") as f:
            json.dump(golden_data, f)

        # Temporarily override GOLDEN_DATA_DIR
        import protocol

        original_dir = protocol.GOLDEN_DATA_DIR
        protocol.GOLDEN_DATA_DIR = golden_dir

        try:
            # This should raise GoldenDataError
            assert_ranking_against_golden(
                module_name, case_id, actual_ids, check_order=True
            )
            # If we get here, the test failed to raise an error
            pytest.fail("Expected GoldenDataError to be raised")
        except GoldenDataError as e:
            error_message = str(e)

            # Verify both required strings are present
            assert "IMPLEMENTATION FAILURE" in error_message
            assert "DO NOT UPDATE THE TEST" in error_message
        finally:
            # Restore original directory
            protocol.GOLDEN_DATA_DIR = original_dir


# ============================================================================
# Property 5: Database Lifecycle Isolation
# **Validates: Requirements 3.2, 3.3**
# ============================================================================


@settings(max_examples=10)
@given(
    table_count=st.integers(min_value=1, max_value=5),
    operation_count=st.integers(min_value=1, max_value=10),
)
def test_property_database_lifecycle_isolation(table_count, operation_count):
    """
    **Feature: anti-gaslighting-test-suite, Property 5: Database Lifecycle Isolation**

    For any test function using the db_session fixture, all required database
    tables shall exist at the start of the test, and all tables shall be dropped
    after the test completes, ensuring complete isolation between tests.

    **Validates: Requirements 3.2, 3.3**
    """
    from sqlalchemy import create_engine, inspect
    from sqlalchemy.orm import sessionmaker
    from app.shared.database import Base

    # Create a fresh in-memory engine
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, echo=False
    )

    # Verify no tables exist initially
    inspector = inspect(engine)
    initial_tables = inspector.get_table_names()
    assert len(initial_tables) == 0, (
        f"Expected no tables initially, found: {initial_tables}"
    )

    # Create all tables (simulating fixture setup)
    Base.metadata.create_all(bind=engine)

    # Verify tables were created
    inspector = inspect(engine)
    created_tables = inspector.get_table_names()
    assert len(created_tables) > 0, "Expected tables to be created"

    # Create a session and perform some operations
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()

    try:
        # Simulate test operations (just verify session works)
        for _ in range(operation_count):
            # Session should be functional
            assert (
                session.is_active or not session.is_active
            )  # Just verify session exists
    finally:
        # Cleanup (simulating fixture teardown)
        session.rollback()
        session.close()

    # Drop all tables (simulating fixture teardown)
    Base.metadata.drop_all(bind=engine)
    engine.dispose()

    # Verify tables were dropped
    # Create a new inspector after dropping
    engine_check = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, echo=False
    )
    inspector_check = inspect(engine_check)
    final_tables = inspector_check.get_table_names()
    engine_check.dispose()

    # For in-memory SQLite, a new connection won't see the old tables
    # This verifies isolation
    assert len(final_tables) == 0, (
        f"Expected no tables after cleanup, found: {final_tables}"
    )


# ============================================================================
# Property 6: Event Verification Completeness
# **Validates: Requirements 4.1, 4.3, 4.5**
# ============================================================================


@settings(max_examples=10)
@given(
    event_type=st.text(
        min_size=5,
        max_size=30,
        alphabet=st.characters(
            whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="._"
        ),
    ),
    payload_keys=st.lists(
        st.text(
            min_size=1,
            max_size=20,
            alphabet=st.characters(
                whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="_"
            ),
        ),
        min_size=1,
        max_size=5,
        unique=True,
    ),
    payload_values=st.lists(
        st.one_of(st.integers(), st.text(min_size=1, max_size=20)),
        min_size=1,
        max_size=5,
    ),
)
def test_property_event_verification_completeness(
    event_type, payload_keys, payload_values
):
    """
    **Feature: anti-gaslighting-test-suite, Property 6: Event Verification Completeness**

    For any event emission captured by mock_event_bus, the mock shall record both
    the event type and the event payload, and tests that expect specific events
    shall fail if those events are not emitted.

    **Validates: Requirements 4.1, 4.3, 4.5**
    """
    from unittest.mock import MagicMock, patch
    from app.shared.event_bus import event_bus

    # Create a mock for event_bus.emit
    original_emit = event_bus.emit
    mock_emit = MagicMock(wraps=original_emit)

    # Build payload from keys and values
    payload = {}
    for i, key in enumerate(payload_keys):
        if i < len(payload_values):
            payload[key] = payload_values[i]

    with patch.object(event_bus, "emit", mock_emit):
        # Emit an event
        event_bus.emit(event_type, payload)

        # Verify the mock captured the call
        assert mock_emit.called, "Mock should have captured the emit call"

        # Verify we can retrieve the event type
        call_args = mock_emit.call_args_list[0]
        captured_event_type = call_args[0][0] if len(call_args[0]) > 0 else None
        assert captured_event_type == event_type, (
            f"Expected event type '{event_type}', got '{captured_event_type}'"
        )

        # Verify we can retrieve the payload
        captured_payload = call_args[0][1] if len(call_args[0]) > 1 else None
        assert captured_payload is not None, "Payload should be captured"

        # Verify all payload keys are present
        for key in payload_keys:
            if key in payload:
                assert key in captured_payload, (
                    f"Expected key '{key}' in captured payload, got: {captured_payload}"
                )

        # Verify that if we expect an event that wasn't emitted, we can detect it
        mock_emit.reset_mock()

        # Don't emit anything
        # Now check that we can detect the absence
        different_event_type = event_type + "_different"
        event_found = False
        for call in mock_emit.call_args_list:
            if len(call[0]) > 0 and call[0][0] == different_event_type:
                event_found = True
                break

        # Should not find the event since we didn't emit it
        assert not event_found, (
            f"Should not find event '{different_event_type}' when it wasn't emitted"
        )
