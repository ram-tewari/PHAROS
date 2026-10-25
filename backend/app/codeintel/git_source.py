"""Safe access to repository content via the ``git`` CLI.

Design points (each closes a concrete hole in the previous pipeline):

* **Content comes from git objects, never the working tree.** Remote
  repositories are cloned ``--bare``, and files are read with
  ``git cat-file`` at a pinned commit. A malicious repository therefore
  cannot use symlinks to make the indexer read files outside the clone
  (symlinks have mode 120000 and are skipped; submodules, 160000, too).
* **Only tracked files at one commit are indexed**, which gives
  ``.gitignore`` semantics for free and makes indexing reproducible.
* **Remote URLs are validated**: https only, an allowlist of hosts, no
  credentials / ports / IP literals in the URL, and HTTP redirects are not
  followed, so the API cannot be turned into an SSRF probe of internal
  hosts.
* **Private-repo tokens never appear in argv, URLs or logs**: they are
  passed as a host-scoped ``http.extraHeader`` through ``GIT_CONFIG_*``
  environment variables.
* Every git invocation has a timeout and never prompts for credentials.
"""

from __future__ import annotations

import base64
import ipaddress
import logging
import os
import re
import shutil
import subprocess
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)

_SEGMENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
_SHA_RE = re.compile(r"^[0-9a-f]{40}([0-9a-f]{24})?$")
_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,199}$")

GIT_TIMEOUT_SECONDS = 120


class RepoSpecError(ValueError):
    """The repository reference is malformed or not allowed (not retryable)."""


class GitError(RuntimeError):
    """A git command failed.

    ``retryable`` is False for failures that will not fix themselves
    (repository not found, authentication refused, unknown branch).
    """

    def __init__(self, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.retryable = retryable


@dataclass(frozen=True)
class RepoRef:
    """A validated repository reference."""

    #: Stable identity used as ``repositories.url``.
    canonical_url: str
    #: "github" | "git" | "local"
    source_type: str
    #: Human-readable name, e.g. "owner/repo".
    name: str
    #: https URL git clones from (remote only).
    clone_url: str | None = None
    #: Absolute path of a local repository (local only).
    local_path: str | None = None
    host: str | None = None

    @property
    def is_github(self) -> bool:
        return self.source_type == "github"

    def raw_url(self, commit: str, path: str) -> str | None:
        """URL serving the file's raw bytes at ``commit`` (None for local repos)."""
        return raw_file_url(self.canonical_url, commit, path)

    def web_url(self, commit: str, path: str, start: int | None, end: int | None) -> str | None:
        return web_file_url(self.canonical_url, commit, path, start, end)


#: Hosts whose raw-file endpoints the code resolver may fetch from.
RAW_CONTENT_HOSTS = frozenset({"raw.githubusercontent.com", "gitlab.com", "bitbucket.org"})


def raw_file_url(canonical_url: str, commit: str, path: str) -> str | None:
    parts = urlsplit(canonical_url)
    if parts.scheme != "https":
        return None
    repo_path = parts.path.strip("/")
    if parts.hostname == "github.com":
        return f"https://raw.githubusercontent.com/{repo_path}/{commit}/{path}"
    if parts.hostname == "gitlab.com":
        return f"https://gitlab.com/{repo_path}/-/raw/{commit}/{path}"
    if parts.hostname == "bitbucket.org":
        return f"https://bitbucket.org/{repo_path}/raw/{commit}/{path}"
    return None


def web_file_url(canonical_url: str, commit: str, path: str, start: int | None, end: int | None) -> str | None:
    parts = urlsplit(canonical_url)
    if parts.scheme != "https":
        return None
    if parts.hostname == "github.com":
        anchor = f"#L{start}-L{end}" if start and end else ""
        return f"{canonical_url}/blob/{commit}/{path}{anchor}"
    if parts.hostname == "gitlab.com":
        anchor = f"#L{start}-{end}" if start and end else ""
        return f"{canonical_url}/-/blob/{commit}/{path}{anchor}"
    return None


def parse_repo_spec(
    spec: str,
    *,
    allowed_hosts: list[str] | tuple[str, ...],
    allow_local: bool = False,
) -> RepoRef:
    """Validate ``spec`` and return a :class:`RepoRef`.

    Accepted remote forms: ``https://github.com/owner/repo(.git)``,
    ``github.com/owner/repo``, and ``owner/repo`` (GitHub). Local paths are
    accepted only when ``allow_local`` is True (the CLI, never the API).
    """
    if not isinstance(spec, str):
        raise RepoSpecError("repository must be a string")
    spec = spec.strip()
    if not spec or len(spec) > 2048:
        raise RepoSpecError("repository reference is empty or too long")
    if any(ord(c) < 0x20 or c in "\\ " for c in spec):
        raise RepoSpecError("repository reference contains whitespace or control characters")

    looks_local = spec.startswith(("/", "./", "../", "~", "file:"))
    if looks_local:
        if not allow_local:
            raise RepoSpecError("local repositories can only be indexed from the CLI")
        return _local_ref(spec)

    if "://" not in spec:
        if re.match(r"^[A-Za-z0-9-]+/[A-Za-z0-9._-]+$", spec):
            spec = f"https://github.com/{spec}"
        else:
            spec = f"https://{spec}"

    try:
        parts = urlsplit(spec)
        port = parts.port  # raises ValueError for "host:junk" (e.g. "javascript:alert(1)")
    except ValueError as exc:
        raise RepoSpecError("malformed repository URL") from exc
    if parts.scheme != "https":
        raise RepoSpecError("only https:// repository URLs are accepted")
    if parts.username or parts.password or "@" in parts.netloc:
        raise RepoSpecError(
            "credentials in repository URLs are not accepted; configure GIT_CLONE_TOKEN instead"
        )
    if port is not None:
        raise RepoSpecError("custom ports are not accepted in repository URLs")
    if parts.query or parts.fragment:
        raise RepoSpecError("repository URLs must not contain a query or fragment")
    host = (parts.hostname or "").lower().rstrip(".")
    if _is_ip_literal(host):
        raise RepoSpecError("IP-address hosts are not accepted")
    allowed = {h.lower() for h in allowed_hosts}
    if host not in allowed:
        raise RepoSpecError(f"host {host!r} is not in CODEINTEL_ALLOWED_GIT_HOSTS")

    segments = [s for s in parts.path.split("/") if s]
    if segments and segments[-1].endswith(".git"):
        segments[-1] = segments[-1][:-4]
    if len(segments) < 2 or (host == "github.com" and len(segments) != 2):
        raise RepoSpecError("expected a URL of the form https://host/owner/repo")
    for seg in segments:
        if seg in (".", "..") or not _SEGMENT_RE.match(seg):
            raise RepoSpecError(f"invalid path segment {seg!r} in repository URL")

    path = "/".join(segments)
    if host == "github.com":
        path = path.lower()  # GitHub owner/repo names are case-insensitive.
    canonical = f"https://{host}/{path}"
    return RepoRef(
        canonical_url=canonical,
        source_type="github" if host == "github.com" else "git",
        name=path,
        clone_url=canonical + ".git",
        host=host,
    )


def _is_ip_literal(host: str) -> bool:
    try:
        ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return False
    return True


def _local_ref(spec: str) -> RepoRef:
    raw = spec[len("file://"):] if spec.startswith("file://") else spec
    path = Path(os.path.expanduser(raw)).resolve()
    if not path.is_dir():
        raise RepoSpecError(f"local repository {path} does not exist")
    try:
        out = _run(["git", "-C", str(path), "rev-parse", "--git-dir"], timeout=30)
    except GitError as exc:
        raise RepoSpecError(f"{path} is not a git repository") from exc
    if not out.strip():
        raise RepoSpecError(f"{path} is not a git repository")
    return RepoRef(
        canonical_url=path.as_uri(),
        source_type="local",
        name=path.name,
        local_path=str(path),
    )


def validate_ref(ref: str | None) -> str | None:
    if ref is None or ref == "":
        return None
    if not _REF_RE.match(ref) or ".." in ref or ref.endswith((".lock", "/")) or "@{" in ref:
        raise RepoSpecError(f"invalid branch or ref name {ref!r}")
    return ref


# ── git execution ───────────────────────────────────────────────────────────


def _git_env(extra_config: list[tuple[str, str]] | None = None) -> dict[str, str]:
    env = dict(os.environ)
    env.update(
        GIT_TERMINAL_PROMPT="0",
        GIT_ASKPASS="",
        SSH_ASKPASS="",
        GIT_LFS_SKIP_SMUDGE="1",
        LC_ALL="C",
    )
    config = list(extra_config or [])
    # Never follow redirects and never use any transport but https.
    config += [
        ("http.followRedirects", "false"),
        ("protocol.allow", "never"),
        ("protocol.https.allow", "always"),
        ("protocol.file.allow", "always"),  # local repositories (CLI)
        ("core.hooksPath", os.devnull),
    ]
    base = int(env.get("GIT_CONFIG_COUNT", "0") or 0)
    for i, (key, value) in enumerate(config, start=base):
        env[f"GIT_CONFIG_KEY_{i}"] = key
        env[f"GIT_CONFIG_VALUE_{i}"] = value
    env["GIT_CONFIG_COUNT"] = str(base + len(config))
    return env


_SENSITIVE_RE = re.compile(r"(authorization:\s*\S+\s+)\S+", re.I)


def _sanitize(text: str) -> str:
    text = _SENSITIVE_RE.sub(r"\1***", text)
    return text.strip()[-800:]


def _classify(stderr: str) -> bool:
    """Return True if a git failure is worth retrying."""
    s = stderr.lower()
    permanent = (
        "repository not found",
        "not found",
        "authentication failed",
        "could not read username",
        "remote branch",
        "invalid refspec",
        "couldn't find remote ref",
        "unknown revision",
        "needed a single revision",
        "bad revision",
        "not a valid object name",
        "terminal prompts disabled",
        "http 401",
        "http 403",
        "http 404",
        "redirect",
    )
    return not any(p in s for p in permanent)


def _run(args: list[str], *, timeout: int = GIT_TIMEOUT_SECONDS, env: dict | None = None,
         input_bytes: bytes | None = None) -> str:
    try:
        proc = subprocess.run(
            args,
            input=input_bytes,
            capture_output=True,
            timeout=timeout,
            env=env or _git_env(),
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise GitError(f"git {args[1:3]} timed out after {timeout}s", retryable=True) from exc
    except FileNotFoundError as exc:
        raise GitError("git executable not found on PATH", retryable=False) from exc
    if proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", errors="replace")
        raise GitError(f"git failed: {_sanitize(stderr)}", retryable=_classify(stderr))
    return proc.stdout.decode("utf-8", errors="replace")


def _auth_config(ref: RepoRef, token: str | None) -> list[tuple[str, str]]:
    if not token or not ref.host:
        return []
    basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    # Scoped to the repository host only.
    return [(f"http.https://{ref.host}/.extraHeader", f"Authorization: Basic {basic}")]


# ── checkout lifecycle ──────────────────────────────────────────────────────


@dataclass
class TreeEntry:
    path: str
    blob_sha: str
    size: int
    mode: str


class Checkout:
    """A repository at a pinned commit, ready to be read.

    Use as a context manager; remote clones are deleted on exit.
    """

    def __init__(self, git_dir: str, commit: str, *, temp_dir: str | None = None,
                 branch: str | None = None) -> None:
        self.git_dir = git_dir
        self.commit = commit
        self.branch = branch
        self._temp_dir = temp_dir
        self._reader: subprocess.Popen | None = None

    def __enter__(self) -> Checkout:
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    def close(self) -> None:
        if self._reader is not None:
            try:
                self._reader.stdin.close()  # type: ignore[union-attr]
                self._reader.wait(timeout=10)
            except Exception:
                self._reader.kill()
            self._reader = None
        if self._temp_dir:
            shutil.rmtree(self._temp_dir, ignore_errors=True)
            self._temp_dir = None

    def _git(self, *args: str, timeout: int = GIT_TIMEOUT_SECONDS) -> str:
        return _run(["git", f"--git-dir={self.git_dir}", *args], timeout=timeout)

    def list_files(self) -> Iterator[TreeEntry]:
        """Regular files tracked at the commit (symlinks and submodules excluded)."""
        out = self._git("ls-tree", "-r", "-z", "--long", "--full-tree", self.commit, timeout=300)
        for record in out.split("\0"):
            if not record:
                continue
            meta, _, path = record.partition("\t")
            fields = meta.split()
            if len(fields) != 4:
                continue
            mode, obj_type, sha, size = fields
            if obj_type != "blob" or mode not in ("100644", "100755"):
                continue
            yield TreeEntry(path=path, blob_sha=sha, size=int(size) if size.isdigit() else 0, mode=mode)

    def read_blob(self, sha: str) -> bytes:
        """Read one blob through a persistent ``git cat-file --batch`` process."""
        if not re.fullmatch(r"[0-9a-f]{40,64}", sha):
            raise ValueError("invalid blob sha")
        if self._reader is None:
            self._reader = subprocess.Popen(
                ["git", f"--git-dir={self.git_dir}", "cat-file", "--batch"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                env=_git_env(),
            )
        proc = self._reader
        assert proc.stdin and proc.stdout
        proc.stdin.write(sha.encode() + b"\n")
        proc.stdin.flush()
        header = proc.stdout.readline().decode()
        parts = header.split()
        if len(parts) != 3 or parts[1] != "blob":
            raise GitError(f"cannot read blob {sha[:12]}", retryable=False)
        size = int(parts[2])
        data = proc.stdout.read(size)
        proc.stdout.read(1)  # trailing newline
        return data


def open_checkout(ref: RepoRef, *, branch: str | None = None, token: str | None = None,
                  timeout: int = 600) -> Checkout:
    """Resolve ``ref`` at ``branch`` (default branch when None) to a :class:`Checkout`."""
    branch = validate_ref(branch)
    if ref.source_type == "local":
        assert ref.local_path
        git_dir = _run(["git", "-C", ref.local_path, "rev-parse", "--absolute-git-dir"], timeout=30).strip()
        target = branch or "HEAD"
        commit = _run(["git", f"--git-dir={git_dir}", "rev-parse", "--verify", f"{target}^{{commit}}"], timeout=30).strip()
        return Checkout(git_dir, commit, branch=branch)

    assert ref.clone_url
    temp_dir = tempfile.mkdtemp(prefix="pharos_ingest_")
    git_dir = os.path.join(temp_dir, "repo.git")
    args = ["git", "clone", "--bare", "--depth", "1", "--single-branch", "--no-tags", "--quiet"]
    if branch:
        args += ["--branch", branch]
    args += ["--", ref.clone_url, git_dir]
    try:
        _run(args, timeout=timeout, env=_git_env(_auth_config(ref, token)))
        commit = _run(["git", f"--git-dir={git_dir}", "rev-parse", "--verify", "HEAD^{commit}"], timeout=30).strip()
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise
    logger.info("Cloned %s @ %s (branch=%s)", ref.canonical_url, commit[:12], branch or "default")
    return Checkout(git_dir, commit, temp_dir=temp_dir, branch=branch)


def read_file_at_commit(git_dir: str, commit: str, path: str) -> bytes:
    """Read ``path`` at ``commit`` from a local repository (code resolution)."""
    if not _SHA_RE.match(commit):
        raise ValueError("commit must be a full SHA")
    if path.startswith("/") or ".." in path.split("/"):
        raise ValueError("invalid path")
    proc = subprocess.run(
        ["git", f"--git-dir={git_dir}", "cat-file", "blob", f"{commit}:{path}"],
        capture_output=True,
        timeout=30,
        env=_git_env(),
        check=False,
    )
    if proc.returncode != 0:
        raise GitError("file not found at commit", retryable=False)
    return proc.stdout


def local_git_dir(path: str) -> str:
    return _run(["git", "-C", path, "rev-parse", "--absolute-git-dir"], timeout=30).strip()
