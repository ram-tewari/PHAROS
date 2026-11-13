"""Activation by hold-out: what the writer does with a backtest record, and what recall serves."""

import pytest
from sqlalchemy import select

from app.database.models import MemoryItem, Repository
from app.learning.checks import Activation, Companion, Paths
from app.learning.memory import Candidate, MemoryWriter, set_status
from app.learning.recall import item_to_dict, memory_for_context, search_memory

ACT = Activation(window=200, min_applied=10, min_lower=0.7, observe_lower=0.2)
WINDOW = {"from": "a" * 12, "to": "b" * 12, "commits": 200}


def _check(partner: str) -> dict:
    return Companion(when=Paths(globs=("src/a.py",)), then=Paths(globs=(partner,))).to_json()


def _cand(key: str, partner: str = "CHANGES.md", **kw) -> Candidate:
    return Candidate(key=key, kind="co_change", title=key, body=f"{key} body.", support=20, confidence=0.9,
                     evidence=[{"kind": "commit", "sha": "c" * 40, "date": "2026-01-01", "subject": "x"}],
                     source="history", scope={"paths": ["src/a.py"]}, eligible=True, check=_check(partner), **kw)


def _record(partner: str, applied: int, held: int) -> dict:
    return {"check": _check(partner), "applied": applied, "held": held, "window": WINDOW,
            "counter_examples": [{"sha": "d" * 12, "date": "2026-02-01", "subject": "missed it"}]}


@pytest.fixture
def repo(session):
    row = Repository(url="https://example.com/o/r", name="r", repo_metadata={}, last_commit_sha="e" * 40)
    session.add(row)
    session.commit()
    return row


def _items(session, repo) -> dict[str, MemoryItem]:
    return {i.key: i for i in session.execute(select(MemoryItem).where(MemoryItem.repository_id == repo.id)).scalars()}


def _learn(session, repo, holdout, run="run-1", commit="e" * 40):
    writer = MemoryWriter(session, repo.id, commit, run, holdout=holdout, activation=ACT)
    writer.apply([_cand("cochange/requirement"), _cand("cochange/observation"), _cand("cochange/untested"),
                  _cand("cochange/failed"), _cand("cochange/changed"),
                  Candidate(key="history/origin/src/a.py", kind="history", title="Origin", body="Added in x.",
                            evidence=[{"kind": "commit", "sha": "c" * 40, "date": "2026-01-01", "subject": "x"}],
                            support=1, confidence=1.0, source="history", eligible=True)])
    session.commit()
    return writer


HOLDOUT = {"cochange/requirement": _record("CHANGES.md", 40, 39), "cochange/observation": _record("CHANGES.md", 40, 18),
           "cochange/untested": _record("CHANGES.md", 3, 3), "cochange/failed": _record("CHANGES.md", 40, 2),
           "cochange/changed": _record("src/other.py", 40, 40)}


def test_status_and_strength_come_from_the_holdout_record(session, repo):
    writer = _learn(session, repo, HOLDOUT)
    items = _items(session, repo)
    got = {k: (i.status, i.strength, (i.holdout or {}).get("outcome")) for k, i in items.items()}
    assert got == {
        "cochange/requirement": ("active", "requirement", "requirement"),
        "cochange/observation": ("active", "observation", "observation"),  # 45 %: information, not a rule
        "cochange/untested": ("proposed", "observation", "untested"),
        "cochange/failed": ("stale", "observation", "failed"),
        "cochange/changed": ("proposed", "observation", "changed"),
        "history/origin/src/a.py": ("active", "advisory", None),  # not checkable: the old path, advisory
    }
    req = items["cochange/requirement"]
    assert req.predicate == _check("CHANGES.md") and (req.holdout["applied"], req.holdout["held"]) == (40, 39)
    assert req.holdout["counter_examples"][0]["subject"] == "missed it"
    assert req.holdout["activation"]["min_applied"] == 10
    assert "applied 40 times and held 39 times" in req.body  # the text says what was measured
    assert "applied" not in items["cochange/changed"].body  # a record for another rule proves nothing
    assert items["cochange/failed"].invalidated_at_commit == "e" * 40 and "held 2 times" in \
        items["cochange/failed"].holdout["reason"]
    assert (req.served, req.complied, req.helped) == (0, 0, 0)
    assert writer.stats.outcomes == {"requirement": 1, "observation": 1, "untested": 1, "failed": 1, "changed": 1}
    full = item_to_dict(req, full=True)
    assert full["strength"] == "requirement" and full["rule"].startswith("A change of at most 30 files")


def test_without_a_backtest_nothing_checkable_is_active(session, repo):
    _learn(session, repo, None)
    items = _items(session, repo)
    assert {i.status for k, i in items.items() if k.startswith("cochange/")} == {"proposed"}
    assert items["history/origin/src/a.py"].status == "active"


def test_human_decisions_win_over_the_backtest(session, repo):
    _learn(session, repo, HOLDOUT)
    items = _items(session, repo)
    set_status(session, items["cochange/failed"], "accept")
    set_status(session, items["cochange/requirement"], "reject")
    session.commit()
    _learn(session, repo, HOLDOUT, run="run-2", commit="f" * 40)
    items = _items(session, repo)
    assert (items["cochange/failed"].status, items["cochange/failed"].strength) == ("active", "requirement")
    assert items["cochange/requirement"].status == "rejected"


def test_observations_are_served_on_request_only(session, repo):
    _learn(session, repo, HOLDOUT)
    chunks = [{"path": "src/a.py", "rank": 1, "language": "python", "repository": {"id": str(repo.id)}}]
    served = {i["key"] for i in memory_for_context(session, [repo], chunks, "change a")["items"]}
    assert "cochange/requirement" in served and "cochange/observation" not in served
    found = {r["key"]: r for r in search_memory(session, None, "cochange observation body", [repo.id], k=20)}
    assert found["cochange/observation"]["strength"] == "observation"
    assert found["cochange/requirement"]["rule"].endswith("also touches CHANGES.md.")
