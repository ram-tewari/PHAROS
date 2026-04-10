# Phase 21.5: Backend Stabilization - Design

## Overview

This document outlines the technical design for stabilizing the Pharos backend by fixing all 267 failing tests, resolving 22 open issues, and implementing comprehensive security hardening. The design follows a systematic approach organized by problem category.

## Architecture Principles

1. **Security First**: All security issues resolved before feature fixes
2. **Test-Driven Fixes**: Fix tests to validate correct behavior, not to pass incorrectly
3. **Minimal Changes**: Make smallest changes necessary to fix issues
4. **Backward Compatibility**: Maintain API compatibility where possible
5. **Configuration Validation**: Validate all configuration at startup
6. **Proper Mocking**: Use dependency injection for testability

## Problem Categories and Solutions

### Category 1: Security Hardening (Critical Priority)

#### 1.1 Hardcoded Secrets Removal

**Problem**: JWT_SECRET_KEY and POSTGRES_PASSWORD have default values

**Solution**:
```python
# backend/app/config/settings.py
class Settings(BaseSettings):
    # Remove defaults, make required
    JWT_SECRET_KEY: SecretStr  # No default
    POSTGRES_PASSWORD: str | None = None  # Optional for SQLite
    
    @validator('JWT_SECRET_KEY')
    def validate_jwt_secret(cls, v):
        secret = v.get_secret_value()
        if secret == "change-this-secret-key-in-production":
            raise ValueError("JWT_SECRET_KEY must be changed from default")
        if len(secret) < 32:
            raise ValueError("JWT_SECRET_KEY must be at least 32 characters")
        return v
    
    def model_post_init(self, __context):
        # Validate production requirements
        if self.ENV == "production":
            if not self.JWT_SECRET_KEY:
                raise ValueError("JWT_SECRET_KEY required in production")
```

**Files Changed**:
- `backend/app/config/settings.py`
- `backend/.env.example` (add required variables)
- `backend/docs/deployment.md` (document requirements)

#### 1.2 Authentication Bypass Removal

**Problem**: TEST_MODE bypasses authentication in production code

**Solution**:
```python
# backend/app/shared/security.py
# Remove TEST_MODE checks from production code

# backend/tests/conftest.py
@pytest.fixture
def bypass_auth(monkeypatch):
    """Fixture to bypass auth in tests via dependency override"""
    from app.shared.security import get_current_user
    
    async def mock_get_current_user():
        return User(id=1, email="test@example.com", tier="free")
    
    # Override dependency in FastAPI app
    app.dependency_overrides[get_current_user] = mock_get_current_user
    yield
    app.dependency_overrides.clear()
```

**Files Changed**:
- `backend/app/shared/security.py` (remove TEST_MODE checks)
- `backend/tests/conftest.py` (add bypass_auth fixture)
- All test files using TEST_MODE (use bypass_auth fixture)

#### 1.3 Open Redirect Fix

**Problem**: OAuth2 callback redirects without validation

**Solution**:
```python
# backend/app/config/settings.py
class Settings(BaseSettings):
    ALLOWED_REDIRECT_URLS: list[str] = ["http://localhost:3000", "http://localhost:5173"]
    
    @validator('ALLOWED_REDIRECT_URLS')
    def validate_redirect_urls(cls, v, values):
        if values.get('ENV') == 'production':
            for url in v:
                if not url.startswith('https://'):
                    raise ValueError(f"Production redirect URLs must use HTTPS: {url}")
        return v

# backend/app/modules/auth/router.py
def validate_redirect_url(url: str, settings: Settings) -> bool:
    """Validate redirect URL against allowlist"""
    parsed = urlparse(url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"
    return base_url in settings.ALLOWED_REDIRECT_URLS

@router.get("/callback/google")
async def google_callback(code: str, state: str):
    # Exchange code for tokens
    tokens = await oauth_provider.exchange_code(code)
    
    # Use HTTP-only cookies instead of URL parameters
    response = RedirectResponse(url=f"{settings.FRONTEND_URL}/auth/success")
    response.set_cookie(
        key="access_token",
        value=tokens.access_token,
        httponly=True,
        secure=settings.ENV == "production",
        samesite="lax",
        max_age=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )
    response.set_cookie(
        key="refresh_token",
        value=tokens.refresh_token,
        httponly=True,
        secure=settings.ENV == "production",
        samesite="lax",
        max_age=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 86400
    )
    return response
```


**Files Changed**:
- `backend/app/config/settings.py` (add ALLOWED_REDIRECT_URLS)
- `backend/app/modules/auth/router.py` (validate redirects, use cookies)
- `backend/app/modules/auth/service.py` (token handling)

#### 1.4 CSRF Protection

**Problem**: No CSRF protection on state-changing endpoints

**Solution**:
```python
# backend/app/middleware/csrf.py
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
import secrets

class CSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Skip CSRF for safe methods
        if request.method in ["GET", "HEAD", "OPTIONS"]:
            return await call_next(request)
        
        # Skip CSRF for API key authentication
        if request.headers.get("Authorization", "").startswith("Bearer"):
            # Validate Origin/Referer for API requests
            origin = request.headers.get("Origin") or request.headers.get("Referer")
            if origin and not self._is_allowed_origin(origin):
                raise HTTPException(status_code=403, detail="Invalid origin")
        
        return await call_next(request)
    
    def _is_allowed_origin(self, origin: str) -> bool:
        # Check against allowed origins
        allowed = [settings.FRONTEND_URL, settings.API_URL]
        return any(origin.startswith(allowed_origin) for allowed_origin in allowed)

# backend/app/__init__.py
app.add_middleware(CSRFMiddleware)
```

**Files Changed**:
- `backend/app/middleware/csrf.py` (new file)
- `backend/app/__init__.py` (register middleware)

#### 1.5 Rate Limiting on Auth Endpoints

**Problem**: No rate limiting on /auth/login and /auth/refresh

**Solution**:
```python
# backend/app/shared/rate_limiter.py
async def check_auth_rate_limit(
    identifier: str,  # IP or user ID
    endpoint: str,  # "login" or "refresh"
    redis: Redis
) -> bool:
    """Strict rate limiting for authentication endpoints"""
    limits = {
        "login": (5, 900),  # 5 attempts per 15 minutes
        "refresh": (10, 3600),  # 10 attempts per hour
    }
    max_attempts, window = limits.get(endpoint, (10, 60))
    
    key = f"auth_rate_limit:{endpoint}:{identifier}"
    current = await redis.incr(key)
    
    if current == 1:
        await redis.expire(key, window)
    
    if current > max_attempts:
        return False
    
    return True

# backend/app/modules/auth/router.py
@router.post("/login")
async def login(
    credentials: LoginRequest,
    request: Request,
    redis: Redis = Depends(get_redis)
):
    # Check rate limit
    ip = request.client.host
    if not await check_auth_rate_limit(ip, "login", redis):
        raise HTTPException(
            status_code=429,
            detail="Too many login attempts. Please try again later."
        )
    
    # Proceed with authentication
    ...
```

**Files Changed**:
- `backend/app/shared/rate_limiter.py` (add auth rate limiting)
- `backend/app/modules/auth/router.py` (apply rate limiting)

#### 1.6 Repository URL Validation (SSRF Prevention)

**Problem**: Arbitrary Git URLs accepted without validation

**Solution**:
```python
# backend/app/utils/url_validator.py
from urllib.parse import urlparse
import ipaddress
import re

ALLOWED_DOMAINS = [
    "github.com",
    "gitlab.com",
    "bitbucket.org",
    "git.sr.ht",
]

BLOCKED_IP_RANGES = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),  # Cloud metadata
    ipaddress.ip_network("::1/128"),  # IPv6 localhost
    ipaddress.ip_network("fc00::/7"),  # IPv6 private
]

def validate_repository_url(url: str) -> tuple[bool, str]:
    """Validate repository URL for SSRF prevention"""
    # Check URL format
    if not re.match(r'^https?://[\w\-\.]+/[\w\-\.]+/[\w\-\.]+$', url):
        return False, "Invalid URL format"
    
    parsed = urlparse(url)
    
    # Only allow HTTPS
    if parsed.scheme != "https":
        return False, "Only HTTPS URLs allowed"
    
    # Check domain allowlist
    if parsed.netloc not in ALLOWED_DOMAINS:
        return False, f"Domain not allowed. Allowed: {', '.join(ALLOWED_DOMAINS)}"
    
    # Resolve hostname and check IP
    try:
        import socket
        ip = socket.gethostbyname(parsed.netloc)
        ip_obj = ipaddress.ip_address(ip)
        
        for blocked_range in BLOCKED_IP_RANGES:
            if ip_obj in blocked_range:
                return False, "IP address in blocked range"
    except Exception as e:
        return False, f"Failed to resolve hostname: {e}"
    
    return True, "Valid"

# backend/app/routers/ingestion.py
@router.post("/ingest-repo")
async def ingest_repo(repo_url: str, ...):
    # Validate URL
    is_valid, message = validate_repository_url(repo_url)
    if not is_valid:
        raise HTTPException(status_code=400, detail=message)
    
    # Proceed with ingestion
    ...
```

**Files Changed**:
- `backend/app/utils/url_validator.py` (new file)
- `backend/app/routers/ingestion.py` (apply validation)
- `backend/app/modules/resources/logic/repo_ingestion.py` (apply validation)

### Category 2: Configuration Management

#### 2.1 Settings Mocking Fix

**Problem**: Settings mocked incorrectly causing attribute access issues

**Solution**:
```python
# backend/tests/conftest.py
@pytest.fixture
def mock_settings():
    """Properly mocked Settings object"""
    from app.config.settings import Settings
    
    # Create real Settings instance with test values
    settings = Settings(
        ENV="test",
        DATABASE_URL="sqlite:///:memory:",
        JWT_SECRET_KEY="test-secret-key-min-32-chars-long",
        JWT_ALGORITHM="HS256",
        JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30,
        JWT_REFRESH_TOKEN_EXPIRE_DAYS=7,
        RATE_LIMIT_FREE_TIER=100,
        RATE_LIMIT_PREMIUM_TIER=1000,
        RATE_LIMIT_ADMIN_TIER=10000,
        TEST_MODE=True,
        REDIS_HOST="localhost",
        REDIS_PORT=6379,
        GRAPH_WEIGHT_VECTOR=0.6,
        GRAPH_WEIGHT_TAGS=0.3,
        GRAPH_WEIGHT_CLASSIFICATION=0.1,
        DEFAULT_HYBRID_SEARCH_WEIGHT=0.5,
        MIN_QUALITY_THRESHOLD=0.3,
        CHUNK_ON_RESOURCE_CREATE=False,
        GRAPH_EXTRACTION_ENABLED=True,
        SYNTHETIC_QUESTIONS_ENABLED=False,
        DEFAULT_RETRIEVAL_STRATEGY="parent-child",
        MODE="CLOUD",
        QUEUE_SIZE=10,
        TASK_TTL=86400,
        WORKER_POLL_INTERVAL=2,
    )
    
    return settings

@pytest.fixture(autouse=True)
def override_get_settings(mock_settings):
    """Override get_settings dependency"""
    from app.config.settings import get_settings
    
    def _get_test_settings():
        return mock_settings
    
    # Store original
    original = get_settings
    
    # Override
    app.dependency_overrides[get_settings] = _get_test_settings
    
    yield mock_settings
    
    # Restore
    app.dependency_overrides.clear()
```

**Files Changed**:
- `backend/tests/conftest.py` (fix Settings mocking)
- All test files (remove manual Settings mocking)


#### 2.2 Requirements Files Split

**Problem**: Missing requirements-base.txt, requirements-cloud.txt, requirements-edge.txt

**Solution**:
```txt
# requirements-base.txt (shared dependencies)
fastapi>=0.104.0
uvicorn[standard]>=0.24.0
sqlalchemy>=2.0.0
alembic>=1.12.0
pydantic>=2.0.0
pydantic-settings>=2.0.0
httpx>=0.25.0
python-jose[cryptography]>=3.3.0
passlib[bcrypt]>=1.7.4
python-multipart>=0.0.6
redis>=5.0.0
celery>=5.3.0

# requirements-cloud.txt (cloud-specific, no GPU)
-r requirements-base.txt
# Exclude torch, transformers with GPU support
sentence-transformers>=2.2.0  # CPU only
openai>=1.0.0
anthropic>=0.7.0

# requirements-edge.txt (edge-specific, with GPU)
-r requirements-base.txt
torch>=2.0.0  # With CUDA support
transformers>=4.30.0
sentence-transformers>=2.2.0
qdrant-client>=1.7.0
```

**Files Changed**:
- `backend/requirements-base.txt` (new file)
- `backend/requirements-cloud.txt` (new file)
- `backend/requirements-edge.txt` (new file)
- `backend/requirements.txt` (keep for backward compatibility, point to base)

#### 2.3 Environment Variable Validation

**Problem**: Missing validation for required environment variables

**Solution**:
```python
# backend/app/config/settings.py
class Settings(BaseSettings):
    @validator('MODE')
    def validate_mode(cls, v):
        if v not in ['CLOUD', 'EDGE']:
            raise ValueError(f"MODE must be 'CLOUD' or 'EDGE', got: {v}")
        return v
    
    @validator('QUEUE_SIZE')
    def validate_queue_size(cls, v):
        if v <= 0:
            raise ValueError(f"QUEUE_SIZE must be positive, got: {v}")
        return v
    
    def model_post_init(self, __context):
        # Validate MODE-specific requirements
        if self.MODE == 'CLOUD':
            if not self.UPSTASH_REDIS_REST_URL:
                raise ValueError("UPSTASH_REDIS_REST_URL required in CLOUD mode")
            if not self.UPSTASH_REDIS_REST_TOKEN:
                raise ValueError("UPSTASH_REDIS_REST_TOKEN required in CLOUD mode")
            if not self.PHAROS_ADMIN_TOKEN:
                raise ValueError("PHAROS_ADMIN_TOKEN required in CLOUD mode")
            if not self.API_URL.startswith('https://'):
                raise ValueError("API_URL must use HTTPS in CLOUD mode")
        
        if self.MODE == 'EDGE':
            if not self.QDRANT_URL:
                raise ValueError("QDRANT_URL required in EDGE mode")
            if not self.QDRANT_API_KEY:
                raise ValueError("QDRANT_API_KEY required in EDGE mode")
```

**Files Changed**:
- `backend/app/config/settings.py` (add validation)

### Category 3: API Endpoint Registration

#### 3.1 Missing Endpoint Registration

**Problem**: Endpoints implemented but not registered (404 errors)

**Solution**:
```python
# backend/app/__init__.py
def register_all_routers(app: FastAPI):
    """Register all module routers"""
    # Existing routers
    app.include_router(resources_router, prefix="/api/v1/resources", tags=["resources"])
    app.include_router(search_router, prefix="/api/v1/search", tags=["search"])
    app.include_router(collections_router, prefix="/api/v1/collections", tags=["collections"])
    app.include_router(annotations_router, prefix="/api/v1/annotations", tags=["annotations"])
    app.include_router(graph_router, prefix="/api/v1/graph", tags=["graph"])
    app.include_router(quality_router, prefix="/api/v1/quality", tags=["quality"])
    app.include_router(taxonomy_router, prefix="/api/v1/taxonomy", tags=["taxonomy"])
    app.include_router(auth_router, prefix="/api/v1/auth", tags=["auth"])
    
    # Missing routers (causing 404s)
    app.include_router(rag_evaluation_router, prefix="/api/v1/rag/evaluation", tags=["rag-evaluation"])
    app.include_router(recommendations_router, prefix="/api/v1/recommendations", tags=["recommendations"])
    app.include_router(advanced_search_router, prefix="/api/v1/search/advanced", tags=["advanced-search"])
    app.include_router(chunking_router, prefix="/api/v1/chunks", tags=["chunks"])
    app.include_router(document_intelligence_router, prefix="/api/v1/document-intelligence", tags=["document-intelligence"])
    app.include_router(ai_planning_router, prefix="/api/v1/ai-planning", tags=["ai-planning"])
    app.include_router(mcp_router, prefix="/api/v1/mcp", tags=["mcp"])
    app.include_router(curation_router, prefix="/api/v1/curation", tags=["curation"])
```

**Files Changed**:
- `backend/app/__init__.py` (register missing routers)
- `backend/app/modules/quality/router.py` (ensure rag_evaluation_router exported)
- `backend/app/modules/recommendations/router.py` (ensure router exported)
- `backend/app/modules/search/router.py` (ensure advanced_search_router exported)
- `backend/app/modules/resources/router.py` (ensure chunking_router exported)

### Category 4: Phase 19 Cloud/Edge Fixes

#### 4.1 Worker Process Function

**Problem**: Cannot import process_job from worker.py

**Solution**:
```python
# backend/deployment/worker.py
import asyncio
from app.config.settings import get_settings
from app.modules.resources.logic.repo_ingestion import ingest_repository
from app.shared.database import get_db_session

async def process_job(job_data: dict) -> dict:
    """Process a repository ingestion job"""
    settings = get_settings()
    
    try:
        repo_url = job_data.get("repo_url")
        user_id = job_data.get("user_id")
        
        # Validate inputs
        if not repo_url:
            raise ValueError("repo_url required")
        
        # Get database session
        async with get_db_session() as session:
            # Ingest repository
            result = await ingest_repository(
                repo_url=repo_url,
                user_id=user_id,
                session=session,
                settings=settings
            )
        
        return {
            "status": "completed",
            "result": result,
            "error": None
        }
    
    except Exception as e:
        return {
            "status": "failed",
            "result": None,
            "error": str(e)
        }

def main():
    """Worker main loop"""
    settings = get_settings()
    
    # Connect to Redis queue
    redis_client = Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        decode_responses=True
    )
    
    while True:
        # Poll for jobs
        job = redis_client.blpop("pharos:jobs", timeout=settings.WORKER_POLL_INTERVAL)
        
        if job:
            job_data = json.loads(job[1])
            result = asyncio.run(process_job(job_data))
            
            # Store result
            redis_client.setex(
                f"pharos:result:{job_data['job_id']}",
                settings.TASK_TTL,
                json.dumps(result)
            )

if __name__ == "__main__":
    main()
```

**Files Changed**:
- `backend/deployment/worker.py` (implement process_job)

#### 4.2 Queue Service Configuration

**Problem**: Queue service not configured error

**Solution**:
```python
# backend/app/services/queue_service.py
from redis import Redis
from app.config.settings import get_settings

class QueueService:
    def __init__(self):
        self.settings = get_settings()
        self._redis = None
    
    @property
    def redis(self) -> Redis:
        if self._redis is None:
            if self.settings.MODE == "CLOUD":
                # Use Upstash Redis REST API
                if not self.settings.UPSTASH_REDIS_REST_URL:
                    raise ValueError("Queue service not configured: upstash_redis_rest_url must be set")
                if not self.settings.UPSTASH_REDIS_REST_TOKEN:
                    raise ValueError("Queue service not configured: upstash_redis_rest_token must be set")
                
                self._redis = Redis.from_url(
                    self.settings.UPSTASH_REDIS_REST_URL,
                    password=self.settings.UPSTASH_REDIS_REST_TOKEN,
                    decode_responses=True
                )
            else:
                # Use local Redis
                self._redis = Redis(
                    host=self.settings.REDIS_HOST,
                    port=self.settings.REDIS_PORT,
                    decode_responses=True
                )
        
        return self._redis
    
    async def submit_job(self, job_data: dict) -> str:
        """Submit job to queue"""
        job_id = str(uuid.uuid4())
        job_data["job_id"] = job_id
        
        # Check queue size
        queue_size = self.redis.llen("pharos:jobs")
        if queue_size >= self.settings.QUEUE_SIZE:
            raise HTTPException(status_code=429, detail="Queue is full")
        
        # Add to queue
        self.redis.rpush("pharos:jobs", json.dumps(job_data))
        
        return job_id
```

**Files Changed**:
- `backend/app/services/queue_service.py` (implement proper configuration)
- `backend/app/routers/ingestion.py` (use QueueService)


### Category 5: Database and Model Fixes

#### 5.1 Resource Model URL Parameter

**Problem**: Resource model doesn't accept 'url' parameter

**Solution**:
```python
# backend/app/database/models.py
class Resource(Base):
    __tablename__ = "resources"
    
    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    content = Column(Text)
    url = Column(String)  # Add url field
    resource_type = Column(String)
    language = Column(String)
    # ... other fields
    
    def __init__(self, **kwargs):
        # Accept url parameter
        if 'url' in kwargs:
            self.url = kwargs.pop('url')
        super().__init__(**kwargs)
```

**Files Changed**:
- `backend/app/database/models.py` (add url field)
- `backend/alembic/versions/YYYYMMDD_add_url_to_resources.py` (migration)

#### 5.2 Foreign Key Constraint Fixes

**Problem**: Tests fail with FOREIGN KEY constraint errors

**Solution**:
```python
# backend/tests/conftest.py
@pytest.fixture
async def sample_user(db_session):
    """Create sample user for tests"""
    user = User(
        id=1,
        email="test@example.com",
        hashed_password="hashed",
        tier="free",
        is_active=True,
        is_verified=True
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user

@pytest.fixture
async def sample_resource(db_session, sample_user):
    """Create sample resource with valid user_id"""
    resource = Resource(
        title="Test Resource",
        content="Test content",
        user_id=sample_user.id,  # Valid foreign key
        resource_type="code",
        language="python"
    )
    db_session.add(resource)
    await db_session.commit()
    await db_session.refresh(resource)
    return resource
```

**Files Changed**:
- `backend/tests/conftest.py` (ensure foreign keys satisfied)
- All test files (use fixtures with valid foreign keys)

#### 5.3 List Parameter Binding Fix

**Problem**: SQLite doesn't support list parameter binding

**Solution**:
```python
# backend/app/modules/recommendations/service.py
async def get_recommendations(resource_ids: list[int], session: AsyncSession):
    # Don't bind list directly
    # BAD: query.filter(Resource.id.in_(resource_ids))
    
    # GOOD: Use bindparam with expanding
    from sqlalchemy import bindparam
    stmt = select(Resource).where(
        Resource.id.in_(bindparam('ids', expanding=True))
    )
    result = await session.execute(stmt, {'ids': resource_ids})
    
    # OR: Build query dynamically
    if resource_ids:
        stmt = select(Resource).where(Resource.id.in_(resource_ids))
    else:
        stmt = select(Resource).where(False)  # Empty result
```

**Files Changed**:
- `backend/app/modules/recommendations/service.py` (fix list binding)
- `backend/app/modules/search/service.py` (fix list binding)

### Category 6: Performance Optimization

#### 6.1 Search Latency Optimization

**Problem**: Search takes >500ms, target is <500ms

**Solution**:
```python
# backend/app/modules/search/service.py
async def hybrid_search(query: str, top_k: int = 10):
    # Use parallel execution
    keyword_task = asyncio.create_task(keyword_search(query, top_k))
    semantic_task = asyncio.create_task(semantic_search(query, top_k))
    
    # Wait for both
    keyword_results, semantic_results = await asyncio.gather(
        keyword_task,
        semantic_task
    )
    
    # Merge results (fast)
    merged = merge_results(keyword_results, semantic_results)
    
    return merged[:top_k]

# Add caching
from functools import lru_cache

@lru_cache(maxsize=1000)
def get_embedding_cached(text: str):
    return get_embedding(text)
```

**Files Changed**:
- `backend/app/modules/search/service.py` (parallel execution, caching)
- `backend/app/shared/embeddings.py` (add caching)

#### 6.2 Hover Response Optimization

**Problem**: Hover takes >100ms, target is <100ms

**Solution**:
```python
# backend/app/modules/graph/router.py
# Add caching for hover info
from cachetools import TTLCache
hover_cache = TTLCache(maxsize=10000, ttl=300)  # 5 minute TTL

@router.get("/hover/{resource_id}")
async def get_hover_info(resource_id: int, line: int, column: int):
    cache_key = f"{resource_id}:{line}:{column}"
    
    # Check cache
    if cache_key in hover_cache:
        return hover_cache[cache_key]
    
    # Compute hover info (optimized)
    hover_info = await compute_hover_info_fast(resource_id, line, column)
    
    # Cache result
    hover_cache[cache_key] = hover_info
    
    return hover_info

async def compute_hover_info_fast(resource_id: int, line: int, column: int):
    # Use indexed queries
    # Limit related chunks to top 5
    # Skip embedding lookup if not needed
    ...
```

**Files Changed**:
- `backend/app/modules/graph/router.py` (add caching, optimize queries)

### Category 7: Event System Fixes

#### 7.1 Resource Chunking Event Handler

**Problem**: ChunkingService not called when resource.created event emitted

**Solution**:
```python
# backend/app/modules/resources/handlers.py
from app.events.event_system import event_bus
from app.modules/resources.service import ChunkingService

@event_bus.subscribe("resource.created")
async def handle_resource_created(event_data: dict):
    """Handle resource.created event"""
    resource_id = event_data.get("resource_id")
    
    if not resource_id:
        logger.error("resource.created event missing resource_id")
        return
    
    # Check if chunking is enabled
    settings = get_settings()
    if not settings.CHUNK_ON_RESOURCE_CREATE:
        logger.info(f"Chunking disabled, skipping resource {resource_id}")
        return
    
    # Trigger chunking
    chunking_service = ChunkingService()
    try:
        await chunking_service.chunk_resource(resource_id)
        logger.info(f"Chunked resource {resource_id}")
    except Exception as e:
        logger.error(f"Failed to chunk resource {resource_id}: {e}")

# Ensure handler is registered at startup
# backend/app/__init__.py
from app.modules.resources.handlers import handle_resource_created
# Handler auto-registers via @event_bus.subscribe decorator
```

**Files Changed**:
- `backend/app/modules/resources/handlers.py` (implement handler)
- `backend/app/modules/resources/service.py` (emit events)
- `backend/app/__init__.py` (import handlers to register)

### Category 8: OAuth2 and Authentication Fixes

#### 8.1 CircuitBreaker Integration Fix

**Problem**: CircuitBreaker object has no attribute 'success'

**Solution**:
```python
# backend/app/shared/oauth2.py
from circuitbreaker import circuit

class GoogleOAuth2Provider:
    def __init__(self):
        self.client_id = settings.GOOGLE_CLIENT_ID
        self.client_secret = settings.GOOGLE_CLIENT_SECRET
        # Don't create CircuitBreaker instance, use decorator
    
    @circuit(failure_threshold=5, recovery_timeout=60)
    async def exchange_code_for_token(self, code: str) -> dict:
        """Exchange authorization code for tokens"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code": code,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret.get_secret_value(),
                    "redirect_uri": f"{settings.API_URL}/auth/callback/google",
                    "grant_type": "authorization_code"
                }
            )
            response.raise_for_status()
            return response.json()
```

**Files Changed**:
- `backend/app/shared/oauth2.py` (fix CircuitBreaker usage)

#### 8.2 Token Revocation Fix

**Problem**: Token revocation not working (returns False)

**Solution**:
```python
# backend/app/shared/security.py
async def revoke_token(token: str, redis: Redis, ttl: int = None) -> bool:
    """Revoke a JWT token"""
    if ttl is None:
        # Use remaining token lifetime
        ttl = get_token_remaining_lifetime(token)
    
    # Store in Redis with TTL
    key = f"revoked_token:{token}"
    result = await redis.setex(key, ttl, "1")
    
    return result  # Returns True if successful

async def is_token_revoked(token: str, redis: Redis) -> bool:
    """Check if token is revoked"""
    key = f"revoked_token:{token}"
    result = await redis.get(key)
    return result is not None
```

**Files Changed**:
- `backend/app/shared/security.py` (fix token revocation)

### Category 9: Rate Limiting Fixes

#### 9.1 Rate Limiter Redis Integration

**Problem**: Rate limiter not setting headers or checking limits correctly

**Solution**:
```python
# backend/app/shared/rate_limiter.py
async def check_rate_limit(
    user_id: int,
    tier: str,
    redis: Redis
) -> tuple[bool, dict]:
    """Check rate limit and return headers"""
    # Get tier limit
    limits = {
        "free": settings.RATE_LIMIT_FREE_TIER,
        "premium": settings.RATE_LIMIT_PREMIUM_TIER,
        "admin": settings.RATE_LIMIT_ADMIN_TIER,
    }
    limit = limits.get(tier, settings.RATE_LIMIT_FREE_TIER)
    
    # Check current usage
    key = f"rate_limit:{user_id}"
    pipe = redis.pipeline()
    pipe.incr(key)
    pipe.ttl(key)
    current, ttl = await pipe.execute()
    
    # Set TTL if new key
    if ttl == -1:
        await redis.expire(key, 3600)  # 1 hour window
        ttl = 3600
    
    # Check if exceeded
    exceeded = current > limit
    
    # Build headers
    headers = {
        "X-RateLimit-Limit": str(limit),
        "X-RateLimit-Remaining": str(max(0, limit - current)),
        "X-RateLimit-Reset": str(int(time.time()) + ttl)
    }
    
    return not exceeded, headers
```

**Files Changed**:
- `backend/app/shared/rate_limiter.py` (fix implementation)

## Testing Strategy

### Test Fixture Improvements

```python
# backend/tests/conftest.py
@pytest.fixture
def quality_score_factory():
    """Factory for creating QualityScore objects"""
    def _create(**kwargs):
        defaults = {
            "overall_score": 0.8,
            "completeness": 0.9,
            "accuracy": 0.85,
            "clarity": 0.75,
            "relevance": 0.8,
        }
        defaults.update(kwargs)
        return QualityScore(**defaults)
    return _create

@pytest.fixture
def resource_factory(db_session, sample_user):
    """Factory for creating Resource objects"""
    async def _create(**kwargs):
        defaults = {
            "title": "Test Resource",
            "content": "Test content",
            "user_id": sample_user.id,
            "resource_type": "code",
            "language": "python",
        }
        defaults.update(kwargs)
        resource = Resource(**defaults)
        db_session.add(resource)
        await db_session.commit()
        await db_session.refresh(resource)
        return resource
    return _create
```

### Performance Test Threshold Updates

```python
# backend/tests/performance/test_search_performance.py
@pytest.mark.performance
async def test_search_latency():
    """Search must complete in <500ms"""
    start = time.time()
    results = await search_service.hybrid_search("test query")
    duration = (time.time() - start) * 1000
    
    assert duration < 500, f"Search took {duration}ms, expected <500ms"
```

## Related Documentation

- [Requirements](requirements.md)
- [Tasks](tasks.md)
- [ISSUES.md](../../../backend/docs/ISSUES.md)
- [Tech Stack](../../../.kiro/steering/tech.md)

