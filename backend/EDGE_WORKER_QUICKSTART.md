# Edge Worker Quick Start

## TL;DR - Start in 3 Commands

```powershell
cd backend
pip install -r requirements-edge.txt
.\start_edge_worker.ps1
```

That's it! The edge worker is now running and processing tasks from the cloud API.

---

## What Just Happened?

1. **Installed dependencies**: PyTorch with CUDA 11.8, sentence-transformers, etc.
2. **Loaded environment**: From `.env.edge` (already configured)
3. **Started worker**: Polling Upstash Redis for tasks

## Expected Output

```
============================================================
Pharos Edge Worker - Local GPU Processing
============================================================
✓ Environment variables validated
🔥 GPU Detected:
   Device: NVIDIA GeForce RTX 4070
   Memory: 12.0 GB
   CUDA Version: 11.8
Loading embedding model...
✓ Embedding model loaded successfully (5.2s)
✓ Connected to Upstash Redis
✓ Connected to database
============================================================
✓ Edge worker ready - waiting for tasks...
============================================================
Starting task polling (interval: 2s)
Press Ctrl+C to stop
```

## Test It

In another terminal, create a test resource:

```powershell
curl -X POST https://pharos-cloud-api.onrender.com/api/resources `
  -H "Authorization: Bearer 4bad61a35f5d570014f9fa2a74ac51c19a35e9185c6f1e2987f96e49eefd3c74" `
  -H "Content-Type: application/json" `
  -d '{"url": "https://github.com/user/repo", "title": "Test Repo"}'
```

Watch the edge worker process it:

```
📥 Received task: task-123456
Processing task task-123456 for resource res-789
✓ Generated embedding (768 dims) in 45ms
✓ Stored embedding for resource res-789
✅ Task completed (total: 1 processed, 0 failed)
```

## Troubleshooting

### "CUDA not available"

Your GPU isn't detected. This is usually a driver issue:

1. Check drivers: `nvidia-smi` (run as admin if needed)
2. Reinstall PyTorch:
   ```powershell
   pip uninstall torch torchvision torchaudio
   pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
   ```
3. Restart terminal

**For now, it will work on CPU** (just slower). Fix GPU later.

### "Failed to load embedding model"

Missing dependencies:

```powershell
pip install sentence-transformers>=2.3.0 einops
```

### "Connection refused"

Check your `.env.edge` file has the correct values:
- `UPSTASH_REDIS_REST_URL=https://living-sculpin-96916.upstash.io`
- `UPSTASH_REDIS_REST_TOKEN=gQAAAAAAAXqUAAIncDFmMDExYmFjN2Y1ZjQ0ZDY2Yjc0NWE1NTBhMzg2ZDg5M3AxOTY5MTY`
- `DATABASE_URL=postgresql+asyncpg://neondb_owner:npg_2Lv8pxVJzgyd@ep-flat-meadow-ahvsmoyw-pooler.c-3.us-east-1.aws.neon.tech/neondb?sslmode=require`

## Stop the Worker

Press `Ctrl+C` in the terminal.

## Run in Background

### Option 1: New Terminal

Just open a new PowerShell window and run:
```powershell
cd C:\Users\rooma\PycharmProjects\pharos\backend
.\start_edge_worker.ps1
```

### Option 2: Windows Task Scheduler

1. Open Task Scheduler
2. Create Basic Task → "Pharos Edge Worker"
3. Trigger: At startup
4. Action: Start a program
5. Program: `powershell.exe`
6. Arguments: `-File "C:\Users\rooma\PycharmProjects\pharos\backend\start_edge_worker.ps1"`
7. Done!

Now it starts automatically when Windows boots.

## Monitor

### View Logs

```powershell
Get-Content backend\edge_worker.log -Tail 50 -Wait
```

### Check Queue

```powershell
python -c "import asyncio; from app.shared.upstash_redis import UpstashRedisClient; print('Queue length:', asyncio.run(UpstashRedisClient().get_queue_length()))"
```

### Check GPU Usage

```powershell
nvidia-smi -l 1  # Update every 1 second
```

## Next Steps

1. ✅ Edge worker running
2. ✅ Cloud API deployed (Render)
3. 🎯 Test end-to-end: Create resource → verify embedding
4. 🎯 Monitor performance: GPU usage, task latency
5. 🎯 Integrate with Ronin: Context retrieval API

## Full Documentation

For detailed setup, troubleshooting, and advanced configuration:
- [Edge Worker Setup Guide](docs/deployment/EDGE_WORKER_SETUP.md)
- [Hybrid Architecture Explained](docs/deployment/HYBRID_ARCHITECTURE_EXPLAINED.md)

---

**Status**: Ready to run  
**Time to start**: ~5 minutes (first time), ~30 seconds (subsequent)  
**GPU required**: No (works on CPU, just slower)
