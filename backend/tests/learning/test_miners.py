"""L1 miner building blocks: pure functions, no database."""

import pytest

from app.learning.miners import (
    _deps_go,
    _deps_npm,
    _deps_python,
    _params,
    _test_pattern,
    addition_pattern,
    case_style,
)
from app.learning.recall import glob_match


@pytest.mark.parametrize("name,style", [
    ("verify_password", "snake_case"), ("_make_timedelta", "snake_case"), ("TokenSigner", "PascalCase"),
    ("createInstance", "camelCase"), ("MAX_RETRIES", "UPPER_SNAKE"), ("Curl_easy_init", "Prefixed_snake"),
    ("run", None), ("URL", None), ("__init__", None),
])
def test_case_style(name, style):
    assert case_style(name) == style


def test_python_dependencies_ignore_environment_markers():
    text = '''[project]
dependencies = [
    "click>=8.1",
    "importlib-metadata>=3.6; python_version < '3.10'",
]
requires-python = ">=3.10"
'''
    deps, runtime = _deps_python(text)
    assert deps == {"click", "importlib-metadata"} and runtime == ">=3.10"


def test_go_and_npm_manifests():
    deps, go = _deps_go("module x\n\ngo 1.15\n\nrequire (\n\tgithub.com/spf13/pflag v1.0.5\n"
                        "\tgolang.org/x/sys v0.1.0 // indirect\n)\n")
    assert deps == {"github.com/spf13/pflag"} and go == "1.15"
    deps, node = _deps_npm('{"dependencies": {"a": "1"}, "peerDependencies": {"b": "2"}, "engines": {"node": ">=22"}}')
    assert deps == {"a", "b"} and node == ">=22"


def test_annotated_parameters():
    sig = "def f(self, a: int, b=1, *args: str, c: dict[str, int] = {}, **kw) -> None:"
    assert _params(sig) == ["a: int", "b=1", "*args: str", "c: dict[str, int] = {}", "**kw"]


@pytest.mark.parametrize("path,pattern", [
    ("tests/test_options.py", "tests/test_*.py"), ("command_test.go", "*_test.go"),
    ("test/hooks.ts", "test/*.ts"), ("tests/data/test1623", "tests/data/testN"),
    ("source/core.test.ts", "source/*.test.ts"),
])
def test_test_patterns(path, pattern):
    assert _test_pattern(path) == pattern


@pytest.mark.parametrize("path,pattern", [
    ("docs/libcurl/opts/CURLOPT_SSL_SIGNATURE_ALGORITHMS.md", "docs/libcurl/opts/CURLOPT_*.md"),
    ("tests/data/test1623", "tests/data/testN"), ("source/errors/TimeoutError.ts", "source/errors/*.ts"),
    ("tests/test_cart.py", "tests/test_*.py"),
])
def test_addition_patterns(path, pattern):
    assert addition_pattern(path) == pattern


@pytest.mark.parametrize("pattern,path,ok", [
    ("src/click/core.py", "src/click/core.py", True), ("src/**", "src/click/core.py", True),
    ("docs/libcurl/opts/CURLOPT_*.md", "docs/libcurl/opts/CURLOPT_URL.md", True),
    ("docs/*.md", "docs/libcurl/x.md", False), ("**/test_*.py", "test_a.py", True),
    ("tests/data/test*", "tests/data/test12", True), ("lib/*.c", "lib/vtls/openssl.c", False),
])
def test_glob_match(pattern, path, ok):
    assert glob_match(pattern, path) is ok
