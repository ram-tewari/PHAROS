"""
Resource Ingestion Integration Tests

Tests the complete resource ingestion workflow including:
- HTTP API endpoint behavior
- Database state verification
- Event emission verification

All assertions use Golden Data from resource_ingestion.json.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from unittest.mock import AsyncMock, MagicMock

from backend.tests.protocol import load_golden_data


@pytest.fixture(autouse=True)
def fake_queue(monkeypatch):
    """The suite runs in CLOUD mode, where ingestion is handed to the edge
    worker through a Redis queue. Stand in for the queue so these tests check
    the API/database flow without a live Redis."""
    from app.services.queue_service import QueueService

    monkeypatch.setattr(QueueService, "__init__", lambda self: None)
    submit = AsyncMock(return_value="job-1")
    monkeypatch.setattr(QueueService, "submit_job", submit)
    return submit


def test_create_resource_queue_unavailable_is_503_and_marks_failed(
    client: TestClient, db_session: Session, monkeypatch
):
    """No queue configured: honest 503 (not a 500), and the row is not left pending."""
    from app.database.models import Resource
    from app.services.queue_service import QueueService

    def not_configured(self):
        raise ValueError("Queue service not configured: REDIS_URL must be set in CLOUD mode")

    monkeypatch.setattr(QueueService, "__init__", not_configured)
    response = client.post("/api/resources", json={"url": "https://example.org/no-queue", "title": "No queue"})

    assert response.status_code == 503
    row = db_session.query(Resource).filter(Resource.title == "No queue").one()
    db_session.refresh(row)
    assert row.ingestion_status == "failed" and "REDIS_URL" in row.ingestion_error


def test_create_resource_success(
    client: TestClient, db_session: Session, mock_event_bus: MagicMock
):
    """
    Test successful resource creation via API.

    Verifies:
    - HTTP 202 response
    - Response contains expected fields
    - Database row created with correct status
    - resource.created event emitted

    Uses Golden Data: resource_ingestion.json -> create_resource_success
    """
    # Load Golden Data
    golden_data = load_golden_data("resource_ingestion")
    test_case = golden_data["create_resource_success"]

    # Make API request
    response = client.post("/api/resources", json=test_case["request"])

    # Verify HTTP response status
    expected_status = test_case["expected_response"]["status_code"]
    assert response.status_code == expected_status, (
        f"IMPLEMENTATION FAILURE: Expected status {expected_status}, got {response.status_code}\n"
        f"DO NOT UPDATE THE TEST - Fix the implementation instead."
    )

    # Verify response body contains expected fields
    response_data = response.json()
    expected_fields = test_case["expected_response"]["body_contains"]
    for field in expected_fields:
        assert field in response_data, (
            f"IMPLEMENTATION FAILURE: Expected field '{field}' in response\n"
            f"DO NOT UPDATE THE TEST - Fix the implementation instead.\n"
            f"Response: {response_data}"
        )

    # Verify database state
    from app.database.models import Resource

    resource_id = response_data["id"]
    db_resource = db_session.query(Resource).filter(Resource.id == resource_id).first()

    assert db_resource is not None, (
        "IMPLEMENTATION FAILURE: Resource not found in database\n"
        "DO NOT UPDATE THE TEST - Fix the implementation instead."
    )

    expected_db_state = test_case["expected_db_state"]
    assert db_resource.ingestion_status == expected_db_state["ingestion_status"], (
        f"IMPLEMENTATION FAILURE: Expected ingestion_status '{expected_db_state['ingestion_status']}', "
        f"got '{db_resource.ingestion_status}'\n"
        f"DO NOT UPDATE THE TEST - Fix the implementation instead."
    )

    assert db_resource.title == expected_db_state["title"], (
        f"IMPLEMENTATION FAILURE: Expected title '{expected_db_state['title']}', "
        f"got '{db_resource.title}'\n"
        f"DO NOT UPDATE THE TEST - Fix the implementation instead."
    )

    # Verify event emission
    expected_events = test_case["expected_events"]
    assert len(expected_events) > 0, "Test case should expect at least one event"

    # Check that event_bus.emit was called
    assert mock_event_bus.called, (
        "IMPLEMENTATION FAILURE: Expected event_bus.emit to be called\n"
        "DO NOT UPDATE THE TEST - Fix the implementation instead."
    )

    # Verify the event type and payload
    expected_event = expected_events[0]
    event_type = expected_event["event_type"]
    payload_fields = expected_event["payload_contains"]

    # Find the call with the expected event type
    event_found = False
    for call in mock_event_bus.call_args_list:
        if len(call[0]) > 0 and call[0][0] == event_type:
            event_found = True
            # Verify payload contains expected fields
            if len(call[0]) > 1:
                payload = call[0][1]
                for field in payload_fields:
                    assert field in payload, (
                        f"IMPLEMENTATION FAILURE: Expected field '{field}' in event payload\n"
                        f"DO NOT UPDATE THE TEST - Fix the implementation instead.\n"
                        f"Event type: {event_type}\n"
                        f"Payload: {payload}"
                    )
            break

    assert event_found, (
        f"IMPLEMENTATION FAILURE: Expected event '{event_type}' not emitted\n"
        f"DO NOT UPDATE THE TEST - Fix the implementation instead.\n"
        f"Calls: {mock_event_bus.call_args_list}"
    )


def test_create_resource_missing_url(client: TestClient, mock_event_bus: MagicMock):
    """
    Test resource creation fails without URL.

    Verifies:
    - HTTP 422 validation error
    - No events emitted

    Uses Golden Data: resource_ingestion.json -> create_resource_missing_url
    """
    # Load Golden Data
    golden_data = load_golden_data("resource_ingestion")
    test_case = golden_data["create_resource_missing_url"]

    # Make API request
    response = client.post("/api/resources", json=test_case["request"])

    # Verify HTTP response status
    expected_status = test_case["expected_response"]["status_code"]
    assert response.status_code == expected_status, (
        f"IMPLEMENTATION FAILURE: Expected status {expected_status}, got {response.status_code}\n"
        f"DO NOT UPDATE THE TEST - Fix the implementation instead."
    )

    # Verify no events emitted
    expected_events = test_case["expected_events"]
    if len(expected_events) == 0:
        # Should not have called emit for resource.created
        resource_created_calls = [
            call
            for call in mock_event_bus.call_args_list
            if len(call[0]) > 0 and call[0][0] == "resource.created"
        ]
        assert len(resource_created_calls) == 0, (
            f"IMPLEMENTATION FAILURE: Expected no 'resource.created' events, but found {len(resource_created_calls)}\n"
            f"DO NOT UPDATE THE TEST - Fix the implementation instead."
        )


def test_create_resource_duplicate_url(
    client: TestClient,
    db_session: Session,
    create_test_resource,
    mock_event_bus: MagicMock,
):
    """
    Test duplicate URL returns existing resource.

    Verifies:
    - HTTP 200 response (existing resource)
    - Database state indicates existing resource
    - No new events emitted

    Uses Golden Data: resource_ingestion.json -> create_resource_duplicate_url
    """
    # Load Golden Data
    golden_data = load_golden_data("resource_ingestion")
    test_case = golden_data["create_resource_duplicate_url"]

    # Create existing resource first
    existing_url = test_case["request"]["url"]
    existing_resource = create_test_resource(
        source=existing_url, title="Existing Resource", ingestion_status="completed"
    )

    # Clear mock to track only new calls
    mock_event_bus.reset_mock()

    # Make API request with duplicate URL
    response = client.post("/api/resources", json=test_case["request"])

    # Verify HTTP response status
    expected_status = test_case["expected_response"]["status_code"]
    assert response.status_code == expected_status, (
        f"IMPLEMENTATION FAILURE: Expected status {expected_status}, got {response.status_code}\n"
        f"DO NOT UPDATE THE TEST - Fix the implementation instead."
    )

    # Verify response indicates existing resource
    response_data = response.json()
    returned_id = response_data.get("id")

    # The returned resource should be the existing one
    assert str(existing_resource.id) == returned_id, (
        f"IMPLEMENTATION FAILURE: Expected existing resource ID {existing_resource.id}, got {returned_id}\n"
        f"DO NOT UPDATE THE TEST - Fix the implementation instead."
    )

    # Verify no new events emitted (since it's an existing resource)
    expected_events = test_case["expected_events"]
    if len(expected_events) == 0:
        # Should not have called emit for resource.created
        resource_created_calls = [
            call
            for call in mock_event_bus.call_args_list
            if len(call[0]) > 0 and call[0][0] == "resource.created"
        ]
        assert len(resource_created_calls) == 0, (
            f"IMPLEMENTATION FAILURE: Expected no 'resource.created' events for duplicate, but found {len(resource_created_calls)}\n"
            f"DO NOT UPDATE THE TEST - Fix the implementation instead."
        )
