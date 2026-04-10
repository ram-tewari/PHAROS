# Cookie-Based Authentication Guide

## Overview

This guide explains how Pharos frontend handles authentication using HTTP-only cookies for OAuth2 callbacks. This is a security enhancement that prevents token exposure in browser history, referer headers, and server logs.

> **Phase 21.5 Update**: OAuth2 callbacks now transmit tokens via HTTP-only cookies instead of URL parameters.

## How OAuth2 Callbacks Work

### Traditional URL Parameter Approach (Old)

Previously, OAuth2 callbacks returned tokens in the URL:

```
http://localhost:3000/auth/callback?access_token=eyJ...&refresh_token=eyJ...
```

**Security Issues:**
- Tokens visible in browser history
- Tokens leaked in Referer header
- Tokens logged in server access logs
- Tokens captured by browser autocomplete

### Cookie-Based Approach (New)

OAuth2 callbacks now set HTTP-only cookies:

```
http://localhost:3000/auth/callback
```

The browser receives tokens in `Set-Cookie` headers:

```
Set-Cookie: access_token=eyJ...; HttpOnly; Secure; SameSite=Lax; Max-Age=1800
Set-Cookie: refresh_token=eyJ...; HttpOnly; Secure; SameSite=Lax; Max-Age=604800
```

**Security Benefits:**
- Tokens never exposed to JavaScript (HttpOnly)
- Tokens only transmitted over HTTPS (Secure)
- Tokens not sent on cross-site requests (SameSite)
- Tokens automatically managed by the browser

## Cookie Security Attributes

### HttpOnly

```http
Set-Cookie: access_token=eyJ...; HttpOnly
```

- Prevents JavaScript access to the cookie
- Protects against XSS attacks
- Tokens cannot be stolen via `document.cookie`

### Secure

```http
Set-Cookie: access_token=eyJ...; Secure
```

- Cookie only transmitted over HTTPS connections
- Prevents token interception in transit
- Required in production environments

### SameSite=Lax

```http
Set-Cookie: access_token=eyJ...; SameSite=Lax
```

- Cookie sent on top-level navigations and GET requests to the same site
- Prevents CSRF attacks from malicious sites
- Allows normal navigation while blocking unauthorized requests

### Max-Age / Expires

```http
Set-Cookie: access_token=eyJ...; Max-Age=1800
Set-Cookie: refresh_token=eyJ...; Max-Age=604800
```

- Access token: 30 minutes (1800 seconds)
- Refresh token: 7 days (604800 seconds)
- Tokens automatically deleted when expired

## Frontend Implementation

### Reading Tokens from Cookies

Since tokens are in HttpOnly cookies, the frontend cannot access them directly via JavaScript. Instead, the browser automatically includes cookies in API requests.

**The frontend does NOT need to read tokens from cookies!**

```typescript
// ❌ This will NOT work - tokens are HttpOnly
const token = document.cookie.split('; ')
  .find(row => row.startsWith('access_token='));

// ✅ Browser automatically includes cookies in API requests
const response = await fetch('/api/v1/resources', {
  method: 'GET',
  // No Authorization header needed - cookies are automatic
});
```

### API Client Configuration

Ensure your API client is configured to use credentials:

```typescript
// api/client.ts
const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL,
  withCredentials: true, // Important: Include cookies in requests
  timeout: 30000,
});

// Request interceptor - not needed for cookie auth
apiClient.interceptors.request.use((config) => {
  // No token manipulation needed
  // Browser handles cookies automatically
  return config;
});

// Response interceptor - handle auth errors
apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (error.response?.status === 401) {
      // Token expired or invalid - trigger re-authentication
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);
```

### OAuth2 Callback Handling

The callback route should verify cookie presence and redirect to the authenticated area:

```typescript
// routes/auth.callback.tsx
import { createFileRoute } from '@tanstack/react-router';

export const Route = createFileRoute('/auth/callback')({
  component: AuthCallback,
});

function AuthCallback() {
  useEffect(() => {
    // Check if cookies were set (user is authenticated)
    // We can't read the cookie value, but we can check if it exists
    const hasAccessToken = document.cookie.includes('access_token=');
    
    if (hasAccessToken) {
      // Cookies set successfully - redirect to app
      window.location.href = '/repositories';
    } else {
      // No cookies - authentication failed
      window.location.href = '/login?error=auth_failed';
    }
  }, []);

  return (
    <div className="flex items-center justify-center min-h-screen">
      <div className="text-center">
        <h1 className="text-2xl font-semibold">Completing sign in...</h1>
        <p className="text-muted-foreground mt-2">
          Please wait while we verify your authentication.
        </p>
      </div>
    </div>
  );
}
```

### Auth Success Page

Create a dedicated success page that confirms authentication:

```typescript
// routes/auth.success.tsx
import { createFileRoute } from '@tanstack/react-router';

export const Route = createFileRoute('/auth/success')({
  component: AuthSuccess,
});

function AuthSuccess() {
  useEffect(() => {
    // Redirect to main app after a brief delay
    const timer = setTimeout(() => {
      window.location.href = '/repositories';
    }, 1500);

    return () => clearTimeout(timer);
  }, []);

  return (
    <div className="flex items-center justify-center min-h-screen">
      <div className="text-center">
        <div className="inline-flex items-center justify-center w-12 h-12 rounded-full bg-green-100 mb-4">
          <svg className="w-6 h-6 text-green-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
          </svg>
        </div>
        <h1 className="text-2xl font-semibold">Sign in successful!</h1>
        <p className="text-muted-foreground mt-2">
          Redirecting you to your repositories...
        </p>
      </div>
    </div>
  );
}
```

## Token Refresh

When the access token expires, the refresh token (also in an HttpOnly cookie) is automatically sent with refresh requests:

```typescript
// lib/auth/refresh.ts
async function refreshAccessToken(): Promise<boolean> {
  try {
    const response = await fetch('/api/v1/auth/refresh', {
      method: 'POST',
      credentials: 'include', // Important: Include cookies
    });

    if (response.ok) {
      // New tokens set in HttpOnly cookies
      return true;
    } else {
      // Refresh failed - need to re-authenticate
      return false;
    }
  } catch (error) {
    console.error('Token refresh failed:', error);
    return false;
  }
}
```

## Logout

When logging out, the backend clears the cookies. The frontend should also clear any local state:

```typescript
// lib/auth/logout.ts
async function logout(): Promise<void> {
  try {
    await fetch('/api/v1/auth/logout', {
      method: 'POST',
      credentials: 'include', // Include cookies for removal
    });
  } catch (error) {
    console.error('Logout request failed:', error);
  } finally {
    // Clear local state
    authStore.getState().clearAuth();
    window.location.href = '/login';
  }
}
```

## Environment Configuration

### Development (.env)

```bash
# API Configuration
VITE_API_BASE_URL=http://localhost:8000

# OAuth2 Redirect URIs (must match backend ALLOWED_REDIRECT_URLS)
VITE_FRONTEND_URL=http://localhost:3000
VITE_FRONTEND_DEV_URL=http://localhost:5173
```

### Production (.env)

```bash
# API Configuration
VITE_API_BASE_URL=https://api.yourdomain.com

# OAuth2 Redirect URIs
VITE_FRONTEND_URL=https://yourdomain.com
```

## Troubleshooting

### Cookies Not Being Set

1. **Check CORS configuration**: Backend must allow credentials
   ```python
   # backend/app/__init__.py
   from fastapi.middleware.cors import CORSMiddleware
   
   app.add_middleware(
     CORSMiddleware,
     allow_origins=["http://localhost:3000"],
     allow_credentials=True,  # Required for cookies
     allow_methods=["*"],
     allow_headers=["*"],
   )
   ```

2. **Verify SameSite attribute**: Cookies with `SameSite=None` require `Secure`

3. **Check domain matching**: Cookie domain must match the request domain

### 401 Unauthorized Errors

1. **Verify credentials mode**: API requests must use `credentials: 'include'`

2. **Check cookie expiration**: Tokens may have expired

3. **Clear old cookies**: Browser may have stale cookies from previous sessions

### Mixed Content Errors (Production)

Ensure all resources are loaded over HTTPS:

```bash
# Verify API calls use HTTPS
curl -I https://api.yourdomain.com/api/v1/auth/me \
  -H "Cookie: access_token=eyJ..."
```

## Security Best Practices

### Do

- ✅ Use `credentials: 'include'` for all API requests
- ✅ Implement proper error handling for 401 responses
- ✅ Redirect to login on authentication failures
- ✅ Clear local state on logout
- ✅ Use HTTPS in production

### Don't

- ❌ Try to read HttpOnly cookies in JavaScript
- ❌ Store tokens in localStorage or sessionStorage
- ❌ Include tokens in URL parameters
- ❌ Make cross-origin requests without proper CORS configuration
- ❌ Disable `withCredentials` for same-origin requests

## Related Documentation

- [Backend Auth API](../backend/docs/api/auth.md)
- [API Overview](../backend/docs/api/overview.md)
- [Setup Guide](setup.md)
- [Auth Shutdown History](../history/auth-shutdown.md)

---

**Last Updated**: February 2026
**Phase**: Phase 21.5 - Backend Stabilization