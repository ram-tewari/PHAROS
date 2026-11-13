"""The Phase 3 evaluation harness (``benchmarks/agent_eval.py``, ``benchmarks/ccrab.py``): its pure parts.

No Docker, network, database or Claude binary: c-CRAB data, git repositories, agent runs and grades
are all synthetic here.
"""

import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND / "benchmarks"))

import agent_eval  # noqa: E402
import ccrab  # noqa: E402

# ── lock and data ───────────────────────────────────────────────────────


def test_the_real_lock_file_matches_the_protocol_hash():
    lock = ccrab.load_lock(agent_eval.LOCK)
    assert lock["counts"]["test"]["instances"] == 105
    assert sum(len(v) for v in lock["test"].values()) == 105
    assert sum(len(v) for v in lock["dev"].values()) == 50


def test_a_changed_lock_file_is_refused(tmp_path):
    copy = tmp_path / "ccrab_phase3.json"
    copy.write_bytes(agent_eval.LOCK.read_bytes().replace(b'"comments": 1', b'"comments": 2', 1))
    with pytest.raises(ccrab.LockError):
        ccrab.load_lock(copy)


def _ccrab_fixture(tmp_path):
    """A tiny c-CRAB copy and a lock file for it: one dev instance (two comments) and one test instance."""
    root = tmp_path / "ccrab"
    (root / ccrab.STAGE4).parent.mkdir(parents=True)
    (root / ccrab.TESTGEN_ZIP).parent.mkdir(parents=True)

    def row(iid, repo, pr, comments):
        return {"instance_id": iid, "repo": repo, "pull_number": pr, "created_at": "2022-01-02T00:00:00Z",
                "base_commit": "b" * 40, "commit_to_review": {"head_commit": "h" * 40},
                "merged_commit": "m" * 40, "title": f"PR {pr}", "body": "why",
                "reference_review_comments": [{"text": c} for c in comments]}

    rows = [row("o__dev-1@aaa", "o/dev", 1, ["first comment", "second comment"]),
            row("o__test-2@bbb", "o/test", 2, ["sealed comment"])]
    (root / ccrab.STAGE4).write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    with zipfile.ZipFile(root / ccrab.TESTGEN_ZIP, "w") as z:
        z.writestr("testgen_combined/o__dev-1@aaa/result.json", json.dumps({"results": [
            {"comment_text": "second comment", "success": True, "language": "python", "test_code": "T2"},
            {"comment_text": "first comment", "success": False, "language": "python", "test_code": "bad"},
            {"comment_text": "first comment", "success": True, "language": "javascript", "test_code": "T1"}]}))
        z.writestr("testgen_combined/o__test-2@bbb/result.json", json.dumps({"results": [
            {"comment_text": "sealed comment", "success": True, "language": "python", "test_code": "S"}]}))

    def entry(iid, pr, n):
        return {"instance_id": iid, "pull_number": pr, "created_at": "2022-01-02T00:00:00Z", "base_commit": "b" * 40,
                "head_commit": "h" * 40, "merged_commit": "m" * 40, "comments": n}

    lock = {"source": {"stage4_sha256": ccrab.sha256_file(root / ccrab.STAGE4),
                       "testgen_zip_sha256": ccrab.sha256_file(root / ccrab.TESTGEN_ZIP)},
            "dev": {"o/dev": [entry("o__dev-1@aaa", 1, 2)]}, "test": {"o/test": [entry("o__test-2@bbb", 2, 1)]},
            "reserve": {}}
    return root, lock


def test_sources_are_verified_and_tests_matched_as_ccrab_does(tmp_path):
    root, lock = _ccrab_fixture(tmp_path)
    ccrab.verify_sources(lock, root)
    [inst] = ccrab.load_instances(lock, root, "dev")
    assert inst.instance_id == "o__dev-1@aaa" and inst.title == "PR 1"
    # The first *verified* test with the comment's text, named by the comment's position.
    assert [(t.index, t.filename, t.language, t.code) for t in inst.tests] == [
        (0, "test_review_comment_0.test.js", "javascript", "T1"), (1, "test_review_comment_1.py", "python", "T2")]
    assert inst.image == "ghcr.io/c-crab-benchmark/o__dev-1"
    assert "sealed" not in repr(inst) and "T1" not in repr(inst)


def test_changed_sources_or_a_disagreeing_lock_are_refused(tmp_path):
    root, lock = _ccrab_fixture(tmp_path)
    bad = json.loads(json.dumps(lock))
    bad["dev"]["o/dev"][0]["head_commit"] = "x" * 40
    with pytest.raises(ccrab.LockError, match="disagree"):
        ccrab.load_instances(bad, root, "dev")
    with open(root / ccrab.STAGE4, "a") as handle:
        handle.write("\n")
    with pytest.raises(ccrab.LockError, match="SHA-256"):
        ccrab.verify_sources(lock, root)


# ── sealing ─────────────────────────────────────────────────────────────


def test_the_test_set_needs_the_locked_run_and_an_outside_path(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    ccrab.check_set_allowed("dev", locked_run=False, sealed_out=None, repo_root=repo)
    with pytest.raises(ccrab.SealedSetError):
        ccrab.check_set_allowed("test", locked_run=False, sealed_out=None, repo_root=repo)
    with pytest.raises(ccrab.SealedSetError):
        ccrab.check_set_allowed("test", locked_run=True, sealed_out=None, repo_root=repo)
    with pytest.raises(ccrab.SealedSetError, match="outside"):
        ccrab.check_set_allowed("test", locked_run=True, sealed_out=repo / "results.json", repo_root=repo)
    with pytest.raises(ccrab.SealedSetError):
        ccrab.check_set_allowed("reserve", locked_run=False, sealed_out=None, repo_root=repo)
    with pytest.raises(ccrab.SealedSetError):
        ccrab.check_set_allowed("dev", locked_run=True, sealed_out=tmp_path / "x.json", repo_root=repo)
    ccrab.check_set_allowed("test", locked_run=True, sealed_out=tmp_path / "x.json", repo_root=repo)


def test_the_cli_refuses_the_test_set_before_reading_any_data(tmp_path, capsys):
    out = tmp_path / "out.json"
    common = ["--ccrab", str(tmp_path / "missing"), "--out", str(out)]
    assert agent_eval.main(["run", "--set", "test", "--workdir", str(tmp_path), "--pg", "postgresql://x", *common]) == 2
    assert agent_eval.main(["gold", "--set", "test", *common]) == 2
    assert agent_eval.main(["run", "--set", "test", "--locked-run", "--sealed-out", str(BACKEND / "x.json"),
                            "--workdir", str(tmp_path), "--pg", "postgresql://x", *common]) == 2
    assert agent_eval.main(["run", "--set", "test", "--locked-run", "--sealed-out", str(out), "--arms", "P0,A",
                            "--workdir", str(tmp_path), "--pg", "postgresql://x", *common]) == 2
    assert "refused" in capsys.readouterr().err and not out.exists()


def test_test_rows_are_skipped_unread_when_loading_dev(tmp_path):
    root, lock = _ccrab_fixture(tmp_path)
    loaded = ccrab.load_instances(lock, root, "dev")
    assert [i.instance_id for i in loaded] == ["o__dev-1@aaa"]
    with pytest.raises(ccrab.SealedSetError):
        ccrab.load_instances(lock, root, "dev", {"o__test-2@bbb"})


def test_scratch_databases_only():
    pg = agent_eval.Postgres("postgresql+psycopg2://postgres@127.0.0.1:1")
    with pytest.raises(agent_eval.HarnessError):
        pg.create("production")
    assert agent_eval.db_name("o__x-1@abc", "B-new").startswith("pharos_bench_s1_")
    assert len(agent_eval.db_name("o__x-1@abc", "t0123456789")) < 64


def test_an_index_is_reused_only_from_the_same_repository_and_code(tmp_path, monkeypatch):
    def inst(iid, repo):
        return SimpleNamespace(instance_id=iid, repo=repo)

    a, b, c = inst("o__r-1@a", "o/r"), inst("o__r-2@b", "o/r"), inst("o__s-3@c", "o/s")
    ck = agent_eval.SafeCheckpoint(tmp_path / "ck.json")
    ck.put({"seconds": 1}, "instances", a.instance_id, "prep", "base_index", "k1")
    ck.put({"seconds": 1}, "instances", c.instance_id, "prep", "base_index", "k1")
    runner = SimpleNamespace(instances=[a, b, c], ck=ck, pg=SimpleNamespace(exists=lambda name: True))
    donor = agent_eval.Runner.index_donor
    assert donor(runner, b, "k1") == agent_eval.db_name(a.instance_id, "tk1")
    assert donor(runner, b, "k2") is None  # other indexing code
    assert donor(runner, inst("o__t-4@d", "o/t"), "k1") is None  # other repository


# ── history truncation ──────────────────────────────────────────────────


def _git(path, *args):
    return subprocess.run(["git", "-C", str(path), *args], capture_output=True, text=True, check=True).stdout.strip()


@pytest.fixture
def history(tmp_path):
    repo = tmp_path / "upstream"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "trunk")
    shas = []
    for i in range(4):
        (repo / "f.txt").write_text(f"v{i}\n")
        _git(repo, "add", "f.txt")
        _git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", f"c{i}")
        shas.append(_git(repo, "rev-parse", "HEAD"))
    _git(repo, "tag", "v-last", shas[-1])
    return repo, shas


def test_truncated_clone_holds_only_the_commit_and_its_ancestors(history, tmp_path):
    repo, shas = history
    dest = tmp_path / "clone"
    agent_eval.truncated_clone(repo, shas[1], dest)
    record = agent_eval.check_history(dest, shas[1], [shas[2], shas[3]])
    assert record["ok"] and record["commits"] == 2 and record["refs"] == 1
    assert (dest / "f.txt").read_text() == "v1\n"
    assert not agent_eval.has_object(dest, shas[3]) and agent_eval.has_object(dest, shas[0])
    assert _git(dest, "tag") == "" and _git(dest, "remote") == ""


def test_history_check_fails_when_a_later_commit_is_present(history, tmp_path):
    repo, shas = history
    dest = tmp_path / "clone"
    agent_eval.truncated_clone(repo, shas[1], dest)
    _git(dest, "fetch", "-q", str(repo), "trunk")
    with pytest.raises(agent_eval.HarnessError):
        agent_eval.check_history(dest, shas[1], [shas[3]])


def test_capture_diff_includes_new_files(history, tmp_path):
    repo, shas = history
    dest = tmp_path / "clone"
    agent_eval.truncated_clone(repo, shas[3], dest)
    (dest / "f.txt").write_text("v3\nmore\n")
    (dest / "new.py").write_text("a = 1\nb = 2\n")
    diff = agent_eval.capture_diff(dest, shas[3])
    assert diff["changed_lines"] == 3 and sorted(diff["files"]) == ["f.txt", "new.py"]
    assert "new file mode" in diff["patch"]


# ── the agent command and its outcome ───────────────────────────────────


def test_arms_differ_only_in_their_mcp_tools():
    server_tools = sorted(agent_eval.RETRIEVAL_TOOLS + agent_eval.PHASE2_MEMORY_TOOLS + ("list_repositories",))
    argv = {arm: agent_eval.agent_argv("claude", arm, Path("cfg.json"), [] if arm == "P0" else server_tools)
            for arm in agent_eval.ARMS}

    def without_tool_lists(a):
        a = list(a)
        for flag in ("--allowedTools", "--disallowedTools"):
            a[a.index(flag) + 1] = "*"
        return a

    assert len({json.dumps(without_tool_lists(a)) for a in argv.values()}) == 1
    p0 = argv["P0"]
    assert p0[p0.index("--tools") + 1] == "Read,Glob,Grep,Edit,Write"
    for flag in ("--restricted", "--strict-mcp-config", "--no-session-persistence", "-p"):
        assert flag in p0
    assert p0[p0.index("--model") + 1] == "claude-sonnet-5-5"
    a = argv["A"]
    denied = a[a.index("--disallowedTools") + 1].split(",")
    assert "Bash" in denied and "WebFetch" in denied and "mcp__pharos__search_memory" in denied
    assert "mcp__pharos__retrieve_context" in a[a.index("--allowedTools") + 1].split(",")
    assert "mcp__pharos__retrieve_context" not in denied


def test_the_prompt_is_the_pr_text_and_the_fixed_instruction():
    inst = SimpleNamespace(repo="o/r", title="Add X", body="Because Y.")
    prompt = agent_eval.agent_prompt(inst)
    assert prompt.endswith(agent_eval.INSTRUCTION) and "Add X" in prompt and "Because Y." in prompt
    assert "diff" not in prompt


def _stream(tools, result=None, mcp="connected"):
    lines = [json.dumps({"type": "system", "subtype": "init", "tools": tools,
                         "mcp_servers": [{"name": "pharos", "status": mcp}], "model": "claude-sonnet-5-5"}),
             json.dumps({"type": "assistant", "message": {"content": [
                 {"type": "tool_use", "name": "mcp__pharos__retrieve_context", "input": {}},
                 {"type": "tool_use", "name": "Read", "input": {}}]}})]
    if result:
        lines.append(json.dumps({"type": "result", **result}))
    return agent_eval.parse_stream(lines)


def test_outcomes_are_classified():
    tools_a = agent_eval.expected_tools("A")
    ok = _stream(tools_a, {"subtype": "success", "is_error": False, "num_turns": 7,
                           "usage": {"input_tokens": 5, "output_tokens": 9, "cache_read_input_tokens": 100}})
    assert agent_eval.classify(ok, 0, "", "A")["status"] == "ok"
    assert ok["tool_calls"] == {"mcp__pharos__retrieve_context": 1, "Read": 1}
    assert agent_eval.usage_of(ok["result"])["total_tokens"] == 114
    turns = _stream(tools_a, {"subtype": "error_max_turns", "is_error": False})
    assert agent_eval.classify(turns, 1, "", "A") == {"status": "ok", "reason": "max turns", "pause": False}
    limit = _stream(tools_a, {"subtype": "success", "is_error": True, "result": "Claude usage limit reached"})
    assert agent_eval.classify(limit, 1, "", "A")["pause"] is True
    assert agent_eval.classify(_stream(tools_a), 1, "boom", "A")["status"] == "infra"
    assert agent_eval.classify(_stream(tools_a, {"subtype": "success"}, mcp="failed"), 0, "", "A")["status"] == "infra"
    with pytest.raises(agent_eval.HarnessError):
        agent_eval.classify(_stream(tools_a + ["Bash"], {"subtype": "success"}), 0, "", "A")
    with pytest.raises(agent_eval.HarnessError):
        agent_eval.classify(_stream(tools_a, {"subtype": "success"}), 0, "", "P0")


# ── leakage ─────────────────────────────────────────────────────────────


def test_leakage_check(tmp_path):
    inst = SimpleNamespace(created_at="2022-05-01T00:00:00Z", pull_number=7, base_commit="b" * 40)
    cache = tmp_path / "cache" / "o_r"
    cache.mkdir(parents=True)
    early = {"url": "u1", "pr": 3, "created_at": "2022-01-01T00:00:00Z"}
    (cache / "review_comments.json").write_text(json.dumps([early]))
    evidence = [[{"kind": "review", "url": "u1", "pr": 3}, {"kind": "commit", "sha": "a" * 40}]]
    ok = agent_eval.leakage_check(inst, evidence, ["b" * 40], tmp_path / "cache", lambda s: True)
    assert ok["passed"] and ok["readable_reviews"] == 1 and ok["cited_commits"] == 1
    later = agent_eval.leakage_check(inst, evidence, ["b" * 40], tmp_path / "cache", lambda s: False)
    assert not later["passed"]
    own = [[{"kind": "review", "url": "u9", "pr": 7}]]
    assert not agent_eval.leakage_check(inst, own, ["b" * 40], tmp_path / "cache", lambda s: True)["passed"]
    (cache / "review_comments.json").write_text(json.dumps([early, {"url": "u2", "pr": 4,
                                                                    "created_at": "2022-06-01T00:00:00Z"}]))
    assert not agent_eval.leakage_check(inst, evidence, ["b" * 40], tmp_path / "cache", lambda s: True)["passed"]
    assert not agent_eval.leakage_check(inst, [], ["c" * 40], tmp_path / "nothing", lambda s: True)["passed"]
    assert agent_eval.seed_reviews([early, {"pr": 7, "created_at": "2022-01-01"}, {"pr": 1, "created_at": "2023"}],
                                   inst.created_at, 7) == [early]


# ── scoring and the bootstrap ───────────────────────────────────────────


def _synthetic(shares: dict[str, list[float]], repos: list[str], tests: int = 2, lines=None, missing=()):
    meta = {f"i{k}": {"repo": repos[k], "tests": tests} for k in range(len(repos))}
    data = {"instances": {}}
    for arm, values in shares.items():
        for k, share in enumerate(values):
            iid = f"i{k}"
            if (iid, arm) in missing:
                continue
            passed = round(share * tests)
            node = data["instances"].setdefault(iid, {"grade": {}, "agent": {}})
            node["grade"][arm] = {"tests": {str(t): {"passed": t < passed} for t in range(tests)}}
            node["agent"][arm] = {"changed_lines": (lines or {}).get(arm, 10), "wall_s": 60.0, "reason": "completed",
                                  "tool_calls": {"mcp__pharos__search_code": 2} if arm != "P0" else {},
                                  "usage": {"total_tokens": 1000, "output_tokens": 100, "num_turns": 5,
                                            "cost_usd": 0.5}}
    return data, meta


def test_report_measures_on_synthetic_data():
    repos = ["r1", "r1", "r2", "r2", "r3", "r3", "r4", "r4"]
    shares = {"P0": [0, 0, 0, 0, 0, 0, 0, 0], "A": [0, 0.5, 0, 0, 0.5, 0, 0, 0],
              "B-old": [0, 0.5, 0, 0, 0.5, 0, 0, 0], "B-new": [1, 0.5, 0.5, 0.5, 1, 0.5, 0.5, 0.5]}
    data, meta = _synthetic(shares, repos, lines={"A": 10, "B-new": 20})
    out = agent_eval.report(data, meta, list(agent_eval.ARMS))
    primary = out["measure_1"]
    assert primary["complete"] and primary["passes"]
    assert primary["difference"]["delta"] == pytest.approx(0.5)
    assert primary["difference"]["ci95"][0] > 0 and primary["difference"]["n"] == 8
    assert out["arms"]["B-new"]["comments_resolved"] == 10 and out["arms"]["B-new"]["comments"] == 16
    assert out["measure_4_guard"] == {"median_changed_lines": {"A": 10, "B-new": 20}, "passes": True}
    loro = out["measure_8_leave_one_repository_out"]
    assert set(loro["by_repository_removed"]) == {"r1", "r2", "r3", "r4"}
    assert loro["range"][0] <= 0.5 <= loro["range"][1]
    assert out["differences"]["A - P0"]["delta"] == pytest.approx(0.125)
    assert out["arms"]["A"]["pharos_tool_calls"] == 16 and out["arms"]["P0"]["pharos_tool_calls"] == 0
    assert out["arms"]["A"]["cost_usd"]["total"] == 4.0
    assert out["verdict"].startswith("measures 1 and 4 pass")


def test_bootstrap_is_paired_with_5000_resamples_and_seed_1():
    a, b = [1.0, 0.0, 0.5, 1.0], [0.0, 0.0, 0.5, 0.5]
    first, second = agent_eval.paired_delta(a, b), agent_eval.paired_delta(a, b)
    assert first == second and first["delta"] == pytest.approx(0.375)
    assert first["wins"] == 2 and first["losses"] == 0
    assert agent_eval.paired_delta(a, b, n=5000, seed=1) == first


def test_incomplete_runs_and_failed_guards_have_no_pass():
    repos = ["r1", "r2", "r3"]
    shares = {"A": [0, 0, 0], "B-new": [1, 1, 1]}
    data, meta = _synthetic(shares, repos, lines={"A": 4, "B-new": 9}, missing=[("i2", "B-new")])
    out = agent_eval.report(data, meta, ["A", "B-new"])
    assert not out["measure_1"]["complete"] and not out["measure_1"]["passes"]
    assert out["verdict"] == "no verdict: the run is incomplete"
    assert out["measure_4_guard"]["passes"] is False  # 9 > 2 * 4
    assert agent_eval.resolved_share({"tests": {}, "no_change": True}, 3) == 0.0


# ── checkpoint and resume ───────────────────────────────────────────────


def test_checkpoint_writes_are_atomic_and_reload(tmp_path):
    path = tmp_path / "ck.json"
    ck = agent_eval.SafeCheckpoint(path)
    ck.put({"x": 1}, "instances", "i1", "agent", "A")
    ck.append({"reason": "r"}, "instances", "i1", "infra", "A")
    again = agent_eval.SafeCheckpoint(path)
    assert again.get("instances", "i1", "agent", "A") == {"x": 1}
    assert len(again.get("instances", "i1", "infra", "A")) == 1
    assert not (tmp_path / "ck.json.tmp").exists()


def test_rerunning_resumes_without_repeating_a_call(history, tmp_path, monkeypatch):
    repo, shas = history
    inst = ccrab.Instance(instance_id="o__r-1@abc", repo="o/r", pull_number=1, created_at="2022",
                          base_commit=shas[2], head_commit=shas[3], merged_commit="m" * 40, title="t", body="b",
                          tests=[ccrab.CommentTest(0, "test_review_comment_0.py", "python", "code")])
    calls = {"agent": 0, "grade": 0}
    outcomes = iter(["infra", "ok", "ok"])

    def fake_run_agent(claude, arm, inst, checkout, server, transcript, **kw):
        calls["agent"] += 1
        status = next(outcomes)
        (checkout / "f.txt").write_text("changed\n")
        return {"status": status, "reason": "network" if status == "infra" else "completed", "pause": False,
                "wall_s": 1.0, "usage": {"num_turns": 3, "total_tokens": 10, "output_tokens": 2, "cost_usd": 0.0},
                "tool_calls": {}, "init": None}

    class FakeBox:
        def __init__(self, image):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            pass

    def fake_grade(box, commit, tests, patch=None):
        calls["grade"] += 1
        assert commit == shas[3] and "changed" in patch
        return {"tests": {"0": {"passed": True}}, "error": None}

    monkeypatch.setattr(agent_eval, "run_agent", fake_run_agent)
    monkeypatch.setattr(ccrab, "pull_image", lambda image: 0.0)
    monkeypatch.setattr(ccrab, "Container", FakeBox)
    monkeypatch.setattr(ccrab, "grade", fake_grade)

    def fresh_checkout(self, inst, arm):
        dest = tmp_path / "agent" / arm / "r"
        agent_eval.truncated_clone(repo, shas[3], dest)
        return dest

    monkeypatch.setattr(agent_eval.Runner, "checkouts", lambda self, inst: None)
    monkeypatch.setattr(agent_eval.Runner, "agent_checkout", fresh_checkout)
    args = SimpleNamespace(arms=["P0"], workdir=str(tmp_path / "work"), code=None, pg="postgresql://u@h:1",
                           claude="claude", embedder="hash", model=agent_eval.MODEL, max_turns=5, infra_attempts=3,
                           pr_diff=False, remove_images=False, mirrors=str(tmp_path))
    out = tmp_path / "run.json"

    def run():
        ck = agent_eval.SafeCheckpoint(out)
        return agent_eval.Runner(args, [inst], ck, sealed=False).run(), ck

    code, ck = run()  # the first run hits an infrastructure failure: no result, nothing graded
    assert code == 0 and calls == {"agent": 1, "grade": 0}
    assert len(ck.get("instances", inst.instance_id, "infra", "P0")) == 1
    code, ck = run()  # the rerun repeats the failed run, then grades it
    assert calls == {"agent": 2, "grade": 1}
    assert ck.get("instances", inst.instance_id, "grade", "P0")["tests"]["0"]["passed"]
    assert ck.get("report")["arms"]["P0"]["resolved_share"] == 1.0
    code, ck = run()  # nothing left: no call is repeated
    assert calls == {"agent": 2, "grade": 1}


def test_gold_status():
    tests = [ccrab.CommentTest(0, "a.py", "python", ""), ccrab.CommentTest(1, "b.py", "python", "")]
    fail = {"tests": {"0": {"passed": False}, "1": {"passed": False}}, "error": None}
    passed = {"tests": {"0": {"passed": True}, "1": {"passed": True}}, "error": None}
    assert ccrab.gold_status(fail, passed, tests)["reproduced"]
    half = {"tests": {"0": {"passed": True}, "1": {"passed": False}}, "error": None}
    assert not ccrab.gold_status(half, passed, tests)["reproduced"]
    assert not ccrab.gold_status(fail, half, tests)["reproduced"]
    assert not ccrab.gold_status(fail, {"tests": {}, "error": "git checkout failed"}, tests)["reproduced"]
    assert ccrab.test_command(tests[0], "/workspace/a.py") == (
        "python -m pytest /workspace/a.py -x -v --tb=short --no-header -c /dev/null -p no:cacheprovider")
    assert hashlib.sha256(b"").hexdigest() != ccrab.LOCK_SHA256
