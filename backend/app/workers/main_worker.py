"""
Pharos Unified Edge Worker

Single long-running process that:
  - Loads the local embedding model (RTX 4070).
  - Serves the FastAPI /embed endpoint on port EDGE_EMBED_PORT (default 8001).
  - Blocks on BOTH Redis queues with one connection:
        BLPOP pharos:tasks ingest_queue 30
    Routing by source queue:
        pharos:tasks   -> resource-level ingestion (process_ingestion)
        ingest_queue   -> repo-level clone/parse/embed/store

Upstash quota note: timeout=30s caps idle commands at ~2,880/day, well under
the 100,000/month free tier. DO NOT lower the timeout without re-doing the math.

Usage:
    python worker.py            # via dispatcher
    python -m app.workers.main_worker
    bash start_worker.sh        # bulletproof launcher
"""

from __future__ import annotations

import asyncio
import ast
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Queue keys are exported so the dispatch banner in start_worker.sh stays in sync.
RESOURCE_QUEUE = "pharos:tasks"
REPO_QUEUE = "ingest_queue"
QUEUES = [RESOURCE_QUEUE, REPO_QUEUE]
BLPOP_TIMEOUT_SECONDS = 30


# ---------------------------------------------------------------------------
# Boot checks
# ---------------------------------------------------------------------------

def check_environment() -> None:
    """Validate required environment variables for EDGE mode."""
    required = [
        "MODE",
        "UPSTASH_REDIS_REST_URL",
        "UPSTASH_REDIS_REST_TOKEN",
        "DATABASE_URL",
    ]
    missing = [v for v in required if not os.getenv(v)]
    if missing:
        logger.error(f"Missing required env vars: {', '.join(missing)}")
        sys.exit(1)

    if os.getenv("MODE") != "EDGE":
        logger.error(f"MODE must be 'EDGE', got: {os.getenv('MODE')!r}")
        sys.exit(1)

    logger.info("Environment validated (MODE=EDGE)")


def check_gpu() -> str:
    """Log GPU status; never abort if CUDA is missing."""
    try:
        import torch
        if torch.cuda.is_available():
            name = torch.cuda.get_device_name(0)
            mem = torch.cuda.get_device_properties(0).total_memory / 1e9
            logger.info(f"GPU: {name} ({mem:.1f} GB), CUDA {torch.version.cuda}")
            return "cuda"
        logger.warning("CUDA unavailable — falling back to CPU")
        return "cpu"
    except ImportError:
        logger.error("PyTorch not installed; install requirements-edge.txt")
        sys.exit(1)


def load_embedding_model():
    from app.shared.embeddings import EmbeddingService

    logger.info("Loading embedding model...")
    t0 = time.time()
    svc = EmbeddingService()
    if not svc.warmup():
        logger.error("Embedding warmup failed")
        sys.exit(1)
    logger.info(f"Embedding model ready in {time.time() - t0:.1f}s")
    return svc


async def connect_to_redis():
    from app.shared.upstash_redis import UpstashRedisClient

    client = UpstashRedisClient()
    if not await client.ping():
        logger.error("Upstash PING failed")
        sys.exit(1)
    logger.info("Upstash Redis connected")
    return client


async def connect_to_database():
    from app.config.settings import get_settings
    from app.shared.database import get_db, init_database

    settings = get_settings()
    db_url = settings.get_database_url()
    init_database(db_url, env=settings.ENV)
    logger.info("Database connected")
    return get_db


# ---------------------------------------------------------------------------
# Resource-level handler (formerly edge.py / process_task)
# ---------------------------------------------------------------------------

async def handle_resource_task(task: Dict[str, Any]) -> bool:
    """Run the full single-resource ingestion pipeline in a worker thread."""
    task_id = task.get("task_id")
    resource_id = task.get("resource_id")
    if resource_id is None:
        logger.error(f"resource task {task_id} missing resource_id; payload={task}")
        return False

    logger.info(f"[RESOURCE] task={task_id} resource_id={resource_id}")

    def _run_sync() -> bool:
        from app.modules.resources.service import process_ingestion
        try:
            t0 = time.time()
            process_ingestion(resource_id=resource_id)
            logger.info(
                f"[RESOURCE] resource_id={resource_id} done in {time.time() - t0:.1f}s"
            )
            return True
        except Exception as exc:
            logger.error(
                f"[RESOURCE] resource_id={resource_id} failed: {exc}",
                exc_info=True,
            )
            return False

    return await asyncio.get_event_loop().run_in_executor(None, _run_sync)


# ---------------------------------------------------------------------------
# Repository handler (formerly RepositoryWorker in repo.py)
# ---------------------------------------------------------------------------

class RepositoryIngestor:
    """Clone -> parse -> AST -> embed -> persist a GitHub repository."""

    def __init__(self, embedding_service):
        self.embedding_service = embedding_service

    async def ingest(self, task: Dict[str, Any]) -> bool:
        repo_url = task.get("repo_url") or task.get("payload")
        if not repo_url:
            logger.error(f"[REPO] task missing repo_url: {task}")
            return False

        started = datetime.now()
        logger.info(f"[REPO] ingest {repo_url}")

        temp_dir: Optional[Path] = None
        try:
            temp_dir = Path(tempfile.mkdtemp(prefix="pharos_repo_"))
            if not self._clone(repo_url, temp_dir):
                return False

            metadata = self._parse(temp_dir)
            embeddings = self._embed(metadata)
            repo_id = await self._persist(repo_url, metadata, embeddings)

            duration = (datetime.now() - started).total_seconds()
            logger.info(
                f"[REPO] {repo_url} -> {repo_id} | "
                f"files={metadata['total_files']} lines={metadata['total_lines']} "
                f"embeddings={len(embeddings)} duration={duration:.1f}s"
            )
            return True
        except Exception as exc:
            logger.error(f"[REPO] {repo_url} failed: {exc}", exc_info=True)
            return False
        finally:
            if temp_dir and temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)

    @staticmethod
    def _clone(repo_url: str, target_dir: Path) -> bool:
        if not repo_url.startswith(("http://", "https://", "git@")):
            repo_url = f"https://{repo_url}.git"
        elif not repo_url.endswith(".git"):
            repo_url = f"{repo_url}.git"

        result = subprocess.run(
            ["git", "clone", "--depth", "1", repo_url, str(target_dir)],
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode != 0:
            logger.error(f"[REPO] clone failed: {result.stderr.strip()}")
            return False
        return True

    @staticmethod
    def _parse(repo_dir: Path) -> Dict[str, Any]:
        meta: Dict[str, Any] = {
            "files": [],
            "total_files": 0,
            "total_lines": 0,
            "languages": {},
            "imports": {},
            "functions": [],
            "classes": [],
        }
        py_files = list(repo_dir.rglob("*.py"))
        meta["total_files"] = len(py_files)

        for py in py_files:
            try:
                rel = py.relative_to(repo_dir).as_posix()
                content = py.read_text(encoding="utf-8", errors="ignore")
                lines = len(content.splitlines())
                file_data: Dict[str, Any] = {
                    "path": rel,
                    "size": py.stat().st_size,
                    "lines": lines,
                    "imports": [],
                    "functions": [],
                    "classes": [],
                }
                try:
                    tree = ast.parse(content, filename=rel)
                    for node in ast.walk(tree):
                        if isinstance(node, ast.Import):
                            file_data["imports"].extend(a.name for a in node.names)
                        elif isinstance(node, ast.ImportFrom) and node.module:
                            file_data["imports"].append(node.module)
                    file_data["functions"] = [
                        n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
                    ]
                    file_data["classes"] = [
                        n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)
                    ]
                except SyntaxError:
                    pass

                if file_data["imports"]:
                    meta["imports"][rel] = file_data["imports"]
                meta["functions"].extend(
                    {"file": rel, "name": f} for f in file_data["functions"]
                )
                meta["classes"].extend(
                    {"file": rel, "name": c} for c in file_data["classes"]
                )
                meta["files"].append(file_data)
                meta["total_lines"] += lines
            except Exception as exc:
                logger.warning(f"[REPO] parse failed for {py}: {exc}")

        meta["languages"]["Python"] = len(py_files)
        return meta

    def _embed(self, metadata: Dict[str, Any]) -> Dict[str, list]:
        embeddings: Dict[str, list] = {}
        for file_data in metadata["files"]:
            try:
                rel = file_data["path"].replace("\\", "/")
                summary = " | ".join([
                    f"File: {rel}",
                    f"Functions: {', '.join(file_data['functions'][:10])}",
                    f"Classes: {', '.join(file_data['classes'][:10])}",
                    f"Imports: {', '.join(file_data['imports'][:10])}",
                ])
                vec = self.embedding_service.generate_embedding(summary)
                if vec:
                    embeddings[rel] = vec
            except Exception as exc:
                logger.warning(f"[REPO] embed failed for {file_data['path']}: {exc}")
        return embeddings

    @staticmethod
    async def _persist(
        repo_url: str,
        metadata: Dict[str, Any],
        embeddings: Dict[str, list],
    ) -> str:
        from sqlalchemy import text
        from app.shared.database import get_db

        repo_id = ""
        async for session in get_db():
            try:
                meta_json = {k: v for k, v in metadata.items() if k != "embeddings"}
                existing = await session.execute(
                    text("SELECT id FROM repositories WHERE url = :url"),
                    {"url": repo_url},
                )
                existing_id = existing.scalar_one_or_none()
                if existing_id:
                    repo_id = str(existing_id)
                    await session.execute(
                        text(
                            """
                            UPDATE repositories
                            SET metadata = CAST(:metadata AS jsonb),
                                total_files = :total_files,
                                total_lines = :total_lines,
                                updated_at = NOW()
                            WHERE id = :repo_id
                            """
                        ),
                        {
                            "repo_id": repo_id,
                            "metadata": json.dumps(meta_json),
                            "total_files": metadata["total_files"],
                            "total_lines": metadata["total_lines"],
                        },
                    )
                else:
                    inserted = await session.execute(
                        text(
                            """
                            INSERT INTO repositories (
                                id, url, name, metadata,
                                total_files, total_lines,
                                created_at, updated_at
                            ) VALUES (
                                gen_random_uuid(), :url, :name, CAST(:metadata AS jsonb),
                                :total_files, :total_lines,
                                NOW(), NOW()
                            ) RETURNING id
                            """
                        ),
                        {
                            "url": repo_url,
                            "name": repo_url.split("/")[-1],
                            "metadata": json.dumps(meta_json),
                            "total_files": metadata["total_files"],
                            "total_lines": metadata["total_lines"],
                        },
                    )
                    repo_id = str(inserted.scalar_one())

                await session.commit()

                for idx, file_data in enumerate(metadata["files"], 1):
                    try:
                        rel = file_data["path"].replace("\\", "/")
                        github_blob = f"{repo_url}/blob/HEAD/{rel}"
                        github_raw = (
                            "https://raw.githubusercontent.com/"
                            f"{repo_url.replace('github.com/', '')}/HEAD/{rel}"
                        )
                        identifier = f"repo:{repo_id}:{rel}"
                        file_meta = {
                            "repo_id": repo_id,
                            "repo_url": repo_url,
                            "repo_name": repo_url.split("/")[-1],
                            "file_path": rel,
                            "file_size": file_data.get("size", 0),
                            "lines": file_data.get("lines", 0),
                            "imports": file_data.get("imports", []),
                            "functions": file_data.get("functions", []),
                            "classes": file_data.get("classes", []),
                        }

                        res = await session.execute(
                            text(
                                """
                                INSERT INTO resources (
                                    id, title, type, format, source, identifier,
                                    description, subject, read_status, quality_score,
                                    created_at, updated_at
                                ) VALUES (
                                    gen_random_uuid(), :title, :type, :format, :source, :identifier,
                                    :description, CAST(:subject AS jsonb), :read_status, :quality_score,
                                    NOW(), NOW()
                                ) RETURNING id
                                """
                            ),
                            {
                                "title": rel,
                                "type": "code",
                                "format": "text/x-python",
                                "source": github_blob,
                                "identifier": identifier,
                                "description": json.dumps(file_meta),
                                "subject": json.dumps(file_data.get("imports", [])[:10]),
                                "read_status": "unread",
                                "quality_score": 0.0,
                            },
                        )
                        resource_id = str(res.scalar_one())

                        semantic_summary = " | ".join([
                            f"File: {rel}",
                            f"Functions: {', '.join(file_data.get('functions', [])[:10])}",
                            f"Classes: {', '.join(file_data.get('classes', [])[:10])}",
                            f"Imports: {', '.join(file_data.get('imports', [])[:10])}",
                        ])

                        await session.execute(
                            text(
                                """
                                INSERT INTO document_chunks (
                                    id, resource_id, chunk_index,
                                    content, semantic_summary,
                                    is_remote, github_uri, branch_reference,
                                    start_line, end_line,
                                    ast_node_type, symbol_name,
                                    chunk_metadata, created_at
                                ) VALUES (
                                    gen_random_uuid(), :resource_id, 0,
                                    NULL, :semantic_summary,
                                    TRUE, :github_uri, 'HEAD',
                                    1, :end_line,
                                    'module', :symbol_name,
                                    CAST(:chunk_metadata AS jsonb), NOW()
                                )
                                """
                            ),
                            {
                                "resource_id": resource_id,
                                "semantic_summary": semantic_summary,
                                "github_uri": github_raw,
                                "end_line": file_data.get("lines", 0),
                                "symbol_name": rel.replace("/", ".").replace(".py", ""),
                                "chunk_metadata": json.dumps({
                                    "file_path": rel,
                                    "language": "python",
                                    "lines": file_data.get("lines", 0),
                                    "functions": file_data.get("functions", []),
                                    "classes": file_data.get("classes", []),
                                    "imports": file_data.get("imports", []),
                                }),
                            },
                        )

                        if rel in embeddings:
                            await session.execute(
                                text(
                                    """
                                    UPDATE resources
                                    SET embedding = CAST(:embedding AS vector)
                                    WHERE id = :resource_id
                                    """
                                ),
                                {
                                    "resource_id": resource_id,
                                    "embedding": json.dumps(embeddings[rel]),
                                },
                            )

                        if idx % 100 == 0:
                            await session.commit()
                    except Exception as exc:
                        logger.warning(f"[REPO] persist file failed: {exc}")

                await session.commit()
                return repo_id
            except Exception:
                await session.rollback()
                raise
            finally:
                break
        return repo_id


# ---------------------------------------------------------------------------
# FastAPI /embed server (kept from edge.py)
# ---------------------------------------------------------------------------

async def run_embed_server(embedding_service) -> None:
    import uvicorn
    from fastapi import FastAPI, HTTPException
    from pydantic import BaseModel

    app = FastAPI(title="Pharos Edge Embed Server", docs_url=None, redoc_url=None)

    class EmbedRequest(BaseModel):
        text: str

    class EmbedResponse(BaseModel):
        embedding: list[float]

    @app.post("/embed", response_model=EmbedResponse)
    def embed(req: EmbedRequest) -> EmbedResponse:
        text = (req.text or "").strip()
        if not text:
            raise HTTPException(status_code=400, detail="text must be non-empty")
        vec = embedding_service.generate_embedding(text)
        if not vec:
            raise HTTPException(status_code=503, detail="model unavailable")
        return EmbedResponse(embedding=vec)

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "model": embedding_service.embedding_generator.model_name}

    port = int(os.getenv("EDGE_EMBED_PORT", "8001"))
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="info", access_log=False)
    logger.info(f"FastAPI /embed listening on 127.0.0.1:{port}")
    await uvicorn.Server(config).serve()


# ---------------------------------------------------------------------------
# Unified poll/dispatch loop
# ---------------------------------------------------------------------------

async def poll_and_dispatch(redis_client, embedding_service) -> None:
    """One BLPOP, two queues. Route by source queue, never crash on a poison pill."""
    repo_ingestor = RepositoryIngestor(embedding_service)
    processed = 0
    failed = 0

    logger.info(
        f"Polling {QUEUES} with BLPOP timeout={BLPOP_TIMEOUT_SECONDS}s "
        f"(~{86400 // BLPOP_TIMEOUT_SECONDS} idle cmds/day)"
    )

    while True:
        try:
            popped = await redis_client.pop_from_queues(
                QUEUES, timeout=BLPOP_TIMEOUT_SECONDS
            )
            if popped is None:
                continue  # idle, just re-block

            queue_key, task = popped
            task_id = task.get("task_id")
            try:
                if queue_key == REPO_QUEUE:
                    success = await repo_ingestor.ingest(task)
                elif queue_key == RESOURCE_QUEUE:
                    success = await handle_resource_task(task)
                else:
                    logger.warning(f"Unknown queue {queue_key!r}; dropping task")
                    success = False

                if task_id:
                    await redis_client.update_task_status(
                        task_id, "completed" if success else "failed"
                    )
                processed += int(success)
                failed += int(not success)
                logger.info(f"Totals: processed={processed} failed={failed}")
            except Exception as exc:
                # Poison-pill containment: log + mark failed, keep the loop alive.
                failed += 1
                logger.error(
                    f"Handler crash on queue={queue_key} task={task_id}: {exc}",
                    exc_info=True,
                )
                if task_id:
                    try:
                        await redis_client.update_task_status(task_id, "failed")
                    except Exception:
                        logger.exception("Failed to mark task as failed")
        except KeyboardInterrupt:
            logger.info("Shutdown requested; exiting dispatch loop")
            return
        except Exception as exc:
            # Outer guard: never let a transport blip kill the worker.
            logger.error(f"Dispatch loop error: {exc}", exc_info=True)
            await asyncio.sleep(2)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    logger.info("=" * 64)
    logger.info("Pharos Unified Edge Worker")
    logger.info(f"Queues : {QUEUES}")
    logger.info(f"BLPOP  : {BLPOP_TIMEOUT_SECONDS}s timeout (Upstash quota-safe)")
    logger.info("=" * 64)

    check_environment()
    check_gpu()
    embedding_service = load_embedding_model()
    redis_client = await connect_to_redis()
    await connect_to_database()

    logger.info("Boot complete; serving /embed and dispatching tasks")

    await asyncio.gather(
        run_embed_server(embedding_service),
        poll_and_dispatch(redis_client, embedding_service),
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Worker stopped")
        sys.exit(0)
    except Exception as exc:
        logger.error(f"Fatal error: {exc}", exc_info=True)
        sys.exit(1)
