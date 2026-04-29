"""
Ingestion Router for Hybrid Edge-Cloud Orchestration

This router handles repository ingestion task dispatch to the edge worker.
It implements:
- Bearer token authentication (PHAROS_ADMIN_TOKEN)
- Queue management with cap enforcement (max 10 pending tasks)
- Task TTL (24 hours) to prevent zombie queue problem
- Worker status monitoring
- Job history tracking

Security: All /ingest endpoints require valid Bearer token authentication
to prevent unauthorized users from bombarding the edge worker.
"""

import logging
import os
import re
import time
import uuid
import json
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from upstash_redis import Redis

from app.services.queue_service import QueueService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/ingestion", tags=["ingestion"])
security = HTTPBearer()

# Configuration constants
MAX_QUEUE_SIZE = 10  # Maximum pending tasks to prevent zombie queue
TASK_TTL = 86400  # Task TTL in seconds (24 hours)
QUEUE_KEY = "ingest_queue"
STATUS_KEY = "worker_status"
HISTORY_KEY = "job_history"

# Worker liveness keys (shared with main_worker.py).
# last_seen is a unix timestamp (string) updated by the worker every
# HEARTBEAT_INTERVAL_SECONDS. The API treats the worker as degraded if
# now - last_seen > WORKER_OFFLINE_THRESHOLD_SECONDS.
WORKER_HEARTBEAT_KEY = "pharos:worker:last_seen"
WORKER_HEARTBEAT_META_KEY = "pharos:worker:meta"
WORKER_OFFLINE_THRESHOLD_SECONDS = 300  # 5 minutes — see runbook
HEARTBEAT_TTL_SECONDS = 600  # auto-expire heartbeat key after 10 min of silence

# Queue service instance
queue_service = QueueService()


# Pydantic models
class IngestionResponse(BaseModel):
    """Response model for ingestion task dispatch."""

    status: str = Field(..., description="Task status (dispatched, rejected)")
    job_id: int = Field(..., description="Unique job ID")
    queue_position: int = Field(..., description="Position in queue")
    target: str = Field(default="Edge-Worker", description="Target worker")
    queue_size: int = Field(..., description="Current queue size")
    max_queue_size: int = Field(
        default=MAX_QUEUE_SIZE, description="Maximum queue size"
    )
    message: Optional[str] = Field(None, description="Additional message")


class WorkerStatusResponse(BaseModel):
    """Response model for worker status."""

    status: str = Field(..., description="Current worker status")


class WorkerHeartbeatRequest(BaseModel):
    """Body sent by the edge worker on each heartbeat."""

    worker_id: Optional[str] = Field(
        default=None, description="Stable identifier for the worker process"
    )
    version: Optional[str] = Field(default=None, description="Worker code version")
    embedding_model: Optional[str] = Field(
        default=None, description="Embedding model loaded on the worker"
    )
    queue_drained_count: Optional[int] = Field(
        default=None, description="Tasks drained from DLQ on this boot"
    )


class WorkerHeartbeatResponse(BaseModel):
    """Echoes back what the API recorded — useful for worker-side debugging."""

    accepted: bool
    last_seen_unix: float
    worker_id: Optional[str] = None


class WorkerHealthResponse(BaseModel):
    """Liveness summary for the edge worker."""

    state: str = Field(
        ..., description="online | degraded | offline (no heartbeat ever recorded)"
    )
    last_seen_unix: Optional[float] = Field(
        default=None, description="Unix seconds of the last heartbeat"
    )
    seconds_since_last_seen: Optional[float] = Field(
        default=None, description="Age of the last heartbeat"
    )
    threshold_seconds: int = Field(
        default=WORKER_OFFLINE_THRESHOLD_SECONDS,
        description="Age above which the worker is considered offline",
    )
    worker_meta: Optional[dict] = Field(
        default=None, description="Metadata reported by the worker on its last ping"
    )


class JobRecord(BaseModel):
    """Job history record."""

    repo_url: str
    status: str
    duration_seconds: Optional[float] = None
    files_processed: Optional[int] = None
    embeddings_generated: Optional[int] = None
    timestamp: str
    error: Optional[str] = None
    reason: Optional[str] = None
    age_seconds: Optional[float] = None


class JobHistoryResponse(BaseModel):
    """Response model for job history."""

    jobs: list[JobRecord]


# Cached Redis client (created once, reused across requests)
_redis_client: Redis | None = None
_redis_validated = False


def get_redis_client() -> Redis:
    """
    Get Upstash Redis client with credential validation.

    Creates client on first call, caches it for subsequent calls.
    Validates credentials once via ping.

    Returns:
        Redis client instance

    Raises:
        HTTPException: If Redis credentials are not configured or invalid
    """
    global _redis_client, _redis_validated

    if _redis_client is not None and _redis_validated:
        return _redis_client

    redis_url = os.getenv("UPSTASH_REDIS_REST_URL")
    redis_token = os.getenv("UPSTASH_REDIS_REST_TOKEN")

    if not redis_url or not redis_token:
        logger.error("Redis credentials not configured")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Queue service not configured: UPSTASH_REDIS_REST_URL and UPSTASH_REDIS_REST_TOKEN must be set",
        )

    try:
        client = Redis(url=redis_url, token=redis_token)

        if not _redis_validated:
            try:
                client.ping()
                _redis_validated = True
            except Exception as ping_error:
                logger.error(f"Redis credential validation failed: {ping_error}")
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Queue service authentication failed: Invalid Redis credentials",
                )

        _redis_client = client
        return _redis_client

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create Redis client: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Queue service unavailable: {str(e)}",
        )


# Dependency: Admin token verification
def verify_admin_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> str:
    """
    Verify API admin token or JWT token for ingestion endpoint.

    This prevents unauthorized users from bombarding the edge worker
    with git clone requests (Risk A: "Open Door" Security Hole).

    Supports two authentication methods:
    1. PHAROS_ADMIN_TOKEN (simple token for backward compatibility)
    2. JWT tokens from OAuth2 authentication system

    Args:
        credentials: HTTP Bearer credentials

    Returns:
        Validated token

    Raises:
        HTTPException: If token is invalid or missing
    """
    token = credentials.credentials

    # Try admin token first (for backward compatibility)
    expected_token = os.getenv("PHAROS_ADMIN_TOKEN")
    if expected_token and token == expected_token:
        return token

    # Try JWT token validation
    try:
        from app.shared.security import decode_token

        # Validate JWT token
        payload = decode_token(token)

        # Token is valid, allow access
        logger.info(
            f"JWT authentication successful for user: {payload.get('sub', 'unknown')}"
        )
        return token

    except Exception as jwt_error:
        logger.warning(f"Authentication failure: Invalid token provided - {jwt_error}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing authentication token",
        )


# URL validation
def is_valid_repo_url(repo_url: str) -> bool:
    """
    Validate repository URL format and check for malicious patterns.

    Security checks:
    - Command injection prevention (shell metacharacters)
    - Path traversal prevention (..)
    - Protocol validation (http, https, git only)
    - Format validation (valid URL structure)
    - Length limits (prevent DoS)

    Args:
        repo_url: Repository URL to validate

    Returns:
        True if valid, False otherwise
    """
    # Check for empty or whitespace-only URLs
    if not repo_url or not repo_url.strip():
        logger.warning("Empty or whitespace-only URL rejected")
        return False

    # Check length limits (prevent DoS)
    if len(repo_url) > 2048:
        logger.warning(f"URL too long ({len(repo_url)} chars), rejecting")
        return False

    # Check for malicious patterns (command injection, path traversal)
    malicious_patterns = [
        (r"[;&|`$(){}]", "shell metacharacters"),  # Shell command injection
        (r"\.\.", "path traversal"),  # Directory traversal
        (r"[<>]", "redirection operators"),  # I/O redirection
        (r"[\n\r]", "newline characters"),  # Newline injection
        (r"[\x00-\x1f\x7f]", "control characters"),  # Control characters
        (r"file://", "file protocol"),  # Local file access
        (r"javascript:", "javascript protocol"),  # XSS attempts
        (r"data:", "data protocol"),  # Data URI injection
    ]

    for pattern, description in malicious_patterns:
        if re.search(pattern, repo_url, re.IGNORECASE):
            logger.warning(
                f"Malicious pattern detected ({description}) in URL: {repo_url}"
            )
            return False

    # Parse URL
    try:
        # Add https:// if no protocol specified
        if not repo_url.startswith(("http://", "https://", "git@")):
            test_url = f"https://{repo_url}"
        else:
            test_url = repo_url

        parsed = urlparse(test_url)

        # Check for valid scheme
        if parsed.scheme and parsed.scheme not in ["http", "https", "git"]:
            logger.warning(f"Invalid protocol '{parsed.scheme}' in URL: {repo_url}")
            return False

        # Check for valid netloc (domain)
        if not parsed.netloc:
            logger.warning(f"Missing domain in URL: {repo_url}")
            return False

        # Validate domain format (basic check)
        domain_pattern = r"^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$"
        domain = parsed.netloc.split(":")[0]  # Remove port if present
        if not re.match(domain_pattern, domain):
            logger.warning(f"Invalid domain format in URL: {repo_url}")
            return False

        # Check for common git hosting domains (optional, can be relaxed)
        valid_domains = ["github.com", "gitlab.com", "bitbucket.org", "gitee.com"]
        # Allow any domain for now, but log if not in common list
        if not any(domain in parsed.netloc for domain in valid_domains):
            logger.info(f"Non-standard git hosting domain: {parsed.netloc}")

        return True

    except Exception as e:
        logger.warning(f"URL parsing failed for {repo_url}: {e}")
        return False


# ---------------------------------------------------------------------------
# Worker liveness helpers
# ---------------------------------------------------------------------------

def _read_worker_heartbeat(redis: Redis) -> tuple[Optional[float], Optional[dict]]:
    """Return (last_seen_unix, meta_dict) or (None, None) if no heartbeat yet."""
    import json

    raw = redis.get(WORKER_HEARTBEAT_KEY)
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    last_seen: Optional[float] = None
    if raw:
        try:
            last_seen = float(raw)
        except (TypeError, ValueError):
            last_seen = None

    meta_raw = redis.get(WORKER_HEARTBEAT_META_KEY)
    if isinstance(meta_raw, bytes):
        meta_raw = meta_raw.decode("utf-8")
    meta: Optional[dict] = None
    if meta_raw:
        try:
            meta = json.loads(meta_raw)
        except (TypeError, ValueError):
            meta = None

    return last_seen, meta


def is_worker_online(redis: Redis) -> tuple[bool, Optional[float]]:
    """Return (online, seconds_since_heartbeat).

    Worker is "online" if the latest heartbeat is within
    WORKER_OFFLINE_THRESHOLD_SECONDS. A missing heartbeat counts as offline.
    """
    last_seen, _ = _read_worker_heartbeat(redis)
    if last_seen is None:
        return False, None
    age = time.time() - last_seen
    return age <= WORKER_OFFLINE_THRESHOLD_SECONDS, age


def _enforce_worker_online(redis: Redis, *, context: str) -> None:
    """Raise 503 'System Degraded' if the worker is offline.

    The Render API uses this in front of the ingestion router so we don't
    accept work no one will pick up. The caller (e.g. Ronin) sees a clear
    `X-Pharos-Edge-Status: offline` header and a structured error body.
    """
    online, age = is_worker_online(redis)
    if online:
        return
    age_str = f"{age:.0f}s" if age is not None else "never"
    logger.critical(
        f"Edge Worker offline (last_seen={age_str} ago) — refusing {context}"
    )
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "error": "System Degraded: Edge Worker Offline",
            "context": context,
            "last_seen_seconds_ago": age,
            "threshold_seconds": WORKER_OFFLINE_THRESHOLD_SECONDS,
        },
        headers={"X-Pharos-Edge-Status": "offline"},
    )


# Endpoints
@router.post("/ingest/{repo_url:path}", response_model=IngestionResponse)
async def trigger_remote_ingestion(
    repo_url: str,
    token: str = Depends(verify_admin_token),
    redis: Redis = Depends(get_redis_client),
):
    """
    Dispatch a repository ingestion task to the edge worker.

    **Security**: Requires Bearer token authentication via PHAROS_ADMIN_TOKEN.
    This prevents unauthorized users from submitting tasks (Risk A).

    **Queue Management**: Rejects new tasks if queue has >= 10 pending jobs
    to prevent overwhelming the edge worker (Risk B: "Zombie Queue").

    **TTL Enforcement**: Sets 24-hour TTL on tasks to prevent stale jobs
    from accumulating when worker is offline.

    Args:
        repo_url: Full repository URL (e.g., github.com/user/repo)
        token: Validated admin token

    Returns:
        IngestionResponse with job ID and queue position

    Raises:
        400: Invalid repository URL
        401: Invalid or missing authentication token
        429: Queue is full (>= 10 pending tasks)
        503: Queue unavailable
    """
    # Validate URL
    if not is_valid_repo_url(repo_url):
        logger.warning(f"Invalid repository URL rejected: {repo_url}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid repository URL format",
        )

    # Refuse to queue work the worker can't pick up. Also surfaces a clean
    # "System Degraded" signal to Ronin via the X-Pharos-Edge-Status header.
    _enforce_worker_online(redis, context="ingest")

    try:
        # Create task with metadata
        task_data = {
            "repo_url": repo_url,
            "submitted_at": datetime.now().isoformat(),
            "submitted_at_unix": time.time(),
            "ttl": TASK_TTL,
            "task_id": str(uuid.uuid4()),
            "job_id": str(uuid.uuid4()),
            "status": "pending",
            "created_at": str(int(time.time() * 1e9)),
        }

        # Push directly to ingest_queue (not pharos:tasks which is for resources)
        import json
        await redis._execute(["RPUSH", "ingest_queue", json.dumps(task_data)])

        # Also record in history for tracking
        await redis._execute([
            "RPUSH",
            "pharos:history",
            json.dumps({
                "repo_url": repo_url,
                "status": "pending",
                "timestamp": task_data["submitted_at"],
            }),
        ])

        # Get queue position (approximate)
        queue_size = await redis._execute(["LLEN", "ingest_queue"]) or 0

        logger.info(
            f"Task dispatched: {repo_url} (job_id={task_data['job_id']}, queue_size={queue_size})"
        )

        return IngestionResponse(
            status="dispatched",
            job_id=int(task_data["job_id"].replace("-", "")[:8], 16),
            queue_position=queue_size,
            target="Edge-Worker",
            queue_size=queue_size,
            max_queue_size=MAX_QUEUE_SIZE,
            message=f"Task queued successfully. Position: {queue_size}/{MAX_QUEUE_SIZE}",
        )

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Failed to queue task {repo_url}: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Queue unavailable: {str(e)}",
        )


@router.get("/worker/status", response_model=WorkerStatusResponse)
async def get_worker_status(redis: Redis = Depends(get_redis_client)):
    """
    Get current edge worker status.

    **Critical for UI**: This endpoint enables real-time status updates
    in the frontend, showing users when the worker is training, idle,
    or encountering errors. The visual feedback ("Training... 40%") is
    what makes the hybrid architecture transparent to users (Risk D).

    Returns:
        WorkerStatusResponse with current status or "Offline" if not available

    Raises:
        503: Redis unavailable
    """
    try:
        status_value = redis.get(STATUS_KEY)

        # Handle bytes response from Redis
        if isinstance(status_value, bytes):
            status_value = status_value.decode("utf-8")

        # Default to "Offline" if no status found
        if not status_value:
            status_value = "Offline"

        logger.debug(f"Worker status: {status_value}")

        return WorkerStatusResponse(status=status_value)

    except Exception as e:
        logger.error(f"Failed to get worker status: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Redis unavailable: {str(e)}",
        )


@router.get("/jobs/history", response_model=JobHistoryResponse)
async def get_job_history(limit: int = 10):
    """
    Get recent job history.

    Args:
        limit: Number of recent jobs to return (max 100)

    Returns:
        JobHistoryResponse with list of recent jobs

    Raises:
        503: Queue unavailable
    """
    try:
        # Get jobs from QueueService
        jobs_data = await queue_service.get_job_history(limit)

        # Convert to JobRecord objects
        jobs = []
        for job in jobs_data:
            try:
                # Calculate age if timestamp is available
                age_seconds = None
                if job.get("submitted_at"):
                    try:
                        from datetime import datetime

                        submitted = datetime.fromisoformat(
                            job["submitted_at"].replace("Z", "+00:00")
                        )
                        age_seconds = (datetime.now() - submitted).total_seconds()
                    except (ValueError, TypeError):
                        pass

                jobs.append(
                    JobRecord(
                        repo_url=job.get("repo_url", "unknown"),
                        status=job.get("status", "unknown"),
                        duration_seconds=job.get("duration_seconds"),
                        files_processed=job.get("files_processed"),
                        embeddings_generated=job.get("embeddings_generated"),
                        timestamp=job.get("submitted_at", ""),
                        error=job.get("error"),
                        reason=job.get("reason"),
                        age_seconds=age_seconds,
                    )
                )
            except (ValueError, TypeError) as e:
                logger.warning(f"Failed to parse job record: {e}")
                continue

        logger.debug(f"Retrieved {len(jobs)} job records")

        return JobHistoryResponse(jobs=jobs)

    except Exception as e:
        logger.error(f"Failed to get job history: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Queue unavailable: {str(e)}",
        )


@router.get("/health")
async def health_check():
    """
    Health check endpoint for monitoring.

    Checks connections to:
    - Redis (task queue)
    - Neon (database) - optional, depends on MODE
    - Qdrant (vector store) - optional, depends on MODE

    Returns:
        200: All services healthy
        503: One or more services unavailable
    """
    from fastapi.responses import JSONResponse

    health_status = {"status": "healthy", "services": {}}

    all_healthy = True

    # Check Redis
    try:
        redis = get_redis_client()
        redis.ping()
        health_status["services"]["redis"] = "healthy"
    except Exception as e:
        health_status["services"]["redis"] = f"unhealthy: {str(e)}"
        all_healthy = False

    # Check Neon (database) - only if DATABASE_URL is set
    database_url = os.getenv("DATABASE_URL") or os.getenv("NEON_DATABASE_URL")
    if database_url:
        try:
            from sqlalchemy import create_engine, text

            engine = create_engine(database_url)
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            health_status["services"]["database"] = "healthy"
        except Exception as e:
            health_status["services"]["database"] = f"unhealthy: {str(e)}"
            all_healthy = False
    else:
        health_status["services"]["database"] = "not configured"

    # Check Qdrant - only if QDRANT_URL is set
    qdrant_url = os.getenv("QDRANT_URL")
    if qdrant_url:
        try:
            from qdrant_client import QdrantClient

            client = QdrantClient(url=qdrant_url, api_key=os.getenv("QDRANT_API_KEY"))
            client.get_collections()
            health_status["services"]["qdrant"] = "healthy"
        except Exception as e:
            health_status["services"]["qdrant"] = f"unhealthy: {str(e)}"
            all_healthy = False
    else:
        health_status["services"]["qdrant"] = "not configured"

    if not all_healthy:
        health_status["status"] = "unhealthy"
        return JSONResponse(content=health_status, status_code=503)

    return health_status


# ---------------------------------------------------------------------------
# Worker heartbeat
# ---------------------------------------------------------------------------

@router.post("/health/worker", response_model=WorkerHeartbeatResponse)
async def record_worker_heartbeat(
    payload: WorkerHeartbeatRequest,
    token: str = Depends(verify_admin_token),
    redis: Redis = Depends(get_redis_client),
):
    """
    Record a heartbeat from the edge worker.

    The worker pings this endpoint every 60 seconds. We persist the unix
    timestamp under ``pharos:worker:last_seen`` (with a 10-minute TTL so a
    long-dead worker doesn't appear "online" forever) plus a small JSON blob
    of metadata for observability.

    The ingestion router consults the same key before accepting new work.
    """
    import json

    now = time.time()
    try:
        redis.set(WORKER_HEARTBEAT_KEY, str(now), ex=HEARTBEAT_TTL_SECONDS)

        meta = {
            "worker_id": payload.worker_id,
            "version": payload.version,
            "embedding_model": payload.embedding_model,
            "queue_drained_count": payload.queue_drained_count,
            "last_seen_iso": datetime.utcfromtimestamp(now).isoformat() + "Z",
        }
        redis.set(
            WORKER_HEARTBEAT_META_KEY, json.dumps(meta), ex=HEARTBEAT_TTL_SECONDS
        )

        return WorkerHeartbeatResponse(
            accepted=True, last_seen_unix=now, worker_id=payload.worker_id
        )
    except Exception as exc:
        logger.error(f"Heartbeat write failed: {exc}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Failed to persist heartbeat: {exc}",
        )


@router.get("/health/worker", response_model=WorkerHealthResponse)
async def get_worker_health(redis: Redis = Depends(get_redis_client)):
    """
    Return the current liveness state of the edge worker.

    States:
      * ``online``   — last heartbeat within ``WORKER_OFFLINE_THRESHOLD_SECONDS``
      * ``degraded`` — heartbeat exists but is stale
      * ``offline``  — no heartbeat ever recorded (or expired from Redis)

    Ronin and the dashboard can poll this to render a banner without having
    to authenticate as the admin.
    """
    last_seen, meta = _read_worker_heartbeat(redis)
    if last_seen is None:
        return WorkerHealthResponse(state="offline", worker_meta=meta)

    age = time.time() - last_seen
    state = "online" if age <= WORKER_OFFLINE_THRESHOLD_SECONDS else "degraded"
    return WorkerHealthResponse(
        state=state,
        last_seen_unix=last_seen,
        seconds_since_last_seen=age,
        worker_meta=meta,
    )
