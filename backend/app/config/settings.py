"""
Neo Alexandria 2.0 - Application Configuration

This module provides centralized configuration management using Pydantic Settings.
It handles environment variables, default values, and configuration validation.

Related files:
- app/database/base.py: Uses DATABASE_URL for database connection
- app/services/quality_service.py: Uses MIN_QUALITY_THRESHOLD for quality scoring
- .env: Environment variables file (optional)
- alembic.ini: Database migration configuration

Configuration includes:
- Database connection settings
- Environment-specific settings (dev/staging/prod)
- Quality control thresholds
- Backup and timezone preferences
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr, Field, field_validator, model_validator
from pydantic_settings import BaseSettings


_SQLITE_DEFAULT_URL = "sqlite:///./backend.db"
_BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """
    Application settings using Pydantic Settings for configuration management.

    Provides type-safe configuration with environment variable support and
    sensible defaults for development and production environments.
    """

    DATABASE_URL: str = _SQLITE_DEFAULT_URL
    TEST_DATABASE_URL: str | None = None  # Optional test database URL
    ENV: Literal["dev", "staging", "prod"] = "dev"

    # Browser origins allowed by CORS (API clients using bearer tokens don't
    # need this; it matters only for a browser frontend).
    ALLOWED_ORIGINS: list[str] = [
        "http://localhost:5173",  # Vite dev server
        "http://localhost:3000",  # Common dev server
        "https://pharos.onrender.com",  # Production cloud
    ]

    # PostgreSQL configuration
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str | None = None  # Optional for SQLite, required for PostgreSQL
    POSTGRES_DB: str = "neo_alexandria_dev"
    POSTGRES_PORT: int = 5432

    # GitHub API token for code-intelligence reads.
    # Personal Access Token (classic) with repo:read scope.
    # Raises unauthenticated rate limit from 60 → 5,000 req/hr.
    GITHUB_API_TOKEN: SecretStr | None = None

    # GitHub fetcher concurrency cap (simultaneous raw-content requests)
    GITHUB_FETCH_CONCURRENCY: int = 10

    # Redis URL shorthand (overrides REDIS_HOST/PORT when set)
    REDIS_URL: str | None = None  # e.g. "redis://localhost:6379/2"

    # File Upload Validation
    ALLOWED_FILE_EXTENSIONS: set[str] = {
        # Documents
        ".pdf",
        ".doc",
        ".docx",
        ".txt",
        ".rtf",
        ".odt",
        # Code
        ".py",
        ".js",
        ".ts",
        ".jsx",
        ".tsx",
        ".java",
        ".c",
        ".cpp",
        ".h",
        ".cs",
        ".go",
        ".rs",
        ".rb",
        ".php",
        ".swift",
        ".kt",
        ".scala",
        # Markup
        ".html",
        ".css",
        ".scss",
        ".json",
        ".yaml",
        ".yml",
        ".xml",
        ".md",
        # Data
        ".csv",
        ".tsv",
        ".jsonl",
        ".parquet",
        # Images (for metadata extraction)
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".bmp",
        ".tiff",
        ".webp",
    }
    BLOCKED_FILE_EXTENSIONS: set[str] = {
        ".exe",
        ".bat",
        ".cmd",
        ".sh",
        ".bash",
        ".ps1",
        ".dll",
        ".so",
        ".jar",
        ".class",
        ".pyc",
        ".pyo",
        ".pyd",
        ".env",
        ".key",
        ".pem",
    }
    MAX_FILE_UPLOAD_SIZE: int = 50 * 1024 * 1024  # 50 MB default

    # Repository URL Validation
    ALLOWED_REPOSITORY_DOMAINS: list[str] = [
        "github.com",
        "gitlab.com",
        "bitbucket.org",
        "sourceforge.net",
        "codeberg.org",
        "sr.ht",
    ]
    BLOCKED_IP_RANGES: list[str] = [
        # Loopback
        "127.0.0.0/8",
        "::1/128",
        # Private networks (RFC 1918)
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        # Link-local
        "169.254.0.0/16",
        "fe80::/10",
        # Docker/Kubernetes
        "172.17.0.0/16",
        "10.244.0.0/16",
        "10.96.0.0/12",
        # Cloud metadata endpoints
        "169.254.169.254/32",
        "metadata.google.internal",
        # Multicast
        "224.0.0.0/4",
        "ff00::/8",
    ]

    # Testing
    TEST_MODE: bool = Field(default=False)

    @field_validator("MODE")
    @classmethod
    def validate_mode(cls, v: str) -> str:
        """Validate MODE is either CLOUD or EDGE."""
        if v not in ["CLOUD", "EDGE"]:
            raise ValueError(f"MODE must be 'CLOUD' or 'EDGE', got: {v}")
        return v

    @field_validator("QUEUE_SIZE")
    @classmethod
    def validate_queue_size(cls, v: int) -> int:
        """Validate QUEUE_SIZE is positive."""
        if v <= 0:
            raise ValueError(f"MAX_QUEUE_SIZE must be positive, got: {v}")
        return v

    @model_validator(mode="after")
    def validate_production_requirements(self):
        """Refuse test-only switches in production (they disable auth)."""
        import os

        if self.ENV == "prod":
            if self.TEST_MODE:
                raise ValueError("TEST_MODE must be False in production.")
            if os.getenv("TESTING", "").lower() in ("true", "1", "yes"):
                raise ValueError("TESTING must not be set in production.")
            if os.getenv("TEST_AUTH_BYPASS"):
                raise ValueError("TEST_AUTH_BYPASS must not be set in production.")
        return self

    @property
    def is_test_mode(self) -> bool:
        """Check if running in test mode from TESTING env var."""
        import os

        return os.getenv("TESTING", "").lower() in ("true", "1", "yes")

    MIN_QUALITY_THRESHOLD: float = 0.7
    BACKUP_FREQUENCY: Literal["daily", "weekly", "monthly"] = "weekly"
    TIMEZONE: str = "UTC"

    # Redis configuration for Celery and caching
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_CACHE_DB: int = 2
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"
    
    @model_validator(mode='after')
    def set_celery_urls(self):
        """Override Celery URLs if REDIS_URL is set."""
        if self.REDIS_URL:
            base_url = self.REDIS_URL.rsplit('/', 1)[0] if '/' in self.REDIS_URL else self.REDIS_URL
            self.CELERY_BROKER_URL = f"{base_url}/0"
            self.CELERY_RESULT_BACKEND = f"{base_url}/1"
        return self

    # Vector embedding configuration
    EMBEDDING_MODEL_NAME: str = "nomic-ai/nomic-embed-text-v1"
    DEFAULT_HYBRID_SEARCH_WEIGHT: float = 0.5  # 0.0=keyword only, 1.0=semantic only
    EMBEDDING_CACHE_SIZE: int = 1000  # for model caching if needed

    # Graph configuration - Hybrid Knowledge Graph
    DEFAULT_GRAPH_NEIGHBORS: int = 7
    GRAPH_OVERVIEW_MAX_EDGES: int = 50
    GRAPH_WEIGHT_VECTOR: float = 0.6
    GRAPH_WEIGHT_TAGS: float = 0.3
    GRAPH_WEIGHT_CLASSIFICATION: float = 0.1
    GRAPH_VECTOR_MIN_SIM_THRESHOLD: float = 0.85  # for overview candidate pruning

    # Personalized Recommendation Engine
    RECOMMENDATION_PROFILE_SIZE: int = 50
    RECOMMENDATION_KEYWORD_COUNT: int = 5
    RECOMMENDATION_CANDIDATES_PER_KEYWORD: int = 10
    SEARCH_PROVIDER: str = "ddgs"  # currently supports only ddgs
    SEARCH_TIMEOUT: int = 10

    # Advanced RAG Architecture
    # Chunking Configuration
    CHUNK_ON_RESOURCE_CREATE: bool = True  # Enable automatic chunking during ingestion
    CHUNKING_STRATEGY: str = "semantic"  # "semantic" or "fixed"
    CHUNK_SIZE: int = 500  # Words for semantic, characters for fixed
    CHUNK_OVERLAP: int = 50  # Words or characters overlap between chunks

    # Graph Extraction Configuration
    GRAPH_EXTRACTION_ENABLED: bool = True  # Enable graph extraction
    GRAPH_EXTRACTION_METHOD: str = "llm"  # "llm", "spacy", or "hybrid"
    GRAPH_EXTRACT_ON_CHUNK: bool = (
        True  # Enable automatic graph extraction after chunking
    )

    # Synthetic Questions Configuration
    SYNTHETIC_QUESTIONS_ENABLED: bool = (
        False  # Enable synthetic question generation (expensive, opt-in)
    )
    QUESTIONS_PER_CHUNK: int = 2  # Number of questions to generate per chunk
    QUESTION_GENERATION_MODEL: str = "gpt-3.5-turbo"  # Model for question generation

    # Retrieval Configuration
    DEFAULT_RETRIEVAL_STRATEGY: str = (
        "parent-child"  # "parent-child", "graphrag", or "hybrid"
    )
    PARENT_CHILD_CONTEXT_WINDOW: int = 2  # Number of surrounding chunks to include
    GRAPHRAG_MAX_HOPS: int = 2  # Maximum graph traversal depth

    MODE: Literal["CLOUD", "EDGE"] = "CLOUD"  # Deployment mode

    # Upstash Redis (for task queue and status tracking)
    UPSTASH_REDIS_REST_URL: str | None = None
    UPSTASH_REDIS_REST_TOKEN: SecretStr | None = None

    # Neon Database (serverless PostgreSQL)
    NEON_DATABASE_URL: str | None = None

    # Qdrant Cloud (vector database)
    QDRANT_URL: str | None = None
    QDRANT_API_KEY: SecretStr | None = None

    # API Authentication (machine-to-machine bearer tokens; see SECURITY.md)
    # Full access: ingestion, admin, everything.
    PHAROS_ADMIN_TOKEN: SecretStr | None = None
    # Optional read-only token for assistants: search, context, repository
    # listing, MCP. Cannot trigger ingestion or admin operations.
    PHAROS_READ_TOKEN: SecretStr | None = None

    # Host headers the native MCP endpoint accepts (DNS-rebinding protection
    # stays on). Localhost is always allowed; add your public hostname, e.g.
    # ["pharos-cloud-api.onrender.com"], or MCP requests get HTTP 421.
    MCP_ALLOWED_HOSTS: list[str] = []

    # ── Embeddings (app/codeintel/embeddings.py) ───────────────────────────
    # auto | none | hash | sentence-transformers | http | onnx
    # auto = http in CLOUD mode when EDGE_EMBEDDING_URL is set, else none;
    #        sentence-transformers in EDGE mode.
    EMBEDDING_BACKEND: str = "auto"
    EDGE_EMBEDDING_URL: str | None = None
    # Bearer token the edge embed server requires (strongly recommended when
    # the server is exposed through Tailscale Funnel or any public URL).
    EDGE_EMBED_TOKEN: SecretStr | None = None
    EMBEDDING_ONNX_DIR: str | None = None
    EMBEDDING_MODEL_ID: str | None = None

    # ── Code ingestion limits & safety (app/codeintel) ─────────────────────
    # Remote hosts the API may ask the worker to clone from (https only).
    CODEINTEL_ALLOWED_GIT_HOSTS: list[str] = ["github.com", "gitlab.com", "bitbucket.org"]
    CODEINTEL_MAX_FILE_BYTES: int = 1_000_000
    CODEINTEL_MAX_FILES: int = 20_000
    CODEINTEL_CLONE_TIMEOUT_SECONDS: int = 600
    # Token used for cloning private repositories on allowed hosts (sent as
    # an HTTP header via git config, never placed in URLs or logs).
    GIT_CLONE_TOKEN: SecretStr | None = None
    # Ingestion jobs whose heartbeat is older than this are re-queued.
    INGESTION_JOB_STALE_SECONDS: int = 900
    # Redis key carrying job-id wake-up notifications (state lives in Postgres).
    # Defaults to the queue main_worker.py already BLPOPs, so the edge worker
    # picks up jobs without an extra Redis poll (Upstash quota).
    INGESTION_NOTIFY_KEY: str = "ingest_queue"

    # Task Queue Configuration
    QUEUE_SIZE: int = Field(default=10, alias="MAX_QUEUE_SIZE")  # Maximum pending tasks
    TASK_TTL: int = Field(
        default=86400, alias="TASK_TTL_SECONDS"
    )  # 24 hours - tasks older than this are skipped

    # Edge Worker Configuration
    WORKER_POLL_INTERVAL: int = 2  # Seconds between queue polls
    DEVICE: str | None = None  # Set automatically based on CUDA availability

    # Feedback Loop (Phase 6) — Heuristic Sieve & Local Extraction
    FEEDBACK_LOOP_ENABLED: bool = False  # Master switch for the nightly sieve
    FEEDBACK_SURVIVAL_DAYS: int = 14  # Days a structural change must survive
    FEEDBACK_GITHUB_OWNER: str = ""  # GitHub repo owner (e.g. "ram-tewari")
    FEEDBACK_GITHUB_REPO: str = ""  # GitHub repo name (e.g. "pharos")
    FEEDBACK_REDIS_QUEUE: str = "pharos_extraction_jobs"  # Redis queue name for jobs
    FEEDBACK_LOCAL_LLM_URL: str = "http://localhost:11434"  # Ollama/vLLM endpoint
    FEEDBACK_LOCAL_LLM_MODEL: str = "codellama:13b"  # Model name for extraction
    # Minimum control-flow node density (control-flow nodes / total AST nodes)
    # for a file to pass the sieve. Filters out flat config / boilerplate /
    # dataclass-only modules that survive untouched but carry no logic.
    FEEDBACK_MIN_AST_DENSITY: float = 0.01
    # Minimum absolute count of control-flow nodes in a file. Catches tiny
    # files whose ratio looks high but have no real logic.
    FEEDBACK_MIN_CONTROL_FLOW_NODES: int = 3

    class Config:
        # backend/.env, then backend/config/.env (later files win); resolved
        # from this file so the API, CLI and worker agree whatever their cwd.
        env_file = (str(_BACKEND_DIR / ".env"), str(_BACKEND_DIR / "config" / ".env"))
        env_file_encoding = "utf-8"
        extra = "ignore"  # Ignore extra fields in .env file

    def __init__(self, **kwargs):
        """
        Initialize settings with MODE-aware configuration.

        CLOUD mode: Lightweight, no torch imports
        EDGE mode: Full ML stack with CUDA detection
        """
        super().__init__(**kwargs)

        # MODE-aware initialization
        if self.MODE == "CLOUD":
            # Cloud mode: Skip heavy imports
            pass
        elif self.MODE == "EDGE":
            # Edge mode: Verify CUDA and set device
            try:
                import torch

                self.DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

                # Log GPU information
                if self.DEVICE == "cuda":
                    gpu_name = torch.cuda.get_device_name(0)
                    gpu_memory = torch.cuda.get_device_properties(0).total_memory / 1e9
                    print("Edge Worker GPU Detected:")
                    print(f"   Device: {gpu_name}")
                    print(f"   Memory: {gpu_memory:.1f} GB")
                    print(f"   CUDA Version: {torch.version.cuda}")  # type: ignore[attr-defined]
                else:
                    print("CUDA not available, falling back to CPU")
            except ImportError:
                raise ImportError(
                    "MODE=EDGE requires torch to be installed. "
                    "Install with: pip install -r requirements-edge.txt"
                )

    def get_database_url(self) -> str:
        """
        Return the configured database URL.

        ``DATABASE_URL`` always wins when it is set, by environment, ``.env``
        or keyword (this is how Neon, Docker Compose and CI provide the
        database) -- even when it is set to the SQLite default. Only when it
        is not set at all *and* ``POSTGRES_PASSWORD`` is set do we assemble a
        URL from the individual ``POSTGRES_*`` settings. Driver selection
        happens later, in ``app.shared.db_url.normalize_database_url``.

        (Previously any PostgreSQL ``DATABASE_URL`` was silently replaced by
        one built from ``POSTGRES_*`` defaults, i.e. ``localhost`` — so
        Alembic never connected to the database it was pointed at.)
        """
        from urllib.parse import quote

        if "DATABASE_URL" in self.model_fields_set or not self.POSTGRES_PASSWORD:
            return self.DATABASE_URL

        encoded_password = quote(self.POSTGRES_PASSWORD, safe="")
        return (
            f"postgresql://{self.POSTGRES_USER}:"
            f"{encoded_password}@{self.POSTGRES_SERVER}:"
            f"{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )


@lru_cache()
def get_settings() -> Settings:
    """
    Get cached settings instance.

    Returns a singleton Settings instance that is cached for the lifetime
    of the application. This ensures consistent configuration across all
    modules and avoids repeated environment variable parsing.

    Returns:
        Settings: Cached configuration instance

    Raises:
        ValueError: If configuration validation fails
    """
    import os

    settings = Settings()

    # Validate graph weights sum to 1.0
    total_weight = (
        settings.GRAPH_WEIGHT_VECTOR
        + settings.GRAPH_WEIGHT_TAGS
        + settings.GRAPH_WEIGHT_CLASSIFICATION
    )
    if abs(total_weight - 1.0) > 1e-6:
        raise ValueError(
            f"Configuration validation failed: GRAPH_WEIGHT_VECTOR + GRAPH_WEIGHT_TAGS + "
            f"GRAPH_WEIGHT_CLASSIFICATION must sum to 1.0, got {total_weight}. "
            f"Expected type: float (sum=1.0)"
        )

    # A PostgreSQL DATABASE_URL is self-contained; no POSTGRES_* checks needed.

    # Validate Redis configuration
    if settings.REDIS_PORT <= 0 or settings.REDIS_PORT > 65535:
        raise ValueError(
            f"Configuration validation failed: REDIS_PORT must be between 1 and 65535, "
            f"got {settings.REDIS_PORT}. Expected type: int (1-65535)"
        )

    # Validate quality threshold
    if not 0.0 <= settings.MIN_QUALITY_THRESHOLD <= 1.0:
        raise ValueError(
            f"Configuration validation failed: MIN_QUALITY_THRESHOLD must be between 0.0 and 1.0, "
            f"got {settings.MIN_QUALITY_THRESHOLD}. Expected type: float (0.0-1.0)"
        )

    # Validate hybrid search weight
    if not 0.0 <= settings.DEFAULT_HYBRID_SEARCH_WEIGHT <= 1.0:
        raise ValueError(
            f"Configuration validation failed: DEFAULT_HYBRID_SEARCH_WEIGHT must be between 0.0 and 1.0, "
            f"got {settings.DEFAULT_HYBRID_SEARCH_WEIGHT}. Expected type: float (0.0-1.0)"
        )

    # Validate Advanced RAG configuration
    if settings.CHUNKING_STRATEGY not in ("semantic", "fixed"):
        raise ValueError(
            f"Configuration validation failed: CHUNKING_STRATEGY must be 'semantic' or 'fixed', "
            f"got '{settings.CHUNKING_STRATEGY}'. Expected type: str ('semantic' | 'fixed')"
        )

    if settings.CHUNK_SIZE <= 0:
        raise ValueError(
            f"Configuration validation failed: CHUNK_SIZE must be positive, "
            f"got {settings.CHUNK_SIZE}. Expected type: int (> 0)"
        )

    if settings.CHUNK_OVERLAP < 0:
        raise ValueError(
            f"Configuration validation failed: CHUNK_OVERLAP must be non-negative, "
            f"got {settings.CHUNK_OVERLAP}. Expected type: int (>= 0)"
        )

    if settings.CHUNK_OVERLAP >= settings.CHUNK_SIZE:
        raise ValueError(
            f"Configuration validation failed: CHUNK_OVERLAP must be less than CHUNK_SIZE, "
            f"got CHUNK_OVERLAP={settings.CHUNK_OVERLAP}, CHUNK_SIZE={settings.CHUNK_SIZE}. "
            f"Expected: CHUNK_OVERLAP < CHUNK_SIZE"
        )

    if settings.GRAPH_EXTRACTION_METHOD not in ("llm", "spacy", "hybrid"):
        raise ValueError(
            f"Configuration validation failed: GRAPH_EXTRACTION_METHOD must be 'llm', 'spacy', or 'hybrid', "
            f"got '{settings.GRAPH_EXTRACTION_METHOD}'. Expected type: str ('llm' | 'spacy' | 'hybrid')"
        )

    if settings.QUESTIONS_PER_CHUNK <= 0:
        raise ValueError(
            f"Configuration validation failed: QUESTIONS_PER_CHUNK must be positive, "
            f"got {settings.QUESTIONS_PER_CHUNK}. Expected type: int (> 0)"
        )

    if settings.DEFAULT_RETRIEVAL_STRATEGY not in (
        "parent-child",
        "graphrag",
        "hybrid",
    ):
        raise ValueError(
            f"Configuration validation failed: DEFAULT_RETRIEVAL_STRATEGY must be 'parent-child', 'graphrag', or 'hybrid', "
            f"got '{settings.DEFAULT_RETRIEVAL_STRATEGY}'. Expected type: str ('parent-child' | 'graphrag' | 'hybrid')"
        )

    if settings.PARENT_CHILD_CONTEXT_WINDOW < 0:
        raise ValueError(
            f"Configuration validation failed: PARENT_CHILD_CONTEXT_WINDOW must be non-negative, "
            f"got {settings.PARENT_CHILD_CONTEXT_WINDOW}. Expected type: int (>= 0)"
        )

    if settings.GRAPHRAG_MAX_HOPS <= 0:
        raise ValueError(
            f"Configuration validation failed: GRAPHRAG_MAX_HOPS must be positive, "
            f"got {settings.GRAPHRAG_MAX_HOPS}. Expected type: int (> 0)"
        )

    # Validate Hybrid Edge-Cloud Orchestration configuration
    if settings.MODE not in ("CLOUD", "EDGE"):
        raise ValueError(
            f"Configuration validation failed: MODE must be 'CLOUD' or 'EDGE', "
            f"got '{settings.MODE}'. Expected type: Literal['CLOUD', 'EDGE']"
        )

    # Only validate edge-cloud requirements if explicitly enabled
    # This allows existing tests to run without edge-cloud configuration
    phase19_enabled = os.getenv("PHASE19_ENABLED", "").lower() in ("true", "1", "yes")

    if phase19_enabled:
        # Validate Upstash Redis configuration (required for both modes)
        if not settings.UPSTASH_REDIS_REST_URL:
            raise ValueError(
                "Configuration validation failed: UPSTASH_REDIS_REST_URL must be set. "
                "Expected type: str (non-empty)"
            )

        # Enforce HTTPS for Upstash Redis (Requirement 11.3)
        if not settings.UPSTASH_REDIS_REST_URL.startswith("https://"):
            raise ValueError(
                f"Configuration validation failed: UPSTASH_REDIS_REST_URL must use HTTPS, "
                f"got '{settings.UPSTASH_REDIS_REST_URL}'. Expected: https://..."
            )

        if not settings.UPSTASH_REDIS_REST_TOKEN:
            raise ValueError(
                "Configuration validation failed: UPSTASH_REDIS_REST_TOKEN must be set. "
                "Expected type: SecretStr (non-empty)"
            )

        # Validate PHAROS_ADMIN_TOKEN (required for security)
        if not settings.PHAROS_ADMIN_TOKEN:
            raise ValueError(
                "Configuration validation failed: PHAROS_ADMIN_TOKEN must be set for API authentication. "
                "Expected type: SecretStr (non-empty)"
            )

        # Validate queue configuration
        if settings.QUEUE_SIZE <= 0:
            raise ValueError(
                f"Configuration validation failed: MAX_QUEUE_SIZE must be positive, "
                f"got {settings.QUEUE_SIZE}. Expected type: int (> 0)"
            )

        if settings.TASK_TTL <= 0:
            raise ValueError(
                f"Configuration validation failed: TASK_TTL_SECONDS must be positive, "
                f"got {settings.TASK_TTL}. Expected type: int (> 0)"
            )

        if settings.WORKER_POLL_INTERVAL <= 0:
            raise ValueError(
                f"Configuration validation failed: WORKER_POLL_INTERVAL must be positive, "
                f"got {settings.WORKER_POLL_INTERVAL}. Expected type: int (> 0)"
            )

        # Mode-specific validation
        if settings.MODE == "CLOUD":
            # Cloud mode: Validate cloud-specific requirements
            # Enforce HTTPS for Qdrant (Requirement 11.3)
            if settings.QDRANT_URL and not settings.QDRANT_URL.startswith("https://"):
                raise ValueError(
                    f"Configuration validation failed: QDRANT_URL must use HTTPS, "
                    f"got '{settings.QDRANT_URL}'. Expected: https://..."
                )

            # Enforce HTTPS for Neon (Requirement 11.3)
            if settings.NEON_DATABASE_URL:
                if not settings.NEON_DATABASE_URL.startswith("postgresql://"):
                    raise ValueError(
                        f"Configuration validation failed: NEON_DATABASE_URL must be a PostgreSQL URL, "
                        f"got '{settings.NEON_DATABASE_URL}'. Expected: postgresql://..."
                    )
                # Check if Neon URL uses SSL (Neon always uses SSL)
                # Note: PostgreSQL URLs don't show https://, but Neon enforces SSL by default

        elif settings.MODE == "EDGE":
            # Edge mode: Validate edge-specific requirements
            if not settings.QDRANT_URL:
                raise ValueError(
                    "Configuration validation failed: QDRANT_URL must be set in EDGE mode. "
                    "Expected type: str (non-empty)"
                )

            # Enforce HTTPS for Qdrant (Requirement 11.3)
            if not settings.QDRANT_URL.startswith("https://"):
                raise ValueError(
                    f"Configuration validation failed: QDRANT_URL must use HTTPS, "
                    f"got '{settings.QDRANT_URL}'. Expected: https://..."
                )

            if not settings.QDRANT_API_KEY:
                raise ValueError(
                    "Configuration validation failed: QDRANT_API_KEY must be set in EDGE mode. "
                    "Expected type: SecretStr (non-empty)"
                )

    return settings


