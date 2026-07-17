# Quick Instructions: Restart Edge Worker

## TL;DR

The edge worker stopped sending heartbeats 8+ minutes ago. Restart it to test Phase 2 polyglot AST.

---

## One-Command Restart

```powershell
.\restart_worker.ps1
```

This will:
1. Stop any existing worker processes
2. Verify environment variables are set
3. Start fresh worker process
4. Worker will send heartbeat within 60 seconds

---

## Verify It's Working

```powershell
.\check_worker_status.ps1
```

Expected output:
```
Worker State: online
Last Heartbeat: [recent timestamp]
Seconds Ago: <60s
✓ Worker is healthy and ready to process tasks
```

---

## Test Phase 2 (Polyglot AST)

Once worker is online:

### 1. Ingest Go Repository
```powershell
$token = '4bad61a35f5d570014f9fa2a74ac51c19a35e9185c6f1e2987f96e49eefd3c74'

Invoke-WebRequest -Uri "https://pharos-cloud-api.onrender.com/api/v1/ingestion/ingest/github.com/fatih/color" `
  -Method POST `
  -Headers @{ "Authorization" = "Bearer $token" }
```

### 2. Wait 1-2 Minutes
Monitor worker logs:
```powershell
cd backend
Get-Content worker.log -Wait
```

Look for:
```
[REPO] ingest https://github.com/fatih/color (branch=default)
[REPO] github.com/fatih/color done | resources=15 chunks=234 failed=0 duration=45.2s
```

### 3. Search for Go Code
```powershell
$searchBody = @{
    query = "color function"
    strategy = "parent-child"
    top_k = 10
    include_code = $true
} | ConvertTo-Json

Invoke-WebRequest -Uri "https://pharos-cloud-api.onrender.com/api/search/advanced" `
  -Method POST `
  -Headers @{ 
    "Authorization" = "Bearer $token"
    "Content-Type" = "application/json"
  } `
  -Body $searchBody `
  | Select-Object -ExpandProperty Content | ConvertFrom-Json | ConvertTo-Json -Depth 10
```

### 4. Verify AST Extraction
Check response for:
- ✅ `language: "go"`
- ✅ `ast_node_type: "function"` (not "block")
- ✅ `symbol_name: "github.com/fatih/color.Color.Printf"`
- ✅ `code: "func (c *Color) Printf(...)"`

If you see `ast_node_type: "function"` → **Phase 2 is working!** 🎉

---

## What Was Fixed

### Phase 1: Search Serialization ✅
- All metadata fields populated (file_name, github_uri, line numbers)
- Code resolution works for all chunks
- Deployed and verified on production

### Phase 2: Polyglot AST ✅
- Tree-sitter parsers for 7 languages (C, C++, Go, Rust, JS, TS, Python)
- AST extraction for all supported languages
- Graceful fallback to line-chunking for unsupported languages
- Deployed but **not yet tested** (needs worker online)

---

## Why Worker Stopped

You mentioned "i stopped edge worker" in the chat. The worker needs to be running to:
1. Process ingestion tasks from `ingest_queue`
2. Generate embeddings on GPU (RTX 4070)
3. Send heartbeats to production API

Without the worker:
- Ingestion endpoint returns 503 (refuses new work)
- Cannot test Phase 2 polyglot AST
- Cannot ingest new repositories

---

## Files Created

1. **`restart_worker.ps1`** - Safely restart the worker
2. **`check_worker_status.ps1`** - Check worker health
3. **`WORKER_STATUS_2026_05_03.md`** - Detailed status report
4. **`RESTART_WORKER_INSTRUCTIONS.md`** - This file

---

## Next Steps

1. ⏳ Run `.\restart_worker.ps1` to start worker
2. ⏳ Run `.\check_worker_status.ps1` to verify online
3. ⏳ Ingest Go repo (github.com/fatih/color)
4. ⏳ Search and verify `ast_node_type: "function"`
5. ⏳ Celebrate Phase 2 completion! 🎉

---

**ETA**: 30 seconds to restart, 2 minutes to test Phase 2

