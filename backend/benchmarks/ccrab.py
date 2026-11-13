"""c-CRAB data and grading for the Phase 3 evaluation (docs/benchmarks/phase3-eval-protocol.md).

Data comes from two places, both checked against hashes before use:

- the locked split ``benchmarks/datasets/ccrab_phase3.json`` (ids, commits and counts, no text), whose
  SHA-256 is fixed here;
- a copy of the c-CRAB dataset repository at the pinned commit, whose ``stage4_agent_resolved.jsonl``
  and ``testgen_combined.zip`` must match the hashes recorded in the lock file. That copy is treated as
  data only: its files are read, nothing in it is executed and git is never run inside it.

Grading follows c-CRAB's ``pipeline/agent_resolver.py`` and ``pipeline/test_runner.py``: in the
instance's Docker image the repository at ``/workspace`` is checked out with ``git checkout --force``
and ``git clean -fd``, reinstalled with ``pip install -e . --no-deps``, the change under test is
applied, the package is reinstalled, and each comment's generated test is copied in as
``/workspace/test_review_comment_<i>.py`` and run with
``python -m pytest <file> -x -v --tb=short --no-header -c /dev/null -p no:cacheprovider``
(``npx jest --no-coverage <file>`` for JavaScript and TypeScript tests). A test passes when the
command exits 0. A change that leaves the tree unchanged resolves nothing, without running tests, as
in c-CRAB.
"""

from __future__ import annotations

import hashlib
import io
import json
import subprocess
import tarfile
import time
import uuid
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

LOCK_SHA256 = "8784fbdf9b09ecf5311f026568b59420ba3961abface8705da186601f2064427"  # pragma: allowlist secret
SETS = ("test", "dev", "reserve")
STAGE4 = Path("results_pipeline_funnel/stage4_agent_resolved.jsonl")
TESTGEN_ZIP = Path("raw_results_compressed/testgen_combined.zip")
TEST_TIMEOUT = 120  # agent_resolver.verify_with_test
SETUP_TIMEOUT = 120
EXTENSIONS = {"python": ".py", "javascript": ".test.js", "typescript": ".test.ts", "go": "_test.go"}


class LockError(RuntimeError):
    """The lock file or the c-CRAB data does not match what the protocol locked."""


class SealedSetError(RuntimeError):
    """A sealed set was asked for without the flags that allow it."""


class InfraError(RuntimeError):
    """Docker, the network or a container failed: not a result. Retried on resume."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load_lock(path: Path, expected: str = LOCK_SHA256) -> dict:
    """The lock file, after checking its SHA-256 against the protocol's."""
    actual = sha256_file(path)
    if actual != expected:
        raise LockError(f"{path.name} has SHA-256 {actual}, the protocol locked {expected}")
    return json.loads(path.read_text())


def verify_sources(lock: dict, ccrab_dir: Path) -> None:
    """The c-CRAB files must be the ones the lock file was made from."""
    for rel, key in ((STAGE4, "stage4_sha256"), (TESTGEN_ZIP, "testgen_zip_sha256")):
        path = ccrab_dir / rel
        if not path.is_file():
            raise LockError(f"missing c-CRAB file {rel}")
        actual = sha256_file(path)
        if actual != lock["source"][key]:
            raise LockError(f"{rel} has SHA-256 {actual}, the lock file records {lock['source'][key]}")


def check_set_allowed(set_name: str, *, locked_run: bool, sealed_out: Path | None, repo_root: Path) -> None:
    """The sealing rule: the test set runs only as the locked run, with results outside the repository.

    The reserve is not run in Phase 3 at all; the dev set never runs as a locked run.
    """
    if set_name not in SETS:
        raise SealedSetError(f"unknown set {set_name!r}")
    if set_name == "reserve":
        raise SealedSetError("the reserve set is not run in Phase 3")
    if set_name == "test" and not locked_run:
        raise SealedSetError("the test set is sealed: it runs only with --locked-run and --sealed-out")
    if locked_run:
        if set_name != "test":
            raise SealedSetError("--locked-run is only for the test set")
        if sealed_out is None:
            raise SealedSetError("--locked-run needs --sealed-out (a path outside the repository)")
        out = Path(sealed_out).expanduser().resolve()
        root = Path(repo_root).resolve()
        if out == root or root in out.parents:
            raise SealedSetError(f"--sealed-out must be outside the repository ({root})")


@dataclass(frozen=True)
class CommentTest:
    index: int  # position of the comment in the instance's reference_review_comments
    filename: str  # test_review_comment_<index><ext>, as c-CRAB names it
    language: str
    code: str = field(repr=False)


@dataclass
class Instance:
    instance_id: str
    repo: str
    pull_number: int
    created_at: str
    base_commit: str
    head_commit: str
    merged_commit: str
    title: str = field(repr=False)
    body: str = field(repr=False)
    tests: list[CommentTest] = field(repr=False)

    @property
    def image(self) -> str:
        return f"ghcr.io/c-crab-benchmark/{self.instance_id.split('@')[0].lower()}"

    @property
    def slug(self) -> str:
        return self.instance_id.replace("/", "__").replace("@", "_")

    @property
    def url(self) -> str:
        return f"https://github.com/{self.repo}"


def lock_entries(lock: dict, set_name: str) -> list[dict]:
    """Ids, commits and counts of one set, with the repository name added: never any text."""
    return [dict(entry, repo=repo) for repo, entries in sorted(lock[set_name].items()) for entry in entries]


def match_tests(comments: list[dict], testgen: dict) -> list[CommentTest]:
    """c-CRAB's ``match_tests_to_comments``: each comment takes the first verified test with its text."""
    tests = []
    for i, comment in enumerate(comments):
        for entry in testgen.get("results", []):
            if entry.get("comment_text") == comment["text"] and entry.get("success"):
                language = entry.get("language", "python")
                tests.append(CommentTest(index=i, filename=f"test_review_comment_{i}{EXTENSIONS.get(language, '.py')}",
                                         language=language, code=entry["test_code"]))
                break
    return tests


def load_instances(lock: dict, ccrab_dir: Path, set_name: str, ids: set[str] | None = None) -> list[Instance]:
    """The instances of ``set_name`` (optionally only ``ids``), with their PR text and tests.

    Rows of other sets are skipped as soon as their id is read, and nothing is printed.
    """
    wanted = {e["instance_id"]: e for e in lock_entries(lock, set_name)}
    if ids is not None:
        unknown = ids - set(wanted)
        if unknown:
            raise SealedSetError(f"{len(unknown)} requested instance(s) are not in the {set_name} set")
        wanted = {k: v for k, v in wanted.items() if k in ids}
    rows: dict[str, dict] = {}
    with open(ccrab_dir / STAGE4) as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("instance_id") in wanted:
                rows[row["instance_id"]] = row
    out = []
    with zipfile.ZipFile(ccrab_dir / TESTGEN_ZIP) as archive:
        for iid, entry in wanted.items():
            row = rows.get(iid)
            if row is None:
                raise LockError(f"{iid} is in the lock file but not in stage 4")
            checks = {"repo": row["repo"], "pull_number": row["pull_number"], "created_at": row["created_at"],
                      "base_commit": row["base_commit"], "head_commit": row["commit_to_review"]["head_commit"],
                      "merged_commit": row["merged_commit"]}
            bad = [k for k, v in checks.items() if entry[k] != v]
            if bad:
                raise LockError(f"{iid}: lock file and stage 4 disagree on {', '.join(bad)}")
            testgen = json.loads(archive.read(f"testgen_combined/{iid.replace('/', '__')}/result.json"))
            tests = match_tests(row["reference_review_comments"], testgen)
            if len(tests) != entry["comments"] or len(row["reference_review_comments"]) != entry["comments"]:
                raise LockError(f"{iid}: expected {entry['comments']} comment tests, matched {len(tests)}")
            out.append(Instance(instance_id=iid, title=row.get("title") or "", body=row.get("body") or "",
                                tests=tests, **checks))
    return out


# ── Docker ──────────────────────────────────────────────────────────────

DOCKER_ERRORS = ("Error response from daemon", "Cannot connect to the Docker daemon", "No such container",
                 "is not running", "OCI runtime", "RWLayer unexpectedly nil")


def _docker(*args: str, timeout: float = 600, stdin: bytes | None = None) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(["docker", *args], input=stdin, capture_output=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise InfraError(f"docker {args[0]}: {exc}") from exc


def pull_image(image: str, attempts: int = 3) -> float:
    """Make sure ``image`` is present; returns the seconds spent pulling."""
    if _docker("image", "inspect", image, timeout=60).returncode == 0:
        return 0.0
    t0 = time.monotonic()
    last = ""
    for attempt in range(attempts):
        result = _docker("pull", "--platform", "linux/amd64", image, timeout=3600)
        if result.returncode == 0:
            return time.monotonic() - t0
        last = result.stderr.decode(errors="replace")[-300:]
        time.sleep(5 * (attempt + 1))
    raise InfraError(f"docker pull {image} failed: {last}")


def remove_image(image: str) -> None:
    _docker("image", "rm", "-f", image, timeout=300)


class Container:
    """One long-running container of an instance image (``sleep infinity``), as c-CRAB runs them."""

    def __init__(self, image: str):
        self.image = image
        self.name = f"pharos-eval-{uuid.uuid4().hex[:12]}"
        self.started = False

    def __enter__(self) -> Container:
        result = _docker("run", "--detach", "--platform", "linux/amd64", "--name", self.name, "--workdir",
                         "/workspace", self.image, "sleep", "infinity", timeout=600)
        if result.returncode != 0:
            raise InfraError(f"docker run failed: {result.stderr.decode(errors='replace')[-300:]}")
        self.started = True
        return self

    def __exit__(self, *exc) -> None:
        if self.started:
            _docker("rm", "-f", self.name, timeout=120)

    def run(self, command: str, timeout: float) -> tuple[int, str]:
        """``bash -lc command`` in /workspace: (exit code, output). A timeout is exit code -1."""
        try:
            result = subprocess.run(["docker", "exec", self.name, "bash", "-lc", command], capture_output=True,
                                    timeout=timeout, check=False)
        except subprocess.TimeoutExpired as exc:
            out = (exc.stdout or b"") + (exc.stderr or b"")
            return -1, out.decode(errors="replace") + f"\nCommand timed out after {timeout}s"
        except OSError as exc:
            raise InfraError(f"docker exec: {exc}") from exc
        out = (result.stdout + b"\n" + result.stderr).decode(errors="replace").strip()
        if result.returncode in (125, 126, 127) and any(marker in out for marker in DOCKER_ERRORS):
            raise InfraError(f"docker exec failed: {out[-300:]}")
        return result.returncode, out

    def put(self, data: bytes, container_dir: str, name: str) -> None:
        """Copy ``data`` into the container as ``container_dir/name`` (a tar stream: no host mounts)."""
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w") as tar:
            info = tarfile.TarInfo(name)
            info.size, info.mode, info.mtime = len(data), 0o644, int(time.time())
            tar.addfile(info, io.BytesIO(data))
        for attempt in range(3):  # c-CRAB retries docker cp on transient errors too
            result = _docker("cp", "-", f"{self.name}:{container_dir}", stdin=buffer.getvalue(), timeout=120)
            if result.returncode == 0:
                return
            time.sleep(2 * (attempt + 1))
        raise InfraError(f"docker cp failed: {result.stderr.decode(errors='replace')[-300:]}")


def test_command(test: CommentTest, path: str) -> str:
    if test.language == "python":
        return f"python -m pytest {path} -x -v --tb=short --no-header -c /dev/null -p no:cacheprovider"
    if test.language in ("javascript", "typescript"):
        return f"npx jest --no-coverage {path}"
    if test.language == "go":
        return f"go test -v -run . {str(Path(path).parent)}"
    raise ValueError(f"no test runner for {test.language}")


def _install(box: Container, languages: set[str]) -> None:
    if "python" in languages:
        box.run("pip install -e . --no-deps --quiet", SETUP_TIMEOUT)
    if languages & {"javascript", "typescript"}:
        box.run("npm install --ignore-scripts", SETUP_TIMEOUT)


def grade(box: Container, commit: str, tests: list[CommentTest], patch: str | None = None,
          *, keep_output: int = 1500) -> dict:
    """Run every comment test against ``commit`` plus ``patch`` (a ``git diff --binary``), c-CRAB style.

    Returns ``{"tests": {index: {"passed", "seconds", "output"}}, "error": None | str}``. A checkout or
    patch that fails is an error result (every test counts as failed); Docker failures raise InfraError.
    """
    languages = {t.language for t in tests}
    rc, out = box.run(f"git checkout --force {commit} && git clean -fd --quiet", SETUP_TIMEOUT)
    if rc != 0:
        return {"tests": {}, "error": f"git checkout failed: {out[-500:]}"}
    _install(box, languages)
    if patch is not None:
        box.put(patch.encode(), "/tmp", "pharos_change.patch")
        rc, out = box.run("git apply --whitespace=nowarn /tmp/pharos_change.patch", SETUP_TIMEOUT)
        if rc != 0:
            return {"tests": {}, "error": f"patch did not apply: {out[-500:]}"}
        _install(box, languages)
    results = {}
    for test in tests:
        if test.language in ("javascript", "typescript") and box.run("which npx", 10)[0] != 0:
            results[str(test.index)] = {"passed": False, "seconds": 0.0,
                                        "output": "npx/node.js is not installed in this Docker image."}
            continue
        box.put(test.code.encode(), "/workspace", test.filename)
        t0 = time.monotonic()
        rc, out = box.run(test_command(test, f"/workspace/{test.filename}"), TEST_TIMEOUT)
        results[str(test.index)] = {"passed": rc == 0, "seconds": round(time.monotonic() - t0, 1),
                                    "output": out[-keep_output:]}
    return {"tests": results, "error": None}


def gold_status(head: dict, merged: dict, tests: list[CommentTest]) -> dict:
    """Does the instance reproduce: every test fails at ``head_commit`` and passes at ``merged_commit``?"""
    idx = [str(t.index) for t in tests]
    head_failed = [i for i in idx if not head["tests"].get(i, {}).get("passed", False)]
    merged_passed = [i for i in idx if merged["tests"].get(i, {}).get("passed", False)]
    ok = not head["error"] and not merged["error"]
    return {"reproduced": ok and len(head_failed) == len(idx) and len(merged_passed) == len(idx),
            "fail_at_head": len(head_failed), "pass_at_merged": len(merged_passed), "tests": len(idx),
            "head_error": head["error"], "merged_error": merged["error"]}
