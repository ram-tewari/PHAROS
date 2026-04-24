"""
Pharos Embed Server — standalone, zero app.* imports.

Designed to run in WSL to avoid Windows WMI/antivirus hangs.
Serves /embed and /health, and polls pharos:tasks for resource embedding updates.

Usage (WSL):
    python embed_server.py
    EDGE_EMBED_PORT=8002 python embed_server.py

Note on nomic-embed-text-v1 prefixes:
    Resources in NeonDB were ingested WITHOUT search_document: / search_query:
    prefixes, so this server passes raw text so query embeddings land in the
    same space as stored document vectors.
"""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import text

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

REDIS_URL     = os.environ["UPSTASH_REDIS_REST_URL"].rstrip("/")
REDIS_TOKEN   = os.environ["UPSTASH_REDIS_REST_TOKEN"]
DATABASE_URL  = os.environ.get("DATABASE_URL", "")
EMBED_MODEL   = os.environ.get("EMBEDDING_MODEL_NAME", "nomic-ai/nomic-embed-text-v1")
PORT          = int(os.environ.get("EDGE_EMBED_PORT", "8001"))
POLL_INTERVAL = float(os.environ.get("WORKER_POLL_INTERVAL", "3"))

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("embed_server")

# ---------------------------------------------------------------------------
# Embedding model (loaded once at startup)
# ---------------------------------------------------------------------------

_model = None


def load_model() -> None:
    global _model
    try:
        import torch
        device = "cuda" if torch.cuda.is_available() else "cpu"
        if device == "cuda":
            props = torch.cuda.get_device_properties(0)
            log.info(f"GPU: {props.name} ({props.total_memory // 1024**3}GB)")
    except ImportError:
        device = "cpu"
        log.warning("torch not available — running on CPU")

    log.info(f"Loading {EMBED_MODEL} on {device}...")
    from sentence_transformers import SentenceTransformer
    _model = SentenceTransformer(EMBED_MODEL, trust_remote_code=True, device=device)
    log.info("Model ready")


def embed(text: str) -> list[float]:
    if _model is None:
        raise RuntimeError("model not loaded")
    return _model.encode(text, normalize_embeddings=True).tolist()


# ---------------------------------------------------------------------------
# Upstash Redis (REST API — no redis-py, no TCP connection)
# ---------------------------------------------------------------------------

_http: httpx.AsyncClient | None = None


def _redis() -> httpx.AsyncClient:
    global _http
    if _http is None:
        _http = httpx.AsyncClient(
            headers={"Authorization": f"Bearer {REDIS_TOKEN}"},
            timeout=12.0,
        )
    return _http


async def _rcmd(*args) -> object:
    resp = await _redis().post(REDIS_URL, json=list(args))
    resp.raise_for_status()
    return resp.json().get("result")


async def pop_task() -> dict | None:
    result = await _rcmd("BLPOP", "pharos:tasks", "1")
    if result:
        return json.loads(result[1])
    return None


async def set_task_status(task_id: str, status: str) -> None:
    await _rcmd("SET", f"pharos:task:{task_id}:status", status, "EX", "86400")


# ---------------------------------------------------------------------------
# Database (minimal — only updates resources.embedding)
# ---------------------------------------------------------------------------

_session_factory: async_sessionmaker | None = None


def _async_db_url(url: str) -> str:
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("sqlite:///"):
        return url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
    return url


async def init_db() -> None:
    global _session_factory
    if not DATABASE_URL:
        log.warning("DATABASE_URL not set — embedding updates disabled")
        return
    engine = create_async_engine(_async_db_url(DATABASE_URL), pool_pre_ping=True)
    _session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    log.info("Database connected")


async def _update_resource_embedding(resource_id: str, embedding: list[float]) -> int:
    if _session_factory is None:
        return 0
    # Explicit ::uuid and ::vector casts — asyncpg is strict about
    # parameter types and won't implicitly cast text to uuid/vector.
    # pgvector's text format is '[f1,f2,...]', which matches json.dumps output.
    async with _session_factory() as session:
        # Use CAST() not ::type — the :: syntax collides with
        # SQLAlchemy's :param markers and asyncpg rejects it.
        result = await session.execute(
            text(
                "UPDATE resources "
                "SET embedding = CAST(:emb AS vector) "
                "WHERE id = CAST(:rid AS uuid)"
            ),
            {"emb": json.dumps(embedding), "rid": resource_id},
        )
        await session.commit()
        return result.rowcount or 0


# ---------------------------------------------------------------------------
# Task processing
# ---------------------------------------------------------------------------

async def process_task(task: dict) -> bool:
    task_id = task.get("task_id", "?")
    resource_id = task.get("resource_id")

    if not resource_id:
        log.error(f"Task {task_id}: missing resource_id")
        return False

    log.info(f"Task {task_id}: embedding resource {resource_id}")

    if _session_factory is None:
        log.warning("No DB — skipping resource embedding update")
        return False

    try:
        async with _session_factory() as session:
            row = (await session.execute(
                text("SELECT title, description FROM resources WHERE id = :rid"),
                {"rid": resource_id},
            )).fetchone()

        if not row:
            log.error(f"Task {task_id}: resource {resource_id} not found")
            return False

        text_to_embed = " ".join(filter(None, [row.title, row.description])).strip()
        if not text_to_embed:
            log.warning(f"Task {task_id}: resource {resource_id} has no text to embed")
            return False

        vec = embed(text_to_embed)
        rowcount = await _update_resource_embedding(resource_id, vec)
        log.info(
            f"Task {task_id}: stored embedding dim={len(vec)} rows_updated={rowcount}"
        )
        if rowcount == 0:
            log.warning(
                f"Task {task_id}: UPDATE matched 0 rows for resource {resource_id}"
            )
            return False
        return True

    except Exception as exc:
        log.error(f"Task {task_id} failed: {exc}", exc_info=True)
        return False


# ---------------------------------------------------------------------------
# Queue poll loop
# ---------------------------------------------------------------------------

async def poll_loop() -> None:
    log.info("Queue poll loop started (pharos:tasks)")
    ok = fail = 0
    while True:
        try:
            task = await pop_task()
            if task:
                success = await process_task(task)
                tid = task.get("task_id", "?")
                if success:
                    ok += 1
                    await set_task_status(tid, "completed")
                    log.info(f"Queue: {ok} ok / {fail} failed")
                else:
                    fail += 1
                    await set_task_status(tid, "failed")
            else:
                await asyncio.sleep(POLL_INTERVAL)
        except Exception as exc:
            log.error(f"Poll loop error: {exc}")
            await asyncio.sleep(POLL_INTERVAL)


# ---------------------------------------------------------------------------
# FastAPI
# ---------------------------------------------------------------------------

api = FastAPI(title="Pharos Embed Server", docs_url=None, redoc_url=None)


class EmbedReq(BaseModel):
    text: str


class EmbedResp(BaseModel):
    embedding: list[float]


@api.post("/embed", response_model=EmbedResp)
def embed_endpoint(req: EmbedReq) -> EmbedResp:
    if not req.text.strip():
        raise HTTPException(400, "text must be non-empty")
    return EmbedResp(embedding=embed(req.text))


@api.get("/health")
def health():
    return {"status": "ok", "model": EMBED_MODEL}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main() -> None:
    log.info("=" * 60)
    log.info("Pharos Embed Server (standalone)")
    log.info("=" * 60)

    load_model()
    await init_db()
    asyncio.create_task(poll_loop())

    log.info(f"Listening on 0.0.0.0:{PORT}")
    cfg = uvicorn.Config(api, host="0.0.0.0", port=PORT, log_level="warning", access_log=False)
    await uvicorn.Server(cfg).serve()


if __name__ == "__main__":
    asyncio.run(main())
