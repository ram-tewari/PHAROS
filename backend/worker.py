"""
Pharos worker dispatcher.

    python worker.py            # run the unified main_worker

The legacy `edge`, `repo`, and `combined` subcommands have been collapsed into
one process: app.workers.main_worker. It blocks on both pharos:tasks and
ingest_queue with a single BLPOP and routes by source queue.
"""

import sys
from pathlib import Path

# Arm faulthandler immediately so a native segfault in torch / nomic custom
# code prints a Python stack to stderr instead of vanishing silently.
try:
    import faulthandler
    faulthandler.enable()
except Exception:
    pass

# Force line-buffered stdio so log lines surface in real time even when our
# stdout is a pipe (supervisor, file redirect, etc).
try:
    sys.stdout.reconfigure(line_buffering=True)  # type: ignore[attr-defined]
    sys.stderr.reconfigure(line_buffering=True)  # type: ignore[attr-defined]
except Exception:
    pass

# Load .env before any app imports so check_environment() sees the vars.
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

# Workaround: Python 3.13 platform.*() uses WMI on Windows which can hang
# indefinitely. Cache a synthetic uname_result so all platform.*() calls bypass
# WMI before any app module imports.
try:
    import platform as _platform
    import os as _os

    _cached_uname = _platform.uname_result(
        system="Windows",
        node=_os.environ.get("COMPUTERNAME", "localhost"),
        release="11",
        version="10.0.0",
        machine=_os.environ.get("PROCESSOR_ARCHITECTURE", "AMD64"),
    )
    _platform.uname = lambda: _cached_uname
except Exception:
    pass


def main() -> None:
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
