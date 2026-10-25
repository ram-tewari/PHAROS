# Neo Alexandria Authentication Quick Start

## Overview

Neo Alexandria uses JWT (JSON Web Token) authentication. All API endpoints require authentication except `/auth/*`, `/docs`, and `/openapi.json`.

## Step 1: Create a Test User

First, you need a user account. Connect to the database and create one:

### Option A: Using Docker (if backend container is running)

```bash
docker exec -it neo-alexandria-backend python -c "
from app.shared.database import get_sync_db
from app.modules.auth.model import User
from app.shared.security import get_password_hash

db = next(get_sync_db())
user = User(
    email='admin@test.com',
    username='admin',
    hashed_password=get_password_hash('admin123'),
    tier='admin',
    is_active=True
)
db.add(user)
db.commit()
print('User created successfully!')
"
```

### Option B: Using Python Script

```python
from app.shared.database import get_sync_db
from app.modules.auth.model import User
from app.shared.security import get_password_hash

db = next(get_sync_db())
user = User(
    email='admin@test.com',
    username='admin',
    hashed_password=get_password_hash('admin123'),
    tier='admin',  # Options: 'free', 'premium', 'admin'
    is_active=True
)
db.add(user)
db.commit()
print('User created!')
```

## Step 2: Login to Get Access Token

### Using curl (Windows PowerShell)

```powershell
curl -X POST http://localhost:8000/auth/login `
  -H "Content-Type: application/x-www-form-urlencoded" `
  -d "username=admin@test.com&password=admin123"
```

### Using curl (Linux/Mac)

```bash
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin@test.com&password=admin123"
```

### Response

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 1800
}
```

## Step 3: Use Token in API Requests

### Save the token

```powershell
# PowerShell
$TOKEN = "your_access_token_here"
```

```bash
# Bash
TOKEN="your_access_token_here"
```

### Make authenticated requests

```powershell
# PowerShell - List resources
curl http://localhost:8000/resources `
  -H "Authorization: Bearer $TOKEN"

# PowerShell - Create resource
curl -X POST http://localhost:8000/resources `
  -H "Authorization: Bearer $TOKEN" `
  -H "Content-Type: application/json" `
  -d '{"url":"https://example.com","title":"Test Resource"}'
```

```bash
# Bash - List resources
curl http://localhost:8000/resources \
  -H "Authorization: Bearer $TOKEN"

# Bash - Create resource
curl -X POST http://localhost:8000/resources \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://example.com","title":"Test Resource"}'
```

## Step 4: Refresh Token (Optional)

When your access token expires (default: 30 minutes), use the refresh token:

```bash
curl -X POST http://localhost:8000/auth/refresh \
  -H "Authorization: Bearer <refresh_token>"
```

## Python Example

```python
import requests

# 1. Login
response = requests.post(
    "http://localhost:8000/auth/login",
    data={
        "username": "admin@test.com",
        "password": "admin123"
    }
)
tokens = response.json()
access_token = tokens["access_token"]

# 2. Use token for requests
headers = {"Authorization": f"Bearer {access_token}"}

# List resources
resources = requests.get(
    "http://localhost:8000/resources",
    headers=headers
)
print(resources.json())

# Create resource
new_resource = requests.post(
    "http://localhost:8000/resources",
    headers=headers,
    json={
        "url": "https://example.com",
        "title": "Test Resource"
    }
)
print(new_resource.json())
```

## User Tiers and Rate Limits

- **Free Tier**: 100 requests per hour
- **Premium Tier**: 1000 requests per hour  
- **Admin Tier**: Unlimited requests

## OAuth2 (Optional)

You can also authenticate using Google or GitHub:

### Google OAuth
```bash
# 1. Get authorization URL
curl http://localhost:8000/auth/google

# 2. Visit the URL in browser and authorize
# 3. You'll be redirected with a code
# 4. Exchange code for tokens (handled automatically)
```

### GitHub OAuth
```bash
# 1. Get authorization URL
curl http://localhost:8000/auth/github

# 2. Visit the URL in browser and authorize
# 3. You'll be redirected with a code
# 4. Exchange code for tokens (handled automatically)
```

## Troubleshooting

### "Not authenticated" error
- Make sure you're including the `Authorization: Bearer <token>` header
- Check that your token hasn't expired (30 minutes default)
- Verify the token format is correct

### "Could not validate credentials"
- Your token may be expired - use refresh token to get a new one
- Token may be invalid - login again

### "User not found"
- Create a user account first (see Step 1)
- Check database connection

### Auth endpoints not found
- Verify auth module is registered in `app/__init__.py`
- Check that backend container is running
- Try accessing `/docs` to see all available endpoints

## Testing Script

Run the included test script:

```bash
python test_auth.py
```

This will test:
1. Unauthenticated requests (should fail)
2. Login flow
3. Authenticated requests (should succeed)
