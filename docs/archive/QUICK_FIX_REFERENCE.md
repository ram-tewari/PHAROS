# Pharos Reliability Fixes — Quick Reference Card

> **One-page cheat sheet** for the May 2, 2026 reliability improvements

---

## The Problem (One Sentence)

NeonDB connection drop mid-ingestion cascaded into 57k file failures because the per-file except block didn't call `session.rollback()`.

---

## The Fixes (8 Changes)

| # | Fix | File | Lines | Impact |
|---|-----|------|-------|--------|
| 1 | Session rollback | `ast_pipeline.py` | 414-430 | Prevents cascade failures |
| 2 | Dedicated executor | `main_worker.py` | 33-50 | Prevents /embed starvation |
| 3 | Timeout increase | `search/service.py` | 191-196 | Cold-start tolerant |
| 4 | Worker heartbeat | `main_worker.py` | 52-90 | Visibility into worker state |
| 5 | DLQ + drain | `main_worker.py` | 92-180 | Prevents lost work |
| 6 | Worker-offline guard | `ingestion.py` | 500-645 | Refuses jobs if offline |
| 7 | Temp dir cleanup | `clear_stale_temp_dirs.py` | NEW | Reclaims ~3 GB |
| 8 | Daemonization | `pharos-edge-worker.service` | NEW | Auto-restart on crash |

---

## New Endpoints

```bash
# Record worker heartbeat (called by worker every 60s)
POST /api/v1/ingestion/health/worker
Authorization: Bearer <PHAROS_ADMIN_TOKEN>

# Query worker state
GET /api/v1/ingestion/health/worker
Authorization: Bearer <PHAROS_ADMIN_TOKEN>
# Returns: {"state": "online|degraded|offline", "seconds_since_last_seen": N}
```

---

## New Environment Variables (Worker)

```bash
# Required for heartbeat
PHAROS_ADMIN_TOKEN=4bad61a35f5d570014f9fa2a74ac51c19a35e9185c6f1e2987f96e49eefd3c74
PHAROS_CLOUD_URL=https://pharos-cloud-api.onrender.com

# Optional
PHAROS_INGESTION_THREADS=4  # Dedicated executor threads
```

---

## New Redis Keys

```bash
pharos:worker:last_seen  # Heartbeat timestamp (10-min TTL)
pharos:dlq               # Dead Letter Queue (tasks >4 hours old)
```

---

## Quick Commands

### Check worker status
```bash
curl -H "Authorization: Bearer $PHAROS_ADMIN_TOKEN" \
  https://pharos-cloud-api.onrender.com/api/v1/ingestion/health/worker
```

### Clean stale temp dirs
```bash
cd backend
python clear_stale_temp_dirs.py --delete
```

### Restart worker (Windows)
```powershell
cd C:\Users\rooma\PycharmProjects\pharos\backend
.\start_worker.ps1
```

### Restart worker (Linux/WSL)
```bash
cd backend
bash start_worker.sh
```

### Install systemd service (Linux)
```bash
sudo cp deployment/pharos-edge-worker.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now pharos-edge-worker
```

### Install NSSM service (Windows)
```powershell
# See deployment/NSSM_WINDOWS_SETUP.md for full guide
nssm install PharosEdgeWorker "C:\...\python.exe" "worker.py"
nssm start PharosEdgeWorker
```

---

## Before/After Metrics

| Metric | Before | After |
|--------|--------|-------|
| Cascade failure rate | 90% (57k/59k) | 0% (expected) |
| /embed timeout rate | High (during ingest) | 0% (isolated) |
| Worker visibility | None | Heartbeat (60s) |
| Stale task handling | None | DLQ (4h TTL) |
| Worker auto-restart | Manual | systemd/NSSM |

---

## Deployment Checklist

- [ ] Restart edge worker with new code
- [ ] Verify heartbeat working (worker shows "online")
- [ ] Re-ingest Linux kernel (should complete without cascade)
- [ ] Clean stale temp dirs (~3 GB)
- [ ] Deploy to Render (for new heartbeat endpoints)
- [ ] Set up daemonization (systemd or NSSM)

---

## Troubleshooting

### Worker shows "offline" but it's running
1. Check worker logs for heartbeat errors
2. Verify `PHAROS_ADMIN_TOKEN` is set
3. Test heartbeat endpoint manually

### Tasks sitting in queue forever
1. Check worker status (GET /health/worker)
2. If offline >5 min, API refuses new jobs (503)
3. Restart worker — DLQ drains on startup

### Stale pharos_ingest_* dirs filling disk
```bash
python clear_stale_temp_dirs.py --delete
```

---

## Documentation

- **Full Details**: `notebooklm/UPDATES_2026_05_02.md`
- **Update Guide**: `notebooklm/UPDATE_CHECKLIST.md`
- **Executive Summary**: `RELIABILITY_IMPROVEMENTS_SUMMARY.md`
- **This Card**: `QUICK_FIX_REFERENCE.md`

---

**Last Updated**: May 2, 2026  
**Status**: Ready for deployment  
**Priority**: HIGH — Deploy before next large ingestion

