# Pharos Edge Worker as a Windows Service (NSSM)

Goal: the edge worker starts on boot, restarts forever if it crashes, and logs
go to a rotating file so a long-running ingest doesn't fill the console
buffer.

We use [NSSM — the Non-Sucking Service Manager](https://nssm.cc/) because the
worker is a long-lived Python process, and the alternative (`sc.exe`) doesn't
handle stdout/stderr or restart policies cleanly.

---

## 1. Prerequisites

- Worker checkout at `C:\Users\rooma\PycharmProjects\pharos`
- A virtualenv with the edge requirements installed (`requirements-edge.txt`)
  at e.g. `C:\Users\rooma\PycharmProjects\pharos\.venv`
- NSSM installed and on PATH:

  ```powershell
  winget install --id NSSM.NSSM -e
  # or: choco install nssm
  ```

---

## 2. Create the env file

NSSM accepts a single `AppEnvironmentExtra` blob. Easiest is to keep your
secrets in `start_worker.ps1` *or* create a dedicated env file
`C:\ProgramData\Pharos\edge-worker.env` (one `KEY=VALUE` per line).

Required keys (mirror `start_worker.ps1`):

```
MODE=EDGE
UPSTASH_REDIS_REST_URL=https://...upstash.io
UPSTASH_REDIS_REST_TOKEN=...
DATABASE_URL=postgresql+asyncpg://...
EMBEDDING_MODEL_NAME=nomic-ai/nomic-embed-text-v1
PHAROS_ADMIN_TOKEN=...
PHAROS_CLOUD_URL=https://pharos-cloud-api.onrender.com
PYTHONIOENCODING=utf-8
PYTHONUTF8=1
```

`PHAROS_ADMIN_TOKEN` and `PHAROS_CLOUD_URL` are required for the heartbeat —
without them the worker shows up as **Offline** to the cloud API and the
ingestion router will refuse new work.

---

## 3. Install the service

Run from an **elevated PowerShell** (Admin):

```powershell
$service = "PharosEdgeWorker"
$python  = "C:\Users\rooma\PycharmProjects\pharos\.venv\Scripts\python.exe"
$workdir = "C:\Users\rooma\PycharmProjects\pharos\backend"
$logdir  = "C:\ProgramData\Pharos\logs"

New-Item -ItemType Directory -Force -Path $logdir | Out-Null

nssm install   $service $python "worker.py"
nssm set       $service AppDirectory          $workdir
nssm set       $service Description           "Pharos edge worker (embedding model + ingestion dispatcher)"
nssm set       $service Start                 SERVICE_AUTO_START

# Restart policy: come back up forever, but throttle if it's crashing fast.
nssm set       $service AppExit Default       Restart
nssm set       $service AppRestartDelay       10000          # 10s between restarts
nssm set       $service AppThrottle           5000           # consider startup 'failed' if it dies <5s in
nssm set       $service AppStopMethodSkip     0              # use full stop sequence
nssm set       $service AppStopMethodConsole  15000          # 15s for graceful Ctrl+C
nssm set       $service AppKillProcessTree    1

# Logs (rotated daily, capped at 50 MB).
nssm set       $service AppStdout             "$logdir\worker.log"
nssm set       $service AppStderr             "$logdir\worker.err.log"
nssm set       $service AppRotateFiles        1
nssm set       $service AppRotateOnline       1
nssm set       $service AppRotateSeconds      86400
nssm set       $service AppRotateBytes        52428800

# Environment — point at the env file *or* set inline. Inline shown below.
# (NSSM expects NUL-separated KEY=VALUE entries; the GUI is easier for editing.)
nssm set       $service AppEnvironmentExtra `
    "MODE=EDGE" `
    "PHAROS_CLOUD_URL=https://pharos-cloud-api.onrender.com" `
    "PYTHONIOENCODING=utf-8" `
    "PYTHONUTF8=1"
# Add UPSTASH_*, DATABASE_URL, EMBEDDING_MODEL_NAME, PHAROS_ADMIN_TOKEN
# either via the same command or by running `nssm edit PharosEdgeWorker`.

# Optional: run as a specific user instead of LocalSystem so file paths
# (huggingface cache under %USERPROFILE%) resolve to your account.
# nssm set    $service ObjectName ".\rooma" "<your-windows-password>"

nssm start     $service
```

Verify:

```powershell
Get-Service PharosEdgeWorker
Get-Content "C:\ProgramData\Pharos\logs\worker.log" -Tail 50 -Wait

# Heartbeat should show up within ~60s:
$h = @{ Authorization = "Bearer $env:PHAROS_ADMIN_TOKEN" }
Invoke-RestMethod -Uri "https://pharos-cloud-api.onrender.com/api/v1/ingestion/health/worker" -Headers $h
# -> { state: "online", last_seen_unix: ..., seconds_since_last_seen: <60 }
```

---

## 4. Day-to-day operations

```powershell
nssm restart PharosEdgeWorker     # after deploying new code
nssm stop    PharosEdgeWorker
nssm start   PharosEdgeWorker
nssm status  PharosEdgeWorker
nssm edit    PharosEdgeWorker     # GUI to tweak any setting
nssm remove  PharosEdgeWorker confirm
```

If the worker is crash-looping, NSSM honours `AppThrottle` to back off — but
also tail the log file. The first lines tell you whether it's an env-var
problem (missing UPSTASH_* etc.) or a model-load failure (CUDA / Hugging
Face cache).

---

## 5. Why NSSM and not Task Scheduler

`Task Scheduler` doesn't restart a foreground Python process when it exits
non-zero. `sc.exe` requires the Python program to be a real Windows service
(it isn't). NSSM is the standard wrapper for "long-running script as a
service" on Windows.
