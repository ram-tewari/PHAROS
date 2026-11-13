"""The time-split backtest on a small synthetic repository built in a temp directory.

Before the split, ``a.py`` changes with ``b.py``, ``c.py`` with ``d.py`` and ``e.py`` with ``f.py``.
After it, ``a.py`` keeps changing with ``b.py`` (and is renamed on the way), ``c.py`` changes alone, and
``e.py`` changes only twice.
"""

import os
import subprocess

import pytest

from app.learning.backtest import (
    following,
    holdout_records,
    holdout_window,
    load_changes,
    protocol_precision,
    under_learned_names,
)
from app.learning.checks import Activation, Message, decide


def _git(cwd, *args):
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com", GIT_COMMITTER_NAME="t",
               GIT_COMMITTER_EMAIL="t@example.com")
    return subprocess.run(["git", *args], cwd=cwd, env=env, check=True, capture_output=True, text=True).stdout


class Repo:
    def __init__(self, path):
        self.path = path
        self.n = 0
        _git(path, "init", "-q", "-b", "main")

    def touch(self, *names, message=None):
        for name in names:
            target = self.path / name
            old = target.read_text() if target.exists() else "".join(
                f"def {name[0]}_helper_{i}(value):\n    return value + {i}\n\n\n" for i in range(12))
            self.n += 1
            target.write_text(old + f"def {name[0]}_change_{self.n}(value):\n    return value\n\n\n")
        _git(self.path, "add", "-A")
        _git(self.path, "commit", "-q", "-m", message or f"change {' '.join(names)} ({self.n})")
        return self.head

    def rename(self, old, new, *also):
        _git(self.path, "mv", old, new)
        return self.touch(*also, message=f"rename {old} to {new}")

    @property
    def head(self):
        return _git(self.path, "rev-parse", "HEAD").strip()


SPLIT_AT = 35  # commits in the learning phase, the first one included
WINDOW = 26


@pytest.fixture(scope="module")
def repo(tmp_path_factory):
    r = Repo(tmp_path_factory.mktemp("synthetic"))
    r.touch("a.py", "b.py", "c.py", "d.py", "e.py", "f.py", "g.py", message="initial")
    for i in range(12):
        r.touch("a.py", "b.py")
        r.touch("c.py", "d.py")
        if i < 10:
            r.touch("e.py", "f.py")
    r.split = r.head
    for _ in range(10):
        r.touch("a.py", "b.py")  # still holds
        r.touch("c.py")  # stops holding
    r.rename("a.py", "a2.py", "b.py")  # the rule follows the file under its new name
    r.touch("a2.py", "b.py")
    r.touch("e.py", "f.py")  # rarely applies
    r.touch("e.py", "f.py")
    r.touch("g.py")
    r.touch("g.py")
    return r


def test_the_window_is_counted_on_the_first_parent_chain(repo):
    split, shas = holdout_window(repo.path, repo.head, WINDOW)
    assert split == repo.split and len(shas) == WINDOW and shas[-1] == repo.head
    assert following(repo.path, repo.split, 5) == shas[:5]
    # A short chain gets half of it.
    split, shas = holdout_window(repo.path, repo.split, 200)
    assert len(shas) == (SPLIT_AT - 1) // 2


def test_backtest_records_rules_that_hold_stop_holding_or_rarely_apply(repo):
    records, summary = holdout_records(repo.path, repo.head, WINDOW, families=["cochange"])
    assert summary["split"] == repo.split[:12] and summary["commits"] == WINDOW
    held = records["cochange/a.py"]
    assert held["check"]["then"] == {"globs": ["b.py"]}
    assert (held["applied"], held["held"]) == (12, 12)  # 10 plain, the rename, one under the new name
    stopped = records["cochange/c.py"]
    assert (stopped["applied"], stopped["held"]) == (10, 0)
    assert len(stopped["counter_examples"]) == 5 and stopped["counter_examples"][0]["subject"].startswith("change c.py")
    rare = records["cochange/e.py"]
    assert (rare["applied"], rare["held"]) == (2, 2)
    act = Activation(window=WINDOW, min_applied=5, min_lower=0.6, observe_lower=0.2)
    assert decide(held["check"], held, act).strength == "requirement"
    assert decide(stopped["check"], stopped, act).status == "stale"
    assert decide(rare["check"], rare, act).outcome == "untested"  # held twice: proves little
    assert held["window"] == {"from": repo.split[:12], "to": repo.head[:12], "commits": WINDOW}


def test_renames_in_the_window_map_back_to_learned_names(repo):
    _, shas = holdout_window(repo.path, repo.head, WINDOW)
    raw = load_changes(repo.path, shas)
    mapped = under_learned_names(raw)
    after = [c for c in raw if "a2.py" in c.touched()]
    assert after and all("a.py" in m.touched() for m, c in zip(mapped, raw, strict=True) if c in after)


def test_protocol_precision_pools_active_requirements(repo):
    act = Activation(window=10, min_applied=3, min_lower=0.4, observe_lower=0.1)
    result = protocol_precision(repo.path, repo.split, n=WINDOW, activation=act, families=["cochange"])
    assert result["later_commits"] == WINDOW
    rules = {r["key"]: r for r in result["rules"]}
    assert (rules["cochange/c.py"]["applied"], rules["cochange/c.py"]["held"]) == (10, 0)
    after = [r for r in result["rules"] if r["status"] == "active" and r["strength"] == "requirement"]
    assert result["after"]["active"] == len(after)
    assert result["after"]["applied"] == sum(r["applied"] for r in after)
    assert result["after"]["held"] == sum(r["held"] for r in after)
    before = [r for r in result["rules"] if r["eligible"]]
    assert result["before"]["applied"] == sum(r["applied"] for r in before)


def test_a_merge_is_one_change_against_its_first_parent(tmp_path):
    r = Repo(tmp_path)
    r.touch("a.py", "b.py", message="initial")
    _git(r.path, "checkout", "-q", "-b", "topic")
    r.touch("a.py", message="topic: one")
    r.touch("b.py", message="topic: two")
    _git(r.path, "checkout", "-q", "main")
    r.touch("c.py", message="main: c")
    _git(r.path, "merge", "-q", "--no-ff", "-m", "Merge branch 'topic'", "topic")
    [merge] = load_changes(r.path, [r.head])
    assert merge.merge and merge.touched() == {"a.py", "b.py"} and merge.lines
    assert Message(label="x", subject="^topic").evaluate(merge) is None  # merge messages are not the author's
