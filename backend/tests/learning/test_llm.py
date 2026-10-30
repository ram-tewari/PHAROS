"""The Codex CLI adapter, against a fake ``codex`` binary (no network, no login)."""

import json
import stat
import sys
import textwrap

import pytest

from app.learning.llm import CodexCLI, LLMUnavailable, drop_nulls, openai_strict

FAKE = textwrap.dedent("""\
    #!{python}
    import json, os, sys, time
    args = sys.argv[1:]
    if args[:2] == ["login", "status"]:
        print(os.environ.get("FAKE_LOGIN", "Logged in using ChatGPT")); sys.exit(0)
    if args[:2] == ["features", "list"]:
        print("shell_tool  stable  true"); print("apps  stable  true"); print("goals  stable  true"); sys.exit(0)
    assert args[0] == "exec"
    prompt = sys.stdin.read()
    if "SLOW" in prompt:
        time.sleep(30)
    out = args[args.index("-o") + 1]
    record = {{"argv": args, "prompt": prompt, "openai_key_seen": "OPENAI_API_KEY" in os.environ,
              "schema": json.load(open(args[args.index("--output-schema") + 1]))}}
    json.dump({{"answer": "ok", "extra": None, "record": json.dumps(record)}}, open(out, "w"))
    print(json.dumps({{"type": "turn.completed", "usage": {{"input_tokens": 11, "output_tokens": 3}}}}))
    """)

SCHEMA = {"type": "object", "properties": {"answer": {"type": "string"}, "extra": {"type": "string"},
                                           "record": {"type": "string"}}, "required": ["answer"]}


@pytest.fixture
def codex(tmp_path, monkeypatch):
    path = tmp_path / "codex"
    path.write_text(FAKE.format(python=sys.executable))
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-should-never-reach-codex")
    return str(path)


def test_exec_is_hardened_and_never_sees_an_api_key(codex):
    llm = CodexCLI(path=codex, timeout=20)
    result = llm.complete("Be brief.", "the secret prompt", SCHEMA)
    assert result["answer"] == "ok" and "extra" not in result  # nulls dropped
    record = json.loads(result["record"])
    argv = record["argv"]
    for flag in ("--ephemeral", "--ignore-user-config", "--ignore-rules", "--skip-git-repo-check", "--json"):
        assert flag in argv
    assert argv[argv.index("-s") + 1] == "read-only"
    # Only features this CLI reports are disabled (an unknown name could fail the command).
    assert [argv[i + 1] for i, a in enumerate(argv) if a == "--disable"] == ["shell_tool", "apps", "goals"]
    assert "the secret prompt" in record["prompt"] and not any("secret" in a for a in argv)
    assert record["openai_key_seen"] is False
    assert record["schema"]["additionalProperties"] is False
    assert llm.usage.calls == 1 and llm.usage.input_tokens == 11 and llm.usage.output_tokens == 3


def test_not_ready_without_a_chatgpt_login(codex, monkeypatch):
    monkeypatch.setenv("FAKE_LOGIN", "Logged in using an API key")
    with pytest.raises(LLMUnavailable):
        CodexCLI(path=codex).complete("x", "y", SCHEMA)


def test_call_budget_and_timeout(codex):
    llm = CodexCLI(path=codex, timeout=20, max_calls=1)
    llm.complete("x", "y", SCHEMA)
    with pytest.raises(LLMUnavailable, match="budget"):
        llm.complete("x", "y", SCHEMA)
    slow = CodexCLI(path=codex, timeout=1)
    with pytest.raises(LLMUnavailable, match="timed out"):
        slow.complete("x", "SLOW", SCHEMA)
    assert slow.usage.failures == 1


def test_missing_binary_is_unavailable(tmp_path):
    with pytest.raises(LLMUnavailable):
        CodexCLI(path=str(tmp_path / "nope")).complete("x", "y", SCHEMA)


def test_openai_strict_requires_every_property_and_round_trips_nulls():
    strict = openai_strict({"type": "object", "properties": {"a": {"type": "string"}, "b": {"const": "x"}},
                            "required": ["a"]})
    assert strict["required"] == ["a", "b"] and strict["additionalProperties"] is False
    assert strict["properties"]["b"] == {"type": ["string", "null"], "enum": ["x", None]}
    assert drop_nulls({"a": "1", "b": None, "c": [{"d": None}]}) == {"a": "1", "c": [{}]}
