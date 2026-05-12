"""
pharos-edge: supervisor + status CLI for the Pharos edge worker.

Subcommands:
  start [--wsl]       Detach a supervisor that owns the worker subprocess and
                      restarts it with exponential backoff if it crashes.
  stop                Stop the supervisor (which stops the worker).
  restart [--wsl]     stop + start.
  status              Rich table: supervisor, worker, heartbeat, queues, logs.
  logs [-n N]         Print the last N lines of the worker log.
  run [--wsl]         Foreground supervisor (for debugging / systemd-style use).
  doctor              Validate env, deps, Upstash, GPU.

State is kept in backend/.pharos_edge/ — supervisor.pid, worker.pid, state.json,
and rotating logs/ — none of which are committed to git.
"""

from __future__ import annotations

import sys as _sys
# Force UTF-8 for our stdout/stderr so rich's unicode glyphs (✓ ● ✗ …) don't
# blow up on Windows cp1252 consoles. Must happen before any rich import.
try:
    _sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    _sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
except Exception:
    pass

import argparse
import datetime as _dt
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Paths and constants
# ---------------------------------------------------------------------------

BACKEND_DIR = Path(__file__).resolve().parent
STATE_DIR = BACKEND_DIR / ".pharos_edge"
LOG_DIR = STATE_DIR / "logs"
SUPERVISOR_PID = STATE_DIR / "supervisor.pid"
WORKER_PID = STATE_DIR / "worker.pid"
STATE_FILE = STATE_DIR / "state.json"
LOG_FILE = LOG_DIR / "worker.log"
SUPERVISOR_LOG = LOG_DIR / "supervisor.log"

BACKOFF_SECONDS = [5, 15, 60, 300, 300]  # cap at 5 minutes between retries
STATE_REFRESH_SECONDS = 2.0
WORKER_POLL_SECONDS = 1.0
LOG_ROTATE_BYTES = 10 * 1024 * 1024  # 10 MB
LOG_ROTATE_KEEP = 5

DEFAULT_CLOUD_URL = "https://pharos-cloud-api.onrender.com"

IS_WINDOWS = os.name == "nt"

# ---------------------------------------------------------------------------
# Small utilities (kept inline so this file has no Pharos-internal imports)
# ---------------------------------------------------------------------------


def _ensure_dirs() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def _now_iso() -> str:
    return _dt.datetime.now().isoformat(timespec="seconds")


def _read_pid(path: Path) -> Optional[int]:
    try:
        return int(path.read_text().strip())
    except Exception:
        return None


def _write_pid(path: Path, pid: int) -> None:
    path.write_text(str(pid))


def _pid_alive(pid: Optional[int]) -> bool:
    if not pid:
        return False
    if IS_WINDOWS:
        # os.kill(pid, 0) is unreliable on Windows for detached / no-console
        # processes — it returns OSError "Invalid procedure call" even when
        # the process is plainly alive. Use OpenProcess + GetExitCodeProcess
        # via ctypes instead. PROCESS_QUERY_LIMITED_INFORMATION (0x1000) is
        # granted to most processes regardless of console state.
        try:
            import ctypes
            from ctypes import wintypes
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            STILL_ACTIVE = 259
            k32 = ctypes.windll.kernel32
            handle = k32.OpenProcess(
                PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid)
            )
            if not handle:
                return False
            try:
                code = wintypes.DWORD(0)
                ok = k32.GetExitCodeProcess(handle, ctypes.byref(code))
                if not ok:
                    return False
                return code.value == STILL_ACTIVE
            finally:
                k32.CloseHandle(handle)
        except Exception:
            return False
    else:
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True


def _read_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {}


def _write_state(state: dict) -> None:
    state["updated_at"] = _now_iso()
    tmp = STATE_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2))
    tmp.replace(STATE_FILE)


def _rotate_if_needed(path: Path) -> None:
    try:
        if not path.exists() or path.stat().st_size < LOG_ROTATE_BYTES:
            return
        stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        path.rename(path.with_name(f"{path.stem}.{stamp}.log"))
        # Trim old rotations
        rotated = sorted(
            path.parent.glob(f"{path.stem}.*.log"), key=lambda p: p.stat().st_mtime
        )
        for old in rotated[:-LOG_ROTATE_KEEP]:
            old.unlink(missing_ok=True)
    except Exception:
        # Rotation is best-effort; never let it kill the supervisor.
        pass


def _read_env_file() -> dict:
    env = {}
    env_path = BACKEND_DIR / ".env"
    if not env_path.exists():
        return env
    for line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


# ---------------------------------------------------------------------------
# Rich rendering (lazy import — keep CLI fast for non-status commands)
# ---------------------------------------------------------------------------


def _console():
    from rich.console import Console
    return Console()


def _print_ok(msg: str) -> None:
    _console().print(f"[green]✓[/green] {msg}")


def _print_warn(msg: str) -> None:
    _console().print(f"[yellow]![/yellow] {msg}")


def _print_err(msg: str) -> None:
    _console().print(f"[red]✗[/red] {msg}")


# ---------------------------------------------------------------------------
# Worker subprocess spawning
# ---------------------------------------------------------------------------


def _worker_cmd(mode: str) -> list[str]:
    """Return the argv that launches a single worker process."""
    if mode == "wsl":
        # Run under WSL. Assumes WSL has the same backend mounted at /mnt/c/...
        # and that `python3` resolves to a venv with deps. User can override via
        # PHAROS_WSL_PYTHON.
        wsl_python = os.environ.get("PHAROS_WSL_PYTHON", "python3")
        wsl_path = _windows_to_wsl(BACKEND_DIR)
        return [
            "wsl", "--",
            "bash", "-lc",
            f"cd {wsl_path} && {wsl_python} -u -X faulthandler worker.py",
        ]
    # Windows / native
    return [sys.executable, "-u", "-X", "faulthandler", "worker.py"]


def _windows_to_wsl(p: Path) -> str:
    s = str(p).replace("\\", "/")
    if len(s) > 2 and s[1] == ":":
        drive = s[0].lower()
        return f"/mnt/{drive}{s[2:]}"
    return s


def _spawn_worker(mode: str) -> subprocess.Popen:
    _ensure_dirs()
    _rotate_if_needed(LOG_FILE)
    log_handle = open(LOG_FILE, "ab", buffering=0)
    log_handle.write(
        f"\n=== worker boot @ {_now_iso()} mode={mode} cmd={_worker_cmd(mode)!r} ===\n".encode()
    )

    creationflags = 0
    if IS_WINDOWS:
        # CREATE_NEW_PROCESS_GROUP lets us send CTRL_BREAK_EVENT later.
        # CREATE_NO_WINDOW prevents the worker from inheriting / allocating a
        # console — without this, Intel MKL's Fortran runtime (forrtl) traps
        # CTRL_CLOSE on the parent terminal and aborts numpy/sklearn-using
        # workers when the launching shell window closes.
        # CREATE_BREAKAWAY_FROM_JOB makes a best-effort attempt to escape the
        # parent's job object (e.g. PowerShell's). If the parent job forbids
        # breakaway, the flag is silently ignored on most Windows builds.
        CREATE_NO_WINDOW = 0x08000000
        CREATE_BREAKAWAY_FROM_JOB = 0x01000000
        creationflags = (
            subprocess.CREATE_NEW_PROCESS_GROUP
            | CREATE_NO_WINDOW
            | CREATE_BREAKAWAY_FROM_JOB
        )

    try:
        proc = subprocess.Popen(
            _worker_cmd(mode),
            cwd=str(BACKEND_DIR),
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            creationflags=creationflags,
            start_new_session=not IS_WINDOWS,
        )
    except OSError:
        # Parent job may have JOB_OBJECT_LIMIT_BREAKAWAY_OK disabled. Retry
        # without the breakaway flag — we still get the no-console isolation.
        if IS_WINDOWS:
            creationflags &= ~CREATE_BREAKAWAY_FROM_JOB
        proc = subprocess.Popen(
            _worker_cmd(mode),
            cwd=str(BACKEND_DIR),
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            creationflags=creationflags,
            start_new_session=not IS_WINDOWS,
        )
    _write_pid(WORKER_PID, proc.pid)
    return proc


def _terminate_worker(proc: subprocess.Popen, *, timeout: float = 10.0) -> None:
    if proc.poll() is not None:
        return
    try:
        if IS_WINDOWS:
            proc.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            proc.terminate()
    except Exception:
        pass
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            proc.kill()
        except Exception:
            pass
        try:
            proc.wait(timeout=5)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Supervisor loop (the long-running piece)
# ---------------------------------------------------------------------------


def _supervise(mode: str) -> int:
    """Long-running supervisor. Returns process exit code."""
    _ensure_dirs()
    _write_pid(SUPERVISOR_PID, os.getpid())

    sup_log = open(SUPERVISOR_LOG, "a", encoding="utf-8")

    def _log(msg: str) -> None:
        line = f"[{_now_iso()}] {msg}\n"
        sup_log.write(line)
        sup_log.flush()
        try:
            print(line.rstrip(), flush=True)
        except Exception:
            pass

    _log(f"supervisor start pid={os.getpid()} mode={mode}")

    started_at = time.time()
    restart_count = 0
    last_exit_code: Optional[int] = None
    last_crash_at: Optional[str] = None
    stopping = False

    def _on_signal(signum, frame):
        nonlocal stopping
        stopping = True
        _log(f"supervisor signal={signum} — shutting down")

    # Handle Ctrl+C / SIGTERM cleanly.
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _on_signal)
        except Exception:
            pass
    if IS_WINDOWS:
        try:
            signal.signal(signal.SIGBREAK, _on_signal)  # type: ignore[attr-defined]
        except Exception:
            pass

    proc: Optional[subprocess.Popen] = None
    backoff_idx = 0

    try:
        while not stopping:
            # (Re)start worker if needed.
            if proc is None or proc.poll() is not None:
                if proc is not None:
                    last_exit_code = proc.returncode
                    last_crash_at = _now_iso()
                    restart_count += 1
                    _log(
                        f"worker exited code={last_exit_code} "
                        f"restart_count={restart_count}"
                    )
                    wait_for = BACKOFF_SECONDS[min(backoff_idx, len(BACKOFF_SECONDS) - 1)]
                    backoff_idx += 1
                    _log(f"backoff {wait_for}s before respawn")
                    # Sleep in 1s slices so stop is responsive.
                    end = time.time() + wait_for
                    while time.time() < end and not stopping:
                        _write_state({
                            "status": "backoff",
                            "mode": mode,
                            "supervisor_pid": os.getpid(),
                            "worker_pid": None,
                            "started_at": _dt.datetime.fromtimestamp(started_at).isoformat(timespec="seconds"),
                            "restart_count": restart_count,
                            "last_exit_code": last_exit_code,
                            "last_crash_at": last_crash_at,
                            "backoff_until": _dt.datetime.fromtimestamp(end).isoformat(timespec="seconds"),
                        })
                        time.sleep(min(1.0, end - time.time()))
                    if stopping:
                        break

                _log("spawning worker")
                try:
                    proc = _spawn_worker(mode)
                    _log(f"worker pid={proc.pid}")
                except Exception as exc:
                    _log(f"spawn failed: {exc!r}")
                    proc = None
                    continue

            # Worker is running — refresh state and poll.
            _write_state({
                "status": "running",
                "mode": mode,
                "supervisor_pid": os.getpid(),
                "worker_pid": proc.pid,
                "started_at": _dt.datetime.fromtimestamp(started_at).isoformat(timespec="seconds"),
                "restart_count": restart_count,
                "last_exit_code": last_exit_code,
                "last_crash_at": last_crash_at,
            })

            # If the worker has been up for 60s without crashing, reset backoff.
            if proc.poll() is None and time.time() - started_at > 60:
                if backoff_idx > 0:
                    _log("worker stable >60s — resetting backoff")
                    backoff_idx = 0

            time.sleep(WORKER_POLL_SECONDS)
    finally:
        if proc is not None and proc.poll() is None:
            _log("terminating worker on supervisor exit")
            _terminate_worker(proc)
        _write_state({
            "status": "stopped",
            "mode": mode,
            "supervisor_pid": None,
            "worker_pid": None,
            "started_at": _dt.datetime.fromtimestamp(started_at).isoformat(timespec="seconds"),
            "restart_count": restart_count,
            "last_exit_code": last_exit_code,
            "last_crash_at": last_crash_at,
            "stopped_at": _now_iso(),
        })
        try:
            SUPERVISOR_PID.unlink(missing_ok=True)
            WORKER_PID.unlink(missing_ok=True)
        except Exception:
            pass
        _log("supervisor exit")
        sup_log.close()
    return 0


# ---------------------------------------------------------------------------
# Status (renders local state + cloud + Upstash)
# ---------------------------------------------------------------------------


def _query_cloud_heartbeat(env: dict) -> dict:
    import urllib.request
    import urllib.error

    cloud_url = (
        env.get("PHAROS_CLOUD_URL")
        or env.get("PHAROS_API_URL")
        or DEFAULT_CLOUD_URL
    ).rstrip("/")
    url = f"{cloud_url}/api/v1/ingestion/health/worker"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=6) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"_error": str(e)}


def _query_upstash_queues(env: dict) -> dict:
    import urllib.request
    import urllib.error

    base = env.get("UPSTASH_REDIS_REST_URL", "").rstrip("/")
    token = env.get("UPSTASH_REDIS_REST_TOKEN", "")
    if not base or not token:
        return {"_error": "Upstash env not set"}
    out = {}
    queues = ["ingest_queue", "pharos:tasks", "dlq:ingest", "ingest_dlq", "pharos:dlq"]
    for q in queues:
        try:
            req = urllib.request.Request(
                f"{base}/LLEN/{q}",
                headers={"Authorization": f"Bearer {token}"},
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                out[q] = json.loads(resp.read()).get("result", "?")
        except Exception as e:
            out[q] = f"err: {e}"
    return out


def _tail_log(path: Path, n: int = 6) -> list[str]:
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        return []
    # Decode best-effort and split.
    text = data.decode("utf-8", errors="replace")
    lines = text.splitlines()
    return lines[-n:]


def cmd_status(args: argparse.Namespace) -> int:
    from rich.console import Console
    from rich.table import Table
    from rich import box

    console = Console()
    state = _read_state()
    env = _read_env_file()

    sup_pid = _read_pid(SUPERVISOR_PID)
    wrk_pid = _read_pid(WORKER_PID)
    sup_alive = _pid_alive(sup_pid)
    wrk_alive = _pid_alive(wrk_pid)

    table = Table(title="Pharos Edge Worker", box=box.ROUNDED, show_header=False)
    table.add_column("k", style="bold cyan", no_wrap=True)
    table.add_column("v")

    def _dot(ok: bool, label_ok: str = "running", label_bad: str = "stopped") -> str:
        return f"[green]●[/green] {label_ok}" if ok else f"[red]○[/red] {label_bad}"

    table.add_row("Supervisor", f"{_dot(sup_alive)}  pid {sup_pid or '—'}")
    table.add_row("Worker process", f"{_dot(wrk_alive)}  pid {wrk_pid or '—'}")
    table.add_row("Mode", state.get("mode", "—"))
    table.add_row("Restarts (session)", str(state.get("restart_count", 0)))
    last_exit = state.get("last_exit_code")
    if last_exit is not None:
        table.add_row("Last exit code", f"[red]{last_exit}[/red]  at {state.get('last_crash_at')}")
    if state.get("status") == "backoff" and state.get("backoff_until"):
        table.add_row("Backoff until", f"[yellow]{state['backoff_until']}[/yellow]")
    if state.get("started_at"):
        table.add_row("Supervisor started", state["started_at"])

    # Cloud heartbeat
    hb = _query_cloud_heartbeat(env)
    if hb.get("_error"):
        table.add_section()
        table.add_row("Cloud heartbeat", f"[red]error[/red] {hb['_error']}")
    else:
        st = hb.get("state", "unknown")
        color = {"online": "green", "degraded": "yellow", "offline": "red"}.get(st, "white")
        age = hb.get("seconds_since_last_seen")
        age_s = f"{age:.1f}s ago" if isinstance(age, (int, float)) else "never"
        table.add_section()
        table.add_row("Cloud heartbeat", f"[{color}]{st}[/{color}]  ({age_s})")
        meta = hb.get("worker_meta") or {}
        if meta:
            table.add_row("Reported worker", f"{meta.get('worker_id', '?')}  v{meta.get('version', '?')}")
            table.add_row("Embedding model", str(meta.get("embedding_model") or "—"))

    # Upstash queues
    queues = _query_upstash_queues(env)
    if queues.get("_error"):
        table.add_section()
        table.add_row("Queues", f"[red]error[/red] {queues['_error']}")
    else:
        table.add_section()
        for q, v in queues.items():
            table.add_row(f"queue: {q}", str(v))

    console.print(table)

    # Recent log
    recent = _tail_log(LOG_FILE, n=8)
    if recent:
        console.print()
        console.rule("[bold]last 8 worker log lines[/bold]")
        for line in recent:
            console.print(f"  {line}", style="dim")

    return 0


# ---------------------------------------------------------------------------
# start / stop / restart / logs / run / doctor
# ---------------------------------------------------------------------------


def _spawn_detached_supervisor(mode: str) -> int:
    """Spawn `pharos_edge.py run` as a detached process and return its PID."""
    _ensure_dirs()
    cmd = [sys.executable, str(Path(__file__).resolve()), "run"]
    if mode == "wsl":
        cmd.append("--wsl")

    if IS_WINDOWS:
        DETACHED_PROCESS = 0x00000008
        CREATE_NEW_PROCESS_GROUP = 0x00000200
        CREATE_NO_WINDOW = 0x08000000
        CREATE_BREAKAWAY_FROM_JOB = 0x01000000
        flags = (
            DETACHED_PROCESS
            | CREATE_NEW_PROCESS_GROUP
            | CREATE_NO_WINDOW
            | CREATE_BREAKAWAY_FROM_JOB
        )
        out = open(LOG_DIR / "supervisor.out", "ab", buffering=0)
        try:
            proc = subprocess.Popen(
                cmd, cwd=str(BACKEND_DIR),
                stdout=out, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                creationflags=flags, close_fds=True,
            )
        except OSError:
            # Parent job forbids breakaway — retry without that flag.
            flags &= ~CREATE_BREAKAWAY_FROM_JOB
            proc = subprocess.Popen(
                cmd, cwd=str(BACKEND_DIR),
                stdout=out, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                creationflags=flags, close_fds=True,
            )
    else:
        out = open(LOG_DIR / "supervisor.out", "ab", buffering=0)
        proc = subprocess.Popen(
            cmd, cwd=str(BACKEND_DIR),
            stdout=out, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
            start_new_session=True, close_fds=True,
        )
    return proc.pid


def cmd_start(args: argparse.Namespace) -> int:
    existing = _read_pid(SUPERVISOR_PID)
    if existing and _pid_alive(existing):
        _print_warn(f"supervisor already running (pid {existing}). Use restart instead.")
        return 0
    mode = "wsl" if args.wsl else ("native-windows" if IS_WINDOWS else "native")
    pid = _spawn_detached_supervisor(mode)
    _print_ok(f"supervisor launched, pid {pid}, mode={mode}")
    _print_ok(f"logs:   {LOG_FILE}")
    _print_ok(f"status: python pharos_edge.py status")
    return 0


def cmd_stop(args: argparse.Namespace) -> int:
    pid = _read_pid(SUPERVISOR_PID)
    if not pid:
        _print_warn("no supervisor.pid found — nothing to stop")
        return 0
    if not _pid_alive(pid):
        _print_warn(f"supervisor pid {pid} not alive — cleaning up stale pidfile")
        SUPERVISOR_PID.unlink(missing_ok=True)
        WORKER_PID.unlink(missing_ok=True)
        return 0

    try:
        if IS_WINDOWS:
            os.kill(pid, signal.CTRL_BREAK_EVENT)
        else:
            os.kill(pid, signal.SIGTERM)
    except Exception as e:
        _print_err(f"failed to signal supervisor: {e}")
        return 1

    # Wait up to 20s for graceful exit.
    deadline = time.time() + 20
    while time.time() < deadline and _pid_alive(pid):
        time.sleep(0.5)
    if _pid_alive(pid):
        _print_warn("supervisor did not exit in 20s, killing")
        try:
            if IS_WINDOWS:
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], check=False)
            else:
                os.kill(pid, signal.SIGKILL)
        except Exception as e:
            _print_err(f"hard-kill failed: {e}")
            return 1
    _print_ok("supervisor stopped")
    return 0


def cmd_restart(args: argparse.Namespace) -> int:
    cmd_stop(args)
    time.sleep(1.0)
    return cmd_start(args)


def cmd_run(args: argparse.Namespace) -> int:
    """Foreground supervisor. Used both manually and by `start` (detached)."""
    mode = "wsl" if args.wsl else ("native-windows" if IS_WINDOWS else "native")
    return _supervise(mode)


def cmd_logs(args: argparse.Namespace) -> int:
    if not LOG_FILE.exists():
        _print_warn(f"no log yet at {LOG_FILE}")
        return 0
    lines = _tail_log(LOG_FILE, n=args.lines)
    sys.stdout.write("\n".join(lines))
    sys.stdout.write("\n")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    from rich.console import Console
    console = Console()

    env = _read_env_file()

    def _check(label: str, ok: bool, detail: str = "") -> None:
        mark = "[green]✓[/green]" if ok else "[red]✗[/red]"
        console.print(f"  {mark} {label}{('  ' + detail) if detail else ''}")

    console.rule("Environment")
    for v in ("MODE", "DATABASE_URL", "UPSTASH_REDIS_REST_URL", "UPSTASH_REDIS_REST_TOKEN", "PHAROS_ADMIN_TOKEN"):
        _check(v, bool(env.get(v)))

    console.rule("Python deps")
    for mod, _ in [("torch", None), ("sentence_transformers", None), ("safetensors", None), ("rich", None), ("dotenv", None)]:
        try:
            __import__(mod)
            _check(mod, True)
        except Exception as e:
            _check(mod, False, f"({e.__class__.__name__})")

    console.rule("GPU")
    try:
        import torch
        if torch.cuda.is_available():
            name = torch.cuda.get_device_name(0)
            mem = torch.cuda.get_device_properties(0).total_memory / 1024 ** 3
            _check("CUDA", True, f"{name}, {mem:.1f} GB")
        else:
            _check("CUDA", False, "torch installed but no CUDA device")
    except Exception as e:
        _check("CUDA", False, str(e))

    console.rule("Network")
    hb = _query_cloud_heartbeat(env)
    if hb.get("_error"):
        _check("cloud /health/worker", False, hb["_error"])
    else:
        _check("cloud /health/worker", True, f"state={hb.get('state')}")
    queues = _query_upstash_queues(env)
    if queues.get("_error"):
        _check("upstash LLEN", False, queues["_error"])
    else:
        _check("upstash LLEN", True, f"ingest_queue={queues.get('ingest_queue')}")

    console.rule("WSL")
    wsl = shutil.which("wsl")
    if wsl:
        _check("wsl present", True, wsl)
    else:
        _check("wsl present", False, "install WSL to use --wsl mode")

    return 0


# ---------------------------------------------------------------------------
# CLI plumbing
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="pharos-edge", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("start", help="Launch a detached supervisor")
    s.add_argument("--wsl", action="store_true", help="Run worker under WSL")
    s.set_defaults(func=cmd_start)

    s = sub.add_parser("stop", help="Stop the supervisor (and worker)")
    s.set_defaults(func=cmd_stop)

    s = sub.add_parser("restart", help="Stop + start")
    s.add_argument("--wsl", action="store_true")
    s.set_defaults(func=cmd_restart)

    s = sub.add_parser("run", help="Run supervisor in the foreground")
    s.add_argument("--wsl", action="store_true")
    s.set_defaults(func=cmd_run)

    s = sub.add_parser("status", help="Show live status")
    s.set_defaults(func=cmd_status)

    s = sub.add_parser("logs", help="Print last N log lines")
    s.add_argument("-n", "--lines", type=int, default=50)
    s.set_defaults(func=cmd_logs)

    s = sub.add_parser("doctor", help="Validate env, deps, GPU, network")
    s.set_defaults(func=cmd_doctor)

    return p


def main(argv: Optional[list[str]] = None) -> int:
    _ensure_dirs()
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args) or 0


if __name__ == "__main__":
    raise SystemExit(main())
