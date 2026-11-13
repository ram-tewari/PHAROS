"""Phase 3 evaluation harness: a coding agent revises a real pull request before review (c-CRAB).

Implements docs/benchmarks/phase3-eval-protocol.md. For each instance of the locked split
(``benchmarks/datasets/ccrab_phase3.json``):

1. a working checkout at ``head_commit`` is made whose git history holds only that commit's ancestors;
2. each arm's PHAROS is prepared over its own scratch database (``pharos_bench*``): the index is
   built at ``base_commit``, memory is learned there from a clone that holds only ``base_commit``'s
   history, and the index is then moved to ``head_commit`` (memory stays as learned). The leakage
   check runs on the result;
3. the test agent (``claude -p``, same model, prompt, permissions and turn limit in every arm) gets
   the pull request's title and description and the protocol's instruction, once per arm. Arms
   differ only in the MCP tools they get, served by a local PHAROS server per arm;
4. the agent's final diff against ``head_commit`` is graded with every comment's test in the
   instance's Docker image, as c-CRAB grades (see ``ccrab.py``).

Every agent answer and every grade is checkpointed as it arrives; rerunning the same command resumes
without repeating a call. Infrastructure failures (Docker, network, MCP server, usage limit) are kept
apart from agent results, counted, and retried on resume. A usage limit pauses the run.

The test set is sealed: it runs only with ``--locked-run --sealed-out <path outside the repository>``,
first grades every instance's gold commits, prints progress counts only, and writes the report only
when the run is complete. Commands::

    python benchmarks/agent_eval.py gold --set dev --ccrab <c-CRAB clone> --out <file>
    python benchmarks/agent_eval.py run --set dev --arms P0,A,B-new --instances <id> ... \\
        --ccrab <c-CRAB clone> --out <file> --workdir <dir> --pg postgresql+psycopg2://postgres@127.0.0.1:55450 \\
        --embedder onnx=<model dir>
    python benchmarks/agent_eval.py report --out <file>

See docs/benchmarks/phase3-harness-notes.md.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import re
import secrets
import shutil
import signal
import socket
import statistics
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "benchmarks"))

import ccrab  # noqa: E402
from phase2_eval import Checkpoint  # noqa: E402
from retrieval_eval import paired_delta  # noqa: E402

from app.learning.llm import find_claude  # noqa: E402

LOCK = BACKEND / "benchmarks" / "datasets" / "ccrab_phase3.json"
WORKER = BACKEND / "benchmarks" / "agent_eval_worker.py"

# The protocol's fixed instruction, the same in every arm.
INSTRUCTION = ("You wrote this change and are about to ask the maintainers of this repository to review it. "
               "Revise it so that they would accept it. Do not weaken or delete existing tests.")
MODEL = "claude-sonnet-5-5"
MAX_TURNS = 60
AGENT_TIMEOUT = 2400  # seconds of wall time for one agent run
INFRA_ATTEMPTS = 3  # infrastructure failures of one run before the run stops trying it

# The test agent's own tools: file read, search and edit. No shell, no web.
AGENT_TOOLS = ("Read", "Glob", "Grep", "Edit", "Write")
ALWAYS_DENIED = ("Bash", "WebFetch", "WebSearch")

# ── The arms (later stages edit these tables) ──────────────────────────
#
# A *serving* is one PHAROS: a code version and how its memory is learned (None: nothing is learned,
# so memory is off). Each serving gets its own database per instance and its own local server.
# An arm is a serving plus the MCP tools the agent may use from it.

CODE = {"current": None, "phase2-baseline": "phase2-baseline"}  # name -> git tag (None: this checkout)
SERVINGS = {
    "retrieval": {"code": "current", "learn": None},
    "phase2": {"code": "phase2-baseline", "learn": {"tier": "deterministic", "reviews": False}},
    "phase3": {"code": "current", "learn": {"tier": "deterministic", "reviews": False}},
}
RETRIEVAL_TOOLS = ("retrieve_context", "search_code", "find_symbol")
PHASE2_MEMORY_TOOLS = ("get_repo_brief", "search_memory", "list_skills", "get_skill")
ARMS = {
    "P0": {"serving": None, "mcp_tools": ()},
    "A": {"serving": "retrieval", "mcp_tools": RETRIEVAL_TOOLS},
    "B-old": {"serving": "phase2", "mcp_tools": RETRIEVAL_TOOLS + PHASE2_MEMORY_TOOLS},
    # Until Phase 3 memory exists, B-new is the current memory, so the pipeline can be tested.
    "B-new": {"serving": "phase3", "mcp_tools": RETRIEVAL_TOOLS + PHASE2_MEMORY_TOOLS},
}
PAIRS = (("B-new", "A"), ("B-new", "P0"), ("B-new", "B-old"), ("A", "P0"))

USAGE_LIMIT_RE = re.compile(r"usage limit|limit reached|hit your (usage )?limit|out of (extra )?usage|"
                            r"weekly limit|5-hour limit|resets at", re.I)
INFRA_RE = re.compile(r"rate.?limit|overloaded|api error|internal server error|connection (error|refused|reset)|"
                      r"timed? ?out|authenticat|not logged in|please run /login|credit balance|ECONN|socket", re.I)


class HarnessError(RuntimeError):
    """The harness itself is wrong (for example, the agent got a tool it must not have): stop."""


class PauseRun(RuntimeError):
    """A usage limit: stop now and resume later from the checkpoint."""


# ── checkpoint ──────────────────────────────────────────────────────────


class SafeCheckpoint(Checkpoint):
    """``phase2_eval.Checkpoint`` with atomic writes and a lock, so a crash never leaves half a file."""

    def __init__(self, path: Path) -> None:
        super().__init__(path)
        self._lock = threading.Lock()

    def put(self, value, *keys) -> None:
        with self._lock:
            node = self.data
            for k in keys[:-1]:
                node = node.setdefault(k, {})
            node[keys[-1]] = value
            tmp = self.path.with_name(self.path.name + ".tmp")
            tmp.write_text(json.dumps(self.data, indent=1))
            os.replace(tmp, self.path)

    def append(self, value, *keys) -> None:
        current = list(self.get(*keys) or [])
        self.put([*current, value], *keys)


# ── git: checkouts whose history ends at a commit ──────────────────────


def git(path: Path, *args: str, timeout: float = 1800, check: bool = True) -> str:
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    result = subprocess.run(["git", "-C", str(path), *args], capture_output=True, text=True, errors="replace",
                            timeout=timeout, env=env, check=False)
    if check and result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args[:3])} failed: {result.stderr.strip()[-400:]}")
    return result.stdout


def has_object(repo: Path, sha: str) -> bool:
    return subprocess.run(["git", "-C", str(repo), "cat-file", "-e", sha], capture_output=True,
                          check=False).returncode == 0


def has_ancestor(repo: Path, ancestor: str, commit: str) -> bool:
    return subprocess.run(["git", "-C", str(repo), "merge-base", "--is-ancestor", ancestor, commit],
                          capture_output=True, check=False).returncode == 0


def ensure_commit(mirror: Path, sha: str, pull_number: int | None = None) -> None:
    """Make ``sha`` present in the mirror: pull-request heads often live only under ``refs/pull``."""
    if has_object(mirror, f"{sha}^{{commit}}"):
        return
    attempts = [["fetch", "-q", "origin", sha]]
    if pull_number:
        attempts.append(["fetch", "-q", "origin", f"+refs/pull/{pull_number}/head:refs/pharos/pull/{pull_number}"])
    for args in attempts:
        git(mirror, *args, check=False)
        if has_object(mirror, f"{sha}^{{commit}}"):
            git(mirror, "update-ref", f"refs/pharos/keep/{sha}", sha)
            return
    raise ccrab.InfraError(f"commit {sha[:12]} is not in the mirror and could not be fetched")


def ensure_mirror(url: str, root: Path, commits: list[tuple[str, int | None]]) -> Path:
    """The full mirror of ``url`` (``app.learning.history``'s layout), holding every one of ``commits``.

    A pull request's commits, and sometimes its base, are not on any branch: they are fetched by SHA
    or from ``refs/pull/<n>/head`` and pinned under ``refs/pharos/``.
    """
    from app.learning.history import mirror_name

    path = root / mirror_name(url)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(["git", "clone", "-q", "--no-checkout", url, str(path)], capture_output=True,
                                text=True, timeout=3600, check=False, env=dict(os.environ, GIT_TERMINAL_PROMPT="0"))
        if result.returncode != 0:
            shutil.rmtree(path, ignore_errors=True)
            raise ccrab.InfraError(f"git clone {url} failed: {result.stderr[-300:]}")
    for sha, pull in commits:
        ensure_commit(path, sha, pull)
    return path


def truncated_clone(source: Path, commit: str, dest: Path, branch: str = "main") -> None:
    """A new repository at ``dest`` holding ``commit`` and its ancestors only, checked out at ``commit``.

    The objects are fetched by SHA from ``source`` into a fresh object store (no alternates, no
    tags, no remote), so nothing later than ``commit`` exists in it.
    """
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    git(dest, "init", "-q", "-b", branch)
    git(dest, "fetch", "-q", "--no-tags", "--upload-pack",
        "git -c uploadpack.allowAnySHA1InWant=true upload-pack", str(source), commit)
    git(dest, "update-ref", f"refs/heads/{branch}", commit)
    git(dest, "checkout", "-q", "--force", branch)
    (dest / ".git" / "FETCH_HEAD").unlink(missing_ok=True)
    git(dest, "reflog", "expire", "--expire=now", "--all")


def check_history(clone: Path, commit: str, later: list[str]) -> dict:
    """Assert the clone's history ends at ``commit``: every ref is at it and ``later`` commits are absent."""
    refs = [line.split() for line in git(clone, "for-each-ref", "--format=%(objectname) %(refname)").splitlines()]
    bad_refs = [name for sha, name in refs if sha != commit]
    head = git(clone, "rev-parse", "HEAD").strip()
    present = [sha for sha in later if has_object(clone, sha)]
    reachable = int(git(clone, "rev-list", "--all", "--count").strip())
    ancestors = int(git(clone, "rev-list", "--count", commit).strip())
    ok = not bad_refs and head == commit and not present and reachable == ancestors
    result = {"ok": ok, "head": head == commit, "refs": len(refs), "bad_refs": bad_refs,
              "later_present": len(present), "commits": reachable}
    if not ok:
        raise HarnessError(f"history of {clone} does not end at {commit[:12]}: {result}")
    return result


def capture_diff(checkout: Path, head: str) -> dict:
    """The agent's change against ``head`` (new files included), with its size in changed lines."""
    git(checkout, "add", "-A")
    patch = git(checkout, "diff", "--cached", "--binary", head)
    added = deleted = 0
    files = []
    for line in git(checkout, "diff", "--cached", "--numstat", head).splitlines():
        a, d, path = line.split("\t", 2)
        added += int(a) if a.isdigit() else 0
        deleted += int(d) if d.isdigit() else 0
        files.append(path)
    return {"patch": patch, "changed_lines": added + deleted, "added": added, "deleted": deleted,
            "files": files, "patch_sha256": hashlib.sha256(patch.encode()).hexdigest()}


# ── PHAROS code checkouts, databases and servers ────────────────────────


def code_dir(name: str, workdir: Path, overrides: dict[str, str]) -> Path:
    """The PHAROS code an arm is served from: this checkout, a git tag exported once, or an override."""
    if name in overrides:
        return Path(overrides[name]).resolve()
    tag = CODE[name]
    if tag is None:
        return REPO_ROOT
    dest = workdir / "pharos-code" / name
    if not (dest / "backend" / "app").is_dir():
        dest.mkdir(parents=True, exist_ok=True)
        archive = subprocess.run(["git", "-C", str(REPO_ROOT), "archive", "--format=tar", tag, "backend"],
                                 capture_output=True, check=True).stdout
        subprocess.run(["tar", "-x", "-C", str(dest)], input=archive, check=True)
        (dest / "PHAROS_CODE").write_text(git(REPO_ROOT, "rev-parse", f"{tag}^{{commit}}").strip() + "\n")
    return dest


def code_key(name: str, path: Path) -> str:
    """Identity of the code that builds an index: servings with equal keys share one base index."""
    parts = ("backend/app/codeintel", "backend/alembic", "backend/app/database")
    tag = CODE.get(name)
    if path == REPO_ROOT or tag is not None:
        rev = "HEAD" if path == REPO_ROOT else tag
        trees = [git(REPO_ROOT, "rev-parse", f"{rev}:{p}").strip() for p in parts]
        dirty = git(REPO_ROOT, "diff", "HEAD", "--", *parts) if path == REPO_ROOT else ""
        if dirty:
            trees.append(dirty)
        return hashlib.sha1("\n".join(trees).encode()).hexdigest()[:10]
    return hashlib.sha1(str(path).encode()).hexdigest()[:10]


def db_name(instance_id: str, suffix: str) -> str:
    return f"pharos_bench_s1_{hashlib.sha1(instance_id.encode()).hexdigest()[:10]}_{suffix}".replace("-", "_")


class Postgres:
    """Creates and drops the scratch databases; refuses any name that is not ``pharos_bench*``."""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self._engine = None

    @property
    def engine(self):
        from sqlalchemy import create_engine

        if self._engine is None:
            self._engine = create_engine(f"{self.base_url}/postgres", isolation_level="AUTOCOMMIT")
        return self._engine

    def url(self, name: str) -> str:
        return f"{self.base_url}/{name}"

    @staticmethod
    def _check(name: str) -> None:
        if not re.fullmatch(r"pharos_bench[a-z0-9_]*", name):
            raise HarnessError(f"refusing database {name!r}: scratch databases are named pharos_bench*")

    def exists(self, name: str) -> bool:
        from sqlalchemy import text

        with self.engine.connect() as conn:
            return conn.execute(text("select 1 from pg_database where datname = :n"), {"n": name}).first() is not None

    def create(self, name: str, template: str | None = None) -> None:
        from sqlalchemy import create_engine, text

        self._check(name)
        self.drop(name)
        with self.engine.connect() as conn:
            conn.execute(text(f'create database "{name}"' + (f' template "{template}"' if template else "")))
        if template is None:
            engine = create_engine(self.url(name))
            with engine.begin() as conn:
                conn.execute(text("create extension if not exists vector"))
            engine.dispose()

    def retarget(self, name: str, path: Path) -> None:
        """Point a copied database's only repository at another local checkout of the same repository."""
        from sqlalchemy import create_engine, text

        self._check(name)
        engine = create_engine(self.url(name))
        with engine.begin() as conn:
            if conn.execute(text("select count(*) from repositories")).scalar_one() != 1:
                raise HarnessError(f"{name} does not hold exactly one repository")
            conn.execute(text("update repositories set url = :u, local_path = :p"),
                         {"u": path.resolve().as_uri(), "p": str(path.resolve())})
        engine.dispose()

    def drop(self, name: str) -> None:
        from sqlalchemy import text

        self._check(name)
        with self.engine.connect() as conn:
            conn.execute(text(f'drop database if exists "{name}" with (force)'))


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def pharos_env(code: Path, database_url: str, embedder: str, tokens: dict[str, str]) -> dict[str, str]:
    """A clean environment for PHAROS code: nothing from the caller's settings leaks in."""
    env = {k: os.environ[k] for k in ("PATH", "HOME", "TMPDIR", "LANG", "LC_ALL", "USER") if k in os.environ}
    env |= {"PYTHONPATH": str(code / "backend"), "DATABASE_URL": database_url, "ENV": "dev", "MODE": "CLOUD",
            "PHAROS_READ_TOKEN": tokens["read"], "PHAROS_ADMIN_TOKEN": tokens["admin"],
            "PYTHONDONTWRITEBYTECODE": "1"}
    if embedder == "hash":
        env["EMBEDDING_BACKEND"] = "hash"
    elif embedder.startswith("onnx="):
        env |= {"EMBEDDING_BACKEND": "onnx", "EMBEDDING_ONNX_DIR": str(Path(embedder[5:]).expanduser().resolve())}
    else:
        raise SystemExit(f"unknown embedder {embedder!r} (use 'hash' or 'onnx=<dir>')")
    return env


def run_worker(code: Path, env: dict[str, str], *args: str, timeout: float = 4 * 3600) -> dict:
    result = subprocess.run([sys.executable, str(WORKER), *args], cwd=code / "backend", env=env, capture_output=True,
                            text=True, timeout=timeout, check=False)
    if result.returncode != 0:
        raise ccrab.InfraError(f"worker {args[0]} failed: {result.stderr.strip()[-800:]}")
    return json.loads(result.stdout.strip().splitlines()[-1])


class Server:
    """A local PHAROS API (with its MCP endpoint at ``/mcp/``) from one code checkout over one database."""

    def __init__(self, code: Path, env: dict[str, str], log: Path):
        self.code, self.env, self.log = code, env, log
        self.port = free_port()
        self.url = f"http://127.0.0.1:{self.port}"
        self.process: subprocess.Popen | None = None

    def __enter__(self) -> Server:
        self.log.parent.mkdir(parents=True, exist_ok=True)
        handle = open(self.log, "ab")
        self.process = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
                                         "--port", str(self.port), "--log-level", "warning"],
                                        cwd=self.code / "backend", env=self.env, stdout=handle, stderr=handle,
                                        start_new_session=True)
        handle.close()
        deadline = time.monotonic() + 240
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise ccrab.InfraError(f"PHAROS server exited ({self.process.returncode}); see {self.log}")
            try:
                with urllib.request.urlopen(f"{self.url}/health", timeout=5) as response:  # noqa: S310 - localhost
                    if response.status == 200:
                        return self
            except (urllib.error.URLError, OSError):
                pass
            time.sleep(1)
        self.__exit__()
        raise ccrab.InfraError("PHAROS server did not become healthy")

    def __exit__(self, *exc) -> None:
        if self.process and self.process.poll() is None:
            with contextlib.suppress(OSError):
                os.killpg(self.process.pid, signal.SIGTERM)
            try:
                self.process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                with contextlib.suppress(OSError):
                    os.killpg(self.process.pid, signal.SIGKILL)

    def mcp(self, method: str, params: dict | None = None) -> dict:
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}).encode()
        request = urllib.request.Request(f"{self.url}/mcp/", data=body, method="POST", headers={
            "Content-Type": "application/json", "Accept": "application/json, text/event-stream",
            "Authorization": f"Bearer {self.env['PHAROS_READ_TOKEN']}"})
        with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310 - localhost
            return json.loads(response.read().decode())

    def tools(self) -> list[str]:
        self.mcp("initialize", {"protocolVersion": "2025-03-26", "capabilities": {},
                                "clientInfo": {"name": "pharos-agent-eval", "version": "1"}})
        return sorted(t["name"] for t in self.mcp("tools/list")["result"]["tools"])

    def mcp_config(self) -> dict:
        return {"mcpServers": {"pharos": {"type": "http", "url": f"{self.url}/mcp/",
                                          "headers": {"Authorization": f"Bearer {self.env['PHAROS_READ_TOKEN']}"}}}}


# ── the test agent ──────────────────────────────────────────────────────


def agent_prompt(inst: ccrab.Instance, pr_diff: str | None = None) -> str:
    """The pull request's title and description, then the protocol's instruction (identical in every arm)."""
    parts = [f"Repository: {inst.repo}", f"Pull request title: {inst.title.strip()}",
             "Pull request description:\n" + (inst.body.strip() or "(none)")]
    if pr_diff is not None:
        parts.append("The pull request's change (git diff of the base commit against the current commit):\n"
                     f"```diff\n{pr_diff}\n```")
    parts.append(INSTRUCTION)
    return "\n\n".join(parts)


def disallowed_tools(arm: str, server_tools: list[str]) -> list[str]:
    """Built-in tools no arm may use, and every PHAROS tool this arm does not get."""
    allowed = set(ARMS[arm]["mcp_tools"])
    return list(ALWAYS_DENIED) + [f"mcp__pharos__{t}" for t in server_tools if t not in allowed]


def expected_tools(arm: str) -> list[str]:
    return sorted(list(AGENT_TOOLS) + [f"mcp__pharos__{t}" for t in ARMS[arm]["mcp_tools"]])


def agent_argv(claude: str, arm: str, mcp_config: Path, server_tools: list[str], *, model: str = MODEL,
               max_turns: int = MAX_TURNS) -> list[str]:
    """``claude -p`` for one arm. Everything but the MCP tool lists is the same in every arm.

    ``--restricted`` drops every built-in tool that runs commands or code and WebFetch, confines file
    tools to the working directory and ignores user and project settings; ``--tools`` keeps only
    file read, search and edit; ``--strict-mcp-config`` loads only PHAROS (or nothing, in P0);
    ``--permission-mode dontAsk`` with ``--allowedTools`` approves exactly these tools and denies
    anything else without asking.
    """
    allowed = list(AGENT_TOOLS) + [f"mcp__pharos__{t}" for t in ARMS[arm]["mcp_tools"]]
    return [claude, "-p", "--output-format", "stream-json", "--verbose", "--model", model,
            "--max-turns", str(max_turns), "--restricted", "--tools", ",".join(AGENT_TOOLS),
            "--strict-mcp-config", "--mcp-config", str(mcp_config), "--permission-mode", "dontAsk",
            "--allowedTools", ",".join(allowed), "--disallowedTools", ",".join(disallowed_tools(arm, server_tools)),
            "--no-session-persistence", "--disable-slash-commands"]


def parse_stream(lines: list[str]) -> dict:
    """The parts of a ``stream-json`` transcript the harness records."""
    out: dict = {"init": None, "result": None, "tool_calls": Counter(), "retries": 0}
    for line in lines:
        try:
            event = json.loads(line)
        except ValueError:
            continue
        kind, sub = event.get("type"), event.get("subtype")
        if kind == "system" and sub == "init":
            out["init"] = {"tools": sorted(event.get("tools") or []), "model": event.get("model"),
                           "mcp_servers": event.get("mcp_servers") or [],
                           "claude_code_version": event.get("claude_code_version")}
        elif kind == "system" and sub == "api_retry":
            out["retries"] += 1
        elif kind == "assistant":
            for block in (event.get("message") or {}).get("content") or []:
                if block.get("type") == "tool_use":
                    out["tool_calls"][block.get("name", "?")] += 1
        elif kind == "result":
            out["result"] = event
    out["tool_calls"] = dict(out["tool_calls"])
    return out


def classify(parsed: dict, returncode: int | None, stderr: str, arm: str, *, timed_out: bool = False) -> dict:
    """Agent result or infrastructure failure? Raises HarnessError when the agent got the wrong tools."""
    init, result = parsed["init"], parsed["result"]
    if init is not None and init["tools"] != expected_tools(arm):
        raise HarnessError(f"arm {arm} got tools {init['tools']}, expected {expected_tools(arm)}")
    text = " ".join([stderr or "", (result or {}).get("result") or "" if result and result.get("is_error") else ""])
    if USAGE_LIMIT_RE.search(text):
        return {"status": "infra", "reason": "usage limit", "pause": True}
    if timed_out:
        return {"status": "infra", "reason": "agent timed out", "pause": False}
    if init is not None and ARMS[arm]["serving"]:
        status = {s.get("name"): s.get("status") for s in init["mcp_servers"]}
        if status.get("pharos") != "connected":
            return {"status": "infra", "reason": f"PHAROS MCP server {status.get('pharos')}", "pause": False}
    if result is None:
        return {"status": "infra", "reason": f"no result (exit {returncode}): {(stderr or '')[-200:]}", "pause": False}
    sub = result.get("subtype")
    if sub == "error_max_turns":
        return {"status": "ok", "reason": "max turns", "pause": False}
    if sub != "success" or result.get("is_error"):
        reason = f"{sub}: {(result.get('result') or '')[-200:]}"
        return {"status": "infra", "reason": reason, "pause": bool(USAGE_LIMIT_RE.search(reason))}
    return {"status": "ok", "reason": "completed", "pause": False}


def usage_of(result: dict | None) -> dict:
    usage = (result or {}).get("usage") or {}
    keys = ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
    out = {k: int(usage.get(k) or 0) for k in keys}
    out["total_tokens"] = sum(out.values())
    out["cost_usd"] = round(float((result or {}).get("total_cost_usd") or 0), 4)
    out["num_turns"] = int((result or {}).get("num_turns") or 0)
    out["duration_ms"] = int((result or {}).get("duration_ms") or 0)
    return out


def run_agent(claude: str, arm: str, inst: ccrab.Instance, checkout: Path, server: Server | None,
              transcript: Path, *, model: str, max_turns: int, pr_diff: str | None) -> dict:
    """One ``claude -p`` run in ``checkout``. Returns the classified outcome with usage and timings."""
    transcript.parent.mkdir(parents=True, exist_ok=True)
    config = transcript.with_suffix(".mcp.json")
    config.write_text(json.dumps(server.mcp_config() if server else {"mcpServers": {}}))
    config.chmod(0o600)
    server_tools = server.tools() if server else []
    missing = set(ARMS[arm]["mcp_tools"]) - set(server_tools)
    if missing:
        raise HarnessError(f"arm {arm}: the PHAROS server lacks {sorted(missing)}")
    argv = agent_argv(claude, arm, config, server_tools, model=model, max_turns=max_turns)
    env = {k: v for k, v in os.environ.items() if not k.startswith(("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"))}
    env["MCP_TIMEOUT"] = "60000"
    t0 = time.monotonic()
    timed_out = False
    with open(transcript, "w") as out, open(transcript.with_suffix(".stderr"), "w") as err:
        process = subprocess.Popen(argv, cwd=checkout, stdin=subprocess.PIPE, stdout=out, stderr=err, text=True,
                                   env=env, start_new_session=True)
        try:
            process.communicate(agent_prompt(inst, pr_diff), timeout=AGENT_TIMEOUT)
        except subprocess.TimeoutExpired:
            timed_out = True
            with contextlib.suppress(OSError):
                os.killpg(process.pid, signal.SIGINT)
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                with contextlib.suppress(OSError):
                    os.killpg(process.pid, signal.SIGKILL)
                process.wait()
    wall = time.monotonic() - t0
    config.unlink(missing_ok=True)
    parsed = parse_stream(transcript.read_text(errors="replace").splitlines())
    stderr = transcript.with_suffix(".stderr").read_text(errors="replace")
    outcome = classify(parsed, process.returncode, stderr, arm, timed_out=timed_out)
    return outcome | {"wall_s": round(wall, 1), "usage": usage_of(parsed["result"]),
                      "tool_calls": parsed["tool_calls"], "api_retries": parsed["retries"],
                      "init": parsed["init"], "result_subtype": (parsed["result"] or {}).get("subtype"),
                      "server_tools": server_tools}


# ── leakage ─────────────────────────────────────────────────────────────


def allowed_review(comment: dict, created_at: str, pull_number: int) -> bool:
    """A review comment the learner may read: created before the PR, and not on that PR."""
    return (comment.get("created_at") or "9999") < created_at and int(comment.get("pr") or 0) != pull_number


def seed_reviews(comments: list[dict], created_at: str, pull_number: int) -> list[dict]:
    return [c for c in comments if allowed_review(c, created_at, pull_number)]


def _shas(node) -> set[str]:
    found: set[str] = set()
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "sha" and isinstance(value, str) and re.fullmatch(r"[0-9a-f]{7,40}", value):
                found.add(value)
            else:
                found |= _shas(value)
    elif isinstance(node, list):
        for value in node:
            found |= _shas(value)
    return found


def leakage_check(inst: ccrab.Instance, evidence: list, briefs: list[str], cache_dir: Path,
                  is_ancestor) -> dict:
    """The protocol's automatic check for one learned memory.

    - memory was learned at ``base_commit`` (every brief is for it);
    - every review comment the learner could read (its cache, inspected after learning, so a
      network fetch would show) was created before the pull request and is not on it;
    - every review the memory cites is one of those, and is not on the pull request;
    - every commit the memory cites is an ancestor of ``base_commit``.
    """
    violations = []
    readable = []
    for path in sorted(cache_dir.rglob("review_comments.json")) if cache_dir.exists() else []:
        readable += json.loads(path.read_text())
    for c in readable:
        if not allowed_review(c, inst.created_at, inst.pull_number):
            violations.append(f"readable review {c.get('url') or c.get('id')} ({c.get('created_at')}, PR {c.get('pr')})")
    known = {c.get("url"): c for c in readable}
    reviews = [e for item in evidence for e in (item or []) if isinstance(e, dict) and e.get("kind") == "review"]
    for e in reviews:
        if int(e.get("pr") or 0) == inst.pull_number:
            violations.append(f"memory cites a review on this PR: {e.get('url')}")
        elif e.get("url") not in known:
            violations.append(f"memory cites a review the learner was not given: {e.get('url')}")
    shas = set().union(*(_shas(item) for item in evidence)) if evidence else set()
    later = sorted(s for s in shas if not is_ancestor(s))
    violations += [f"memory cites commit {s[:12]}, not an ancestor of base_commit" for s in later[:20]]
    wrong_briefs = [b for b in briefs if b != inst.base_commit]
    violations += [f"brief learned at {b[:12]}, not base_commit" for b in wrong_briefs]
    return {"passed": not violations and bool(briefs), "readable_reviews": len(readable),
            "cited_reviews": len(reviews), "cited_commits": len(shas), "briefs": len(briefs),
            "violations": violations[:20], "violation_count": len(violations)}


def memory_evidence(database_url: str, repository_path: Path) -> tuple[list, list[str]]:
    """Every memory item's evidence and every brief's commit, read straight from an arm's database."""
    from sqlalchemy import create_engine, text

    engine = create_engine(database_url)
    try:
        with engine.connect() as conn:
            repo = conn.execute(text("select id from repositories where url = :u"),
                                {"u": repository_path.resolve().as_uri()}).scalar_one()
            evidence = [row[0] for row in conn.execute(
                text("select evidence from memory_items where repository_id = :r"), {"r": repo})]
            briefs = [row[0] for row in conn.execute(
                text("select commit_sha from repo_briefs where repository_id = :r"), {"r": repo})]
    finally:
        engine.dispose()
    return [e if isinstance(e, list) else json.loads(e or "[]") for e in evidence], briefs


# ── report ──────────────────────────────────────────────────────────────


def resolved_share(grade: dict, n_tests: int) -> float:
    passed = sum(1 for t in (grade.get("tests") or {}).values() if t.get("passed"))
    return passed / n_tests if n_tests else 0.0


def _stats(values: list[float]) -> dict:
    if not values:
        return {"n": 0}
    return {"n": len(values), "mean": round(statistics.fmean(values), 2), "median": round(statistics.median(values), 2),
            "total": round(sum(values), 2)}


def report(data: dict, meta: dict[str, dict], arms: list[str]) -> dict:
    """The protocol's measures 1, 4 to 8 from the checkpoint (2 and 3 come from the precision backtest).

    ``meta`` maps instance id to ``{"repo", "tests"}`` for every instance of the set.
    """
    inst_data = data.get("instances") or {}
    graded = {a: {i: inst_data[i]["grade"][a] for i in meta if (inst_data.get(i, {}).get("grade") or {}).get(a)}
              for a in arms}
    share = {a: {i: resolved_share(g, meta[i]["tests"]) for i, g in graded[a].items()} for a in arms}
    out: dict = {"instances": len(meta), "arms": {}, "differences": {}}
    for a in arms:
        vals = list(share[a].values())
        comments = sum(meta[i]["tests"] for i in share[a])
        resolved = sum(sum(1 for t in (graded[a][i].get("tests") or {}).values() if t.get("passed")) for i in share[a])
        agents = {i: inst_data[i]["agent"][a] for i in graded[a]}
        out["arms"][a] = {
            "scored": len(vals), "resolved_share": round(statistics.fmean(vals), 4) if vals else None,
            "comments_resolved": resolved, "comments": comments,
            "no_change": sum(1 for i in graded[a] if graded[a][i].get("no_change")),
            "changed_lines": _stats([agents[i]["changed_lines"] for i in agents]),
            "tokens": _stats([agents[i]["usage"]["total_tokens"] for i in agents]),
            "output_tokens": _stats([agents[i]["usage"]["output_tokens"] for i in agents]),
            "turns": _stats([agents[i]["usage"]["num_turns"] for i in agents]),
            "wall_s": _stats([agents[i]["wall_s"] for i in agents]),
            "cost_usd": _stats([agents[i]["usage"]["cost_usd"] for i in agents]),
            "max_turns_hit": sum(1 for i in agents if agents[i].get("reason") == "max turns"),
            "pharos_tool_calls": sum(n for i in agents for t, n in (agents[i].get("tool_calls") or {}).items()
                                     if t.startswith("mcp__pharos__")),
            "infra_failures": sum(len((inst_data.get(i, {}).get("infra") or {}).get(a) or []) for i in meta),
        }
    for x, y in PAIRS:
        if x not in arms or y not in arms:
            continue
        both = [i for i in meta if i in share[x] and i in share[y]]
        if both:
            out["differences"][f"{x} - {y}"] = paired_delta([share[x][i] for i in both],
                                                            [share[y][i] for i in both]) | {"n": len(both)}
    if "B-new" in arms and "A" in arms:
        both = [i for i in meta if i in share["B-new"] and i in share["A"]]
        complete = len(both) == len(meta)
        primary = out["differences"].get("B-new - A")
        loro = {}
        for repo in sorted({meta[i]["repo"] for i in both}):
            rest = [i for i in both if meta[i]["repo"] != repo]
            if rest:
                loro[repo] = paired_delta([share["B-new"][i] for i in rest], [share["A"][i] for i in rest])["delta"]
        lines = {a: [inst_data[i]["agent"][a]["changed_lines"] for i in both] for a in ("A", "B-new")}
        med = {a: statistics.median(v) if v else None for a, v in lines.items()}
        guard = med["A"] is not None and med["B-new"] <= 2 * med["A"]
        out["measure_1"] = {"complete": complete, "difference": primary,
                            "passes": bool(complete and primary and primary["ci95"][0] > 0)}
        out["measure_4_guard"] = {"median_changed_lines": med, "passes": bool(guard)}
        out["measure_8_leave_one_repository_out"] = {
            "by_repository_removed": loro, "range": [min(loro.values()), max(loro.values())] if loro else None}
        out["verdict"] = ("no verdict: the run is incomplete" if not complete else
                          "measures 1 and 4 pass (2 and 3 are measured separately)"
                          if out["measure_1"]["passes"] and guard else "fails")
    gold = {i: (inst_data.get(i) or {}).get("gold") for i in meta}
    gold = {i: g for i, g in gold.items() if g and "reproduced" in g}
    if gold:
        repro = sorted(i for i, g in gold.items() if g["reproduced"])
        out["gold"] = {"checked": len(gold), "reproduced": len(repro),
                       "not_reproduced": sorted(set(gold) - set(repro))}
        if "B-new" in arms and "A" in arms:
            sub = [i for i in repro if i in share["B-new"] and i in share["A"]]
            if sub:
                out["differences"]["B-new - A (gold reproduces)"] = paired_delta(
                    [share["B-new"][i] for i in sub], [share["A"][i] for i in sub]) | {"n": len(sub)}
    used = {ARMS[a]["serving"] for a in arms if a in ARMS}
    leak = [(s, r) for i in meta for s, r in ((inst_data.get(i) or {}).get("leakage") or {}).items() if s in used]
    if leak:
        out["leakage_check"] = {"checked": len(leak), "passed": sum(1 for _, r in leak if r["passed"]),
                                "failed": sorted({s for s, r in leak if not r["passed"]})}
    prep = [(inst_data.get(i) or {}).get("prep") or {} for i in meta]
    out["preparation_s"] = {
        "index_base": _stats([v["seconds"] for p in prep for v in (p.get("base_index") or {}).values()]),
        "learn": _stats([v["learn"]["seconds"] for p in prep for v in (p.get("servings") or {}).values()
                         if v.get("learn")]),
        "reindex_head": _stats([v["reindex"]["seconds"] for p in prep for v in (p.get("servings") or {}).values()
                                if v.get("reindex")]),
    }
    return out


# ── commands ────────────────────────────────────────────────────────────


def _instances(args, lock: dict) -> list[ccrab.Instance]:
    ccrab.check_set_allowed(args.set, locked_run=getattr(args, "locked_run", False),
                            sealed_out=getattr(args, "sealed_out", None), repo_root=REPO_ROOT)
    if getattr(args, "locked_run", False) and (args.instances or args.repos or args.limit):
        raise ccrab.SealedSetError("the locked run covers the whole test set: no --instances, --repos or --limit")
    ccrab.verify_sources(lock, Path(args.ccrab))
    entries = ccrab.lock_entries(lock, args.set)
    ids = [e["instance_id"] for e in entries if (not args.repos or e["repo"] in args.repos)]
    if args.instances:
        ids = [i for i in ids if i in set(args.instances)]
        if len(ids) != len(set(args.instances)):
            raise ccrab.SealedSetError(f"some --instances are not in the {args.set} set")
    if args.limit:
        ids = ids[:args.limit]
    return ccrab.load_instances(lock, Path(args.ccrab), args.set, set(ids))


def _out_path(args) -> Path:
    if getattr(args, "locked_run", False):
        return Path(args.sealed_out).expanduser().resolve()
    if not args.out:
        raise SystemExit("--out is required")
    return Path(args.out).expanduser().resolve()


def _say(sealed: bool, message: str, counts: str) -> None:
    """Dev runs say what happened; the locked run prints progress counts only."""
    print(counts if sealed else message, flush=True)


def gold_one(inst: ccrab.Instance, ck: SafeCheckpoint, remove: bool) -> dict:
    """Grade ``head_commit`` unchanged (every test must fail) and ``merged_commit`` (every test must pass)."""
    done = ck.get("instances", inst.instance_id, "gold")
    if done and "reproduced" in done:
        return done
    try:
        pulled = ccrab.pull_image(inst.image)
        with ccrab.Container(inst.image) as box:
            t0 = time.monotonic()
            head = ccrab.grade(box, inst.head_commit, inst.tests)
            merged = ccrab.grade(box, inst.merged_commit, inst.tests)
        status = ccrab.gold_status(head, merged, inst.tests) | {
            "pull_s": round(pulled, 1), "grade_s": round(time.monotonic() - t0, 1),
            "head": head, "merged": merged}
    except ccrab.InfraError as exc:
        ck.append({"reason": str(exc)[:300], "at": time.strftime("%Y-%m-%dT%H:%M:%S")},
                  "instances", inst.instance_id, "infra", "gold")
        return {"infra": str(exc)[:300]}
    finally:
        if remove:
            ccrab.remove_image(inst.image)
    ck.put(status, "instances", inst.instance_id, "gold")
    return status


def cmd_gold(args) -> int:
    if args.set == "test":
        raise ccrab.SealedSetError("the gold check is not run on the test set: the locked run does it first")
    lock = ccrab.load_lock(LOCK)
    instances = _instances(args, lock)
    ck = SafeCheckpoint(_out_path(args))
    ck.put({"kind": "gold", "set": args.set, "lock_sha256": ccrab.LOCK_SHA256}, "run")
    keep = set(args.keep_images or [])

    def one(inst):
        status = gold_one(inst, ck, remove=args.remove_images and inst.repo not in keep)
        line = ("infra failure: " + status["infra"]) if "infra" in status else (
            f"{'reproduces' if status['reproduced'] else 'DOES NOT reproduce'}: "
            f"{status['fail_at_head']}/{status['tests']} fail at head, "
            f"{status['pass_at_merged']}/{status['tests']} pass at merged")
        print(f"{inst.instance_id}: {line}", flush=True)
        return status

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(one, instances))
    ok = [i.instance_id for i, r in zip(instances, results, strict=True) if r.get("reproduced")]
    bad = [i.instance_id for i, r in zip(instances, results, strict=True) if "reproduced" in r and not r["reproduced"]]
    infra = [i.instance_id for i, r in zip(instances, results, strict=True) if "infra" in r]
    summary = {"reproduced": len(ok), "total": len(instances), "not_reproduced": bad, "infra": infra}
    ck.put(summary, "summary")
    print(json.dumps(summary, indent=1))
    return 0 if not infra else 1


class Runner:
    """Prepares, runs and grades one set, resuming from the checkpoint."""

    def __init__(self, args, instances: list[ccrab.Instance], ck: SafeCheckpoint, sealed: bool):
        self.args, self.instances, self.ck, self.sealed = args, instances, ck, sealed
        self.arms = args.arms
        self.workdir = Path(args.workdir).expanduser().resolve()
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.transcripts = ck.path.with_name(ck.path.stem + ".transcripts")
        self.overrides = dict(kv.split("=", 1) for kv in args.code or [])
        self.pg = Postgres(args.pg)
        self.tokens = {"read": secrets.token_urlsafe(24), "admin": secrets.token_urlsafe(24)}
        self.claude = args.claude or find_claude()
        if not self.claude:
            raise SystemExit("claude CLI not found (set PHAROS_CLAUDE_PATH or --claude)")
        self.servings = sorted({ARMS[a]["serving"] for a in self.arms if ARMS[a]["serving"]})

    # paths
    def inst_dir(self, inst) -> Path:
        return self.workdir / "instances" / inst.slug

    def src(self, inst) -> Path:
        return self.inst_dir(inst) / "src" / inst.repo.split("/")[-1]

    def base_clone(self, inst) -> Path:
        return self.inst_dir(inst) / "base" / inst.repo.split("/")[-1]

    def say(self, message: str) -> None:
        done = sum(1 for i in self.instances for a in self.arms
                   if self.ck.get("instances", i.instance_id, "grade", a))
        _say(self.sealed, message, f"progress: {done}/{len(self.instances) * len(self.arms)} arm runs graded")

    # preparation
    def checkouts(self, inst) -> None:
        """The head clone (index and agent source) and the base clone (learning), each history-truncated."""
        key = ("instances", inst.instance_id, "prep", "history")
        if self.ck.get(*key) and self.src(inst).exists() and self.base_clone(inst).exists():
            return
        t0 = time.monotonic()
        mirror = ensure_mirror(inst.url, Path(self.args.mirrors).expanduser(),
                               [(inst.base_commit, inst.pull_number), (inst.head_commit, inst.pull_number)])
        truncated_clone(mirror, inst.head_commit, self.src(inst))
        # From the mirror: base_commit is not always an ancestor of head_commit (the PR's target branch
        # may have moved on after the PR branched off).
        truncated_clone(mirror, inst.base_commit, self.base_clone(inst))
        record = {"base_is_ancestor_of_head": has_ancestor(mirror, inst.base_commit, inst.head_commit),
                  "base_commit_date": git(mirror, "show", "-s", "--format=%cI", inst.base_commit).strip(),
                  "head_commit_date": git(mirror, "show", "-s", "--format=%cI", inst.head_commit).strip(),
                  "pr_created_at": inst.created_at,"head": check_history(self.src(inst), inst.head_commit, [inst.merged_commit]),
                  "base": check_history(self.base_clone(inst), inst.base_commit,
                                        [inst.head_commit, inst.merged_commit]),
                  "seconds": round(time.monotonic() - t0, 1)}
        self.ck.put(record, *key)

    def serving_db(self, inst, serving: str) -> str:
        """The serving's database for this instance: base index (shared by code), learn, reindex at head.

        The index at ``base_commit`` and learning use the base clone; the database's repository is then
        pointed at the head clone and indexed at ``head_commit`` (incrementally; memory stays).
        """
        spec = SERVINGS[serving]
        code = code_dir(spec["code"], self.workdir, self.overrides)
        ckey = code_key(spec["code"], code)
        template = db_name(inst.instance_id, f"t{ckey}")
        target = db_name(inst.instance_id, serving)
        prep = ("instances", inst.instance_id, "prep")
        if self.ck.get(*prep, "servings", serving, "done") and self.pg.exists(target):
            return self.pg.url(target)
        env = lambda url: pharos_env(code, url, self.args.embedder, self.tokens)  # noqa: E731
        if not (self.ck.get(*prep, "base_index", ckey) and self.pg.exists(template)):
            donor = self.index_donor(inst, ckey) if self.args.reuse_index else None
            self.pg.create(template, template=donor)
            if donor:  # another instance's index of this repository: point it here, then index incrementally
                self.pg.retarget(template, self.base_clone(inst))
            run_worker(code, env(self.pg.url(template)), "migrate")
            stats = run_worker(code, env(self.pg.url(template)), "index", str(self.base_clone(inst)),
                               inst.base_commit)
            stats["reused_from"] = donor
            self.ck.put(stats, *prep, "base_index", ckey)
            self.say(f"  indexed {inst.instance_id} at base_commit with {spec['code']} code"
                     f"{' (incrementally)' if donor else ''}: {stats.get('chunks_total')} chunks, "
                     f"{stats.get('files_indexed')} files embedded, {stats['seconds']} s")
        self.pg.create(target, template=template)
        url = self.pg.url(target)
        run_worker(code, env(url), "migrate")
        record: dict = {"code": spec["code"], "code_key": ckey, "learn": None}
        if spec["learn"]:
            cache = self.inst_dir(inst) / f"learn-cache-{serving}"
            shutil.rmtree(cache, ignore_errors=True)
            cache.mkdir(parents=True)
            if spec["learn"].get("reviews"):
                raise HarnessError("learning from review comments needs a review source (stage S3)")
            learn_env = env(url) | {
                "LEARNING_CACHE_DIR": str(cache), "LEARNING_MIRROR_DIR": str(cache / "git"),
                # No network while learning: what the learner reads is only what the harness gave it.
                "HTTPS_PROXY": "http://127.0.0.1:9", "HTTP_PROXY": "http://127.0.0.1:9",
                "https_proxy": "http://127.0.0.1:9", "http_proxy": "http://127.0.0.1:9",
                "GIT_ALLOW_PROTOCOL": "file",
                "PHAROS_EVAL_GITHUB_URL": inst.url, "PHAROS_EVAL_REVIEWS_BEFORE": inst.created_at,
                "PHAROS_EVAL_EXCLUDE_PR": str(inst.pull_number)}
            base = self.base_clone(inst)
            record["learn"] = run_worker(code, learn_env, "learn", str(base), str(base), str(base),
                                         inst.base_commit)
            evidence, briefs = memory_evidence(url, base)

            def is_ancestor(sha: str, base=base) -> bool:
                return subprocess.run(["git", "-C", str(base), "merge-base", "--is-ancestor", sha,
                                       inst.base_commit], capture_output=True, check=False).returncode == 0

            leak = leakage_check(inst, evidence, briefs, cache, is_ancestor)
            check_history(base, inst.base_commit, [inst.head_commit, inst.merged_commit])  # nothing was fetched
            self.ck.put(leak, "instances", inst.instance_id, "leakage", serving)
            if not leak["passed"]:
                raise HarnessError(f"leakage check failed for {inst.instance_id} ({serving})")
            record["memory_items"] = len(evidence)
        self.pg.retarget(target, self.src(inst))
        record["reindex"] = run_worker(code, env(url), "index", str(self.src(inst)), inst.head_commit)
        record["done"] = True
        self.ck.put(record, *prep, "servings", serving)
        return url

    def index_donor(self, inst, ckey: str) -> str | None:
        """A finished base index of the same repository by the same code, from an earlier instance.

        Re-indexing is incremental by blob SHA, so starting from it and indexing this instance's
        ``base_commit`` gives the same index as starting empty, while embedding only changed files.
        """
        for other in self.instances:
            if other.repo != inst.repo or other.instance_id == inst.instance_id:
                continue
            name = db_name(other.instance_id, f"t{ckey}")
            if self.ck.get("instances", other.instance_id, "prep", "base_index", ckey) and self.pg.exists(name):
                return name
        return None

    # one instance
    def pending(self, inst) -> list[str]:
        return [a for a in self.arms if not self.ck.get("instances", inst.instance_id, "grade", a)]

    def needs_agent(self, inst, arm) -> bool:
        if self.ck.get("instances", inst.instance_id, "agent", arm):
            return False
        tries = self.ck.get("instances", inst.instance_id, "infra", arm) or []
        return len(tries) < self.args.infra_attempts

    def agent_checkout(self, inst, arm) -> Path:
        dest = self.inst_dir(inst) / "agent" / arm / inst.repo.split("/")[-1]
        if dest.exists():
            shutil.rmtree(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        flag = ["-c"] if sys.platform == "darwin" else []  # APFS copy-on-write clone
        subprocess.run(["cp", *flag, "-R", str(self.src(inst)), str(dest)], check=True)
        git(dest, "checkout", "-q", "--force", "main")
        git(dest, "clean", "-qfdx")
        return dest

    def run_arms(self, inst) -> None:
        todo = [a for a in self.pending(inst) if self.needs_agent(inst, a)]
        if not todo:
            return
        self.checkouts(inst)
        pr_diff = git(self.src(inst), "diff", inst.base_commit, inst.head_commit) if self.args.pr_diff else None
        by_serving: dict[str | None, list[str]] = {}
        for arm in todo:
            by_serving.setdefault(ARMS[arm]["serving"], []).append(arm)
        for serving, arms in by_serving.items():
            server_ctx = contextlib.nullcontext(None)
            if serving:
                spec = SERVINGS[serving]
                url = self.serving_db(inst, serving)
                code = code_dir(spec["code"], self.workdir, self.overrides)
                server_ctx = Server(code, pharos_env(code, url, self.args.embedder, self.tokens),
                                    self.inst_dir(inst) / f"server-{serving}.log")
            with server_ctx as server:
                for arm in arms:
                    self.one_agent(inst, arm, server, pr_diff)

    def one_agent(self, inst, arm, server, pr_diff) -> None:
        checkout = self.agent_checkout(inst, arm)
        transcript = self.transcripts / inst.slug / f"{arm}.jsonl"
        outcome = run_agent(self.claude, arm, inst, checkout, server, transcript, model=self.args.model,
                            max_turns=self.args.max_turns, pr_diff=pr_diff)
        if outcome["status"] != "ok":
            self.ck.append({"reason": outcome["reason"], "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                            "wall_s": outcome["wall_s"]}, "instances", inst.instance_id, "infra", arm)
            self.say(f"  {inst.instance_id} {arm}: infrastructure failure ({outcome['reason']})")
            if outcome["pause"]:
                raise PauseRun(outcome["reason"])
            return
        diff = capture_diff(checkout, inst.head_commit)
        record = outcome | diff
        self.ck.put(record, "instances", inst.instance_id, "agent", arm)
        shutil.rmtree(checkout.parent, ignore_errors=True)
        u = outcome["usage"]
        self.say(f"  {inst.instance_id} {arm}: {u['num_turns']} turns, {u['total_tokens']} tokens, "
                 f"{outcome['wall_s']} s, {diff['changed_lines']} changed lines, "
                 f"{sum(n for t, n in outcome['tool_calls'].items() if t.startswith('mcp__'))} PHAROS calls")

    def grade_arms(self, inst) -> None:
        todo = [a for a in self.pending(inst) if self.ck.get("instances", inst.instance_id, "agent", a)]
        if not todo:
            return
        try:
            ccrab.pull_image(inst.image)
            with ccrab.Container(inst.image) as box:
                for arm in todo:
                    agent = self.ck.get("instances", inst.instance_id, "agent", arm)
                    if not agent["patch"].strip():
                        result = {"tests": {}, "error": None, "no_change": True}
                    else:
                        result = ccrab.grade(box, inst.head_commit, inst.tests, agent["patch"]) | {"no_change": False}
                    self.ck.put(result, "instances", inst.instance_id, "grade", arm)
                    passed = sum(1 for t in result["tests"].values() if t["passed"])
                    self.say(f"  {inst.instance_id} {arm}: {passed}/{len(inst.tests)} comment tests pass")
        except ccrab.InfraError as exc:
            self.ck.append({"reason": f"grading: {exc}"[:300], "at": time.strftime("%Y-%m-%dT%H:%M:%S")},
                           "instances", inst.instance_id, "infra", "grading")
            self.say(f"  {inst.instance_id}: grading infrastructure failure")

    def run(self) -> int:
        if self.sealed:  # step 1 of the locked run: every instance's gold commits
            for n, inst in enumerate(self.instances, 1):
                gold_one(inst, self.ck, remove=False)
                print(f"gold check: {n}/{len(self.instances)} instances", flush=True)
        for n, inst in enumerate(self.instances, 1):
            self.say(f"[{n}/{len(self.instances)}] {inst.instance_id}")
            try:
                self.run_arms(inst)
            except ccrab.InfraError as exc:
                for arm in [a for a in self.pending(inst) if self.needs_agent(inst, a)]:
                    self.ck.append({"reason": f"preparation: {exc}"[:300], "at": time.strftime("%Y-%m-%dT%H:%M:%S")},
                                   "instances", inst.instance_id, "infra", arm)
                self.say(f"  {inst.instance_id}: preparation failed ({str(exc)[:200]})")
                continue
            except PauseRun as exc:
                print(f"paused: {exc}. Rerun the same command to resume.", flush=True)
                return 75
            self.grade_arms(inst)
            if self.args.remove_images:
                ccrab.remove_image(inst.image)
        meta = {i.instance_id: {"repo": i.repo, "tests": len(i.tests)} for i in self.instances}
        complete = all(self.ck.get("instances", i.instance_id, "grade", a) for i in self.instances for a in self.arms)
        if self.sealed and not complete:
            print("the locked run is not complete: no report until it is. Rerun to resume.", flush=True)
            return 1
        result = report(self.ck.data, meta, self.arms)
        self.ck.put(result, "report")
        print(json.dumps(result, indent=1))
        return 0


def cmd_run(args) -> int:
    lock = ccrab.load_lock(LOCK)
    args.arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    unknown = [a for a in args.arms if a not in ARMS]
    if unknown:
        raise SystemExit(f"unknown arms {unknown} (known: {list(ARMS)})")
    if args.locked_run and sorted(args.arms) != sorted(ARMS):
        raise ccrab.SealedSetError("the locked run runs every arm in the same run")
    if args.locked_run and args.pr_diff:
        raise ccrab.SealedSetError("--pr-diff is not part of the protocol")
    instances = _instances(args, lock)
    ck = SafeCheckpoint(_out_path(args))
    config = {"kind": "agent", "set": args.set, "lock_sha256": ccrab.LOCK_SHA256, "arms": args.arms,
              "model": args.model, "max_turns": args.max_turns, "embedder": args.embedder, "pr_diff": args.pr_diff,
              "locked_run": args.locked_run, "reuse_index": args.reuse_index, "instances": [i.instance_id for i in instances],
              "arm_table": {a: ARMS[a] for a in args.arms}, "servings": SERVINGS}
    previous = ck.get("run")
    fixed = ("set", "model", "max_turns", "embedder", "pr_diff", "locked_run")
    if previous and any(previous.get(k) != config[k] for k in fixed):
        raise SystemExit(f"{ck.path} was started with other settings; use a new --out to change them")
    ck.put(config, "run")
    return Runner(args, instances, ck, sealed=args.locked_run).run()


def cmd_mirror(args) -> int:
    """Clone or update the git mirrors of a set's repositories. Reads only ids and commits from the lock
    file (allowed for the test set too: no comment, test or patch is touched)."""
    lock = ccrab.load_lock(LOCK)
    entries = [e for e in ccrab.lock_entries(lock, args.set) if not args.repos or e["repo"] in args.repos]
    root = Path(args.mirrors).expanduser()
    by_repo: dict[str, list[dict]] = {}
    for e in entries:
        by_repo.setdefault(e["repo"], []).append(e)
    failed = []
    for n, (repo, items) in enumerate(sorted(by_repo.items()), 1):
        t0 = time.monotonic()
        try:
            ensure_mirror(f"https://github.com/{repo}", root, [(c, e["pull_number"]) for e in items
                                                             for c in (e["base_commit"], e["head_commit"])])
            print(f"[{n}/{len(by_repo)}] {repo}: {len(items)} instances, {time.monotonic() - t0:.0f} s", flush=True)
        except ccrab.InfraError as exc:
            failed.append(repo)
            print(f"[{n}/{len(by_repo)}] {repo}: failed ({str(exc)[:200]})", flush=True)
    return 1 if failed else 0


def cmd_report(args) -> int:
    ck = SafeCheckpoint(_out_path(args))
    run = ck.get("run") or {}
    if run.get("locked_run") and not ck.get("report"):
        print("the locked run is not complete: no scores are shown before it is.")
        return 1
    lock = ccrab.load_lock(LOCK)
    entries = {e["instance_id"]: e for e in ccrab.lock_entries(lock, run["set"])}
    meta = {i: {"repo": entries[i]["repo"], "tests": entries[i]["comments"]} for i in run["instances"]}
    result = report(ck.data, meta, run["arms"])
    print(json.dumps(result, indent=1))
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)

    def common(p, sets=True):
        p.add_argument("--out", help="checkpoint and results (a JSON file)")
        if sets:
            p.add_argument("--set", default="dev", choices=ccrab.SETS)
            p.add_argument("--ccrab", required=True, help="the c-CRAB dataset repository at the pinned commit")
            p.add_argument("--instances", nargs="*", help="only these instance ids")
            p.add_argument("--repos", nargs="*", help="only these repositories (owner/name)")
            p.add_argument("--limit", type=int)

    g = sub.add_parser("gold", help="grade head_commit and merged_commit of every instance (no LLM)")
    common(g)
    g.add_argument("--workers", type=int, default=2)
    g.add_argument("--remove-images", action="store_true", help="remove each image after grading it")
    g.add_argument("--keep-images", nargs="*", help="repositories whose images are kept")
    g.set_defaults(func=cmd_gold)

    r = sub.add_parser("run", help="run the arms and grade them")
    common(r)
    r.add_argument("--arms", default=",".join(ARMS))
    r.add_argument("--workdir", required=True)
    r.add_argument("--mirrors", default=str(Path.home() / ".cache" / "pharos" / "git"))
    r.add_argument("--pg", required=True, help="PostgreSQL server URL without a database name")
    r.add_argument("--embedder", default="hash", help="'hash' or 'onnx=<model dir>'")
    r.add_argument("--code", nargs="*", help="override a code checkout: name=path (names: " + ", ".join(CODE) + ")")
    r.add_argument("--claude", help="the claude binary (default: PHAROS_CLAUDE_PATH, PATH, VS Code extension)")
    r.add_argument("--model", default=MODEL)
    r.add_argument("--max-turns", type=int, default=MAX_TURNS)
    r.add_argument("--infra-attempts", type=int, default=INFRA_ATTEMPTS)
    r.add_argument("--pr-diff", action="store_true", help="also show the PR's diff (not in the protocol; dev only)")
    r.add_argument("--remove-images", action="store_true")
    r.add_argument("--no-reuse-index", dest="reuse_index", action="store_false",
                   help="index every instance from empty instead of from an earlier instance of its repository")
    r.add_argument("--locked-run", action="store_true", help="the one locked run of the test set")
    r.add_argument("--sealed-out", help="the locked run's results, outside the repository")
    r.set_defaults(func=cmd_run)

    m = sub.add_parser("mirror", help="clone the git mirrors of a set's repositories (ids and commits only)")
    m.add_argument("--set", default="dev", choices=("dev", "test"))
    m.add_argument("--repos", nargs="*")
    m.add_argument("--mirrors", default=str(Path.home() / ".cache" / "pharos" / "git"))
    m.set_defaults(func=cmd_mirror)

    p = sub.add_parser("report", help="compute the report from a checkpoint")
    common(p, sets=False)
    p.add_argument("--sealed-out")
    p.set_defaults(func=cmd_report)
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "report" and args.sealed_out:
        args.locked_run = True
    try:
        return args.func(args)
    except (ccrab.SealedSetError, ccrab.LockError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
