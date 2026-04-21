"""
Repository Ingestion Worker (Full-Featured)

This worker processes GitHub repository ingestion tasks with complete workflow:
1. Clones repository temporarily
2. Parses ALL Python files (no artificial limits)
3. Performs AST analysis (imports, functions, classes)
4. Generates embeddings for semantic search
5. Stores metadata in PostgreSQL
6. Code stays on GitHub (hybrid storage)

Usage:
    python worker.py repo

This is the production-ready version with full AST parsing and embeddings.
For GPU-accelerated Node2Vec graph embeddings, use deployment/worker.py with Qdrant.
"""

import os
import sys
import json
import asyncio
import signal
import subprocess
import tempfile
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Verify MODE is set to EDGE
if os.getenv("MODE") != "EDGE":
    print("[ERROR] Configuration Error: MODE must be set to 'EDGE' in .env")
    sys.exit(1)

# Import services
try:
    import requests
    from sqlalchemy import text
    from app.shared.database import init_database, get_db
    from app.config.settings import get_settings
    # Import converter to register event handler
    from app.modules.resources import repository_converter  # noqa: F401
except ImportError as e:
    print(f"[ERROR] Import Error: {e}")
    sys.exit(1)


class RepositoryWorker:
    """Worker that processes GitHub repository ingestion tasks."""

    def __init__(self):
        """Initialize the repository worker."""
        print("[INIT] Initializing repository worker...")
        sys.stdout.flush()

        # Validate Redis credentials
        redis_url = os.getenv("UPSTASH_REDIS_REST_URL")
        redis_token = os.getenv("UPSTASH_REDIS_REST_TOKEN")

        if not redis_url or not redis_token:
            print("[ERROR] Redis credentials not set")
            sys.exit(1)

        self.redis_url = redis_url
        self.redis_token = redis_token
        self.queue_key = "pharos:tasks"  # Must match QueueService.QUEUE_KEY

        # Test Redis connection
        print("[INIT] Testing Redis connection...")
        sys.stdout.flush()

        try:
            response = requests.post(
                self.redis_url,
                headers={"Authorization": f"Bearer {self.redis_token}"},
                json=["PING"],
                timeout=5,
            )
            if response.status_code == 200:
                print("[OK] Connected to Upstash Redis")
                sys.stdout.flush()
            else:
                print(f"[ERROR] Redis connection failed: {response.status_code}")
                sys.exit(1)
        except Exception as e:
            print(f"[ERROR] Redis connection error: {e}")
            sys.exit(1)

        # Initialize database
        print("[INIT] Initializing database...")
        sys.stdout.flush()

        init_database()
        print("[OK] Database initialized")
        sys.stdout.flush()

        # Initialize settings
        self.settings = get_settings()
        print("[OK] Settings loaded")
        sys.stdout.flush()

        # Shutdown flag
        self.shutdown_requested = False

        # Register signal handlers
        signal.signal(signal.SIGINT, self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)

        print("[OK] Repository worker initialized")
        print()
        sys.stdout.flush()

    def _handle_shutdown(self, signum, frame):
        """Handle SIGINT/SIGTERM for graceful shutdown."""
        print("\n[SHUTDOWN] Shutdown signal received...")
        self.shutdown_requested = True

    def _redis_command(self, command: list) -> Optional[any]:
        """Execute a Redis command via REST API."""
        try:
            response = requests.post(
                self.redis_url,
                headers={"Authorization": f"Bearer {self.redis_token}"},
                json=command,
                timeout=5,
            )
            if response.status_code == 200:
                result = response.json()
                return result.get("result")
            return None
        except Exception as e:
            print(f"[WARN] Redis error: {e}")
            return None

    def clone_repository(self, repo_url: str, target_dir: Path) -> bool:
        """Clone a GitHub repository."""
        try:
            # Normalize URL format
            if not repo_url.startswith(("http://", "https://", "git@")):
                # Add https:// prefix and .git suffix
                repo_url = f"https://{repo_url}.git"
            elif not repo_url.endswith(".git"):
                # Add .git suffix if missing
                repo_url = f"{repo_url}.git"
            
            print(f"[CLONE] Cloning {repo_url}...")
            sys.stdout.flush()

            result = subprocess.run(
                ["git", "clone", "--depth", "1", repo_url, str(target_dir)],
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )

            if result.returncode == 0:
                print(f"[OK] Repository cloned to {target_dir}")
                sys.stdout.flush()
                return True
            else:
                print(f"[ERROR] Clone failed: {result.stderr}")
                return False

        except subprocess.TimeoutExpired:
            print("[ERROR] Clone timeout (5 minutes)")
            return False
        except Exception as e:
            print(f"[ERROR] Clone error: {e}")
            return False

    def parse_repository(self, repo_dir: Path) -> Dict:
        """Parse repository and extract metadata with AST analysis."""
        print("[PARSE] Analyzing repository structure...")
        sys.stdout.flush()

        metadata = {
            "files": [],
            "total_files": 0,
            "total_lines": 0,
            "languages": {},
            "imports": {},  # Track import relationships
            "functions": [],  # Track all functions
            "classes": [],  # Track all classes
        }

        # Find all Python files
        python_files = list(repo_dir.rglob("*.py"))
        metadata["total_files"] = len(python_files)

        print(f"[PARSE] Found {len(python_files)} Python files")
        print("[PARSE] Parsing ALL files (no limit)...")
        sys.stdout.flush()

        # Parse ALL files (no artificial limit)
        for idx, py_file in enumerate(python_files, 1):
            try:
                relative_path = py_file.relative_to(repo_dir)
                content = py_file.read_text(encoding='utf-8', errors='ignore')
                lines = len(content.splitlines())

                # Basic file metadata
                file_data = {
                    "path": str(relative_path),
                    "size": py_file.stat().st_size,
                    "lines": lines,
                }

                # AST parsing for imports, functions, classes
                try:
                    import ast
                    tree = ast.parse(content, filename=str(relative_path))

                    # Extract imports
                    imports = []
                    for node in ast.walk(tree):
                        if isinstance(node, ast.Import):
                            for alias in node.names:
                                imports.append(alias.name)
                        elif isinstance(node, ast.ImportFrom):
                            if node.module:
                                imports.append(node.module)

                    file_data["imports"] = imports

                    # Track imports for dependency graph
                    if imports:
                        metadata["imports"][str(relative_path)] = imports

                    # Extract functions
                    functions = [node.name for node in ast.walk(tree)
                                if isinstance(node, ast.FunctionDef)]
                    file_data["functions"] = functions
                    metadata["functions"].extend([
                        {"file": str(relative_path), "name": f} for f in functions
                    ])

                    # Extract classes
                    classes = [node.name for node in ast.walk(tree)
                              if isinstance(node, ast.ClassDef)]
                    file_data["classes"] = classes
                    metadata["classes"].extend([
                        {"file": str(relative_path), "name": c} for c in classes
                    ])

                except SyntaxError:
                    # File has syntax errors, skip AST parsing
                    file_data["imports"] = []
                    file_data["functions"] = []
                    file_data["classes"] = []

                metadata["files"].append(file_data)
                metadata["total_lines"] += lines

                # Progress indicator every 100 files
                if idx % 100 == 0:
                    print(f"[PARSE] Progress: {idx}/{len(python_files)} files...")
                    sys.stdout.flush()

            except Exception as e:
                print(f"[WARN] Failed to parse {py_file}: {e}")
                continue

        metadata["languages"]["Python"] = len(python_files)

        print(f"[OK] Parsed {len(metadata['files'])} files, {metadata['total_lines']} lines")
        print(f"[OK] Extracted {len(metadata['functions'])} functions, {len(metadata['classes'])} classes")
        print(f"[OK] Found {len(metadata['imports'])} files with imports")
        sys.stdout.flush()

        return metadata

    async def store_repository(self, repo_url: str, metadata: Dict, embeddings: Dict) -> str:
        """Store repository metadata AND create searchable resources/chunks directly."""
        print("[STORE] Saving to database...")
        sys.stdout.flush()

        repo_id = ""
        async for session in get_db():
            try:
                # Store embeddings separately (not in metadata JSON to keep it small)
                metadata_without_embeddings = {k: v for k, v in metadata.items() if k != "embeddings"}

                # Check if repository already exists
                result = await session.execute(
                    text("SELECT id FROM repositories WHERE url = :url"),
                    {"url": repo_url}
                )
                existing_repo = result.scalar_one_or_none()
                
                if existing_repo:
                    print(f"[INFO] Repository already exists: {existing_repo}")
                    print("[INFO] Updating metadata and creating resources...")
                    repo_id = str(existing_repo)
                    
                    # Update existing repository
                    await session.execute(
                        text("""
                            UPDATE repositories
                            SET metadata = CAST(:metadata AS jsonb),
                                total_files = :total_files,
                                total_lines = :total_lines,
                                updated_at = NOW()
                            WHERE id = :repo_id
                        """),
                        {
                            "repo_id": repo_id,
                            "metadata": json.dumps(metadata_without_embeddings),
                            "total_files": metadata["total_files"],
                            "total_lines": metadata["total_lines"],
                        }
                    )
                else:
                    # Create new repository record
                    result = await session.execute(
                        text("""
                            INSERT INTO repositories (
                                id, url, name, metadata,
                                total_files, total_lines,
                                created_at, updated_at
                            ) VALUES (
                                gen_random_uuid(), :url, :name, CAST(:metadata AS jsonb),
                                :total_files, :total_lines,
                                NOW(), NOW()
                            )
                            RETURNING id
                        """),
                        {
                            "url": repo_url,
                            "name": repo_url.split("/")[-1],
                            "metadata": json.dumps(metadata_without_embeddings),
                            "total_files": metadata["total_files"],
                            "total_lines": metadata["total_lines"],
                        }
                    )
                    repo_id = str(result.scalar_one())

                await session.commit()
                print(f"[OK] Repository stored: {repo_id}")
                sys.stdout.flush()

                # Now create resources and chunks directly
                print(f"[CONVERT] Creating {len(metadata['files'])} resources and chunks...")
                sys.stdout.flush()
                
                resources_created = 0
                chunks_created = 0
                embeddings_linked = 0
                
                for idx, file_data in enumerate(metadata["files"], 1):
                    try:
                        # Create resource
                        github_url = f"{repo_url}/blob/main/{file_data['path']}"
                        identifier = f"repo:{repo_id}:{file_data['path']}"
                        
                        file_metadata = {
                            "repo_id": repo_id,
                            "repo_url": repo_url,
                            "repo_name": repo_url.split("/")[-1],
                            "file_path": file_data["path"],
                            "file_size": file_data.get("size", 0),
                            "lines": file_data.get("lines", 0),
                            "imports": file_data.get("imports", []),
                            "functions": file_data.get("functions", []),
                            "classes": file_data.get("classes", [])
                        }
                        
                        result = await session.execute(
                            text("""
                                INSERT INTO resources (
                                    id, title, type, format, source, identifier,
                                    description, subject, read_status, quality_score,
                                    created_at, updated_at
                                ) VALUES (
                                    gen_random_uuid(), :title, :type, :format, :source, :identifier,
                                    :description, CAST(:subject AS jsonb), :read_status, :quality_score,
                                    NOW(), NOW()
                                )
                                RETURNING id
                            """),
                            {
                                "title": file_data["path"],
                                "type": "code",
                                "format": "text/x-python",
                                "source": github_url,
                                "identifier": identifier,
                                "description": json.dumps(file_metadata),
                                "subject": json.dumps(file_data.get("imports", [])[:10]),
                                "read_status": "unread",
                                "quality_score": 0.0,
                            }
                        )
                        resource_id = str(result.scalar_one())
                        resources_created += 1
                        
                        # Create chunk
                        summary_parts = [
                            f"File: {file_data['path']}",
                            f"Functions: {', '.join(file_data.get('functions', [])[:10])}",
                            f"Classes: {', '.join(file_data.get('classes', [])[:10])}",
                            f"Imports: {', '.join(file_data.get('imports', [])[:10])}"
                        ]
                        semantic_summary = " | ".join(summary_parts)
                        
                        github_uri = f"https://raw.githubusercontent.com/{repo_url.replace('github.com/', '')}/main/{file_data['path']}"
                        
                        result = await session.execute(
                            text("""
                                INSERT INTO document_chunks (
                                    id, resource_id, chunk_index,
                                    content, semantic_summary,
                                    is_remote, github_uri, branch_reference,
                                    start_line, end_line,
                                    ast_node_type, symbol_name,
                                    chunk_metadata,
                                    created_at
                                ) VALUES (
                                    gen_random_uuid(), :resource_id, :chunk_index,
                                    NULL, :semantic_summary,
                                    TRUE, :github_uri, :branch_reference,
                                    :start_line, :end_line,
                                    :ast_node_type, :symbol_name,
                                    CAST(:chunk_metadata AS jsonb),
                                    NOW()
                                )
                                RETURNING id
                            """),
                            {
                                "resource_id": resource_id,
                                "chunk_index": 0,
                                "semantic_summary": semantic_summary,
                                "github_uri": github_uri,
                                "branch_reference": "main",
                                "start_line": 1,
                                "end_line": file_data.get("lines", 0),
                                "ast_node_type": "module",
                                "symbol_name": file_data["path"].replace("/", ".").replace(".py", ""),
                                "chunk_metadata": json.dumps({
                                    "file_path": file_data["path"],
                                    "language": "python",
                                    "lines": file_data.get("lines", 0),
                                    "functions": file_data.get("functions", []),
                                    "classes": file_data.get("classes", []),
                                    "imports": file_data.get("imports", [])
                                })
                            }
                        )
                        str(result.scalar_one())
                        chunks_created += 1
                        
                        # Link embedding if available
                        if file_data["path"] in embeddings:
                            await session.execute(
                                text("""
                                    UPDATE resources
                                    SET embedding = :embedding
                                    WHERE id = :resource_id
                                """),
                                {
                                    "resource_id": resource_id,
                                    "embedding": json.dumps(embeddings[file_data["path"]])
                                }
                            )
                            embeddings_linked += 1
                        
                        # Commit every 100 files to avoid huge transactions
                        if idx % 100 == 0:
                            await session.commit()
                            print(f"[CONVERT] Progress: {idx}/{len(metadata['files'])} files...")
                            sys.stdout.flush()
                        
                    except Exception as e:
                        print(f"[WARN] Failed to convert {file_data['path']}: {e}")
                        continue
                
                # Final commit
                await session.commit()
                
                print("[OK] Conversion complete!")
                print(f"  Resources: {resources_created}")
                print(f"  Chunks: {chunks_created}")
                print(f"  Embeddings: {embeddings_linked}")
                sys.stdout.flush()

                return repo_id

            except Exception as e:
                print(f"[ERROR] Database error: {e}")
                import traceback
                traceback.print_exc()
                await session.rollback()
                raise
            finally:
                break
        
        return repo_id

    async def generate_embeddings(self, metadata: Dict) -> Dict:
        """Generate embeddings for repository files and functions."""
        print("[EMBED] Generating embeddings...")
        sys.stdout.flush()

        try:
            from app.shared.embeddings import EmbeddingService

            embedding_service = EmbeddingService()
            embeddings = {}

            # Generate embeddings for each file's content summary
            for idx, file_data in enumerate(metadata["files"], 1):
                try:
                    # Create a summary text for embedding
                    summary_parts = [
                        f"File: {file_data['path']}",
                        f"Functions: {', '.join(file_data.get('functions', [])[:10])}",  # First 10 functions
                        f"Classes: {', '.join(file_data.get('classes', [])[:10])}",  # First 10 classes
                        f"Imports: {', '.join(file_data.get('imports', [])[:10])}",  # First 10 imports
                    ]
                    summary_text = " | ".join(summary_parts)

                    # Generate embedding (synchronous call, not async)
                    embedding = embedding_service.generate_embedding(summary_text)
                    embeddings[file_data['path']] = embedding

                    # Progress indicator every 50 files
                    if idx % 50 == 0:
                        print(f"[EMBED] Progress: {idx}/{len(metadata['files'])} files...")
                        sys.stdout.flush()

                except Exception as e:
                    print(f"[WARN] Failed to generate embedding for {file_data['path']}: {e}")
                    continue

            print(f"[OK] Generated {len(embeddings)} embeddings")
            sys.stdout.flush()

            return embeddings

        except ImportError:
            print("[WARN] Embedding service not available, skipping embeddings")
            return {}
        except Exception as e:
            print(f"[WARN] Embedding generation failed: {e}")
            return {}

    async def process_ingestion(self, task_data: Dict) -> None:
        """Process a repository ingestion task with full workflow."""
        job_start = datetime.now()
        repo_url = task_data.get("repo_url")
        
        if repo_url is None:
            print("[ERROR] Task missing repo_url")
            return
            
        temp_dir = None

        print(f"[TASK] Received task: ingest {repo_url}")
        print("[TASK] Full workflow: clone -> parse -> AST -> embeddings -> store -> convert")
        sys.stdout.flush()

        try:
            # Step 1: Create temporary directory
            temp_dir = Path(tempfile.mkdtemp(prefix="pharos_repo_"))

            # Step 2: Clone repository
            if not self.clone_repository(repo_url, temp_dir):
                print("[ERROR] Failed to clone repository")
                return

            # Step 3: Parse repository with AST analysis
            metadata = self.parse_repository(temp_dir)

            # Step 4: Generate embeddings
            embeddings = await self.generate_embeddings(metadata)
            if embeddings:
                metadata["embeddings_count"] = len(embeddings)
                # Store embeddings in metadata for converter to use
                metadata["embeddings"] = embeddings

            # Step 5: Store in database and create resources/chunks
            repo_id = await self.store_repository(repo_url, metadata, embeddings)

            job_end = datetime.now()
            duration = (job_end - job_start).total_seconds()

            print()
            print("=" * 60)
            print("[SUCCESS] Repository Ingestion Complete")
            print("=" * 60)
            print(f"Repository ID: {repo_id}")
            print(f"Total Files: {metadata['total_files']}")
            print(f"Files Parsed: {len(metadata['files'])}")
            print(f"Total Lines: {metadata['total_lines']:,}")
            print(f"Functions: {len(metadata['functions'])}")
            print(f"Classes: {len(metadata['classes'])}")
            print(f"Files with Imports: {len(metadata['imports'])}")
            if embeddings:
                print(f"Embeddings: {len(embeddings)}")
            print(f"Duration: {duration:.2f}s")
            print("=" * 60)
            print()
            sys.stdout.flush()

        except Exception as e:
            print(f"[ERROR] Error processing task: {e}")
            import traceback
            traceback.print_exc()
            print()
        finally:
            # Cleanup temporary directory
            if temp_dir and temp_dir.exists():
                try:
                    shutil.rmtree(temp_dir)
                    print("[CLEANUP] Removed temporary directory")
                except Exception as e:
                    print(f"[WARN] Failed to cleanup: {e}")

    async def run_async(self) -> None:
        """Async worker loop that polls queue every 2 seconds."""
        print("[WORKER] Polling Redis queue every 2 seconds...")
        print(f"[WORKER] Queue: {self.queue_key}")
        print("[WORKER] Press Ctrl+C to stop")
        print()
        sys.stdout.flush()

        while not self.shutdown_requested:
            try:
                # Poll for tasks (LPOP removes from queue)
                result = self._redis_command(["LPOP", self.queue_key])

                if result:
                    print(f"[DEBUG] Received from queue: {result}")
                    sys.stdout.flush()

                    # Parse task data
                    try:
                        if isinstance(result, str):
                            task_data = json.loads(result)
                        else:
                            task_data = {"repo_url": result}
                    except json.JSONDecodeError:
                        # Legacy format: plain URL string
                        task_data = {"repo_url": result}

                    # Process task (await instead of asyncio.run)
                    await self.process_ingestion(task_data)
                else:
                    # Sleep when idle
                    await asyncio.sleep(2)

            except KeyboardInterrupt:
                print("\n[SHUTDOWN] Shutting down gracefully...")
                break

            except Exception as e:
                print(f"[ERROR] Worker error: {e}")
                import traceback
                traceback.print_exc()
                await asyncio.sleep(5)

        print("[SHUTDOWN] Repository worker stopped")

    def run(self) -> None:
        """Main worker entry point that creates event loop."""
        try:
            asyncio.run(self.run_async())
        except KeyboardInterrupt:
            print("\n[SHUTDOWN] Shutting down gracefully...")
        except Exception as e:
            print(f"[ERROR] Fatal error: {e}")
            import traceback
            traceback.print_exc()


def main():
    """Main entry point for the repository worker."""
    print("=" * 60)
    print("Pharos Repository Ingestion Worker")
    print("=" * 60)
    print()

    # Create and run worker
    worker = RepositoryWorker()
    worker.run()


if __name__ == "__main__":
    main()
