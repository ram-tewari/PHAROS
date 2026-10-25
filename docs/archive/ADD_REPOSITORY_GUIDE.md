# How to Add a Repository to Neo Alexandria

## Quick Start

You're logged in as `ram.tewari.2023@gmail.com`. Here's how to add a repository.

## Option 1: Using curl (Recommended for Testing)

### Add a GitHub Repository

```bash
curl -X POST https://pharos.onrender.com/api/resources/ingest-repo \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -d '{
    "git_url": "https://github.com/username/repo-name"
  }'
```

### Add a Local Repository (if backend has access)

```bash
curl -X POST https://pharos.onrender.com/api/resources/ingest-repo \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -d '{
    "path": "/path/to/local/repo"
  }'
```

## Option 2: Using Python Script

Create a file `add_repo.py`:

```python
import requests

# Your JWT token from login
TOKEN = "your_jwt_token_here"

# Repository to add
REPO_URL = "https://github.com/torvalds/linux"  # Example: Linux kernel

# API endpoint
API_URL = "https://pharos.onrender.com/api/resources/ingest-repo"

# Make request
response = requests.post(
    API_URL,
    headers={
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json"
    },
    json={
        "git_url": REPO_URL
    }
)

print(f"Status: {response.status_code}")
print(f"Response: {response.json()}")

# Track progress
if response.status_code == 200:
    task_id = response.json()["task_id"]
    print(f"\nTask ID: {task_id}")
    print(f"Check status at: {API_URL}/status/{task_id}")
```

Run it:
```bash
python add_repo.py
```

## Option 3: Using PowerShell

```powershell
$token = "your_jwt_token_here"
$repoUrl = "https://github.com/username/repo-name"

$headers = @{
    "Authorization" = "Bearer $token"
    "Content-Type" = "application/json"
}

$body = @{
    git_url = $repoUrl
} | ConvertTo-Json

$response = Invoke-RestMethod `
    -Uri "https://pharos.onrender.com/api/resources/ingest-repo" `
    -Method Post `
    -Headers $headers `
    -Body $body

Write-Host "Task ID: $($response.task_id)"
Write-Host "Status: $($response.status)"
Write-Host "Message: $($response.message)"
```

## Getting Your JWT Token

### Method 1: From Browser DevTools

1. Open browser DevTools (F12)
2. Go to Application/Storage → Local Storage
3. Look for `access_token` or similar
4. Copy the token value

### Method 2: Login via API

```bash
curl -X POST https://pharos.onrender.com/api/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=ram.tewari.2023@gmail.com&password=your_password"
```

Response will include `access_token`.

### Method 3: Use OAuth Token

If you logged in via Google OAuth, the token should be in your browser's local storage or session storage.

## Example Repositories to Try

### Small Repositories (Quick Testing)
```json
{
  "git_url": "https://github.com/octocat/Hello-World"
}
```

### Medium Repositories
```json
{
  "git_url": "https://github.com/fastapi/fastapi"
}
```

### Your Own Repository
```json
{
  "git_url": "https://github.com/YOUR_USERNAME/YOUR_REPO"
}
```

## What Happens After Adding?

1. **Task Created**: You get a `task_id` back immediately
2. **Background Processing**: The system:
   - Clones the repository (if Git URL)
   - Scans all files
   - Creates Resource entries
   - Classifies files (PRACTICE/THEORY/GOVERNANCE)
   - Extracts metadata
   - Generates embeddings
3. **Progress Tracking**: Check status with task_id

## Check Ingestion Status

```bash
curl -X GET https://pharos.onrender.com/api/resources/ingest-status/{task_id} \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

## Troubleshooting

### Error: 401 Unauthorized
**Solution**: Your JWT token is missing or expired. Login again to get a new token.

### Error: 400 Bad Request
**Solution**: Check that:
- Git URL is valid and uses HTTPS
- Repository is public (or you have access)
- You provided either `git_url` OR `path`, not both

### Error: 429 Rate Limit Exceeded
**Solution**: You've hit your rate limit. Wait a minute or upgrade your tier.

### Repository Not Showing Up
**Solution**: 
- Check task status using the task_id
- Look at backend logs for errors
- Ensure repository is public or accessible

## Frontend Integration (Coming Soon)

The frontend UI you're seeing is part of Phase 1 (Workbench Navigation). The repository ingestion UI will be added in a future phase. For now, use the API directly.

## Complete Example

Here's a complete workflow:

```bash
# 1. Login (if needed)
TOKEN=$(curl -X POST https://pharos.onrender.com/api/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=ram.tewari.2023@gmail.com&password=your_password" \
  | jq -r '.access_token')

# 2. Add repository
TASK_ID=$(curl -X POST https://pharos.onrender.com/api/resources/ingest-repo \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"git_url": "https://github.com/octocat/Hello-World"}' \
  | jq -r '.task_id')

echo "Task ID: $TASK_ID"

# 3. Check status (wait a few seconds first)
sleep 5
curl -X GET "https://pharos.onrender.com/api/resources/ingest-status/$TASK_ID" \
  -H "Authorization: Bearer $TOKEN"

# 4. List resources
curl -X GET "https://pharos.onrender.com/api/resources?limit=10" \
  -H "Authorization: Bearer $TOKEN"
```

## API Reference

See `backend/docs/api/ingestion.md` for complete API documentation.

## Need Help?

- Check backend logs in Render dashboard
- Verify your JWT token is valid
- Ensure repository URL is accessible
- Try a small public repository first
