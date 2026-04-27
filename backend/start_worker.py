"""
Pharos Unified Edge Worker — cross-platform launcher.

Use this on Windows where bash isn't available; otherwise prefer start_worker.sh.

Guarantees:
  - cwd is backend/
  - .env is loaded
  - MODE=EDGE is forced
  - Banner prints active queues + 30s BLPOP timeout
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _bootstrap() -> None:
    backend_dir = Path(__file__).resolve().parent
    os.chdir(backend_dir)

    env_file = backend_dir / ".env"
    if env_file.exists():
        try:
            from dotenv import load_dotenv
            load_dotenv(env_file)
        except ImportError:
            print("[WARN] python-dotenv not installed; relying on shell env", file=sys.stderr)
    else:
        print(f"[WARN] {env_file} not found; relying on shell env", file=sys.stderr)

    os.environ["MODE"] = "EDGE"
    os.environ.setdefault("PYTHONUNBUFFERED", "1")

    # Same Windows WMI workaround as worker.py — must run before app imports.
    try:
        import platform as _platform
        _cached_uname = _platform.uname_result(
            system="Windows",
            node=os.environ.get("COMPUTERNAME", "localhost"),
            release="11",
            version="10.0.0",
            machine=os.environ.get("PROCESSOR_ARCHITECTURE", "AMD64"),
        )
        _platform.uname = lambda: _cached_uname
    except Exception:
        pass


def _banner() -> None:
    port = os.environ.get("EDGE_EMBED_PORT", "8001")
    print("=" * 64)
    print("  Pharos Unified Edge Worker")
    print("=" * 64)
    print(f"  Mode             : EDGE")
    print(f"  Queues (BLPOP)   : pharos:tasks, ingest_queue")
    print(f"  BLPOP timeout    : 30s  (~2,880 idle cmds/day, Upstash-safe)")
    print(f"  Embed endpoint   : http://127.0.0.1:{port}/embed")
    print(f"  Working dir      : {os.getcwd()}")
    print(f"  Python           : {sys.version.split()[0]}")
    print("=" * 64, flush=True)


def main() -> None:
    _bootstrap()
    _banner()

    import asyncio
    from app.workers.main_worker import main as worker_main

    try:
        asyncio.run(worker_main())
    except KeyboardInterrupt:
        sys.exit(0)
    except Exception as exc:
        print(f"[ERROR] Fatal error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
