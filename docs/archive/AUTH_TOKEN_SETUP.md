# Authentication Token Setup

## Problem
The backend requires authentication for all endpoints (except `/auth/*`, `/docs`, and health checks). The frontend needs a valid JWT token to make API requests.

## Solution
A test user has been created with a 7-day access token.

## Setup Instructions

### Option 1: Browser Console (Quick)
1. Open your browser to `http://localhost:5173`
2. Open Developer Tools (F12)
3. Go to the Console tab
4. Paste this command and press Enter:

```javascript
localStorage.setItem('access_token', '<REDACTED-JWT>');
localStorage.setItem('refresh_token', 'dummy-refresh-token');
```

4. Refresh the page (F5)
5. Try creating a resource again

### Option 2: Login via UI
1. Navigate to the login page in your app
2. Use these credentials:
   - Email: `test@example.com`
   - Password: `testpassword123`

## Test User Details
- **Email**: test@example.com
- **Username**: testuser
- **Password**: testpassword123
- **Tier**: premium
- **Token Valid Until**: 7 days from creation

## Verification
After setting the token, check:
1. Open Developer Tools → Application → Local Storage
2. You should see `access_token` with the JWT value
3. Try creating a resource - it should now work!

## Token Expiry
The token is valid for 7 days. After that, you'll need to:
- Run `python create_test_user.py` again to get a new token, OR
- Login via the UI with the credentials above
