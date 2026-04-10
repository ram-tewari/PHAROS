# Authentication API

## Overview

The Authentication module provides JWT-based authentication with OAuth2 support for Google and GitHub. All protected endpoints require a valid JWT access token.

## Endpoints

### POST /api/auth/login

Authenticate with username and password using OAuth2 password flow.

**Request:**
```http
POST /api/auth/login HTTP/1.1
Content-Type: application/x-www-form-urlencoded

username=user@example.com&password=yourpassword&scopes=read
```

**Response (200 OK):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

**Error Responses:**
- `401 Unauthorized` - Invalid credentials
- `422 Unprocessable Entity` - Validation error

**Example (curl):**
```bash
curl -X POST http://127.0.0.1:8000/api/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=user@example.com&password=yourpassword"
```

**Example (Python):**
```python
import requests

response = requests.post(
    "http://127.0.0.1:8000/api/auth/login",
    data={
        "username": "user@example.com",
        "password": "yourpassword"
    }
)
tokens = response.json()
access_token = tokens["access_token"]
```

---

### POST /auth/refresh

Obtain a new access token using a refresh token.

**Request:**
```http
POST /auth/refresh HTTP/1.1
Content-Type: application/json

{
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

**Response (200 OK):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

**Error Responses:**
- `401 Unauthorized` - Invalid or expired refresh token
- `403 Forbidden` - Token has been revoked

**Example (curl):**
```bash
curl -X POST http://127.0.0.1:8000/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{"refresh_token": "your_refresh_token"}'
```

---

### POST /auth/logout

Revoke the current access token (logout).

**Request:**
```http
POST /auth/logout HTTP/1.1
Authorization: Bearer <access_token>
```

**Response (200 OK):**
```json
{
  "message": "Successfully logged out"
}
```

**Error Responses:**
- `401 Unauthorized` - Invalid or missing token

**Example (curl):**
```bash
curl -X POST http://127.0.0.1:8000/auth/logout \
  -H "Authorization: Bearer <access_token>"
```

---

### GET /auth/me

Get information about the currently authenticated user.

**Request:**
```http
GET /auth/me HTTP/1.1
Authorization: Bearer <access_token>
```

**Response (200 OK):**
```json
{
  "id": "123e4567-e89b-12d3-a456-426614174000",
  "username": "user@example.com",
  "email": "user@example.com",
  "tier": "premium",
  "is_active": true
}
```

**Error Responses:**
- `401 Unauthorized` - Invalid or missing token

**Example (curl):**
```bash
curl -X GET http://127.0.0.1:8000/auth/me \
  -H "Authorization: Bearer <access_token>"
```

---

### GET /auth/rate-limit

Get current rate limit status for the authenticated user.

**Request:**
```http
GET /auth/rate-limit HTTP/1.1
Authorization: Bearer <access_token>
```

**Response (200 OK):**
```json
{
  "tier": "premium",
  "limit": 1000,
  "remaining": 847,
  "reset": 1704067200
}
```

**Error Responses:**
- `401 Unauthorized` - Invalid or missing token

**Example (curl):**
```bash
curl -X GET http://127.0.0.1:8000/auth/rate-limit \
  -H "Authorization: Bearer <access_token>"
```

---

## OAuth2 Flows

### Google OAuth2

#### GET /auth/google

Initiate Google OAuth2 authentication flow.

**Request:**
```http
GET /auth/google HTTP/1.1
```

**Response (302 Found):**
Redirects to Google's authorization page.

**Example:**
```bash
# Open in browser
http://127.0.0.1:8000/auth/google
```

#### GET /auth/google/callback

Google OAuth2 callback endpoint (handled automatically).

**Query Parameters:**
- `code` - Authorization code from Google
- `state` - CSRF protection token

**Response (302 Found):**
Redirects to frontend with tokens in **HTTP-only cookies** (not URL parameters).

**Security Features:**
- Access token and refresh token set in `HttpOnly` cookies
- `Secure` flag set in production (HTTPS only)
- `SameSite=Lax` to prevent CSRF attacks
- Automatic token management by the browser

**Cookie Details:**
| Cookie | Max-Age | Security |
|--------|---------|----------|
| `access_token` | 30 minutes | HttpOnly, Secure, SameSite=Lax |
| `refresh_token` | 7 days | HttpOnly, Secure, SameSite=Lax |

**Redirect Flow:**
```
1. User completes Google authorization
2. Backend exchanges code for tokens
3. Backend sets tokens in HTTP-only cookies
4. Backend redirects to: {FRONTEND_URL}/auth/success
5. Frontend receives cookies automatically
6. Subsequent API requests include cookies
```

**Setup:**
1. Create OAuth2 credentials at [Google Cloud Console](https://console.cloud.google.com/apis/credentials)
2. Set authorized redirect URI: `http://localhost:8000/auth/google/callback`
3. Configure environment variables:
```bash
GOOGLE_CLIENT_ID=your-client-id
GOOGLE_CLIENT_SECRET=your-client-secret
GOOGLE_REDIRECT_URI=http://localhost:8000/auth/google/callback
FRONTEND_URL=http://localhost:3000
```

---

### GitHub OAuth2

#### GET /auth/github

Initiate GitHub OAuth2 authentication flow.

**Request:**
```http
GET /auth/github HTTP/1.1
```

**Response (302 Found):**
Redirects to GitHub's authorization page.

**Example:**
```bash
# Open in browser
http://127.0.0.1:8000/auth/github
```

#### GET /auth/github/callback

GitHub OAuth2 callback endpoint (handled automatically).

**Query Parameters:**
- `code` - Authorization code from GitHub
- `state` - CSRF protection token

**Response (302 Found):**
Redirects to frontend with tokens in **HTTP-only cookies** (not URL parameters).

**Security Features:**
- Access token and refresh token set in `HttpOnly` cookies
- `Secure` flag set in production (HTTPS only)
- `SameSite=Lax` to prevent CSRF attacks
- Automatic token management by the browser

**Cookie Details:**
| Cookie | Max-Age | Security |
|--------|---------|----------|
| `access_token` | 30 minutes | HttpOnly, Secure, SameSite=Lax |
| `refresh_token` | 7 days | HttpOnly, Secure, SameSite=Lax |

**Redirect Flow:**
```
1. User completes GitHub authorization
2. Backend exchanges code for tokens
3. Backend sets tokens in HTTP-only cookies
4. Backend redirects to: {FRONTEND_URL}/auth/success
5. Frontend receives cookies automatically
6. Subsequent API requests include cookies
```

**Setup:**
1. Create OAuth App at [GitHub Developer Settings](https://github.com/settings/developers)
2. Set authorization callback URL: `http://localhost:8000/auth/github/callback`
3. Configure environment variables:
```bash
GITHUB_CLIENT_ID=your-client-id
GITHUB_CLIENT_SECRET=your-client-secret
GITHUB_REDIRECT_URI=http://localhost:8000/auth/github/callback
FRONTEND_URL=http://localhost:3000
```

---

## JWT Token Structure

### Access Token Claims

```json
{
  "sub": "user@example.com",
  "user_id": "123e4567-e89b-12d3-a456-426614174000",
  "tier": "premium",
  "scopes": ["read", "write"],
  "type": "access",
  "exp": 1704067200,
  "iat": 1704065400
}
```

**Claims:**
- `sub` - Subject (username/email)
- `user_id` - User UUID
- `tier` - Rate limit tier (free, premium, admin)
- `scopes` - Permission scopes
- `type` - Token type (access or refresh)
- `exp` - Expiration timestamp
- `iat` - Issued at timestamp

### Refresh Token Claims

```json
{
  "sub": "user@example.com",
  "user_id": "123e4567-e89b-12d3-a456-426614174000",
  "type": "refresh",
  "exp": 1704672000,
  "iat": 1704065400
}
```

**Note:** Refresh tokens have minimal claims and longer expiration.

## Security Enhancements (Phase 21.5)

### Cookie-Based Token Transmission

As of Phase 21.5, OAuth2 callbacks transmit tokens via **HTTP-only cookies** instead of URL parameters. This provides significant security improvements:

| Aspect | Old (URL Parameters) | New (HTTP-only Cookies) |
|--------|---------------------|------------------------|
| Token Exposure | Visible in browser history | Never exposed to JavaScript |
| Referer Header | Tokens leaked to third parties | Tokens never sent |
| Server Logs | Tokens logged in access logs | Tokens in secure cookies |
| XSS Protection | Tokens accessible via JS | HttpOnly blocks JS access |
| CSRF Protection | None (tokens in URL) | SameSite=Lax prevents CSRF |

### Cookie Security Attributes

All authentication cookies include the following security attributes:

- **HttpOnly**: Prevents JavaScript access, protecting against XSS attacks
- **Secure**: Cookie only transmitted over HTTPS connections
- **SameSite=Lax**: Prevents CSRF attacks while allowing normal navigation
- **Max-Age**: Automatic expiration (access: 30min, refresh: 7 days)

### Frontend Integration

Frontend applications should:

1. Use `credentials: 'include'` for all API requests
2. Handle OAuth2 callbacks at `/auth/callback` or `/auth/success`
3. Redirect to authenticated area after successful callback
4. Implement proper logout that clears local state

See [Frontend Cookie Authentication Guide](../../frontend/docs/guides/cookie-authentication.md) for detailed implementation instructions.

---

## Rate Limiting

### Rate Limit Tiers

| Tier | Requests per Hour |
|------|-------------------|
| Free | 100 |
| Premium | 1,000 |
| Admin | 10,000 |
---

## Related Documentation

- [API Overview](overview.md)
- [Rate Limiting](overview.md#rate-limiting)
- [Error Handling](overview.md#http-status-codes)
- [Architecture Overview](../architecture/overview.md)
