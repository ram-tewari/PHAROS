# Security Fix Plan - Critical Issues

**Created**: 2026-02-16  
**Target Completion**: 2026-02-23 (7 days)  
**Status**: 🔴 Not Started

---

## Overview

This plan addresses 10 security vulnerabilities discovered in the security audit, with focus on 5 critical issues that must be fixed before production deployment.

**Estimated Effort**: 3-4 developer days  
**Priority**: P0 (Block production deployment)  
**Risk if not fixed**: Complete system compromise

---

## Day 1: Authentication & Secrets (4 hours)

### Task 1.1: Remove Hardcoded Secrets (ISSUE-2026-02-16-001)
**Time**: 1 hour  
**Priority**: P0

**Changes**:
```python
# backend/app/config/settings.py

# BEFORE:
JWT_SECRET_KEY: SecretStr = SecretStr("change-this-secret-key-in-production")
POSTGRES_PASSWORD: str = "devpassword"

# AFTER:
JWT_SECRET_KEY: SecretStr = Field(..., description="JWT secret key (required)")
POSTGRES_PASSWORD: SecretStr = Field(..., description="PostgreSQL password (required)")

# Add validation
@validator('JWT_SECRET_KEY')
def validate_jwt_secret(cls, v):
    secret = v.get_secret_value()
    if secret == "change-this-secret-key-in-production":
        raise ValueError("Default JWT secret detected - must set JWT_SECRET_KEY environment variable")
    if len(secret) < 32:
        raise ValueError("JWT secret must be at least 32 characters")
    return v

@validator('POSTGRES_PASSWORD')
def validate_postgres_password(cls, v):
    password = v.get_secret_value()
    if password == "devpassword":
        raise ValueError("Default PostgreSQL password detected - must set POSTGRES_PASSWORD environment variable")
    return v
```

**Files to modify**:
- `backend/app/config/settings.py`

**Testing**:
```bash
# Should fail without env vars
python -c "from app.config.settings import get_settings; get_settings()"

# Should succeed with env vars
export JWT_SECRET_KEY="$(openssl rand -base64 32)"
export POSTGRES_PASSWORD="secure_password_here"
python -c "from app.config.settings import get_settings; get_settings()"
```

---

### Task 1.2: Remove TEST_MODE Bypass (ISSUE-2026-02-16-002)
**Time**: 2 hours  
**Priority**: P0

**Changes**:

**Step 1**: Remove bypass from security.py
```python
# backend/app/shared/security.py

# DELETE THIS ENTIRE BLOCK (lines 363-375):
# if settings.is_test_mode or settings.TEST_MODE:
#     logger.info("TEST_MODE enabled - bypassing authentication")
#     try:
#         payload = decode_token(token)
#         return TokenData(...)
#     except Exception:
#         return TokenData(user_id=1, username="test_user", ...)

# KEEP ONLY:
# Structured error response for invalid/expired tokens (HTTP 401)
credentials_exception = HTTPException(...)
```

**Step 2**: Remove TEST_MODE checks from main app
```python
# backend/app/__init__.py

# DELETE all TEST_MODE checks:
# - Line 102-110: Module loading check
# - Line 213-217: Heavy initialization skip
# - Line 280-285: Lifespan skip
# - Line 325-327: Auth middleware skip

# REPLACE with proper dependency injection in tests
```

**Step 3**: Add environment validation
```python
# backend/app/config/settings.py

@validator('TEST_MODE')
def validate_test_mode(cls, v, values):
    env = values.get('ENV', 'development')
    if v and env == 'production':
        raise ValueError("TEST_MODE cannot be enabled in production environment")
    return v
```

**Files to modify**:
- `backend/app/shared/security.py`
- `backend/app/__init__.py`
- `backend/app/config/settings.py`

**Testing**:
```bash
# Should fail
export ENV=production
export TEST_MODE=true
python -c "from app.config.settings import get_settings; get_settings()"

# Should succeed
export ENV=development
export TEST_MODE=true
python -c "from app.config.settings import get_settings; get_settings()"
```

---

### Task 1.3: Add Rate Limiting to Auth Endpoints (ISSUE-2026-02-16-007)
**Time**: 1 hour  
**Priority**: P0

**Changes**:
```python
# backend/app/modules/auth/router.py

from app.shared.rate_limiter import rate_limit

# Add to login endpoint
@router.post("/login", response_model=TokenResponse)
@rate_limit(max_requests=5, window_seconds=900)  # 5 attempts per 15 minutes
async def login(...):
    ...

# Add to refresh endpoint
@router.post("/refresh", response_model=TokenResponse)
@rate_limit(max_requests=10, window_seconds=3600)  # 10 attempts per hour
async def refresh_token(...):
    ...
```

**Files to modify**:
- `backend/app/modules/auth/router.py`
- `backend/app/shared/rate_limiter.py` (add IP-based rate limiting)

**Testing**:
```bash
# Should block after 5 attempts
for i in {1..6}; do
  curl -X POST http://localhost:8000/auth/login \
    -H "Content-Type: application/json" \
    -d '{"username":"test","password":"wrong"}'
done
```

---

## Day 2: Token Security & Redirects (4 hours)

### Task 2.1: Fix Open Redirect & Token Leakage (ISSUE-2026-02-16-003 & 006)
**Time**: 3 hours  
**Priority**: P0

**Changes**:

**Step 1**: Implement redirect URL validation
```python
# backend/app/modules/auth/router.py

def validate_redirect_url(url: str, settings) -> bool:
    """Validate redirect URL against allowlist."""
    from urllib.parse import urlparse
    
    parsed = urlparse(url)
    
    # Must be HTTPS in production
    if settings.ENV == "production" and parsed.scheme != "https":
        return False
    
    # Check against allowlist
    allowed_hosts = [
        urlparse(settings.FRONTEND_URL).netloc,
        "localhost",
        "127.0.0.1"
    ]
    
    return parsed.netloc in allowed_hosts

# Use in OAuth callbacks
@router.get("/google/callback")
async def google_callback(...):
    ...
    # BEFORE:
    # frontend_callback_url = f"{settings.FRONTEND_URL}/auth/callback?access_token={access_token}&refresh_token={refresh_token}"
    
    # AFTER:
    if not validate_redirect_url(settings.FRONTEND_URL, settings):
        raise HTTPException(status_code=400, detail="Invalid redirect URL")
    
    response = RedirectResponse(url=f"{settings.FRONTEND_URL}/auth/callback")
    
    # Set tokens in HTTP-only cookies
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=settings.ENV == "production",
        samesite="lax",
        max_age=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=settings.ENV == "production",
        samesite="lax",
        max_age=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 86400
    )
    
    return response
```

**Step 2**: Update frontend to read cookies
```javascript
// Frontend needs to read from cookies instead of URL params
// Document this change in migration guide
```

**Files to modify**:
- `backend/app/modules/auth/router.py`
- `backend/docs/OAUTH2_MIGRATION_GUIDE.md` (create)

**Testing**:
```bash
# Should reject invalid redirect
curl -X GET "http://localhost:8000/auth/google/callback?code=test" \
  -H "Cookie: state=valid_state"

# Should set cookies, not URL params
curl -v -X GET "http://localhost:8000/auth/google/callback?code=test" \
  -H "Cookie: state=valid_state" | grep "Set-Cookie"
```

---

### Task 2.2: Add CSRF Protection (ISSUE-2026-02-16-010)
**Time**: 1 hour  
**Priority**: P1

**Changes**:
```python
# backend/app/shared/csrf.py (create new file)

import secrets
from fastapi import Request, HTTPException
from app.shared.cache import cache_service

def generate_csrf_token() -> str:
    """Generate CSRF token."""
    return secrets.token_urlsafe(32)

async def validate_csrf_token(request: Request) -> bool:
    """Validate CSRF token from header."""
    token = request.headers.get("X-CSRF-Token")
    if not token:
        return False
    
    # Verify token exists in cache (set during login)
    cached = await cache_service.get(f"csrf:{token}")
    return cached is not None

# Add middleware
# backend/app/__init__.py

@app.middleware("http")
async def csrf_middleware(request: Request, call_next):
    # Skip for GET, HEAD, OPTIONS
    if request.method in ["GET", "HEAD", "OPTIONS"]:
        return await call_next(request)
    
    # Skip for auth endpoints (use other protection)
    if request.url.path.startswith("/auth/"):
        return await call_next(request)
    
    # Validate CSRF token
    if not await validate_csrf_token(request):
        return JSONResponse(
            status_code=403,
            content={"detail": "CSRF token missing or invalid"}
        )
    
    return await call_next(request)
```

**Files to modify**:
- `backend/app/shared/csrf.py` (create)
- `backend/app/__init__.py`
- `backend/app/modules/auth/router.py` (return CSRF token on login)

---

## Day 3: Input Validation & SSRF (4 hours)

### Task 3.1: Fix SSRF in Repository Cloning (ISSUE-2026-02-16-005)
**Time**: 2 hours  
**Priority**: P0

**Changes**:
```python
# backend/app/routers/ingestion.py

import ipaddress
from urllib.parse import urlparse

def validate_git_url(url: str) -> tuple[bool, str]:
    """
    Validate Git URL against SSRF attacks.
    
    Returns:
        (is_valid, error_message)
    """
    try:
        parsed = urlparse(url)
        
        # Only allow https and git protocols
        if parsed.scheme not in ["https", "git"]:
            return False, f"Invalid protocol: {parsed.scheme}. Only https:// and git:// allowed"
        
        # Allowlist domains
        allowed_domains = [
            "github.com",
            "gitlab.com",
            "bitbucket.org",
            "git.sr.ht"  # SourceHut
        ]
        
        hostname = parsed.hostname
        if not hostname:
            return False, "Invalid URL: no hostname"
        
        # Check domain allowlist
        if not any(hostname.endswith(domain) for domain in allowed_domains):
            return False, f"Domain not allowed: {hostname}. Allowed: {', '.join(allowed_domains)}"
        
        # Block private IP ranges
        try:
            ip = ipaddress.ip_address(hostname)
            if ip.is_private or ip.is_loopback or ip.is_link_local:
                return False, f"Private IP addresses not allowed: {hostname}"
        except ValueError:
            # Not an IP address, continue with domain validation
            pass
        
        # Block cloud metadata endpoints
        if hostname in ["169.254.169.254", "metadata.google.internal"]:
            return False, "Cloud metadata endpoints not allowed"
        
        # URL length limit
        if len(url) > 500:
            return False, "URL too long (max 500 characters)"
        
        return True, ""
        
    except Exception as e:
        return False, f"Invalid URL: {str(e)}"

# Use in endpoint
@router.post("/ingest-repo")
async def ingest_repo(
    repo_url: str,
    token: str = Depends(verify_admin_token),
    redis: Redis = Depends(get_redis_client)
):
    # Validate URL
    is_valid, error_msg = validate_git_url(repo_url)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_msg)
    
    # Continue with ingestion...
```

**Files to modify**:
- `backend/app/routers/ingestion.py`

**Testing**:
```bash
# Should reject private IPs
curl -X POST http://localhost:8000/ingest-repo \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"repo_url":"http://192.168.1.1/repo.git"}'

# Should reject metadata endpoint
curl -X POST http://localhost:8000/ingest-repo \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"repo_url":"http://169.254.169.254/latest/meta-data/"}'

# Should accept valid URL
curl -X POST http://localhost:8000/ingest-repo \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"repo_url":"https://github.com/user/repo.git"}'
```

---

### Task 3.2: Fix File Upload Validation (ISSUE-2026-02-16-004)
**Time**: 2 hours  
**Priority**: P1

**Changes**:
```python
# backend/app/modules/resources/router.py

import magic  # python-magic library

# File validation constants
ALLOWED_EXTENSIONS = {".pdf", ".txt", ".md", ".html", ".htm"}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB

ALLOWED_MIME_TYPES = {
    ".pdf": "application/pdf",
    ".txt": "text/plain",
    ".md": "text/plain",
    ".html": "text/html",
    ".htm": "text/html"
}

def validate_file_upload(file: UploadFile, content: bytes) -> tuple[bool, str]:
    """
    Validate uploaded file for security.
    
    Returns:
        (is_valid, error_message)
    """
    # Check file size
    if len(content) > MAX_FILE_SIZE:
        return False, f"File too large: {len(content)} bytes (max {MAX_FILE_SIZE})"
    
    # Get file extension
    file_ext = Path(file.filename).suffix.lower()
    
    # Check extension allowlist
    if file_ext not in ALLOWED_EXTENSIONS:
        return False, f"File type not allowed: {file_ext}. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
    
    # Verify content type matches extension (magic number validation)
    try:
        mime = magic.from_buffer(content, mime=True)
        expected_mime = ALLOWED_MIME_TYPES.get(file_ext)
        
        if expected_mime and not mime.startswith(expected_mime.split('/')[0]):
            return False, f"File content ({mime}) doesn't match extension ({file_ext})"
    except Exception as e:
        logger.warning(f"Magic number validation failed: {e}")
        # Continue without magic validation if library not available
    
    # Check for null bytes (potential binary content in text file)
    if file_ext in [".txt", ".md", ".html", ".htm"]:
        if b'\x00' in content[:8192]:
            return False, "Binary content detected in text file"
    
    return True, ""

# Use in endpoint
@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    ...
):
    # Read file content
    file_content = await file.read()
    
    # Validate file
    is_valid, error_msg = validate_file_upload(file, file_content)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_msg)
    
    # Continue with upload...
```

**Files to modify**:
- `backend/app/modules/resources/router.py`
- `backend/requirements.txt` (add python-magic)

**Testing**:
```bash
# Should reject large file
dd if=/dev/zero of=large.pdf bs=1M count=51
curl -X POST http://localhost:8000/resources/upload \
  -F "file=@large.pdf"

# Should reject wrong extension
echo "not a pdf" > fake.pdf
curl -X POST http://localhost:8000/resources/upload \
  -F "file=@fake.pdf"

# Should accept valid file
curl -X POST http://localhost:8000/resources/upload \
  -F "file=@valid.pdf"
```

---

## Day 4: Cleanup & Monitoring (3 hours)

### Task 4.1: Fix Temporary File Cleanup (ISSUE-2026-02-16-009)
**Time**: 1 hour  
**Priority**: P2

**Changes**:
```python
# backend/app/utils/repo_parser.py

# BEFORE:
shutil.rmtree(temp_dir, ignore_errors=True)

# AFTER:
try:
    shutil.rmtree(temp_dir)
    logger.info(f"Cleaned up temporary directory: {temp_dir}")
except Exception as e:
    logger.error(f"Failed to cleanup temporary directory {temp_dir}: {e}")
    # Add to cleanup queue for retry
    await cache_service.set(f"cleanup:pending:{temp_dir}", "1", ttl=86400)

# Add periodic cleanup job
# backend/app/tasks/celery_tasks.py

@celery_app.task(name="cleanup_orphaned_temp_dirs")
def cleanup_orphaned_temp_dirs():
    """Cleanup orphaned temporary directories."""
    import tempfile
    temp_base = Path(tempfile.gettempdir())
    
    # Find old temp directories (>24 hours)
    cutoff = time.time() - 86400
    cleaned = 0
    
    for temp_dir in temp_base.glob("pharos_*"):
        if temp_dir.stat().st_mtime < cutoff:
            try:
                shutil.rmtree(temp_dir)
                cleaned += 1
                logger.info(f"Cleaned up orphaned directory: {temp_dir}")
            except Exception as e:
                logger.error(f"Failed to cleanup {temp_dir}: {e}")
    
    return {"cleaned": cleaned}
```

**Files to modify**:
- `backend/app/utils/repo_parser.py`
- `backend/app/modules/resources/logic/repo_ingestion.py`
- `backend/app/tasks/celery_tasks.py`

---

### Task 4.2: Add Security Monitoring (ISSUE-2026-02-16-008)
**Time**: 2 hours  
**Priority**: P2

**Changes**:
```python
# backend/app/shared/security_monitor.py (create new file)

import logging
from datetime import datetime
from app.shared.cache import cache_service

logger = logging.getLogger(__name__)

class SecurityMonitor:
    """Monitor and log security events."""
    
    @staticmethod
    async def log_auth_failure(username: str, ip: str, reason: str):
        """Log authentication failure."""
        key = f"auth:failures:{ip}"
        count = await cache_service.incr(key)
        await cache_service.expire(key, 3600)  # 1 hour TTL
        
        logger.warning(
            f"Authentication failure: username={username}, ip={ip}, "
            f"reason={reason}, count={count}"
        )
        
        # Alert if too many failures
        if count >= 10:
            logger.critical(
                f"SECURITY ALERT: Possible brute force attack from {ip} "
                f"({count} failures in last hour)"
            )
    
    @staticmethod
    async def log_ssrf_attempt(url: str, ip: str):
        """Log SSRF attempt."""
        logger.critical(
            f"SECURITY ALERT: SSRF attempt blocked - url={url}, ip={ip}"
        )
    
    @staticmethod
    async def log_file_upload_rejection(filename: str, reason: str, ip: str):
        """Log rejected file upload."""
        logger.warning(
            f"File upload rejected: filename={filename}, reason={reason}, ip={ip}"
        )
    
    @staticmethod
    async def log_test_mode_activation():
        """Log TEST_MODE activation (should never happen in production)."""
        logger.critical(
            "SECURITY ALERT: TEST_MODE activated - this should never happen in production!"
        )

# Use throughout codebase
```

**Files to modify**:
- `backend/app/shared/security_monitor.py` (create)
- `backend/app/modules/auth/router.py`
- `backend/app/routers/ingestion.py`
- `backend/app/modules/resources/router.py`

---

## Day 5: Testing & Documentation (4 hours)

### Task 5.1: Security Testing
**Time**: 2 hours

**Test Cases**:
```bash
# Test 1: Hardcoded secrets rejected
unset JWT_SECRET_KEY
python -c "from app.config.settings import get_settings; get_settings()"
# Expected: ValueError

# Test 2: TEST_MODE blocked in production
export ENV=production
export TEST_MODE=true
python -c "from app.config.settings import get_settings; get_settings()"
# Expected: ValueError

# Test 3: Rate limiting works
for i in {1..6}; do
  curl -X POST http://localhost:8000/auth/login \
    -d '{"username":"test","password":"wrong"}'
done
# Expected: 429 on 6th request

# Test 4: SSRF blocked
curl -X POST http://localhost:8000/ingest-repo \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"repo_url":"http://169.254.169.254/"}'
# Expected: 400 with error message

# Test 5: File upload validation
echo "fake pdf" > test.pdf
curl -X POST http://localhost:8000/resources/upload -F "file=@test.pdf"
# Expected: 400 with validation error

# Test 6: Tokens in cookies, not URLs
curl -v http://localhost:8000/auth/google/callback?code=test
# Expected: Set-Cookie headers, no tokens in redirect URL

# Test 7: CSRF protection
curl -X POST http://localhost:8000/resources \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"title":"test"}'
# Expected: 403 without CSRF token

curl -X POST http://localhost:8000/resources \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-CSRF-Token: $CSRF_TOKEN" \
  -d '{"title":"test"}'
# Expected: 201 with CSRF token
```

---

### Task 5.2: Update Documentation
**Time**: 2 hours

**Documents to create/update**:

1. **Security Configuration Guide**
```markdown
# backend/docs/SECURITY_CONFIGURATION.md

## Required Environment Variables

### Production (Required)
- JWT_SECRET_KEY: 32+ character random string
- POSTGRES_PASSWORD: Strong database password
- ENV: Set to "production"

### Generate Secrets
```bash
# JWT Secret
openssl rand -base64 32

# PostgreSQL Password
openssl rand -base64 24
```

## Security Checklist
- [ ] JWT_SECRET_KEY set to random value
- [ ] POSTGRES_PASSWORD set to strong password
- [ ] TEST_MODE disabled (not set)
- [ ] ENV set to "production"
- [ ] FRONTEND_URL uses HTTPS
- [ ] Rate limiting enabled
- [ ] CSRF protection enabled
```

2. **OAuth2 Migration Guide**
```markdown
# backend/docs/OAUTH2_MIGRATION_GUIDE.md

## Breaking Changes

### Tokens Now in Cookies
Tokens are no longer passed in URL parameters. Frontend must read from HTTP-only cookies.

### Before
```javascript
const params = new URLSearchParams(window.location.search);
const accessToken = params.get('access_token');
```

### After
```javascript
// Tokens automatically sent in cookies
// No code changes needed for API requests
fetch('/api/resources', {
  credentials: 'include'  // Include cookies
});
```
```

3. **Update main README**
```markdown
# backend/README.md

## Security

⚠️ **IMPORTANT**: Before deploying to production:
1. Set JWT_SECRET_KEY to random 32+ character string
2. Set POSTGRES_PASSWORD to strong password
3. Set ENV=production
4. Never enable TEST_MODE in production
5. Use HTTPS for FRONTEND_URL

See [Security Configuration Guide](docs/SECURITY_CONFIGURATION.md)
```

---

## Verification Checklist

### Pre-Deployment Security Checklist

- [ ] All hardcoded secrets removed
- [ ] TEST_MODE bypass removed from production code
- [ ] Environment validation added (rejects TEST_MODE in production)
- [ ] Rate limiting added to auth endpoints
- [ ] Open redirect fixed with URL validation
- [ ] Tokens moved from URLs to HTTP-only cookies
- [ ] CSRF protection implemented
- [ ] SSRF protection added (URL allowlist, IP blocking)
- [ ] File upload validation enhanced (magic numbers, size limits)
- [ ] Temporary file cleanup fixed
- [ ] Security monitoring added
- [ ] All tests passing
- [ ] Documentation updated
- [ ] Security audit re-run (no critical issues)

---

## Rollout Plan

### Phase 1: Development (Day 1-3)
- Implement all fixes
- Run security tests
- Update documentation

### Phase 2: Staging (Day 4)
- Deploy to staging environment
- Run penetration tests
- Verify monitoring works

### Phase 3: Production (Day 5-7)
- Deploy to production
- Monitor for issues
- Run post-deployment security scan

---

## Monitoring After Deployment

### Metrics to Watch

1. **Authentication Failures**
   - Alert if >10 failures from single IP in 1 hour
   - Alert if >100 failures globally in 1 hour

2. **SSRF Attempts**
   - Alert on any blocked SSRF attempt
   - Review logs daily

3. **File Upload Rejections**
   - Monitor rejection rate
   - Alert if >50% rejection rate (possible attack)

4. **Rate Limit Hits**
   - Monitor rate limit violations
   - Alert if single IP hits limit repeatedly

5. **CSRF Failures**
   - Monitor CSRF token failures
   - Alert if >10 failures in 1 hour

---

## Rollback Plan

If critical issues discovered after deployment:

1. **Immediate**: Revert to previous version
2. **Within 1 hour**: Identify root cause
3. **Within 4 hours**: Fix and redeploy
4. **Within 24 hours**: Post-mortem and prevention plan

---

## Success Criteria

- [ ] All 10 security issues resolved
- [ ] Security audit shows 0 critical issues
- [ ] All tests passing (unit, integration, security)
- [ ] Documentation complete and reviewed
- [ ] Staging deployment successful
- [ ] Production deployment successful
- [ ] No security incidents in first 7 days

---

## Resources

- **Issue Tracker**: `backend/docs/ISSUES.md`
- **Security Audit**: `backend/docs/SECURITY_AUDIT_2026-02-16.md`
- **Issue Guidelines**: `.kiro/steering/issue-tracking.md`

---

## Contact

For questions or issues during implementation:
- Review security audit report
- Check issue tracker for details
- Consult OWASP guidelines
- Run security tests frequently

---

**Status**: Ready to begin  
**Next Step**: Start Day 1 tasks  
**Estimated Completion**: 2026-02-23
