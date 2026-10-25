# OAuth2 Setup Guide for Neo Alexandria

This guide walks you through setting up Google and GitHub OAuth2 authentication for local development.

## Prerequisites

- Backend server running on `http://localhost:8000`
- Frontend server running on `http://localhost:5173` or `http://localhost:5174`

## Option 1: Google OAuth2 Setup

### Step 1: Create Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Click "Select a project" → "New Project"
3. Enter project name: `Neo Alexandria` (or any name)
4. Click "Create"

### Step 2: Enable Google+ API

1. In the Google Cloud Console, go to "APIs & Services" → "Library"
2. Search for "Google+ API"
3. Click on it and click "Enable"

### Step 3: Create OAuth2 Credentials

1. Go to "APIs & Services" → "Credentials"
2. Click "Create Credentials" → "OAuth client ID"
3. If prompted, configure the OAuth consent screen:
   - User Type: **External** (for testing)
   - Click "Create"
   - Fill in required fields:
     - App name: `Neo Alexandria`
     - User support email: Your email
     - Developer contact: Your email
   - Click "Save and Continue"
   - Skip "Scopes" (click "Save and Continue")
   - Add test users (your email) under "Test users"
   - Click "Save and Continue"

4. Back to "Create OAuth client ID":
   - Application type: **Web application**
   - Name: `Neo Alexandria Local Dev`
   - Authorized JavaScript origins:
     - `http://localhost:8000`
     - `http://localhost:5173`
     - `http://localhost:5174`
   - Authorized redirect URIs:
     - `http://localhost:8000/auth/google/callback`
   - Click "Create"

5. Copy the **Client ID** and **Client Secret**

### Step 4: Update Backend .env File

Open `backend/.env` and update:

```env
GOOGLE_CLIENT_ID=your-actual-client-id-here
GOOGLE_CLIENT_SECRET=your-actual-client-secret-here
GOOGLE_REDIRECT_URI=http://localhost:8000/auth/google/callback
```

### Step 5: Restart Backend Server

Stop and restart the backend server to load the new credentials.

---

## Option 2: GitHub OAuth2 Setup

### Step 1: Create GitHub OAuth App

1. Go to [GitHub Developer Settings](https://github.com/settings/developers)
2. Click "OAuth Apps" → "New OAuth App"
3. Fill in the form:
   - **Application name:** `Neo Alexandria Local Dev`
   - **Homepage URL:** `http://localhost:5173` (or 5174)
   - **Application description:** (optional) `Knowledge management system`
   - **Authorization callback URL:** `http://localhost:8000/auth/github/callback`
4. Click "Register application"

### Step 2: Generate Client Secret

1. On the OAuth app page, click "Generate a new client secret"
2. Copy the **Client ID** (shown at top)
3. Copy the **Client Secret** (shown after generation - save it now, you won't see it again!)

### Step 3: Update Backend .env File

Open `backend/.env` and update:

```env
GITHUB_CLIENT_ID=your-actual-client-id-here
GITHUB_CLIENT_SECRET=your-actual-client-secret-here
GITHUB_REDIRECT_URI=http://localhost:8000/auth/github/callback
```

### Step 4: Restart Backend Server

Stop and restart the backend server to load the new credentials.

---

## Testing OAuth Flow

### Test Google Login

1. Open browser to `http://localhost:5174/login` (or 5173)
2. Click "Continue with Google"
3. You should be redirected to Google's login page
4. Sign in with your Google account
5. Grant permissions to the app
6. You should be redirected back to `http://localhost:5174/auth/callback`
7. Then automatically redirected to `http://localhost:5174/dashboard`
8. Verify your profile appears in the header

### Test GitHub Login

1. Open browser to `http://localhost:5174/login` (or 5173)
2. Click "Continue with GitHub"
3. You should be redirected to GitHub's authorization page
4. Click "Authorize" to grant permissions
5. You should be redirected back to `http://localhost:5174/auth/callback`
6. Then automatically redirected to `http://localhost:5174/dashboard`
7. Verify your profile appears in the header

---

## Troubleshooting

### "Google OAuth2 not configured" Error

**Cause:** Backend doesn't have valid Google OAuth credentials

**Solutions:**
1. Verify `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` are set in `backend/.env`
2. Ensure credentials are not placeholder values (`your-google-client-id`)
3. Restart backend server after updating `.env`
4. Check backend logs for OAuth initialization errors

### "GitHub OAuth2 not configured" Error

**Cause:** Backend doesn't have valid GitHub OAuth credentials

**Solutions:**
1. Verify `GITHUB_CLIENT_ID` and `GITHUB_CLIENT_SECRET` are set in `backend/.env`
2. Ensure credentials are not placeholder values (`your-github-client-id`)
3. Restart backend server after updating `.env`
4. Check backend logs for OAuth initialization errors

### "redirect_uri_mismatch" Error (Google)

**Cause:** The redirect URI in your request doesn't match what's configured in Google Cloud Console

**Solutions:**
1. Go to Google Cloud Console → Credentials
2. Edit your OAuth 2.0 Client ID
3. Ensure "Authorized redirect URIs" includes: `http://localhost:8000/auth/google/callback`
4. Save changes and try again

### "The redirect_uri MUST match the registered callback URL" Error (GitHub)

**Cause:** The redirect URI doesn't match what's configured in GitHub OAuth App

**Solutions:**
1. Go to GitHub → Settings → Developer settings → OAuth Apps
2. Edit your OAuth App
3. Ensure "Authorization callback URL" is: `http://localhost:8000/auth/github/callback`
4. Update application and try again

### OAuth Flow Redirects but No Login

**Cause:** Frontend callback handler may have issues

**Solutions:**
1. Open browser DevTools → Console
2. Look for JavaScript errors
3. Check Network tab for failed API calls
4. Verify tokens are being stored in localStorage
5. Check backend logs for `/auth/me` endpoint errors

### "Access blocked: This app's request is invalid" (Google)

**Cause:** OAuth consent screen not properly configured

**Solutions:**
1. Go to Google Cloud Console → "APIs & Services" → "OAuth consent screen"
2. Ensure app is in "Testing" mode
3. Add your email to "Test users"
4. Save and try again

### Backend Server Not Loading OAuth Config

**Cause:** Environment variables not loaded or backend not restarted

**Solutions:**
1. Stop backend server (Ctrl+C)
2. Verify `.env` file has correct values (no quotes around values)
3. Restart backend: `cd backend && uvicorn app.main:app --reload`
4. Check startup logs for OAuth initialization messages

---

## Security Notes

### Development vs Production

**Development (localhost):**
- Use `http://localhost:8000` for redirect URIs
- OAuth apps can be in "Testing" mode
- Test users must be explicitly added

**Production:**
- Use `https://your-domain.com` for redirect URIs
- OAuth apps must be verified/published
- Update `GOOGLE_REDIRECT_URI` and `GITHUB_REDIRECT_URI` in production `.env`

### Protecting Credentials

1. **Never commit credentials to Git:**
   - `.env` is in `.gitignore`
   - Use `.env.example` for templates only

2. **Use different credentials for production:**
   - Create separate OAuth apps for production
   - Use environment-specific redirect URIs

3. **Rotate secrets regularly:**
   - Generate new client secrets periodically
   - Update `.env` and restart services

---

## Quick Reference

### Google OAuth URLs
- Console: https://console.cloud.google.com/
- Credentials: https://console.cloud.google.com/apis/credentials
- Consent Screen: https://console.cloud.google.com/apis/credentials/consent

### GitHub OAuth URLs
- Settings: https://github.com/settings/developers
- OAuth Apps: https://github.com/settings/developers (OAuth Apps tab)

### Backend Endpoints
- Google Login: `http://localhost:8000/auth/google`
- Google Callback: `http://localhost:8000/auth/google/callback`
- GitHub Login: `http://localhost:8000/auth/github`
- GitHub Callback: `http://localhost:8000/auth/github/callback`
- User Profile: `http://localhost:8000/auth/me`
- Token Refresh: `http://localhost:8000/auth/refresh`

### Frontend Routes
- Login Page: `http://localhost:5174/login`
- OAuth Callback: `http://localhost:5174/auth/callback`
- Dashboard: `http://localhost:5174/dashboard`

---

## Next Steps

After setting up OAuth:

1. Test the complete OAuth flow (see "Testing OAuth Flow" above)
2. Verify token refresh works (use "Test Token Refresh" button on dashboard)
3. Test logout functionality
4. Proceed with manual testing checklist in Task 8

---

## Need Help?

If you encounter issues not covered here:

1. Check backend logs for detailed error messages
2. Check browser DevTools console for frontend errors
3. Verify all redirect URIs match exactly (including http/https)
4. Ensure backend server restarted after updating `.env`
5. Try clearing browser cache and localStorage

For OAuth provider-specific issues:
- Google: https://developers.google.com/identity/protocols/oauth2
- GitHub: https://docs.github.com/en/developers/apps/building-oauth-apps
