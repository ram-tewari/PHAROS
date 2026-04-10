"""
Property-Based Tests for Planning Module

Feature: phase20-frontend-backend-infrastructure
Tests properties 21-23 for multi-hop planning agent and architecture parser.
"""

import pytest
import time
from hypothesis import given, strategies as st, settings, HealthCheck
from sqlalchemy.orm import Session

from backend.app.modules.planning.service import MultiHopAgent, ArchitectureParser
from backend.app.modules.planning.schema import GeneratePlanRequest


def has_cycle(dependencies):
    """
    Check if a dependency graph has cycles using DFS.

    Args:
        dependencies: List of (step_id, depends_on_step_id) tuples

    Returns:
        bool: True if cycle exists, False otherwise
    """
    if not dependencies:
        return False

    # Build adjacency list
    graph = {}
    for step_id, depends_on in dependencies:
        if step_id not in graph:
            graph[step_id] = []
        graph[step_id].append(depends_on)

    # Track visited nodes and recursion stack
    visited = set()
    rec_stack = set()

    def dfs(node):
        visited.add(node)
        rec_stack.add(node)

        if node in graph:
            for neighbor in graph[node]:
                if neighbor not in visited:
                    if dfs(neighbor):
                        return True
                elif neighbor in rec_stack:
                    return True

        rec_stack.remove(node)
        return False

    # Check all nodes
    for node in graph:
        if node not in visited:
            if dfs(node):
                return True

    return False


@pytest.mark.asyncio
@given(
    task_description=st.text(min_size=10, max_size=200),
    context_keys=st.lists(st.text(min_size=1, max_size=20), min_size=0, max_size=5),
)
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
async def test_dependency_dag_validity(
    task_description, context_keys, db_session: Session
):
    """
    Feature: phase20-frontend-backend-infrastructure
    Property 21: Dependency DAG validity

    For any generated plan, the task dependencies should form a valid
    directed acyclic graph (no cycles).

    Validates: Requirements 7.3
    """
    # Build context from keys
    context = {key: f"value_{key}" for key in context_keys}

    # Generate plan
    agent = MultiHopAgent(db=db_session)
    result = await agent.generate_plan(
        task_description=task_description, context=context
    )

    # Verify dependencies form a DAG (no cycles)
    assert not has_cycle(result.dependencies), (
        f"Dependencies contain a cycle: {result.dependencies}"
    )

    # Verify all dependency references are valid step IDs
    step_ids = {step.step_id for step in result.steps}
    for step_id, depends_on in result.dependencies:
        assert step_id in step_ids, f"Dependency references invalid step_id: {step_id}"
        assert depends_on in step_ids, (
            f"Dependency references invalid depends_on: {depends_on}"
        )

    # Verify no self-dependencies
    for step_id, depends_on in result.dependencies:
        assert step_id != depends_on, f"Step {step_id} has self-dependency"


@pytest.mark.asyncio
@given(
    task_description=st.text(min_size=10, max_size=200),
)
@settings(
    max_examples=50,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
async def test_planning_step_performance(task_description, db_session: Session):
    """
    Feature: phase20-frontend-backend-infrastructure
    Property 22: Planning step performance

    For any planning step, generation should complete within 30 seconds.

    Validates: Requirements 7.4
    """
    # Generate plan and measure time
    agent = MultiHopAgent(db=db_session)

    start_time = time.time()
    result = await agent.generate_plan(task_description=task_description, context={})
    elapsed_time = time.time() - start_time

    # Verify performance requirement
    assert elapsed_time < 30.0, f"Planning took {elapsed_time:.2f}s, exceeds 30s limit"

    # Verify result is valid
    assert result.plan_id is not None
    assert len(result.steps) > 0
    assert result.estimated_duration is not None


@pytest.mark.asyncio
async def test_plan_refinement_preserves_dag(db_session: Session):
    """
    Test that plan refinement maintains DAG property.
    """
    agent = MultiHopAgent(db=db_session)

    # Generate initial plan
    result = await agent.generate_plan(
        task_description="Implement user authentication",
        context={"framework": "FastAPI"},
    )

    # Verify initial plan has no cycles
    assert not has_cycle(result.dependencies)

    # Refine plan
    refined = await agent.refine_plan(
        plan_id=result.plan_id, feedback="Add OAuth2 support"
    )

    # Verify refined plan still has no cycles
    assert not has_cycle(refined.dependencies), (
        f"Refined plan has cycles: {refined.dependencies}"
    )

    # Verify all steps are present
    assert len(refined.steps) >= len(result.steps)


@pytest.mark.asyncio
async def test_context_preservation_across_refinements(db_session: Session):
    """
    Test that context is preserved across plan refinements.
    """
    agent = MultiHopAgent(db=db_session)

    initial_context = {
        "framework": "FastAPI",
        "database": "PostgreSQL",
        "auth_method": "JWT",
    }

    # Generate initial plan
    result = await agent.generate_plan(
        task_description="Build REST API", context=initial_context
    )

    # Verify context is preserved
    assert result.context_preserved == initial_context

    # Refine plan
    refined = await agent.refine_plan(
        plan_id=result.plan_id, feedback="Add rate limiting"
    )

    # Verify context is still preserved
    assert refined.context_preserved == initial_context


@pytest.mark.asyncio
@given(
    format_type=st.sampled_from(["markdown", "restructuredtext", "plaintext"]),
    num_components=st.integers(min_value=1, max_value=10),
)
@settings(
    max_examples=20,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
async def test_architecture_format_support(
    format_type, num_components, db_session: Session
):
    """
    Feature: phase20-frontend-backend-infrastructure
    Property 23: Format support

    For any architecture document in Markdown, reStructuredText, or plain text format,
    parsing should successfully extract components.

    Validates: Requirements 8.5
    """
    from backend.app.database.models import Resource, DocumentChunk
    from uuid import uuid4

    # Generate architecture document content in specified format
    if format_type == "markdown":
        # Markdown format with headers
        content = "# Architecture Document\n\n"
        for i in range(num_components):
            content += f"## Component {i + 1}\n"
            content += f"This is component {i + 1} description.\n"
            content += f"- Responsibility A\n"
            content += f"- Responsibility B\n\n"

    elif format_type == "restructuredtext":
        # reStructuredText format
        content = "Architecture Document\n=====================\n\n"
        for i in range(num_components):
            content += f"Component {i + 1}\n"
            content += "-" * (len(f"Component {i + 1}")) + "\n"
            content += f"This is component {i + 1} description.\n"
            content += f"* Responsibility A\n"
            content += f"* Responsibility B\n\n"

    else:  # plaintext
        # Plain text format
        content = "Architecture Document\n\n"
        for i in range(num_components):
            content += f"Component {i + 1}:\n"
            content += f"This is component {i + 1} description.\n"
            content += f"- Responsibility A\n"
            content += f"- Responsibility B\n\n"

    # Create resource with architecture document
    resource_id = uuid4()
    resource = Resource(
        id=resource_id,
        title=f"Architecture Doc ({format_type})",
        description=f"Architecture document in {format_type} format",
        type="document",
    )
    db_session.add(resource)
    db_session.commit()

    # Create a single chunk with the content
    chunk = DocumentChunk(
        id=uuid4(),
        resource_id=resource_id,
        content=content,
        chunk_index=0,
        chunk_metadata={"format": format_type},
    )
    db_session.add(chunk)
    db_session.commit()

    # Parse architecture document
    parser = ArchitectureParser(db=db_session)
    result = await parser.parse_architecture_doc(resource_id=resource_id)

    # Verify components were extracted
    # Note: Pattern matching is heuristic-based, so we just verify SOME components were found
    # The exact count may vary based on the format and pattern matching rules
    assert len(result.components) > 0, (
        f"Failed to extract any components from {format_type} format"
    )

    # Verify component structure is valid
    for component in result.components:
        assert component.name is not None and len(component.name) > 0, (
            f"Component has invalid name: {component.name}"
        )
        assert component.description is not None, f"Component has no description"
        assert isinstance(component.responsibilities, list), (
            f"Component responsibilities is not a list"
        )
        assert isinstance(component.interfaces, list), (
            f"Component interfaces is not a list"
        )

    # Verify result structure is complete
    assert isinstance(result.relationships, list)
    assert isinstance(result.patterns, list)
    assert isinstance(result.gaps, list)

    # Cleanup
    db_session.delete(chunk)
    db_session.delete(resource)
    db_session.commit()


# Pytest fixtures
# Note: db_session fixture is provided by conftest.py
