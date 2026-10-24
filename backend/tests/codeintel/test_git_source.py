"""Repository access: validation (SSRF, injection) and safe reading."""

import os
import subprocess

import pytest

from app.codeintel import git_source
from app.codeintel.git_source import GitError, RepoSpecError, open_checkout, parse_repo_spec, validate_ref

HOSTS = ["github.com", "gitlab.com"]


@pytest.mark.parametrize(
    "spec,canonical",
    [
        ("github.com/Fatih/Color", "https://github.com/fatih/color"),
        ("https://github.com/fatih/color.git", "https://github.com/fatih/color"),
        ("fatih/color", "https://github.com/fatih/color"),
        ("https://gitlab.com/group/sub/proj", "https://gitlab.com/group/sub/proj"),
    ],
)
def test_accepts_and_canonicalises(spec, canonical):
    assert parse_repo_spec(spec, allowed_hosts=HOSTS).canonical_url == canonical


@pytest.mark.parametrize(
    "spec,fragment",
    [
        ("http://github.com/a/b", "https"),
        ("ssh://git@github.com/a/b", "https"),
        ("git://github.com/a/b", "https"),
        ("file:///etc/passwd", "CLI"),
        ("/etc", "CLI"),
        ("https://169.254.169.254/latest/meta", "IP-address"),
        ("https://127.0.0.1/a/b", "IP-address"),
        ("https://[::1]/a/b", "IP-address"),
        ("https://internal.corp/a/b", "not in CODEINTEL_ALLOWED_GIT_HOSTS"),
        ("https://github.com.evil.com/a/b", "not in CODEINTEL_ALLOWED_GIT_HOSTS"),
        ("https://user:pw@github.com/a/b", "credentials"),
        ("https://github.com:8443/a/b", "ports"),
        ("https://github.com/a/b?ref=x", "query"),
        ("https://github.com/a/../b", "owner/repo"),
        ("https://github.com/a/b/c", "owner/repo"),
        ("https://github.com/-rf/b", "invalid path segment"),
        ("github.com/a/b;curl evil", "whitespace"),
        ("github.com/a/b\nx", "control"),
        ("", "empty"),
    ],
)
def test_rejects_dangerous_specs(spec, fragment):
    with pytest.raises(RepoSpecError, match=fragment):
        parse_repo_spec(spec, allowed_hosts=HOSTS)


@pytest.mark.parametrize("ref", ["--upload-pack=x", "a..b", "main.lock", "refs/heads/", "x@{1}", "a b"])
def test_rejects_bad_refs(ref):
    with pytest.raises(RepoSpecError):
        validate_ref(ref)


def test_ref_allows_normal_names():
    assert validate_ref("release/1.2") == "release/1.2"
    assert validate_ref(None) is None


def test_local_checkout_reads_committed_content_only(fixture_repo):
    fixture_repo.write("shop/uncommitted.py", "x = 1\n")
    ref = parse_repo_spec(str(fixture_repo.path), allowed_hosts=[], allow_local=True)
    with open_checkout(ref) as co:
        paths = {e.path for e in co.list_files()}
        assert "shop/auth.py" in paths
        assert "shop/uncommitted.py" not in paths
        entry = next(e for e in co.list_files() if e.path == "shop/auth.py")
        assert co.read_blob(entry.blob_sha) == (fixture_repo.path / "shop/auth.py").read_bytes()


def test_symlinks_and_submodules_are_not_listed(fixture_repo, tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("TOP SECRET")
    os.symlink(secret, fixture_repo.path / "shop" / "leak.py")
    os.symlink("/etc/passwd", fixture_repo.path / "passwd.py")
    fixture_repo.commit("add symlinks")
    ref = parse_repo_spec(str(fixture_repo.path), allowed_hosts=[], allow_local=True)
    with open_checkout(ref) as co:
        paths = {e.path for e in co.list_files()}
    assert "shop/leak.py" not in paths and "passwd.py" not in paths


def test_unknown_branch_is_a_permanent_error(fixture_repo):
    ref = parse_repo_spec(str(fixture_repo.path), allowed_hosts=[], allow_local=True)
    with pytest.raises(GitError) as exc:
        open_checkout(ref, branch="does-not-exist")
    assert exc.value.retryable is False


def test_clone_token_is_not_in_argv_or_error(monkeypatch):
    seen = {}

    def fake_run(args, **kwargs):
        seen["args"] = args
        seen["env"] = kwargs.get("env", {})
        return subprocess.CompletedProcess(
            args, 128, b"", b"fatal: Authorization: Basic c2VjcmV0dG9rZW4= rejected\n"
        )

    monkeypatch.setattr(git_source.subprocess, "run", fake_run)
    ref = parse_repo_spec("github.com/a/b", allowed_hosts=HOSTS)
    with pytest.raises(GitError) as exc:
        open_checkout(ref, token="secrettoken")
    assert not any("secrettoken" in a for a in seen["args"])
    assert "c2VjcmV0dG9rZW4" not in str(exc.value)
    header_keys = [k for k, v in seen["env"].items() if k.startswith("GIT_CONFIG_KEY_") and "extraHeader" in v]
    assert header_keys, "token should travel in GIT_CONFIG_* env"
    assert seen["env"][header_keys[0]].startswith("http.https://github.com/")  # host-scoped
    redirects = [v for k, v in seen["env"].items() if k.startswith("GIT_CONFIG_KEY_") and v == "http.followRedirects"]
    assert redirects


def test_raw_urls_pin_the_commit():
    sha = "a" * 40
    assert git_source.raw_file_url("https://github.com/o/r", sha, "x/y.py") == (
        f"https://raw.githubusercontent.com/o/r/{sha}/x/y.py"
    )
    assert git_source.raw_file_url("https://gitlab.com/g/p", sha, "a.go") == f"https://gitlab.com/g/p/-/raw/{sha}/a.go"
    assert git_source.raw_file_url("file:///tmp/x", sha, "a.go") is None
