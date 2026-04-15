"""
Pharos Edge Worker - Local GPU Processing

This worker polls Upstash Redis for embedding tasks and processes them
using the local GPU. It's part of the hybrid edge-cloud architecture where:
- Cloud API (Render): Lightweight API server, queues tasks
- Edge Worker (Local): Heavy ML workloads, processes tasks

Usage:
    python -m app.edge_worker

Environment Variables:
    MODE=EDGE (required)
    UPSTASH_REDIS_REST_URL (required)
    UPSTASH_REDIS_REST_TOKEN (required)
    DATABASE_URL (required, same as cloud API)
    EMBEDDING_MODEL_NAME (optional, default: nomic-ai/nomic-embed-text-v1)
    WORKER_POLL_INTERVAL (optional, default: 2 seconds)
"""

import asyncio
import logging
import os
import sys
import time
from typing import Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("edge_worker.log"),
    ],
)
logger = logging.getLogger(__name__)


def check_environment():
    """Validate required environment variables."""
    required_vars = [
        "MODE",
        "UPSTASH_REDIS_REST_URL",
        "UPSTASH_REDIS_REST_TOKEN",
        "DATABASE_URL",
    ]

    missing = []
    for var in required_vars:
        if not os.getenv(var):
            missing.append(var)

    if missing:
        logger.error(f"Missing required environment variables: {', '.join(missing)}")
        logger.error("Please set these variables before starting the edge worker.")
        sys.exit(1)

    # Validate MODE
    mode = os.getenv("MODE")
    if mode != "EDGE":
        logger.error(f"MODE must be 'EDGE' for edge worker, got: {mode}")
        sys.exit(1)

    logger.info("✓ Environment variables validated")


def check_gpu():
    """Check GPU availability and log device information."""
    try:
        import torch

        if torch.cuda.is_available():
            device_name = torch.cuda.get_device_name(0)
            device_memory = torch.cuda.get_device_properties(0).total_memory / 1e9
            cuda_version = torch.version.cuda

            logger.info("🔥 GPU Detected:")
            logger.info(f"   Device: {device_name}")
            logger.info(f"   Memory: {device_memory:.1f} GB")
            logger.info(f"   CUDA Version: {cuda_version}")
            logger.info(f"   PyTorch Version: {torch.__version__}")

            return "cuda"
        else:
            logger.warning("⚠️  CUDA not available, falling back to CPU")
            logger.warning(
                "   This will be slower. Check NVIDIA drivers and CUDA installation."
            )
            return "cpu"
    except ImportError:
        logger.error("❌ PyTorch not installed!")
        logger.error("   Install with: pip install -r requirements-edge.txt")
        sys.exit(1)


def load_embedding_model():
    """Load the embedding model."""
    from app.shared.embeddings import EmbeddingService

    logger.info("Loading embedding model...")
    start_time = time.time()

    try:
        embedding_service = EmbeddingService()
        if embedding_service.warmup():
            elapsed = time.time() - start_time
            logger.info(f"✓ Embedding model loaded successfully ({elapsed:.1f}s)")
            return embedding_service
        else:
            logger.error("❌ Embedding model warmup failed")
            sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Failed to load embedding model: {e}", exc_info=True)
        sys.exit(1)


async def connect_to_redis():
    """Connect to Upstash Redis."""
    from app.shared.upstash_redis import UpstashRedisClient

    logger.info("Connecting to Upstash Redis...")

    try:
        redis_client = UpstashRedisClient()
        # Test connection
        await redis_client.ping()
        logger.info("✓ Connected to Upstash Redis")
        return redis_client
    except Exception as e:
        logger.error(f"❌ Failed to connect to Upstash Redis: {e}", exc_info=True)
        sys.exit(1)


async def connect_to_database():
    """Connect to database."""
    from app.shared.database import get_async_session
    from app.config.settings import get_settings

    logger.info("Connecting to database...")

    try:
        settings = get_settings()
        db_url = settings.get_database_url()
        logger.info(f"   Database: {db_url.split('@')[1] if '@' in db_url else 'local'}")

        # Test connection
        async for session in get_async_session():
            await session.execute("SELECT 1")
            logger.info("✓ Connected to database")
            break

        return get_async_session
    except Exception as e:
        logger.error(f"❌ Failed to connect to database: {e}", exc_info=True)
        sys.exit(1)


async def process_task(task: dict, embedding_service, db_session_factory):
    """Process a single embedding task."""
    task_id = task.get("task_id")
    resource_id = task.get("resource_id")
    text = task.get("text")

    logger.info(f"Processing task {task_id} for resource {resource_id}")

    try:
        # Generate embedding
        start_time = time.time()
        embedding = embedding_service.generate_embedding(text)
        elapsed = time.time() - start_time

        if not embedding:
            logger.error(f"Failed to generate embedding for task {task_id}")
            return False

        logger.info(
            f"✓ Generated embedding ({len(embedding)} dims) in {elapsed*1000:.0f}ms"
        )

        # Store in database
        async for session in db_session_factory():
            try:
                from app.database import models as db_models

                # Update resource with embedding
                resource = await session.get(db_models.Resource, resource_id)
                if resource:
                    resource.embedding = embedding
                    await session.commit()
                    logger.info(f"✓ Stored embedding for resource {resource_id}")
                    return True
                else:
                    logger.error(f"Resource {resource_id} not found")
                    return False
            except Exception as e:
                logger.error(f"Database error: {e}", exc_info=True)
                await session.rollback()
                return False
            finally:
                await session.close()

    except Exception as e:
        logger.error(f"Error processing task {task_id}: {e}", exc_info=True)
        return False


async def poll_and_process(redis_client, embedding_service, db_session_factory):
    """Poll Redis for tasks and process them."""
    from app.config.settings import get_settings

    settings = get_settings()
    poll_interval = settings.WORKER_POLL_INTERVAL

    logger.info(f"Starting task polling (interval: {poll_interval}s)")
    logger.info("Press Ctrl+C to stop")

    tasks_processed = 0
    tasks_failed = 0

    while True:
        try:
            # Poll for next task
            task = await redis_client.pop_task()

            if task:
                logger.info(f"📥 Received task: {task.get('task_id')}")

                # Process task
                success = await process_task(task, embedding_service, db_session_factory)

                if success:
                    tasks_processed += 1
                    logger.info(
                        f"✅ Task completed (total: {tasks_processed} processed, {tasks_failed} failed)"
                    )

                    # Update task status in Redis
                    await redis_client.update_task_status(
                        task.get("task_id"), "completed"
                    )
                else:
                    tasks_failed += 1
                    logger.error(
                        f"❌ Task failed (total: {tasks_processed} processed, {tasks_failed} failed)"
                    )

                    # Update task status in Redis
                    await redis_client.update_task_status(task.get("task_id"), "failed")
            else:
                # No tasks available, wait before polling again
                await asyncio.sleep(poll_interval)

        except KeyboardInterrupt:
            logger.info("\n🛑 Shutting down edge worker...")
            logger.info(
                f"   Total tasks processed: {tasks_processed} (success), {tasks_failed} (failed)"
            )
            break
        except Exception as e:
            logger.error(f"Error in polling loop: {e}", exc_info=True)
            await asyncio.sleep(poll_interval)


async def main():
    """Main entry point for edge worker."""
    logger.info("=" * 60)
    logger.info("Pharos Edge Worker - Local GPU Processing")
    logger.info("=" * 60)

    # 1. Check environment
    check_environment()

    # 2. Check GPU
    device = check_gpu()

    # 3. Load embedding model
    embedding_service = load_embedding_model()

    # 4. Connect to Redis
    redis_client = await connect_to_redis()

    # 5. Connect to database
    db_session_factory = await connect_to_database()

    logger.info("=" * 60)
    logger.info("✓ Edge worker ready - waiting for tasks...")
    logger.info("=" * 60)

    # 6. Start polling and processing
    await poll_and_process(redis_client, embedding_service, db_session_factory)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\n👋 Edge worker stopped")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
