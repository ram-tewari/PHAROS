"""
Edge Worker for Phase 19 - Hybrid Edge-Cloud Orchestration

This worker runs locally on GPU-enabled hardware and processes repository
ingestion tasks from the Upstash Redis queue. It performs:
1. Repository cloning and parsing
2. Dependency graph construction
3. Neural graph training (Node2Vec)
4. Embedding upload to Qdrant

Requirements: 3.1, 3.2, 3.4, 8.3
"""

import os
import sys
import time
import json
import signal
import torch
from datetime import datetime
from typing import Dict, Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import services
try:
    from upstash_redis import Redis
    from app.modules.graph.neural_service import NeuralGraphService
    from app.utils.repo_parser import RepositoryParser
except ImportError as e:
    print(f"❌ Import Error: {e}")
    print("Make sure you've installed requirements-edge.txt")
    # Only exit when run as a script; re-raise otherwise so tests can mock
    if __name__ == "__main__":
        sys.exit(1)
    else:
        raise


# ============================================================================
# Standalone process_job function (for testing and direct invocation)
# ============================================================================


async def process_job(job_data: dict) -> dict:
    """
    Process a repository ingestion job.

    This is a standalone function that can be imported and called directly
    for testing and integration purposes.

    Args:
        job_data: Dictionary containing:
            - repo_url: Repository URL to process
            - user_id: Optional user ID who submitted the job
            - submitted_at: Optional ISO timestamp when job was submitted
            - ttl: Optional time-to-live in seconds (default 86400)

    Returns:
        Dictionary with:
            - status: "completed" or "failed"
            - result: Result data on success
            - error: Error message on failure

    Example:
        >>> result = await process_job({"repo_url": "https://github.com/user/repo"})
        >>> print(result["status"])
        'completed'
    """
    from app.config.settings import get_settings
    from app.modules.resources.logic.repo_ingestion import ingest_repository
    from app.shared.database import get_db_session
    from app.utils.repo_parser import RepositoryParser

    settings = get_settings()
    repo_url = job_data.get("repo_url")
    user_id = job_data.get("user_id")

    # Validate inputs
    if not repo_url:
        raise ValueError("repo_url is required")

    try:
        # Get database session and process repository
        async with get_db_session() as session:
            result = await ingest_repository(
                repo_url=repo_url, user_id=user_id, session=session, settings=settings
            )

        return {"status": "completed", "result": result, "error": None}

    except Exception as e:
        return {"status": "failed", "result": None, "error": str(e)}


class EdgeWorker:
    """
    Edge Worker that processes repository ingestion tasks.

    Polls Redis queue for tasks, processes them using GPU acceleration,
    and uploads results to Qdrant Cloud.
    """

    def __init__(self):
        """
        Initialize the edge worker with credential validation.

        Validates Redis credentials on startup and fails fast with
        clear error messages if credentials are invalid.

        Requirements: 11.1, 11.2
        """
        # Validate Redis credentials are configured
        redis_url = os.getenv("UPSTASH_REDIS_REST_URL")
        redis_token = os.getenv("UPSTASH_REDIS_REST_TOKEN")

        if not redis_url:
            print("❌ Configuration Error: UPSTASH_REDIS_REST_URL not set")
            print("   Please set UPSTASH_REDIS_REST_URL in your .env.edge file")
            sys.exit(1)

        if not redis_token:
            print("❌ Configuration Error: UPSTASH_REDIS_REST_TOKEN not set")
            print("   Please set UPSTASH_REDIS_REST_TOKEN in your .env.edge file")
            sys.exit(1)

        # Initialize Redis client
        try:
            self.redis = Redis(url=redis_url, token=redis_token)

            # Validate credentials by attempting a ping
            self.redis.ping()
            print("✅ Redis connection validated")

        except Exception as e:
            print(f"❌ Redis Connection Error: {e}")
            print(
                "   Please check your UPSTASH_REDIS_REST_URL and UPSTASH_REDIS_REST_TOKEN"
            )
            print("   Credentials may be invalid or Redis service may be unavailable")
            sys.exit(1)

        # Detect CUDA availability and log hardware configuration
        self.device = "cuda" if torch.cuda.is_available() else "cpu"

        print("🔥 Edge Worker Online")
        print("=" * 60)

        if self.device == "cuda":
            print(f"   GPU: {torch.cuda.get_device_name(0)}")
            print(f"   CUDA Version: {torch.version.cuda}")
            print(
                f"   GPU Memory: {torch.cuda.get_device_properties(0).total_memory / 1e9:.2f} GB"
            )
        else:
            print("   Running on CPU (CUDA not available)")

        print(f"   Device: {self.device}")
        print("=" * 60)

        # Initialize services
        self.parser = RepositoryParser()
        self.neural_service = NeuralGraphService(device=self.device)

        # Set worker status to "Idle" on startup
        self.redis.set("worker_status", "Idle")

        # Shutdown flag
        self.shutdown_requested = False

        # Register signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)

    def _handle_shutdown(self, signum, frame):
        """Handle SIGINT/SIGTERM for graceful shutdown."""
        print("\n🛑 Shutdown signal received. Finishing current job...")
        self.shutdown_requested = True

    def process_job(self, task_data: Dict) -> None:
        """
        Process a single repository ingestion job.

        Args:
            task_data: Task metadata dictionary containing:
                - repo_url: Repository URL
                - submitted_at: ISO timestamp when task was submitted
                - ttl: Time-to-live in seconds

        Requirements: 3.5, 3.7, 6.5, 9.3, 9.4
        """
        job_start = datetime.now()
        repo_path = None

        # Extract task data
        repo_url = task_data.get("repo_url")
        submitted_at = task_data.get("submitted_at")
        ttl = task_data.get("ttl", 86400)  # Default 24 hours

        # Check if task is stale (older than TTL)
        if submitted_at:
            try:
                submitted_time = datetime.fromisoformat(submitted_at)
                age_seconds = (job_start - submitted_time).total_seconds()

                if age_seconds > ttl:
                    print(
                        f"⏭️  Skipping stale task (age: {age_seconds:.0f}s, TTL: {ttl}s): {repo_url}"
                    )

                    # Record as skipped in job history
                    job_record = {
                        "repo_url": repo_url,
                        "status": "skipped",
                        "reason": "Task exceeded TTL",
                        "age_seconds": age_seconds,
                        "ttl": ttl,
                        "timestamp": job_start.isoformat(),
                    }
                    self.redis.lpush("job_history", json.dumps(job_record))
                    self.redis.ltrim("job_history", 0, 99)  # Keep last 100 jobs
                    return
            except (ValueError, TypeError) as e:
                print(f"⚠️  Warning: Could not parse submitted_at timestamp: {e}")

        try:
            # Update status to "Training Graph on {repo_url}"
            self.redis.set("worker_status", f"Training Graph on {repo_url}")

            print(f"⚡ Received Job: {repo_url}")

            # Clone and parse repository
            print("📥 Cloning repository...")
            repo_path = self.parser.clone_repository(repo_url)

            # Build dependency graph
            print("📊 Building dependency graph...")
            dependency_graph = self.parser.build_dependency_graph(repo_path)

            # Train embeddings
            print("🧠 Training Node2Vec...")
            embeddings = self.neural_service.train_embeddings(
                edge_index=dependency_graph.edge_index,
                num_nodes=dependency_graph.num_nodes,
            )

            # Upload to Qdrant
            print("☁️  Uploading embeddings to Qdrant...")
            self.neural_service.upload_embeddings(
                embeddings=embeddings,
                file_paths=dependency_graph.file_paths,
                repo_url=repo_url,
            )

            # Record success in job history
            job_end = datetime.now()
            duration = (job_end - job_start).total_seconds()

            job_record = {
                "repo_url": repo_url,
                "status": "complete",
                "duration_seconds": duration,
                "files_processed": dependency_graph.num_nodes,
                "embeddings_generated": len(embeddings),
                "timestamp": job_end.isoformat(),
            }

            self.redis.lpush("job_history", json.dumps(job_record))
            self.redis.ltrim("job_history", 0, 99)  # Keep last 100 jobs

            print(f"✅ Job Complete ({duration:.2f}s)")

        except Exception as e:
            # Handle errors and record failure
            print(f"❌ Error: {e}")

            # Update status to show error
            error_msg = str(e)[:100]  # Truncate long errors
            self.redis.set("worker_status", f"Error: {error_msg}")

            # Record failure in job history
            job_record = {
                "repo_url": repo_url,
                "status": "failed",
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }
            self.redis.lpush("job_history", json.dumps(job_record))
            self.redis.ltrim("job_history", 0, 99)

            # Clean up GPU memory if CUDA error
            if self.device == "cuda" and "CUDA" in str(e):
                torch.cuda.empty_cache()
                print("🧹 Cleared GPU memory")

        finally:
            # Always clean up temporary files
            if repo_path:
                self.parser.cleanup(repo_path)

            # Update status back to "Idle"
            self.redis.set("worker_status", "Idle")

    def run(self) -> None:
        """
        Main worker loop that polls queue every 2 seconds.

        Requirements: 3.4, 8.3
        """
        print("👀 Polling for jobs (Ctrl+C to stop)...")
        print()

        while not self.shutdown_requested:
            try:
                # Poll for jobs (LPOP removes from queue)
                job = self.redis.lpop("ingest_queue")

                if job:
                    # Parse task data (handle both old string format and new JSON format)
                    task_str = job.decode() if isinstance(job, bytes) else job

                    try:
                        task_data = json.loads(task_str)
                    except json.JSONDecodeError:
                        # Legacy format: plain URL string
                        task_data = {
                            "repo_url": task_str,
                            "submitted_at": None,
                            "ttl": 86400,
                        }

                    # Process the job
                    self.process_job(task_data)
                else:
                    # Sleep when idle (poll every 2 seconds)
                    time.sleep(2)

            except KeyboardInterrupt:
                # Handle Ctrl+C gracefully
                print("\n🛑 Shutting down gracefully...")
                break

            except Exception as e:
                # Handle Redis connection errors and other exceptions
                print(f"❌ Worker Error: {e}")
                self.redis.set("worker_status", f"Error: {str(e)}")

                # Attempt reconnection after delay
                print("🔄 Attempting to reconnect in 5 seconds...")
                time.sleep(5)

        # Cleanup on shutdown
        print("🛑 Worker stopped")
        self.redis.set("worker_status", "Offline")


def main():
    """Main entry point for the edge worker."""
    # Verify required environment variables
    required_vars = [
        "UPSTASH_REDIS_REST_URL",
        "UPSTASH_REDIS_REST_TOKEN",
        "QDRANT_URL",
        "QDRANT_API_KEY",
    ]

    missing_vars = [var for var in required_vars if not os.getenv(var)]

    if missing_vars:
        print("❌ Missing required environment variables:")
        for var in missing_vars:
            print(f"   - {var}")
        print("\nPlease set these in your .env.edge file")
        sys.exit(1)

    # Create and run worker
    worker = EdgeWorker()
    worker.run()


if __name__ == "__main__":
    main()
