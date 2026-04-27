# Ingestion API

Repository ingestion endpoints for the hybrid edge-cloud architecture.

## Overview

The Ingestion API provides endpoints for submitting code repositories for processing by the edge worker. Repositories are queued for asynchronous processing, where they are cloned, parsed, and analyzed to generate structural embeddings.

**Base URL**: `/api/v1/ingestion`

**Authentication**: Bearer token required (`PHAROS_ADMIN_TOKEN` env var)

**Architecture**: Hybrid edge-cloud with Cloud API (Render) and Edge Worker (local GPU)

> **⚠️ Current Status (2026-04-24)**: Submitting a repo via this endpoint pushes a task to `ingest_queue` in Upstash Redis, but **no worker is consistently consuming that queue end-to-end**. The `backend/app/workers/repo.py` file exists, but the full path (clone → AST parse → create Resource rows → fan out to `pharos:tasks` for embedding) is not wired. Tasks pushed to `ingest_queue` will sit until manually re-processed.
>
> **Working path for single resources**: `POST /api/resources` → queues to `pharos:tasks` → edge worker calls `process_ingestion()`. This is the production-verified pipeline.
>
> **To process an existing repo's pending resources**: Run `python backend/scripts/queue_pending_resources.py` locally — it re-pushes every resource with `ingestion_status='pending'` to `pharos:tasks` for the embed server to process.

## Endpoints

### Submit Repository for Ingestion

Queue a code repository for processing by the edge worker.

**Endpoint**: `POST /api/v1/ingestion/ingest/{repo_url}`

**Authentication**: Required (Bearer token — `PHAROS_ADMIN_TOKEN`)

**Parameters**:
- `repo_url` (path, required): Full repository URL (e.g., `github.com/user/repo`)

**Headers**:
```
Authorization: Bearer <PHAROS_ADMIN_TOKEN>
```

**Request Example**:
```bash
curl -X POST https://pharos-cloud-api.onrender.com/api/v1/ingestion/ingest/github.com/user/awesome-project \
  -H "Authorization: Bearer $PHAROS_ADMIN_TOKEN"
```

**Response** (200 OK):
```json
{
  "status": "dispatched",
  "job_id": 1,
  "queue_position": 1,
  "target": "RTX-4070-Node",
  "queue_size": 1,
  "max_queue_size": 10
}
```

**Response Fields**:
- `status`: Always "dispatched" on success
- `job_id`: Unique identifier for this job
- `queue_position`: Position in queue (1 = next to process)
- `target`: Edge worker identifier
- `queue_size`: Current number of pending tasks
- `max_queue_size`: Maximum queue capacity (10)

**Error Responses**:

**400 Bad Request** - Invalid repository URL:
```json
{
  "detail": "Invalid repository URL"
}
```

**401 Unauthorized** - Missing or invalid token:
```json
{
  "detail": "Invalid or missing authentication token"
}
```

**429 Too Many Requests** - Queue is full:
```json
{
  "detail": "Queue is full (10 pending tasks). Please try again later."
}
```

**503 Service Unavailable** - Redis unavailable:
```json
{
  "detail": "Queue unavailable: Connection timeout"
}
```

---

### Get Worker Status

Get the current status of the edge worker.

**Endpoint**: `GET /api/v1/ingestion/worker/status`

**Authentication**: Not required

**Request Example**:
```bash
curl https://your-app.onrender.com/api/v1/ingestion/worker/status
```

**Response** (200 OK):
```json
{
  "status": "Training Graph on github.com/user/repo"
}
```

**Possible Status Values**:
- `"Idle"` - Worker is waiting for tasks
- `"Training Graph on {repo_url}"` - Worker is processing a repository
- `"Error: {error_message}"` - Worker encountered an error
- `"Offline"` - Worker is not running

**Use Case**: Poll this endpoint every 2-5 seconds to show real-time worker status in UI.

**Error Responses**:

**503 Service Unavailable** - Redis unavailable:
```json
{
  "detail": "Redis unavailable: Connection timeout"
}
```

---

### Get Job History

Get recent job history with metrics.

**Endpoint**: `GET /api/v1/ingestion/jobs/history`

**Authentication**: Not required

**Query Parameters**:
- `limit` (optional): Number of jobs to return (default: 10, max: 100)

**Request Example**:
```bash
curl https://your-app.onrender.com/api/v1/ingestion/jobs/history?limit=10
```

**Response** (200 OK):
```json
{
  "jobs": [
    {
      "repo_url": "github.com/user/repo1",
      "status": "complete",
      "duration_seconds": 127.5,
      "files_processed": 342,
      "embeddings_generated": 342,
      "timestamp": "2024-01-20T10:30:00Z"
    },
    {
      "repo_url": "github.com/user/repo2",
      "status": "failed",
      "error": "Failed to clone repository",
      "timestamp": "2024-01-20T10:25:00Z"
    },
    {
      "repo_url": "github.com/user/repo3",
      "status": "skipped",
      "reason": "Task exceeded TTL",
      "age_seconds": 90000,
      "timestamp": "2024-01-20T10:20:00Z"
    }
  ]
}
```

**Job Status Types**:

**Complete**:
- `repo_url`: Repository URL
- `status`: "complete"
- `duration_seconds`: Processing time
- `files_processed`: Number of files parsed
- `embeddings_generated`: Number of embeddings created
- `timestamp`: Completion time (ISO 8601)

**Failed**:
- `repo_url`: Repository URL
- `status`: "failed"
- `error`: Error message
- `timestamp`: Failure time (ISO 8601)

**Skipped**:
- `repo_url`: Repository URL
- `status`: "skipped"
- `reason`: Why task was skipped
- `age_seconds`: Task age when skipped
- `timestamp`: Skip time (ISO 8601)

---

## Authentication

### Bearer Token

All ingestion endpoints require Bearer token authentication using the `PHAROS_ADMIN_TOKEN` environment variable.

**Header Format**:
```
Authorization: Bearer <PHAROS_ADMIN_TOKEN>
```

**Why Authentication?**

Without authentication, anyone could submit repository URLs to your edge worker, potentially:
- Overwhelming your system with requests
- Triggering GitHub API rate limits
- Processing malicious repositories
- Consuming your GPU resources

**Setup**:

1. Generate a secure token:
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

2. Set in Cloud API environment:
```bash
PHAROS_ADMIN_TOKEN=your-secure-token-here
```

3. Use in requests:
```bash
curl -X POST https://your-app.onrender.com/api/v1/ingestion/ingest/github.com/user/repo \
  -H "Authorization: Bearer your-secure-token-here"
```

**Security Best Practices**:
- Use a strong, random token (32+ characters)
- Never commit tokens to Git
- Rotate tokens periodically
- Monitor authentication failures in logs

---

## Queue Management

### Queue Cap

The system enforces a maximum of **10 pending tasks** in the queue to prevent the "zombie queue" problem.

**Why a Queue Cap?**

Without a cap, the queue could fill with hundreds of stale tasks when the edge worker is offline, leading to:
- System overload when worker restarts
- GitHub API rate limit issues
- Processing outdated repositories
- Poor user experience

**Behavior**:
- Queue size checked before accepting new tasks
- Returns 429 (Too Many Requests) when queue is full
- Includes `queue_size` and `max_queue_size` in response
- Users should retry after some tasks complete

### Task TTL

All tasks have a **24-hour TTL (Time To Live)** to prevent processing stale repositories.

**Why TTL?**

Tasks can become stale if:
- Edge worker is offline for extended periods
- Queue fills up and tasks wait too long
- Repository has been updated since submission

**Behavior**:
- TTL set when task is queued
- Worker checks task age before processing
- Tasks older than TTL are skipped
- Skipped tasks recorded in job history with reason

**Task Metadata**:
```json
{
  "repo_url": "github.com/user/repo",
  "submitted_at": "2024-01-20T10:00:00Z",
  "ttl": 86400
}
```

---

## Workflow Example

### Complete Ingestion Workflow

```bash
# 1. Submit repository
curl -X POST https://your-app.onrender.com/api/v1/ingestion/ingest/github.com/user/repo \
  -H "Authorization: Bearer your-token"

# Response:
# {
#   "status": "dispatched",
#   "job_id": 1,
#   "queue_position": 1
# }

# 2. Poll worker status (every 2 seconds)
while true; do
  curl https://your-app.onrender.com/api/v1/ingestion/worker/status
  sleep 2
done

# Status progression:
# {"status": "Idle"}
# {"status": "Training Graph on github.com/user/repo"}
# {"status": "Idle"}

# 3. Check job history
curl https://your-app.onrender.com/api/v1/ingestion/jobs/history?limit=1

# Response:
# {
#   "jobs": [{
#     "repo_url": "github.com/user/repo",
#     "status": "complete",
#     "duration_seconds": 127.5,
#     "files_processed": 342,
#     "embeddings_generated": 342
#   }]
# }
```

### UI Integration Example

```javascript
// Submit repository
async function submitRepository(repoUrl, token) {
  const response = await fetch(
    `/api/v1/ingestion/ingest/${repoUrl}`,
    {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`
      }
    }
  );
  
  if (response.status === 429) {
    alert('Queue is full. Please try again later.');
    return;
  }
  
  const data = await response.json();
  console.log(`Job queued: ${data.job_id}`);
  
  // Start polling worker status
  pollWorkerStatus();
}

// Poll worker status
function pollWorkerStatus() {
  const interval = setInterval(async () => {
    const response = await fetch('/api/v1/ingestion/worker/status');
    const data = await response.json();
    
    // Update UI
    document.getElementById('worker-status').textContent = data.status;
    
    // Show spinner if training
    if (data.status.startsWith('Training')) {
      document.getElementById('spinner').style.display = 'block';
    } else {
      document.getElementById('spinner').style.display = 'none';
    }
    
    // Stop polling if error or offline
    if (data.status.startsWith('Error') || data.status === 'Offline') {
      clearInterval(interval);
      alert(`Worker status: ${data.status}`);
    }
  }, 2000); // Poll every 2 seconds
}
```

---

## Error Handling

### Client-Side Error Handling

```javascript
async function submitRepository(repoUrl, token) {
  try {
    const response = await fetch(
      `/api/v1/ingestion/ingest/${repoUrl}`,
      {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`
        }
      }
    );
    
    if (response.status === 400) {
      throw new Error('Invalid repository URL');
    }
    
    if (response.status === 401) {
      throw new Error('Invalid authentication token');
    }
    
    if (response.status === 429) {
      const data = await response.json();
      throw new Error(data.detail);
    }
    
    if (response.status === 503) {
      throw new Error('Service temporarily unavailable');
    }
    
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    
    return await response.json();
    
  } catch (error) {
    console.error('Ingestion error:', error);
    alert(`Failed to submit repository: ${error.message}`);
  }
}
```

### Retry Logic

```javascript
async function submitWithRetry(repoUrl, token, maxRetries = 3) {
  for (let attempt = 1; attempt <= maxRetries; attempt++) {
    try {
      return await submitRepository(repoUrl, token);
    } catch (error) {
      if (attempt === maxRetries) {
        throw error;
      }
      
      // Exponential backoff
      const delay = Math.pow(2, attempt) * 1000;
      console.log(`Retry ${attempt}/${maxRetries} after ${delay}ms`);
      await new Promise(resolve => setTimeout(resolve, delay));
    }
  }
}
```

---

## Performance Characteristics

### Cloud API

| Metric | Target | Typical |
|--------|--------|---------|
| Queue Dispatch | <100ms | ~30ms |
| Status Query | <50ms | ~20ms |
| History Query | <100ms | ~40ms |

### Edge Worker

| Metric | Target | Typical |
|--------|--------|---------|
| Processing Time (100 files) | <5min | 2-3min |
| GPU Utilization | >70% | 80-90% |
| Throughput | >10 repos/hour | ~15 repos/hour |

---

## Rate Limits

### Queue Limits

- **Maximum Queue Size**: 10 pending tasks
- **Task TTL**: 24 hours
- **Polling Interval**: 2 seconds (recommended)

### API Limits

- **Cloud API**: Render Free Tier limits apply
- **Redis**: 10,000 commands/day (Upstash Free Tier). BLPOP timeout=9s keeps idle polling ≈8.6k req/day — do not reduce this timeout.

---

## Related Documentation

- [Phase 19 Architecture](../architecture/phase19-hybrid.md) - Hybrid architecture overview
- [Cloud Deployment Guide](../guides/phase19-deployment.md) - Deploy Cloud API
- [Edge Worker Setup](../guides/phase19-edge-setup.md) - Set up edge worker
- [Monitoring Guide](../guides/phase19-monitoring.md) - Monitor system health
