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
from typing import Literal

from pydantic import SecretStr, Field, field_validator, model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    Application settings using Pydantic Settings for configuration management.

    Provides type-safe configuration with environment variable support and
    sensible defaults for development and production environments.
    """

    DATABASE_URL: str = "sqlite:///./backend.db"
    TEST_DATABASE_URL: str | None = None  # Optional test database URL
    ENV: Literal["dev", "staging", "prod"] = "dev"

    # Frontend URL for OAuth redirects
    FRONTEND_URL: str = "http://localhost:5173"

    # Allowed redirect URLs for OAuth callbacks (prevent open redirect vulnerability)
    # In production, all URLs must use HTTPS
    ALLOWED_REDIRECT_URLS: list[str] = [
        "http://localhost:5173",  # Vite dev server
        "http://localhost:3000",  # Common dev server
        "https://pharos.onrender.com",  # Production cloud
    ]

    # CSRF Protection: Allowed origins for cross-origin requests
    # Used by CSRFMiddleware to validate Origin/Referer headers
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

    # JWT Authentication
    # Default value provided for development convenience, but MUST be changed in production
    JWT_SECRET_KEY: SecretStr = SecretStr(
        "change-this-secret-key-in-production-min-32-chars-long"
    )
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # OAuth2 Providers - Google
    GOOGLE_CLIENT_ID: str | None = None
    GOOGLE_CLIENT_SECRET: SecretStr | None = None
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/auth/google/callback"

    # OAuth2 Providers - GitHub
    GITHUB_CLIENT_ID: str | None = None
    GITHUB_CLIENT_SECRET: SecretStr | None = None
    GITHUB_REDIRECT_URI: str = "http://localhost:8000/auth/github/callback"

    # GitHub API token for code-intelligence reads (separate from OAuth).
    # Personal Access Token (classic) with repo:read scope.
    # Raises unauthenticated rate limit from 60 → 5,000 req/hr.
    GITHUB_API_TOKEN: SecretStr | None = None

    # GitHub fetcher concurrency cap (simultaneous raw-content requests)
    GITHUB_FETCH_CONCURRENCY: int = 10

    # Redis URL shorthand (overrides REDIS_HOST/PORT when set)
    REDIS_URL: str | None = None  # e.g. "redis://localhost:6379/2"

    # Rate Limiting
    RATE_LIMIT_FREE_TIER: int = 100  # requests per minute
    RATE_LIMIT_PREMIUM_TIER: int = 1000  # requests per minute
    RATE_LIMIT_ADMIN_TIER: int = 10000  # 0 = unlimited

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

    @field_validator("JWT_SECRET_KEY")
    @classmethod
    def validate_jwt_secret(cls, v: SecretStr, info) -> SecretStr:
        """Validate JWT secret key meets security requirements."""
        secret = v.get_secret_value()
        if len(secret) < 32:
            raise ValueError(
                f"JWT_SECRET_KEY must be at least 32 characters, got {len(secret)}"
            )
        # Only reject default value in production
        if secret == "change-this-secret-key-in-production-min-32-chars-long":
            # Check if we're in production mode (will be validated in model_validator)
            # For now, just validate length - production check happens in model_validator
            pass
        return v

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
            raise ValueError(f"QUEUE_SIZE must be positive, got: {v}")
        return v

    @field_validator("ALLOWED_REDIRECT_URLS")
    @classmethod
    def validate_redirect_urls(cls, v: list[str], info) -> list[str]:
        """Validate redirect URLs meet security requirements.

        In production, all redirect URLs must use HTTPS to prevent open redirect attacks.
        HTTP URLs are only allowed for localhost in development mode.

        This validator performs basic format validation. Full HTTPS enforcement
        for production is done in model_validator.
        """
        import warnings

        non_https_urls = []
        for url in v:
            if not url.startswith(("http://", "https://")):
                raise ValueError(
                    f"Redirect URL must start with http:// or https://: {url}"
                )
            if url.startswith("http://"):
                non_https_urls.append(url)

        # Warn about non-HTTPS URLs (will be enforced in model_validator for production)
        if non_https_urls:
            warnings.warn(
                f"Non-HTTPS redirect URLs detected: {non_https_urls}. "
                f"These will be rejected in production mode (ENV=prod). "
                f"Use HTTPS URLs for production deployments.",
                UserWarning,
            )

        return v

    @model_validator(mode="after")
    def validate_production_requirements(self):
        """Validate production environment requirements."""
        import os

        secret = self.JWT_SECRET_KEY.get_secret_value()

        # In production, reject default value and require minimum length
        if self.ENV == "prod":
            if len(secret) < 32:
                raise ValueError(
                    "JWT_SECRET_KEY must be at least 32 characters in production"
                )
            if secret == "change-this-secret-key-in-production-min-32-chars-long":
                raise ValueError(
                    "JWT_SECRET_KEY must be changed from default in production. "
                    'Generate a secure secret: python -c "import secrets; print(secrets.token_hex(32))"'
                )
            # TEST_MODE must not be enabled in production (both setting and env var)
            if self.TEST_MODE:
                raise ValueError(
                    "TEST_MODE must be False in production. "
                    "This is a security requirement to prevent authentication bypass."
                )
            # Also check TESTING environment variable (used by is_test_mode)
            if os.getenv("TESTING", "").lower() in ("true", "1", "yes"):
                raise ValueError(
                    "TESTING environment variable must not be set to 'true' in production. "
                    "This is a security requirement to prevent authentication bypass."
                )

            # Validate redirect URLs use HTTPS in production (prevent open redirect)
            for url in self.ALLOWED_REDIRECT_URLS:
                if not url.startswith("https://"):
                    raise ValueError(
                        f"Production redirect URLs must use HTTPS: {url}. "
                        f"HTTP URLs are only allowed for localhost in development mode."
                    )
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

    # API Authentication
    PHAROS_ADMIN_TOKEN: SecretStr | None = None  # Bearer token for /ingest endpoint

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

    class Config:
        env_file = "config/.env"
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
        Construct database URL based on configuration.

        Returns SQLite URL if DATABASE_URL is set to SQLite,
        otherwise constructs PostgreSQL async URL using asyncpg driver.
        Handles special characters in passwords via URL encoding.

        Returns:
            str: Database connection URL (SQLite or PostgreSQL)

        Examples:
            SQLite: sqlite:///./backend.db
            PostgreSQL: postgresql+asyncpg://user:pass@host:5432/db
        """
        from urllib.parse import quote

        if "sqlite" in self.DATABASE_URL.lower():
            return self.DATABASE_URL

        # URL-encode special characters in password
        encoded_password = quote(self.POSTGRES_PASSWORD or "", safe="")

        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:"
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

    # Validate JWT configuration
    if (
        not settings.JWT_SECRET_KEY
        or settings.JWT_SECRET_KEY.get_secret_value()
        == "change-this-secret-key-in-production"
    ):
        if settings.ENV == "prod":
            raise ValueError(
                "Configuration validation failed: JWT_SECRET_KEY must be set to a secure value in production. "
                "Expected type: SecretStr (non-default value)"
            )

    if settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES <= 0:
        raise ValueError(
            f"Configuration validation failed: JWT_ACCESS_TOKEN_EXPIRE_MINUTES must be positive, "
            f"got {settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES}. Expected type: int (> 0)"
        )

    if settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS <= 0:
        raise ValueError(
            f"Configuration validation failed: JWT_REFRESH_TOKEN_EXPIRE_DAYS must be positive, "
            f"got {settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS}. Expected type: int (> 0)"
        )

    # Validate rate limiting configuration
    if settings.RATE_LIMIT_FREE_TIER < 0:
        raise ValueError(
            f"Configuration validation failed: RATE_LIMIT_FREE_TIER must be non-negative, "
            f"got {settings.RATE_LIMIT_FREE_TIER}. Expected type: int (>= 0)"
        )

    if settings.RATE_LIMIT_PREMIUM_TIER < 0:
        raise ValueError(
            f"Configuration validation failed: RATE_LIMIT_PREMIUM_TIER must be non-negative, "
            f"got {settings.RATE_LIMIT_PREMIUM_TIER}. Expected type: int (>= 0)"
        )

    if settings.RATE_LIMIT_ADMIN_TIER < 0:
        raise ValueError(
            f"Configuration validation failed: RATE_LIMIT_ADMIN_TIER must be non-negative (0 = unlimited), "
            f"got {settings.RATE_LIMIT_ADMIN_TIER}. Expected type: int (>= 0)"
        )

    # Validate PostgreSQL configuration when using PostgreSQL
    if "postgresql" in settings.DATABASE_URL.lower():
        if not settings.POSTGRES_SERVER:
            raise ValueError(
                "Configuration validation failed: POSTGRES_SERVER must be set when using PostgreSQL. "
                "Expected type: str (non-empty)"
            )
        if not settings.POSTGRES_USER:
            raise ValueError(
                "Configuration validation failed: POSTGRES_USER must be set when using PostgreSQL. "
                "Expected type: str (non-empty)"
            )
        if not settings.POSTGRES_PASSWORD:
            raise ValueError(
                "Configuration validation failed: POSTGRES_PASSWORD must be set when using PostgreSQL. "
                "Expected type: str (non-empty)"
            )
        if not settings.POSTGRES_DB:
            raise ValueError(
                "Configuration validation failed: POSTGRES_DB must be set when using PostgreSQL. "
                "Expected type: str (non-empty)"
            )
        if settings.POSTGRES_PORT <= 0 or settings.POSTGRES_PORT > 65535:
            raise ValueError(
                f"Configuration validation failed: POSTGRES_PORT must be between 1 and 65535, "
                f"got {settings.POSTGRES_PORT}. Expected type: int (1-65535)"
            )

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
                f"Configuration validation failed: QUEUE_SIZE must be positive, "
                f"got {settings.QUEUE_SIZE}. Expected type: int (> 0)"
            )

        if settings.TASK_TTL <= 0:
            raise ValueError(
                f"Configuration validation failed: TASK_TTL must be positive, "
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


def validate_redirect_url(
    redirect_url: str, settings: Settings | None = None
) -> tuple[bool, str]:
    """
    Validate a redirect URL against the allowed list.

    This function prevents open redirect vulnerabilities by ensuring:
    1. The URL is in the allowed list
    2. In production mode, the URL uses HTTPS

    Args:
        redirect_url: The redirect URL to validate
        settings: Optional Settings instance (will use get_settings() if not provided)

    Returns:
        tuple: (is_valid: bool, error_message: str)

    Examples:
        >>> validate_redirect_url("https://example.com/callback")
        (True, "")

        >>> validate_redirect_url("http://evil.com", settings)
        (False, "Redirect URL not in allowed list")

        >>> validate_redirect_url("http://example.com", settings)  # In production
        (False, "Redirect URL must use HTTPS in production")
    """
    from urllib.parse import urlparse

    if settings is None:
        settings = get_settings()

    if not redirect_url:
        return False, "Redirect URL cannot be empty"

    # Parse the URL
    try:
        parsed = urlparse(redirect_url)
    except Exception:
        return False, "Invalid URL format"

    # Build the base URL (scheme + netloc) for comparison
    base_url = f"{parsed.scheme}://{parsed.netloc}"

    # Check if the base URL is in the allowed list
    is_allowed = False
    for allowed_url in settings.ALLOWED_REDIRECT_URLS:
        allowed_parsed = urlparse(allowed_url)
        allowed_base = f"{allowed_parsed.scheme}://{allowed_parsed.netloc}"

        # Exact match or prefix match (for paths)
        if base_url == allowed_base or redirect_url.startswith(allowed_url):
            is_allowed = True
            break

    if not is_allowed:
        return False, f"Redirect URL not in allowed list: {base_url}"

    # In production, enforce HTTPS
    if settings.ENV == "prod":
        if parsed.scheme != "https":
            return False, f"Redirect URL must use HTTPS in production: {redirect_url}"

    return True, ""
