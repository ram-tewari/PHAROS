# Phase 19: Hybrid Edge-Cloud Architecture

## Overview

Phase 19 introduces a hybrid edge-cloud architecture that splits Pharos's backend into two complementary components to optimize cost and performance:

1. **Cloud API (Control Plane)** - Lightweight FastAPI service on Render Free Tier
2. **Edge Worker (Compute Plane)** - GPU-accelerated Python worker on local hardware

This architecture leverages serverless infrastructure (Neon Postgres, Qdrant Cloud, Upstash Redis) for $0/month cloud costs while maximizing compute power through local GPU utilization for graph neural network training.

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    PHASE 19: HYBRID EDGE-CLOUD ARCHITECTURE                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                      CLOUD LAYER (Render Free Tier)                  │   │
│  │                                                                      │   │
│  │  ┌────────────────────────────────────────────────────────────────┐  │   │
│  │  │              FastAPI Cloud API (MODE=CLOUD)                    │  │   │
│  │  │                                                                │  │   │
│  │  │  POST /api/v1/ingestion/ingest/{repo_url}                     │  │   │
│  │  │    • Bearer token authentication (PHAROS_ADMIN_TOKEN)         │  │   │
│  │  │    • URL validation                                           │  │   │
│  │  │    • Queue cap enforcement (max 10 pending)                   │  │   │
│  │  │    • Task TTL (24 hours)                                      │  │   │
│  │  │    • Push to Redis queue                                      │  │   │
│  │  │                                                                │  │   │
│  │  │  GET /api/v1/ingestion/worker/status                          │  │   │
│  │  │    • Real-time worker status from Redis                       │  │   │
│  │  │    • UI polling endpoint                                      │  │   │
│  │  │                                                                │  │   │
│  │  │  GET /api/v1/ingestion/jobs/history                           │  │   │
│  │  │    • Last N completed jobs                                    │  │   │
│  │  │    • Success/failure metrics                                  │  │   │
│  │  │                                                                │  │   │
│  │  │  GET /health                                                   │  │   │
│  │  │    • Redis, Neon, Qdrant health checks                        │  │   │
│  │  └────────────────────────────────────────────────────────────────┘  │   │
│  │                                                                      │   │
│  │  Resource Limits:                                                    │   │
│  │  • Memory: 512MB (no ML libraries loaded)                            │   │
│  │  • CPU: Shared                                                       │   │
│  │  • Cost: $0/month                                                    │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    │ HTTPS                                  │
│                                    ▼                                        │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                    SERVERLESS INFRASTRUCTURE                         │   │
│  │                                                                      │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐               │   │
│  │  │ Upstash Redis│  │ Neon Postgres│  │ Qdrant Cloud │               │   │
│  │  │              │  │              │  │              │               │   │
│  │  │ • Task Queue │  │ • Metadata   │  │ • Embeddings │               │   │
│  │  │ • Status     │  │ • Resources  │  │ • Vectors    │               │   │
│  │  │ • Job History│  │ • Users      │  │ • Search     │               │   │
│  │  │              │  │              │  │              │               │   │
│  │  │ Free: 10K    │  │ Free: 3GB    │  │ Free: 1GB    │               │   │
│  │  │ commands/day │  │ storage      │  │ cluster      │               │   │
│  │  └──────────────┘  └──────────────┘  └──────────────┘               │   │
│  │                                                                      │   │
│  │  Total Cloud Cost: $0/month                                          │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    │ HTTP REST API                          │
│                                    │ (Poll every 2s)                        │
│                                    ▼                                        │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                    EDGE LAYER (Local Laptop)                         │   │
│  │                                                                      │   │
│  │  ┌────────────────────────────────────────────────────────────────┐  │   │
│  │  │              Python Edge Worker (MODE=EDGE)                    │  │   │
│  │  │                                                                │  │   │
│  │  │  Main Loop:                                                    │  │   │
│  │  │  1. Poll Redis queue (LPOP ingest_queue)                      │  │   │
│  │  │  2. Check task TTL (skip if stale)                            │  │   │
│  │  │  3. Update status: "Training Graph on {repo}"                 │  │   │
│  │  │  4. Clone repository (GitPython)                              │  │   │
│  │  │  5. Parse imports (Tree-sitter)                               │  │   │
│  │  │  6. Build dependency graph                                    │  │   │
│  │  │  7. Train Node2Vec (PyTorch Geometric)                        │  │   │
│  │  │  8. Upload embeddings (Qdrant)                                │  │   │
│  │  │  9. Record job history                                        │  │   │
│  │  │  10. Update status: "Idle"                                    │  │   │
│  │  │                                                                │  │   │
│  │  │  Components:                                                   │  │   │
│  │  │  • RepositoryParser - Clone & parse repos                     │  │   │
│  │  │  • NeuralGraphService - Train embeddings                      │  │   │
│  │  │  • Error handling & retry logic                               │  │   │
│  │  └────────────────────────────────────────────────────────────────┘  │   │
│  │                                                                      │   │
│  │  Hardware:                                                           │   │
│  │  • CPU: Intel i9 (8+ cores)                                          │   │
│  │  • GPU: NVIDIA RTX 4070 (16GB VRAM)                                  │   │
│  │  • RAM: 16GB                                                         │   │
│  │  • Storage: 50GB                                                     │   │
│  │                                                                      │   │
│  │  Cost: ~$10-20/month (electricity)                                   │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Component Details

### Cloud API (Control Plane)

**Purpose**: Lightweight orchestration layer that dispatches tasks without heavy ML dependencies

**Key Features**:
- **Authentication**: Bearer token (PHAROS_ADMIN_TOKEN) prevents unauthorized access
- **Queue Management**: Cap at 10 pending tasks prevents zombie queue problem
- **Task TTL**: 24-hour expiration prevents stale task processing
- **Real-time Status**: Worker status endpoint for UI updates
- **Job History**: Last 100 jobs with metrics

**Dependencies** (requirements-cloud.txt):
```
-r requirements-base.txt
psycopg2-binary==2.9.9
qdrant-client==1.7.0
```

**Configuration**:
- `MODE=CLOUD` - Excludes PyTorch and ML libraries
- Memory usage: <400MB (well under 512MB limit)
- Startup time: <10 seconds

### Edge Worker (Compute Plane)

**Purpose**: GPU-accelerated worker for repository processing and graph neural network training

**Key Features**:
- **GPU Acceleration**: CUDA support for 10x faster training
- **Repository Parsing**: Tree-sitter for multi-language import extraction
- **Graph Neural Networks**: PyTorch Geometric Node2Vec for structural embeddings
- **Error Recovery**: Retry logic, graceful degradation, cleanup

**Dependencies** (requirements-edge.txt):
```
-r requirements-base.txt
torch==2.1.0
torch-geometric==2.4.0
tree-sitter==0.20.4
tree-sitter-python==0.20.4
tree-sitter-javascript==0.20.3
qdrant-client==1.7.0
numpy==1.24.3
psycopg2-binary==2.9.9
```

**Configuration**:
- `MODE=EDGE` - Loads PyTorch and verifies CUDA
- GPU utilization: 70-90% during training
- Processing time: <5 minutes for 100 files

### Serverless Infrastructure

**Upstash Redis**:
- Task queue (FIFO)
- Worker status tracking
- Job history (last 100 entries)
- Free tier: 10,000 commands/day

**Neon PostgreSQL**:
- Resource metadata
- User data
- Free tier: 3GB storage, scales to zero

**Qdrant Cloud**:
- Structural embeddings (64 dimensions)
- Vector similarity search
- Free tier: 1GB cluster (~1M vectors)

## Data Flow

### Repository Ingestion Flow

```
1. User submits repository URL
   POST /api/v1/ingestion/ingest/github.com/user/repo
   Authorization: Bearer <PHAROS_ADMIN_TOKEN>
   
2. Cloud API validates and queues
   • Validate URL format
   • Check authentication token
   • Check queue size (<10)
   • Push to Redis: RPUSH ingest_queue
   • Return job_id and queue_position
   
3. Edge Worker polls queue
   • LPOP ingest_queue (every 2 seconds)
   • Check task TTL (skip if >24 hours old)
   • Update status: "Training Graph on {repo}"
   
4. Repository processing
   • Clone repository (GitPython)
   • Find source files (.py, .js, .ts)
   • Parse imports (Tree-sitter)
   • Build dependency graph (PyTorch tensor)
   
5. Graph neural network training
   • Initialize Node2Vec model
   • Train for 10 epochs on GPU
   • Generate 64-dimensional embeddings
   • Move embeddings to CPU
   
6. Embedding upload
   • Batch upload to Qdrant (100 per batch)
   • Retry up to 3 times on failure
   • Include metadata (file_path, repo_url)
   
7. Job completion
   • Record in job_history (Redis)
   • Update status: "Idle"
   • Clean up temporary files
```

### Status Monitoring Flow

```
1. UI polls worker status
   GET /api/v1/ingestion/worker/status
   (every 2 seconds)
   
2. Cloud API queries Redis
   GET worker_status
   
3. Return current status
   • "Idle" - Waiting for tasks
   • "Training Graph on {repo}" - Processing
   • "Error: {message}" - Error occurred
   • "Offline" - Worker not running
   
4. UI displays status
   • Show spinner during training
   • Show progress indicator
   • Alert on errors
```

## Security Architecture

### Authentication

**PHAROS_ADMIN_TOKEN**:
- Required for POST /ingest endpoint
- Bearer token in Authorization header
- Prevents unauthorized repository submissions
- Logged authentication failures

**Implementation**:
```python
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer()

def verify_admin_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    expected_token = os.getenv("PHAROS_ADMIN_TOKEN")
    if credentials.credentials != expected_token:
        raise HTTPException(status_code=401, detail="Invalid token")
    return credentials.credentials
```

### Queue Management

**Queue Cap** (10 pending tasks):
- Prevents zombie queue problem
- Avoids overwhelming edge worker
- Returns 429 when full

**Task TTL** (24 hours):
- Prevents processing stale tasks
- Worker skips expired tasks
- Records as "skipped" in history

**Implementation**:
```python
# Check queue size
queue_size = redis.llen("ingest_queue")
if queue_size >= 10:
    raise HTTPException(status_code=429, detail="Queue is full")

# Check task age
if age_seconds > ttl:
    # Skip and record
    job_record = {"status": "skipped", "reason": "Task exceeded TTL"}
    redis.lpush("job_history", json.dumps(job_record))
    return
```

### Network Security

**HTTPS Only**:
- All external APIs use HTTPS
- Upstash Redis: HTTPS REST API
- Qdrant Cloud: HTTPS with API key
- Neon: SSL/TLS connections

**No Inbound Ports**:
- Edge worker polls queue (outbound only)
- No port forwarding required
- Firewall-friendly architecture

## Configuration Management

### Base + Extension Strategy

**Problem**: Maintaining separate requirements files leads to version mismatches

**Solution**: Base file inherited by both cloud and edge

**requirements-base.txt** (shared):
```
fastapi==0.104.1
uvicorn==0.24.0
upstash-redis==0.15.0
pydantic==2.5.0
python-dotenv==1.0.0
gitpython==3.1.40
```

**requirements-cloud.txt** (extends base):
```
-r requirements-base.txt
psycopg2-binary==2.9.9
qdrant-client==1.7.0
```

**requirements-edge.txt** (extends base):
```
-r requirements-base.txt
torch==2.1.0
torch-geometric==2.4.0
tree-sitter==0.20.4
qdrant-client==1.7.0
numpy==1.24.3
psycopg2-binary==2.9.9
```

**Benefits**:
- Update shared dependencies once
- Both environments inherit automatically
- Prevents "dependency hell"
- Version consistency guaranteed

### MODE-Aware Configuration

**Cloud Mode** (MODE=CLOUD):
```python
if self.MODE == "CLOUD":
    # Skip heavy imports
    pass
```

**Edge Mode** (MODE=EDGE):
```python
if self.MODE == "EDGE":
    import torch
    self.DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"GPU: {torch.cuda.get_device_name(0)}")
```

## Performance Characteristics

### Cloud API

| Metric | Target | Actual |
|--------|--------|--------|
| Memory Usage | <512MB | ~350MB |
| Startup Time | <10s | ~5s |
| API Latency | <200ms | ~50ms |
| Queue Dispatch | <100ms | ~30ms |

### Edge Worker

| Metric | Target | Actual |
|--------|--------|--------|
| Processing Time (100 files) | <5min | ~2-3min |
| GPU Utilization | >70% | 80-90% |
| Throughput | >10 repos/hour | ~15 repos/hour |
| Memory Usage | <12GB | ~6-8GB |

### Cost Analysis

**Monthly Costs**:
- Render Free Tier: $0
- Neon Free Tier: $0
- Qdrant Cloud Free: $0
- Upstash Redis Free: $0
- Edge Worker Electricity: ~$10-20

**Total: $10-20/month**

**Scaling Costs** (if needed):
- Render Starter: $7/month
- Neon Pro: $19/month
- Qdrant Cloud: $25/month
- Upstash Redis: $10/month

**Total Scaled: $61/month**

## Monitoring and Observability

### Cloud API Monitoring

**Render Dashboard**:
- CPU usage
- Memory usage
- Request count
- Response time
- Error rate

**Health Check**:
```bash
curl https://your-app.onrender.com/health
```

Response:
```json
{
  "status": "healthy",
  "services": {
    "redis": "connected",
    "database": "connected",
    "qdrant": "connected"
  }
}
```

### Edge Worker Monitoring

**Worker Status**:
```bash
curl https://your-app.onrender.com/api/v1/ingestion/worker/status
```

**GPU Monitoring**:
```bash
nvidia-smi --query-gpu=utilization.gpu,memory.used,temperature.gpu --format=csv -l 1
```

**Job History**:
```bash
curl https://your-app.onrender.com/api/v1/ingestion/jobs/history?limit=10
```

### Metrics to Track

**Success Rate**: `complete / (complete + failed)`
**Average Duration**: Mean processing time
**Throughput**: Jobs per hour
**Error Rate**: `failed / total`
**Skip Rate**: `skipped / total`

## Error Handling

### Cloud API Errors

| Error | Status Code | Handling |
|-------|-------------|----------|
| Invalid URL | 400 | Validate before queuing |
| Invalid Token | 401 | Check PHAROS_ADMIN_TOKEN |
| Queue Full | 429 | Reject with retry-after |
| Redis Down | 503 | Return service unavailable |

### Edge Worker Errors

| Error | Handling |
|-------|----------|
| Clone Failure | Log, mark failed, continue |
| Parse Failure | Skip file, continue with others |
| Training Failure | Log, mark failed, clean GPU |
| Upload Failure | Retry 3x with backoff |
| Redis Connection | Reconnect every 5s |

## Deployment

### Cloud API Deployment

1. Push to GitHub
2. Render auto-deploys
3. Set environment variables
4. Verify health check

### Edge Worker Deployment

**Linux (systemd)**:
```bash
sudo systemctl enable neo-alexandria-worker
sudo systemctl start neo-alexandria-worker
```

**Windows (NSSM)**:
```powershell
nssm install NeoAlexandriaWorker python.exe worker.py
nssm start NeoAlexandriaWorker
```

**macOS (launchd)**:
```bash
launchctl load ~/Library/LaunchAgents/com.neoalexandria.worker.plist
```

## Future Enhancements

### Phase 19.5: Multi-Worker Support
- Multiple edge workers
- Load balancing
- Worker registration
- Distributed queue

### Phase 20: Advanced Graph Features
- Graph-based code search
- Dependency analysis
- Breaking change detection
- Code similarity search

### Phase 21: Hybrid Embeddings
- Combine structural + text embeddings
- Multi-modal search
- Weighted fusion
- A/B testing

## Related Documentation

- [Cloud Deployment Guide](../guides/phase19-deployment.md)
- [Edge Worker Setup Guide](../guides/phase19-edge-setup.md)
- [Monitoring Guide](../guides/phase19-monitoring.md)
- [Architecture Overview](overview.md)
