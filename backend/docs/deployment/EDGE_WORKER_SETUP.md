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
python -m app.edge_worker
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
  -H "Authorization: Bearer 4bad61a35f5d570014f9fa2a74ac51c19a35e9185c6f1e2987f96e49eefd3c74" `
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
   python -m app.edge_worker
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

### Option A: Windows Task Scheduler

1. Open Task Scheduler
2. Create Basic Task
3. Trigger: At startup
4. Action: Start a program
5. Program: `powershell.exe`
6. Arguments: `-File "C:\path\to\pharos\backend\start_edge_worker.ps1"`

### Option B: NSSM (Non-Sucking Service Manager)

```powershell
# Install NSSM
choco install nssm

# Create service
nssm install PharosEdgeWorker "C:\path\to\python.exe" "-m app.edge_worker"
nssm set PharosEdgeWorker AppDirectory "C:\path\to\pharos\backend"
nssm set PharosEdgeWorker AppEnvironmentExtra "MODE=EDGE"

# Start service
nssm start PharosEdgeWorker
```

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

1. **Test end-to-end**: Create resource → verify embedding generated
2. **Monitor performance**: Track GPU usage, task latency
3. **Scale**: Add more edge workers if needed (different machines)
4. **Optimize**: Tune polling interval, batch processing

## Related Documentation

- [Hybrid Architecture Explained](HYBRID_ARCHITECTURE_EXPLAINED.md)
- [Render Deployment Guide](RENDER_FREE_DEPLOYMENT.md)
- [Troubleshooting Guide](../../TROUBLESHOOTING.md)

---

**Status**: Ready for setup  
**Last Updated**: 2026-04-15  
**Next**: Start edge worker and test with cloud API
