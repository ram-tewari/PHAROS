# Edge Worker Setup Guide

## Overview

This guide walks you through setting up the Pharos Edge Worker on your local machine with GPU support.

## Prerequisites

### Hardware
- **GPU**: NVIDIA GPU with CUDA support (RTX 3060, 4070, 4090, etc.)
- **RAM**: 8GB+ recommended (16GB for large models)
- **Storage**: 10GB+ free space for models

### Software
- **Python**: 3.11+ (3.11.9 recommended)
- **CUDA**: 11.8 or 12.1 (check with `nvidia-smi`)
- **Git**: For cloning repository

## Step 1: Check GPU

First, verify your NVIDIA GPU is detected:

```powershell
nvidia-smi
```

Expected output:
```
+-----------------------------------------------------------------------------+
| NVIDIA-SMI 535.xx       Driver Version: 535.xx       CUDA Version: 12.2   |
|-------------------------------+----------------------+----------------------+
| GPU  Name            TCC/WDDM | Bus-Id        Disp.A | Volatile Uncorr. ECC |
| Fan  Temp  Perf  Pwr:Usage/Cap|         Memory-Usage | GPU-Util  Compute M. |
|===============================+======================+======================|
|   0  NVIDIA GeForce ... WDDM  | 00000000:01:00.0  On |                  N/A |
| 30%   45C    P8    15W / 200W |   1234MiB /  8192MiB |      2%      Default |
+-------------------------------+----------------------+----------------------+
```

**If you see "NVIDIA-SMI has failed"**:
- Run PowerShell as Administrator
- Or update NVIDIA drivers: https://www.nvidia.com/Download/index.aspx

## Step 2: Install Dependencies

### Option A: Using requirements-edge.txt (Recommended)

```powershell
cd backend

# Activate virtual environment
.venv\Scripts\Activate.ps1

# Install edge dependencies (includes PyTorch with CUDA 11.8)
pip install -r requirements-edge.txt
```

This will install:
- PyTorch 2.7.1 with CUDA 11.8 support
- sentence-transformers 2.3.0+
- transformers, accelerate, bitsandbytes
- FAISS for vector search
- All other dependencies

### Option B: Manual Installation

If you already have PyTorch installed or want a different CUDA version:

```powershell
# Check current PyTorch version
python -c "import torch; print(torch.__version__)"

# If PyTorch not installed or wrong CUDA version, install:
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118

# Install other dependencies
pip install sentence-transformers>=2.3.0 transformers accelerate einops
```

## Step 3: Verify PyTorch + CUDA

```powershell
python -c "import torch; print('PyTorch:', torch.__version__); print('CUDA Available:', torch.cuda.is_available()); print('Device:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU')"
```

Expected output:
```
PyTorch: 2.7.1+cu118
CUDA Available: True
Device: NVIDIA GeForce RTX 4070
```

**If CUDA Available: False**:
1. Check NVIDIA drivers are installed: `nvidia-smi`
2. Reinstall PyTorch with CUDA: `pip install torch --index-url https://download.pytorch.org/whl/cu118`
3. Restart terminal/IDE

## Step 4: Configure Environment

Copy the edge worker environment file:

```powershell
cd backend
copy .env.edge .env
```

The `.env.edge` file is already configured with:
- `MODE=EDGE` (required)
- `UPSTASH_REDIS_REST_URL` (same as cloud API)
- `UPSTASH_REDIS_REST_TOKEN` (same as cloud API)
- `DATABASE_URL` (NeonDB, same as cloud API)
- `EMBEDDING_MODEL_NAME=nomic-ai/nomic-embed-text-v1`

**No changes needed** - these values are already set correctly!

## Step 5: Test Connection

Test connection to Upstash Redis and NeonDB:

```powershell
python -c "import asyncio; from app.shared.upstash_redis import UpstashRedisClient; asyncio.run(UpstashRedisClient().ping())"
```

Expected output:
```
True
```

## Step 6: Start Edge Worker

### Option A: Using PowerShell Script (Recommended)

```powershell
cd backend
.\start_edge_worker.ps1
```

This script will:
1. Load environment from `.env.edge`
2. Verify MODE=EDGE
3. Check PyTorch installation
4. Check sentence-transformers installation
5. Start the edge worker

### Option B: Manual Start

```powershell
cd backend

# Load environment
Get-Content .env.edge | ForEach-Object {
    if ($_ -match '^([^#][^=]+)=(.*)$') {
        [Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim(), "Process")
    }
}

# Start worker
python worker.py edge
```

## Expected Output

When the edge worker starts successfully, you should see:

```
============================================================
Pharos Edge Worker - Local GPU Processing
============================================================
2026-04-15 12:00:00 - __main__ - INFO - ✓ Environment variables validated
2026-04-15 12:00:00 - __main__ - INFO - 🔥 GPU Detected:
2026-04-15 12:00:00 - __main__ - INFO -    Device: NVIDIA GeForce RTX 4070
2026-04-15 12:00:00 - __main__ - INFO -    Memory: 12.0 GB
2026-04-15 12:00:00 - __main__ - INFO -    CUDA Version: 11.8
2026-04-15 12:00:00 - __main__ - INFO -    PyTorch Version: 2.7.1+cu118
2026-04-15 12:00:00 - __main__ - INFO - Loading embedding model...
2026-04-15 12:00:05 - __main__ - INFO - ✓ Embedding model loaded successfully (5.2s)
2026-04-15 12:00:05 - __main__ - INFO - Connecting to Upstash Redis...
2026-04-15 12:00:05 - __main__ - INFO - ✓ Connected to Upstash Redis
2026-04-15 12:00:05 - __main__ - INFO - Connecting to database...
2026-04-15 12:00:06 - __main__ - INFO -    Database: ep-flat-meadow-ahvsmoyw-pooler.c-3.us-east-1.aws.neon.tech
2026-04-15 12:00:06 - __main__ - INFO - ✓ Connected to database
============================================================
✓ Edge worker ready - waiting for tasks...
============================================================
2026-04-15 12:00:06 - __main__ - INFO - Starting task polling (interval: 2s)
2026-04-15 12:00:06 - __main__ - INFO - Press Ctrl+C to stop
```

## Step 7: Test with a Task

In another terminal, create a test resource via the cloud API:

```powershell
curl -X POST https://pharos-cloud-api.onrender.com/api/resources `
  -H "Authorization: Bearer <REDACTED-PHAROS_ADMIN_TOKEN-rotate>" `
  -H "Content-Type: application/json" `
  -d '{"url": "https://github.com/user/repo", "title": "Test Repo", "description": "Testing edge worker"}'
```

You should see the edge worker process the task:

```
2026-04-15 12:01:00 - __main__ - INFO - 📥 Received task: task-123456
2026-04-15 12:01:00 - __main__ - INFO - Processing task task-123456 for resource res-789
2026-04-15 12:01:00 - __main__ - INFO - ✓ Generated embedding (768 dims) in 45ms
2026-04-15 12:01:00 - __main__ - INFO - ✓ Stored embedding for resource res-789
2026-04-15 12:01:00 - __main__ - INFO - ✅ Task completed (total: 1 processed, 0 failed)
```

## Troubleshooting

### Issue: "CUDA not available"

**Symptoms**:
```
⚠️  CUDA not available, falling back to CPU
```

**Solutions**:
1. Check NVIDIA drivers: `nvidia-smi`
2. Reinstall PyTorch with CUDA:
   ```powershell
   pip uninstall torch torchvision torchaudio
   pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
   ```
3. Restart terminal/IDE
4. Verify: `python -c "import torch; print(torch.cuda.is_available())"`

### Issue: "Failed to load embedding model"

**Symptoms**:
```
❌ Failed to load embedding model: No module named 'sentence_transformers'
```

**Solutions**:
```powershell
pip install sentence-transformers>=2.3.0 einops
```

### Issue: "Connection refused to Upstash Redis"

**Symptoms**:
```
❌ Failed to connect to Upstash Redis: Connection refused
```

**Solutions**:
1. Check `UPSTASH_REDIS_REST_URL` in `.env.edge`
2. Verify token: `UPSTASH_REDIS_REST_TOKEN`
3. Test connection:
   ```powershell
   curl https://living-sculpin-96916.upstash.io/ping `
     -H "Authorization: Bearer YOUR_TOKEN"
   ```

### Issue: "Connection refused to NeonDB"

**Symptoms**:
```
❌ Failed to connect to database: Connection refused
```

**Solutions**:
1. Check `DATABASE_URL` in `.env.edge`
2. Verify `?sslmode=require` is at the end
3. Test connection:
   ```powershell
   python -c "from sqlalchemy import create_engine; engine = create_engine('YOUR_DATABASE_URL'); engine.connect()"
   ```

### Issue: "Out of memory"

**Symptoms**:
```
RuntimeError: CUDA out of memory
```

**Solutions**:
1. Close other GPU applications (games, video editing, etc.)
2. Reduce batch size (not applicable for single embeddings)
3. Use CPU mode temporarily:
   ```powershell
   $env:CUDA_VISIBLE_DEVICES = ""
   python worker.py edge
   ```

### Issue: "No tasks being processed"

**Symptoms**:
- Edge worker running but no tasks appear
- Cloud API returns 202 Accepted but nothing happens

**Solutions**:
1. Check queue length:
   ```powershell
   python -c "import asyncio; from app.shared.upstash_redis import UpstashRedisClient; print(asyncio.run(UpstashRedisClient().get_queue_length()))"
   ```
2. Verify cloud API is queuing tasks (check Render logs)
3. Check edge worker logs for errors
4. Verify `UPSTASH_REDIS_REST_URL` matches between cloud and edge

## Performance Tuning

### GPU Memory Usage

Monitor GPU memory:
```powershell
nvidia-smi -l 1  # Update every 1 second
```

### Polling Interval

Adjust `WORKER_POLL_INTERVAL` in `.env.edge`:
- **2 seconds** (default): Good balance
- **1 second**: More responsive, higher CPU usage
- **5 seconds**: Lower CPU usage, slower response

### Batch Processing

For multiple tasks, the edge worker processes them one at a time. To process in batches, modify `edge_worker.py` to pop multiple tasks.

## Running as a Service

Use NSSM for both the ingestion worker and the embedding HTTP server. NSSM
handles crash-restart and log rotation automatically. See
[NSSM_SERVICE_CONFIG.md](../guides/NSSM_SERVICE_CONFIG.md) for full service
definitions including the `PharosEmbedServer` entry.

```powershell
# Install NSSM if not already present
choco install nssm -y

# Ingestion worker
nssm install PharosEdgeWorker `
  "C:\Users\rooma\PycharmProjects\pharos\backend\.venv\Scripts\python.exe" `
  "worker.py edge"
nssm set PharosEdgeWorker AppDirectory "C:\Users\rooma\PycharmProjects\pharos\backend"
nssm set PharosEdgeWorker AppEnvironmentExtra "MODE=EDGE"
nssm start PharosEdgeWorker

# Embedding HTTP server (see Step 8 below)
nssm install PharosEmbedServer `
  "C:\Users\rooma\PycharmProjects\pharos\backend\.venv\Scripts\python.exe" `
  "-m uvicorn embed_server:app --host 127.0.0.1 --port 8001"
nssm set PharosEmbedServer AppDirectory "C:\Users\rooma\PycharmProjects\pharos\backend"
nssm set PharosEmbedServer AppEnvironmentExtra "MODE=EDGE"
nssm start PharosEmbedServer
```

## Step 8: HTTP Embedding Server

Render's cloud search API cannot load ML models (512 MB RAM limit). Instead it
calls this laptop's `embed_server.py` via Tailscale Funnel to get query
embeddings on demand.

`embed_server.py` is a standalone FastAPI process that:
- loads `nomic-ai/nomic-embed-text-v1` once at startup (same model as ingestion)
- exposes `POST /embed {"text":"..."} → {"embedding":[float,…]}`
- listens on `127.0.0.1:8001` (Tailscale Funnel proxies public HTTPS → this port)

### Start manually (test first)

```powershell
cd C:\Users\rooma\PycharmProjects\pharos\backend
.\.venv\Scripts\Activate.ps1
$env:MODE = "EDGE"
uvicorn embed_server:app --host 127.0.0.1 --port 8001
```

Expected output:
```
INFO:     Loading embedding model: nomic-ai/nomic-embed-text-v1
INFO:     Embedding model ready on cuda
INFO:     Uvicorn running on http://127.0.0.1:8001
```

### Install as NSSM service (auto-starts on boot)

See [NSSM_SERVICE_CONFIG.md](../guides/NSSM_SERVICE_CONFIG.md) — `PharosEmbedServer` section.

## Step 9: Tailscale Funnel Setup

Tailscale Funnel gives the embed server a stable public HTTPS hostname
(`https://<machine>.<tailnet>.ts.net`) that Render can reach without any
firewall changes.

### One-time setup

**1. Install Tailscale for Windows**

Download from https://tailscale.com/download and run the installer. The
installer registers `tailscaled` as a Windows service automatically.

**2. Sign in with GitHub**

```powershell
tailscale login
```

Authenticate with the `ram-tewari` GitHub account when the browser opens.

**3. Enable Funnel in the admin console**

Go to https://login.tailscale.com/admin/machines, click your machine, then
**Edit node attributes** and enable the `funnel` attribute. Save.

**4. Configure Funnel for port 8001**

```powershell
tailscale funnel 8001
```

This registers port 8001 as the Funnel target. The command exits after
configuring; the Tailscale daemon keeps the Funnel rule active across reboots.

**5. Verify Funnel persists after reboot**

Reboot, then check:
```powershell
tailscale funnel status
```

Expected output includes `https://<machine>.<tailnet>.ts.net/ → 127.0.0.1:8001`.

If the Funnel rule does not survive a reboot, install the `PharosTailscaleFunnel`
NSSM fallback service described in
[NSSM_SERVICE_CONFIG.md](../guides/NSSM_SERVICE_CONFIG.md).

**6. Get your public hostname**

```powershell
tailscale status
```

Record the `*.ts.net` hostname shown next to your machine (e.g.,
`desktop-abc123.tail1234.ts.net`).

**7. Set the Render environment variable**

In the Render dashboard, add:
```
EDGE_EMBEDDING_URL = https://desktop-abc123.tail1234.ts.net
```

(No trailing slash. Render restarts automatically.)

## Step 10: End-to-End Verification

With both NSSM services running and Funnel configured, verify the full path:

```bash
# From any machine (or from Render's shell via render.com dashboard)
curl https://<machine>.<tailnet>.ts.net/embed \
  -H "Content-Type: application/json" \
  -d '{"text": "what does the authentication system do"}'
```

Expected response (768 floats, not all shown):
```json
{"embedding": [0.023, -0.041, 0.117, ...]}
```

Health check:
```bash
curl https://<machine>.<tailnet>.ts.net/health
# {"status": "ok", "model": "nomic-ai/nomic-embed-text-v1"}
```

Then run a search from Ronin or via the API and confirm results are non-empty.

## Monitoring

### Logs

Edge worker logs are written to:
- **Console**: Real-time output
- **File**: `backend/edge_worker.log`

View logs:
```powershell
Get-Content backend\edge_worker.log -Tail 50 -Wait
```

### Metrics

Check task statistics:
```powershell
# Queue length
python -c "import asyncio; from app.shared.upstash_redis import UpstashRedisClient; print('Queue:', asyncio.run(UpstashRedisClient().get_queue_length()))"

# Task status
python -c "import asyncio; from app.shared.upstash_redis import UpstashRedisClient; print('Status:', asyncio.run(UpstashRedisClient().get_task_status('task-123')))"
```

## Next Steps

1. **Ingestion**: Create resource → verify embedding generated by edge worker
2. **Search**: Run a search query via Ronin → confirm non-empty results (requires Funnel live)
3. **Monitor GPU**: `nvidia-smi -l 1` during active use
4. **Optimize**: Tune `WORKER_POLL_INTERVAL` in `.env.edge`

## Related Documentation

- [Hybrid Architecture Explained](HYBRID_ARCHITECTURE_EXPLAINED.md)
- [NSSM Service Config](../guides/NSSM_SERVICE_CONFIG.md)
- [Render Deployment Guide](RENDER_FREE_DEPLOYMENT.md)
- [Troubleshooting Guide](../../TROUBLESHOOTING.md)

---

**Status**: Ready for setup  
**Last Updated**: 2026-04-18  
**Next**: Install PharosEmbedServer NSSM service and configure Tailscale Funnel
