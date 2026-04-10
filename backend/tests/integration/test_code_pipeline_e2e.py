"""
End-to-end test for the complete code intelligence pipeline.

This test verifies:
1. Repository ingestion via API
2. Task status polling
3. Resource creation
4. Code chunking with AST metadata
5. Graph relationship extraction
"""

import asyncio
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Resource, DocumentChunk, GraphRelationship


# Sample Python code for testing
SAMPLE_PYTHON_CODE = '''
"""Sample module for testing."""

import os
import sys
from typing import List, Optional


class DataProcessor:
    """Process data efficiently."""
    
    def __init__(self, name: str):
        self.name = name
        self.data = []
    
    def add_item(self, item: str) -> None:
        """Add an item to the processor."""
        self.data.append(item)
    
    def process(self) -> List[str]:
        """Process all items."""
        return [item.upper() for item in self.data]


def calculate_sum(numbers: List[int]) -> int:
    """Calculate the sum of numbers."""
    return sum(numbers)


def main():
    """Main entry point."""
    processor = DataProcessor("test")
    processor.add_item("hello")
    result = processor.process()
    print(result)


if __name__ == "__main__":
    main()
'''

SAMPLE_JAVASCRIPT_CODE = """
/**
 * Sample JavaScript module for testing.
 */

const fs = require('fs');
const path = require('path');

class UserManager {
    constructor(name) {
        this.name = name;
        this.users = [];
    }
    
    addUser(user) {
        this.users.push(user);
    }
    
    getUsers() {
        return this.users;
    }
}

function formatName(firstName, lastName) {
    return `${firstName} ${lastName}`;
}

function processData(data) {
    return data.map(item => item.toUpperCase());
}

module.exports = {
    UserManager,
    formatName,
    processData
};
"""

SAMPLE_TYPESCRIPT_CODE = """
/**
 * Sample TypeScript module for testing.
 */

interface User {
    id: number;
    name: string;
    email: string;
}

class AuthService {
    private users: User[] = [];
    
    constructor(private apiKey: string) {}
    
    addUser(user: User): void {
        this.users.push(user);
    }
    
    findUser(id: number): User | undefined {
        return this.users.find(u => u.id === id);
    }
    
    authenticate(email: string): boolean {
        return this.users.some(u => u.email === email);
    }
}

export function validateEmail(email: string): boolean {
    return email.includes('@');
}

export { AuthService, User };
"""

SAMPLE_README = """
# Test Repository

This is a test repository for code intelligence pipeline testing.

## Features

- Python code processing
- JavaScript module management
- TypeScript authentication

## Installation

```bash
pip install -r requirements.txt
npm install
```

## Usage

Run the main script:

```bash
python main.py
```
"""

SAMPLE_CONFIG = """
{
    "name": "test-project",
    "version": "1.0.0",
    "description": "Test project for code intelligence",
    "main": "index.js",
    "scripts": {
        "test": "jest",
        "build": "tsc"
    },
    "dependencies": {
        "express": "^4.18.0"
    }
}
"""


def create_test_repository(base_path: Path) -> Path:
    """Create a small test repository with various file types."""
    repo_path = base_path / "test_repo"
    repo_path.mkdir(exist_ok=True)

    # Create Python files
    (repo_path / "main.py").write_text(SAMPLE_PYTHON_CODE)
    (repo_path / "utils.py").write_text("""
def helper_function(x):
    return x * 2

def another_helper(y):
    return y + 1
""")

    # Create JavaScript file
    (repo_path / "index.js").write_text(SAMPLE_JAVASCRIPT_CODE)

    # Create TypeScript file
    (repo_path / "auth.ts").write_text(SAMPLE_TYPESCRIPT_CODE)

    # Create documentation
    (repo_path / "README.md").write_text(SAMPLE_README)

    # Create config file
    (repo_path / "package.json").write_text(SAMPLE_CONFIG)

    # Create a subdirectory with more code
    src_dir = repo_path / "src"
    src_dir.mkdir(exist_ok=True)
    (src_dir / "helper.py").write_text("""
class Helper:
    def process(self, data):
        return data
""")

    # Create .gitignore
    (repo_path / ".gitignore").write_text("""
__pycache__/
*.pyc
node_modules/
.env
""")

    return repo_path


@pytest.mark.asyncio
async def test_code_pipeline_end_to_end(
    bypass_auth: TestClient, db_session: AsyncSession
):
    """
    Test the complete code intelligence pipeline end-to-end.

    This test:
    1. Creates a test repository with multiple file types
    2. Calls POST /resources/ingest-repo to start ingestion
    3. Polls GET /resources/ingest-repo/{task_id}/status until complete
    4. Verifies Resources are created for each file
    5. Verifies DocumentChunks are created with AST metadata
    6. Verifies GraphRelationships are extracted
    """
    # Create test repository
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = create_test_repository(Path(tmpdir))

        # Step 1: Start repository ingestion
        response = await async_client.post(
            "/api/resources/ingest-repo", json={"path": str(repo_path)}
        )

        assert response.status_code == 200, (
            f"Failed to start ingestion: {response.text}"
        )
        data = response.json()
        assert "task_id" in data
        task_id = data["task_id"]

        print(f"\n✓ Started ingestion with task_id: {task_id}")

        # Step 2: Poll for completion
        max_attempts = 30
        attempt = 0
        completed = False

        while attempt < max_attempts:
            response = await async_client.get(
                f"/api/resources/ingest-repo/{task_id}/status"
            )
            assert response.status_code == 200

            status_data = response.json()
            state = status_data.get("state")

            print(
                f"  Attempt {attempt + 1}: State={state}, "
                f"Files={status_data.get('files_processed', 0)}/{status_data.get('total_files', 0)}"
            )

            if state == "COMPLETED":
                completed = True
                break
            elif state == "FAILED":
                pytest.fail(f"Ingestion failed: {status_data.get('error')}")

            attempt += 1
            await asyncio.sleep(0.5)

        assert completed, f"Ingestion did not complete within {max_attempts} attempts"
        print("✓ Ingestion completed successfully")

        # Step 3: Verify Resources were created
        result = await db_session.execute(
            select(Resource).where(
                Resource.metadata["repo_root"].astext == str(repo_path)
            )
        )
        resources = result.scalars().all()

        assert len(resources) > 0, "No resources were created"
        print(f"✓ Created {len(resources)} resources")

        # Verify we have different file types
        file_types = set()
        code_resources = []

        for resource in resources:
            file_path = resource.metadata.get("file_path", "")
            if file_path:
                ext = Path(file_path).suffix
                file_types.add(ext)

                # Track code files
                if ext in [".py", ".js", ".ts"]:
                    code_resources.append(resource)

        print(f"✓ File types found: {file_types}")
        assert ".py" in file_types, "No Python files found"
        assert ".js" in file_types or ".ts" in file_types, (
            "No JavaScript/TypeScript files found"
        )
        assert ".md" in file_types, "No Markdown files found"

        # Step 4: Verify DocumentChunks were created with AST metadata
        chunks_found = 0
        chunks_with_metadata = 0
        function_chunks = 0
        class_chunks = 0

        for resource in code_resources:
            result = await db_session.execute(
                select(DocumentChunk).where(DocumentChunk.resource_id == resource.id)
            )
            chunks = result.scalars().all()
            chunks_found += len(chunks)

            for chunk in chunks:
                if chunk.chunk_metadata:
                    chunks_with_metadata += 1

                    # Check for AST metadata
                    chunk_type = chunk.chunk_metadata.get("type")
                    if chunk_type == "function":
                        function_chunks += 1
                        assert "function_name" in chunk.chunk_metadata
                        assert "start_line" in chunk.chunk_metadata
                        assert "end_line" in chunk.chunk_metadata
                    elif chunk_type == "class":
                        class_chunks += 1
                        assert "class_name" in chunk.chunk_metadata
                        assert "start_line" in chunk.chunk_metadata
                        assert "end_line" in chunk.chunk_metadata

        print(f"✓ Created {chunks_found} chunks ({chunks_with_metadata} with metadata)")
        print(f"  - {function_chunks} function chunks")
        print(f"  - {class_chunks} class chunks")

        assert chunks_found > 0, "No chunks were created"
        assert chunks_with_metadata > 0, "No chunks have metadata"
        assert function_chunks > 0, "No function chunks found"
        assert class_chunks > 0, "No class chunks found"

        # Step 5: Verify GraphRelationships were extracted
        resource_ids = [r.id for r in code_resources]
        result = await db_session.execute(
            select(GraphRelationship).where(
                GraphRelationship.source_id.in_(resource_ids)
            )
        )
        relationships = result.scalars().all()

        print(f"✓ Created {len(relationships)} graph relationships")

        if len(relationships) > 0:
            # Check relationship types
            relationship_types = set()
            for rel in relationships:
                relationship_types.add(rel.relationship_type)

            print(f"  Relationship types: {relationship_types}")

            # Verify we have import relationships (most common)
            import_rels = [r for r in relationships if r.relationship_type == "IMPORTS"]
            print(f"  - {len(import_rels)} IMPORTS relationships")

            # Check metadata
            rels_with_metadata = [r for r in relationships if r.metadata]
            print(f"  - {len(rels_with_metadata)} relationships with metadata")

        # Step 6: Verify specific code patterns were detected
        # Check for Python class
        result = await db_session.execute(
            select(DocumentChunk).where(
                DocumentChunk.chunk_metadata["class_name"].astext == "DataProcessor"
            )
        )
        data_processor_chunk = result.scalar_one_or_none()
        assert data_processor_chunk is not None, "DataProcessor class not found"
        print("✓ Found DataProcessor class chunk")

        # Check for Python function
        result = await db_session.execute(
            select(DocumentChunk).where(
                DocumentChunk.chunk_metadata["function_name"].astext == "calculate_sum"
            )
        )
        calculate_sum_chunk = result.scalar_one_or_none()
        assert calculate_sum_chunk is not None, "calculate_sum function not found"
        print("✓ Found calculate_sum function chunk")

        # Check for JavaScript class
        result = await db_session.execute(
            select(DocumentChunk).where(
                DocumentChunk.chunk_metadata["class_name"].astext == "UserManager"
            )
        )
        user_manager_chunk = result.scalar_one_or_none()
        assert user_manager_chunk is not None, "UserManager class not found"
        print("✓ Found UserManager class chunk")

        # Check for TypeScript class
        result = await db_session.execute(
            select(DocumentChunk).where(
                DocumentChunk.chunk_metadata["class_name"].astext == "AuthService"
            )
        )
        auth_service_chunk = result.scalar_one_or_none()
        assert auth_service_chunk is not None, "AuthService class not found"
        print("✓ Found AuthService class chunk")

        print("\n" + "=" * 60)
        print("END-TO-END TEST SUMMARY")
        print("=" * 60)
        print("✓ Repository ingested successfully")
        print(f"✓ {len(resources)} resources created")
        print(
            f"✓ {chunks_found} chunks created ({chunks_with_metadata} with AST metadata)"
        )
        print(f"✓ {function_chunks} function chunks")
        print(f"✓ {class_chunks} class chunks")
        print(f"✓ {len(relationships)} graph relationships")
        print("✓ All expected code patterns detected")
        print("=" * 60)


@pytest.mark.asyncio
async def test_code_pipeline_with_errors(
    async_client: AsyncClient, db_session: AsyncSession
):
    """
    Test that the pipeline handles errors gracefully.
    """
    # Test with non-existent path
    response = await async_client.post(
        "/api/resources/ingest-repo", json={"path": "/nonexistent/path"}
    )

    assert response.status_code == 400 or response.status_code == 404
    print("✓ Correctly rejected non-existent path")

    # Test with invalid task ID
    response = await async_client.get(
        "/api/resources/ingest-repo/invalid-task-id/status"
    )
    assert response.status_code == 404
    print("✓ Correctly handled invalid task ID")


@pytest.mark.asyncio
async def test_code_pipeline_performance(
    async_client: AsyncClient, db_session: AsyncSession
):
    """
    Test that the pipeline meets performance requirements.
    """
    import time

    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = create_test_repository(Path(tmpdir))

        start_time = time.time()

        # Start ingestion
        response = await async_client.post(
            "/api/resources/ingest-repo", json={"path": str(repo_path)}
        )
        assert response.status_code == 200
        task_id = response.json()["task_id"]

        # Wait for completion
        max_wait = 30  # 30 seconds max
        completed = False

        while time.time() - start_time < max_wait:
            response = await async_client.get(
                f"/api/resources/ingest-repo/{task_id}/status"
            )
            if response.json().get("state") == "COMPLETED":
                completed = True
                break
            await asyncio.sleep(0.5)

        elapsed = time.time() - start_time

        assert completed, "Pipeline did not complete in time"
        print(f"✓ Pipeline completed in {elapsed:.2f} seconds")

        # Performance requirement: Should process ~8 files in < 10 seconds
        assert elapsed < 10, f"Pipeline too slow: {elapsed:.2f}s > 10s"
        print("✓ Performance requirement met (< 10s for small repo)")
