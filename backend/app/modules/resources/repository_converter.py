"""
Repository to Resources Converter

Converts repository data from the repositories table to resources/chunks format
so existing search and graph modules can work with code repositories.

This bridges the gap between:
- Repository model (new): repositories table with metadata
- Resource model (existing): resources + chunks tables used by search/graph

Architecture:
- Event-driven: Subscribes to repository.ingested events
- Hybrid storage: Metadata in PostgreSQL, code stays on GitHub
- Reuses embeddings: Links existing embeddings from repository ingestion
- Automatic: Runs immediately after repository ingestion
"""

import logging
import json
from typing import Dict, List

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Global cache for embeddings (passed via event)
_embeddings_cache = {}


class RepositoryConverter:
    """Convert repository data to resources/chunks format for search integration."""

    def __init__(self, db: AsyncSession):
        """
        Initialize converter.

        Args:
            db: Database session
        """
        self.db = db

    async def convert_repository(self, repo_id: str, embeddings: Dict = None) -> Dict:
        """
        Convert a repository to resources and chunks.

        Creates:
        - One resource per file in the repository
        - One chunk per file (with semantic_summary for embedding)
        - Links existing embeddings from repository metadata
        - Creates graph entities for functions/classes

        Args:
            repo_id: Repository UUID
            embeddings: Optional dict of embeddings (file_path -> vector)

        Returns:
            Dict with conversion statistics
        """
        logger.info(f"Converting repository {repo_id} to resources/chunks")

        # Get repository metadata
        result = await self.db.execute(
            text("""
                SELECT id, url, name, metadata, total_files, total_lines
                FROM repositories
                WHERE id = :repo_id
            """),
            {"repo_id": repo_id}
        )
        repo = result.fetchone()

        if not repo:
            raise ValueError(f"Repository {repo_id} not found")

        # Parse metadata (column name is 'metadata' in database)
        metadata = json.loads(repo.metadata) if isinstance(repo.metadata, str) else repo.metadata
        files = metadata.get("files", [])

        # Use provided embeddings or try to get from cache
        if embeddings is None:
            embeddings = _embeddings_cache.get(repo_id, {})

        logger.info(f"Converting {len(files)} files from {repo.name}")
        logger.info(f"Available embeddings: {len(embeddings)}")

        stats = {
            "resources_created": 0,
            "chunks_created": 0,
            "embeddings_linked": 0,
            "entities_created": 0,
            "errors": []
        }

        # Convert each file to resource + chunk
        for file_data in files:
            try:
                # Create resource
                resource_id = await self._create_resource_from_file(
                    repo, file_data
                )
                stats["resources_created"] += 1

                # Create chunk with semantic summary
                chunk_id = await self._create_chunk_from_file(
                    resource_id, repo, file_data
                )
                stats["chunks_created"] += 1

                # Link embedding if available
                if file_data["path"] in embeddings:
                    await self._link_embedding(
                        chunk_id, embeddings[file_data["path"]]
                    )
                    stats["embeddings_linked"] += 1

                # Create graph entities for functions/classes
                entity_count = await self._create_graph_entities(
                    resource_id, file_data
                )
                stats["entities_created"] += entity_count

                # Commit after each file to avoid transaction rollback issues
                await self.db.commit()

            except Exception as e:
                logger.error(f"Error converting file {file_data['path']}: {e}")
                stats["errors"].append({
                    "file": file_data["path"],
                    "error": str(e)
                })
                # Rollback the failed transaction
                await self.db.rollback()

        # Final commit (in case last file succeeded)
        try:
            await self.db.commit()
        except:
            pass

        # Clear embeddings from cache
        if repo_id in _embeddings_cache:
            del _embeddings_cache[repo_id]

        logger.info(
            f"Conversion complete: {stats['resources_created']} resources, "
            f"{stats['chunks_created']} chunks, {stats['embeddings_linked']} embeddings, "
            f"{stats['entities_created']} entities"
        )

        return stats

    async def _create_resource_from_file(
        self, repo, file_data: Dict
    ) -> str:
        """
        Create a resource from a repository file.

        Args:
            repo: Repository database row
            file_data: File metadata dict

        Returns:
            Resource UUID
        """
        # Build GitHub URL for the file
        github_url = f"{repo.url}/blob/main/{file_data['path']}"

        # Store repo_id in identifier field (format: repo:UUID:filepath)
        identifier = f"repo:{repo.id}:{file_data['path']}"

        # Store file metadata in description as JSON
        file_metadata = {
            "repo_id": str(repo.id),
            "repo_url": repo.url,
            "repo_name": repo.name,
            "file_path": file_data["path"],
            "file_size": file_data.get("size", 0),
            "lines": file_data.get("lines", 0),
            "imports": file_data.get("imports", []),
            "functions": file_data.get("functions", []),
            "classes": file_data.get("classes", [])
        }

        # Create resource
        result = await self.db.execute(
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
                "subject": json.dumps(file_data.get("imports", [])[:10]),  # First 10 imports as subjects
                "read_status": "unread",  # Explicitly set read_status
                "quality_score": 0.0,  # Default quality score for code
            }
        )

        resource_id = result.scalar_one()
        return str(resource_id)

    async def _create_chunk_from_file(
        self, resource_id: str, repo, file_data: Dict
    ) -> str:
        """
        Create a chunk from a repository file.

        Uses hybrid storage: content stays on GitHub, only metadata stored.

        Args:
            resource_id: Parent resource UUID
            repo: Repository database row
            file_data: File metadata dict

        Returns:
            Chunk UUID
        """
        # Build semantic summary for embedding (same as repo_worker.py)
        summary_parts = [
            f"File: {file_data['path']}",
            f"Functions: {', '.join(file_data.get('functions', [])[:10])}",
            f"Classes: {', '.join(file_data.get('classes', [])[:10])}",
            f"Imports: {', '.join(file_data.get('imports', [])[:10])}"
        ]
        semantic_summary = " | ".join(summary_parts)

        # Build GitHub raw URL
        github_uri = f"https://raw.githubusercontent.com/{repo.url.split('github.com/')[-1]}/main/{file_data['path']}"

        # Create chunk with hybrid storage fields
        result = await self.db.execute(
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
                "chunk_index": 0,  # One chunk per file
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

        chunk_id = result.scalar_one()
        return str(chunk_id)

    async def _link_embedding(self, chunk_id: str, embedding: List[float]) -> None:
        """
        Link an existing embedding to a chunk.

        Args:
            chunk_id: Chunk UUID
            embedding: Embedding vector
        """
        # Store embedding in resource (for now, until we have separate embeddings table)
        # Get resource_id from chunk
        result = await self.db.execute(
            text("SELECT resource_id FROM document_chunks WHERE id = :chunk_id"),
            {"chunk_id": chunk_id}
        )
        resource_id = result.scalar_one()

        # Update resource with embedding
        await self.db.execute(
            text("""
                UPDATE resources
                SET embedding = :embedding
                WHERE id = :resource_id
            """),
            {
                "resource_id": str(resource_id),
                "embedding": json.dumps(embedding)
            }
        )

    async def _create_graph_entities(
        self, resource_id: str, file_data: Dict
    ) -> int:
        """
        Create graph entities for functions and classes.

        Args:
            resource_id: Parent resource UUID
            file_data: File metadata dict

        Returns:
            Number of entities created
        """
        entity_count = 0

        # Create function entities
        for func in file_data.get("functions", []):
            try:
                await self.db.execute(
                    text("""
                        INSERT INTO graph_entities (
                            id, name, type, entity_metadata, created_at
                        ) VALUES (
                            gen_random_uuid(), :name, :type, CAST(:entity_metadata AS jsonb), NOW()
                        )
                        ON CONFLICT (name, type) DO NOTHING
                    """),
                    {
                        "name": func,
                        "type": "function",
                        "entity_metadata": json.dumps({
                            "file": file_data["path"],
                            "resource_id": resource_id
                        })
                    }
                )
                entity_count += 1
            except Exception as e:
                logger.debug(f"Entity already exists or error: {e}")

        # Create class entities
        for cls in file_data.get("classes", []):
            try:
                await self.db.execute(
                    text("""
                        INSERT INTO graph_entities (
                            id, name, type, entity_metadata, created_at
                        ) VALUES (
                            gen_random_uuid(), :name, :type, CAST(:entity_metadata AS jsonb), NOW()
                        )
                        ON CONFLICT (name, type) DO NOTHING
                    """),
                    {
                        "name": cls,
                        "type": "class",
                        "entity_metadata": json.dumps({
                            "file": file_data["path"],
                            "resource_id": resource_id
                        })
                    }
                )
                entity_count += 1
            except Exception as e:
                logger.debug(f"Entity already exists or error: {e}")

        return entity_count

# Event handler for automatic conversion
def handle_repository_ingested(payload: Dict) -> None:
    """
    Handle repository.ingested event by converting to resources/chunks.

    This is a synchronous wrapper that schedules the async conversion.

    Args:
        payload: Event payload with repo_id and optional embeddings
    """
    repo_id = payload.get("repo_id")
    if not repo_id:
        logger.error("No repo_id in repository.ingested event")
        return

    logger.info(f"[CONVERTER] Auto-converting repository {repo_id} after ingestion")
    print(f"[CONVERTER] Starting automatic conversion for {repo_id}...")

    # Store embeddings in cache if provided
    if "embeddings" in payload:
        _embeddings_cache[repo_id] = payload["embeddings"]
        logger.info(f"[CONVERTER] Cached {len(payload['embeddings'])} embeddings")

    # Run async conversion in event loop
    import asyncio
    
    async def run_conversion():
        """Run the conversion asynchronously."""
        from app.shared.database import get_db
        
        async for db in get_db():
            try:
                converter = RepositoryConverter(db)
                stats = await converter.convert_repository(repo_id)

                logger.info(f"[CONVERTER] Auto-conversion complete: {stats}")
                print("[CONVERTER] Conversion complete!")
                print(f"  Resources: {stats['resources_created']}")
                print(f"  Chunks: {stats['chunks_created']}")
                print(f"  Embeddings: {stats['embeddings_linked']}")
                print(f"  Entities: {stats['entities_created']}")
                if stats['errors']:
                    print(f"  Errors: {len(stats['errors'])}")
                print()

                # Emit event for downstream modules
                from app.shared.event_bus import event_bus
                event_bus.emit("repository.converted", {
                    "repo_id": repo_id,
                    "stats": stats
                })

            except Exception as e:
                logger.error(f"[CONVERTER] Error auto-converting repository {repo_id}: {e}")
                print(f"[CONVERTER] Error: {e}")
                import traceback
                traceback.print_exc()
            finally:
                break
    
    # Create new event loop if needed (for worker context)
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If loop is already running, schedule as task
            asyncio.create_task(run_conversion())
        else:
            # If no loop running, run directly
            loop.run_until_complete(run_conversion())
    except RuntimeError:
        # No event loop, create new one
        asyncio.run(run_conversion())


# Register event handler
from app.shared.event_bus import event_bus
event_bus.subscribe("repository.ingested", handle_repository_ingested)

logger.info("Repository converter initialized and subscribed to repository.ingested events")

