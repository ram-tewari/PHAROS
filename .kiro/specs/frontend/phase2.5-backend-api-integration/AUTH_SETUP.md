# Phase 2.5 Authentication Setup

## Quick Start - Admin Token for Testing

Before implementing Phase 2.5, you need a valid authentication token to test against the production backend at `https://pharos.onrender.com`.

### Option 1: Use Pre-Generated Admin Token (Recommended for Testing)

A 30-day admin token has been generated for you:

```
<REDACTED-JWT>
```

**To use this token:**

1. Start your frontend dev server:
   ```bash
   cd frontend
   npm run dev
   ```

2. Open browser to `http://localhost:5173`

3. Open Developer Tools (F12) → Console

4. Paste this command:
   ```javascript
   localStorage.setItem('access_token', '<REDACTED-JWT>');
   localStorage.setItem('refresh_token', 'admin-refresh-token');
   ```

5. Refresh the page (F5)

6. You're now authenticated as an admin user!

### Option 2: Generate a New Token

If the token expires or you need a fresh one:

```bash
python backend/scripts/create_admin_token.py
```

This will generate a new 30-day admin token and display instructions.

### Option 3: Use OAuth2 (Production Flow)

For production, users will authenticate via Google or GitHub OAuth2:

1. Navigate to `/login` in your app
2. Click "Sign in with Google" or "Sign in with GitHub"
3. Complete OAuth flow
4. Token is automatically stored in localStorage

**Note**: OAuth2 is already configured on the backend at `https://pharos.onrender.com`

## Token Details

**Admin Token Properties**:
- Email: `admin@neoalexandria.dev`
- Tier: `admin` (unlimited rate limits)
- Premium: `true`
- Valid for: 30 days
- Permissions: Full access to all endpoints

## Verification

After setting the token, verify it's working:

1. Open Developer Tools → Application → Local Storage
2. You should see `access_token` with the JWT value
3. Try making an API call (e.g., GET `/api/auth/me`)
4. You should receive a 200 response with user info

## Backend Configuration

The frontend is already configured to use the production backend:

```env
# frontend/.env
VITE_API_BASE_URL=https://pharos.onrender.com
```

No changes needed!

## Troubleshooting

### Token Expired
If you get 401 errors, the token may have expired. Generate a new one:
```bash
python backend/scripts/create_admin_token.py
```

### CORS Errors
The backend is configured to allow requests from `http://localhost:5173`. If you're using a different port, update the backend CORS settings.

### Network Errors
Verify the backend is running:
```bash
curl https://pharos.onrender.com/api/monitoring/health
```

Should return:
```json
{
  "status": "healthy",
  "timestamp": "2024-01-23T..."
}
```

## Next Steps

Once authentication is working:

1. Start implementing Task 1: Configure API Client Foundation
2. Use the admin token for all API requests during development
3. Implement proper OAuth2 flow in Phase 11 (Social Authentication)

---

**Ready to start Phase 2.5 implementation!** 🚀
