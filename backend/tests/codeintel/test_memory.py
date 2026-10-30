"""Phase 2 learning: mining, incremental updates, grounding, context, jobs, API and MCP.

Runs on SQLite and (with PHAROS_TEST_DATABASE_URL) PostgreSQL. The fixture
repository gets a small history first: ``shop/auth.py`` changes together
with ``CHANGES.md`` and its test eight times, and five plugins are added the
same way (a playbook).
"""

import json

import pytest
from sqlalchemy import func, select

from app.codeintel import jobs
from app.codeintel.context import ContextRequest, assemble_context
from app.codeintel.git_source import parse_repo_spec
from app.codeintel.indexer import CodeIndexer
from app.database.models import LearningJob, MemoryItem, MemoryLedger, MemorySkill, RepoBrief, Repository
from app.learning.brief import BRIEF_CHARS
from app.learning.memory import Candidate, MemoryWriter, check_evidence, rollback_run, set_status
from app.learning.pipeline import learn_repository, queue_unlearned, run_learning_job, submit_learning
from app.learning.recall import search_memory
from tests.codeintel.conftest import ADMIN_TOKEN, READ_TOKEN, auth


def _grow_history(repo) -> None:
    repo.write("CHANGES.md", "# Changes\n\n## Version 1.0\n\n- Initial release. #1\n")
    repo.write("tests/test_auth.py", "def test_hash():\n    assert True\n")
    repo.commit("Add changelog and auth test")
    auth = (repo.path / "shop" / "auth.py").read_text()
    for i in range(8):
        auth += f"\n\ndef helper_{i}(value: int) -> int:\n    \"\"\"Helper {i}.\"\"\"\n    return value + {i}\n"
        repo.write("shop/auth.py", auth)
        repo.write("CHANGES.md", (repo.path / "CHANGES.md").read_text() + f"- Change {i}. #{i + 2}\n")
        if i < 6:
            repo.write("tests/test_auth.py", (repo.path / "tests/test_auth.py").read_text()
                       + f"\n\ndef test_helper_{i}():\n    assert True\n")
        repo.commit(f"auth: add helper {i}")
    init = (repo.path / "shop" / "__init__.py").read_text()
    for i in range(5):
        repo.write(f"shop/plugins/plugin_{i}.py", f"def run_plugin_{i}() -> None:\n    \"\"\"Plugin {i}.\"\"\"\n")
        init += f"\n# plugin {i}\n"
        repo.write("shop/__init__.py", init)
        repo.write("CHANGES.md", (repo.path / "CHANGES.md").read_text() + f"- Plugin {i}. #{i + 20}\n")
        repo.commit(f"plugins: add plugin {i}")


@pytest.fixture
def learned(session, fixture_repo, embedder):
    _grow_history(fixture_repo)
    ref = parse_repo_spec(str(fixture_repo.path), allowed_hosts=[], allow_local=True)
    CodeIndexer(session, embedder).index(ref)
    repo = session.execute(select(Repository).where(Repository.url == ref.canonical_url)).scalar_one()
    stats = learn_repository(session, repo, checkout=fixture_repo.path, mirror=fixture_repo.path,
                             commit=repo.last_commit_sha, embedder=embedder)
    return repo, stats


def _item(session, repo, key):
    return session.execute(select(MemoryItem).where(MemoryItem.repository_id == repo.id,
                                                    MemoryItem.key == key)).scalar_one_or_none()


def test_learning_mines_grounded_memory_and_a_brief(session, learned, fixture_repo):
    repo, stats = learned
    assert stats["ungrounded"] == 0 and stats["added"] > 0
    assert stats["embedded"] == stats["added"] - stats["skills"]  # items are embedded, playbooks are not

    cochange = _item(session, repo, "cochange/shop/auth.py")
    assert cochange.status == "active" and cochange.scope == {"paths": ["shop/auth.py"]}
    assert "CHANGES.md 89%" in cochange.body and "tests/test_auth.py 67%" in cochange.body  # 8 and 6 of 9
    changelog = _item(session, repo, "changelog/entries")
    assert changelog is not None and "CHANGES.md" in changelog.body

    skill = session.execute(select(MemorySkill).where(MemorySkill.name == "add-shop-plugins-py")).scalar_one()
    assert skill.status == "active" and skill.support == 5
    assert {f["path"] for f in skill.resources["files"]} >= {"shop/__init__.py", "CHANGES.md"}

    # Grounding: every item's evidence re-checks against the commit it was learned at.
    items = session.execute(select(MemoryItem).where(MemoryItem.repository_id == repo.id)).scalars().all()
    assert items and all(item.evidence for item in items)
    assert all(check_evidence(e, fixture_repo.path, fixture_repo.path) for i in items for e in i.evidence)

    brief = session.execute(select(RepoBrief).where(RepoBrief.repository_id == repo.id)).scalar_one()
    assert brief.commit_sha == repo.last_commit_sha and len(brief.text) <= BRIEF_CHARS
    assert "## Layout" in brief.text and "add-shop-plugins-py" in brief.text
    ledger = session.execute(select(func.count()).select_from(MemoryLedger)
                             .where(MemoryLedger.run_id == stats["run_id"])).scalar_one()
    assert ledger == stats["added"]


def test_relearning_is_incremental_and_respects_human_decisions(session, learned, fixture_repo, embedder):
    repo, first = learned
    cochange = _item(session, repo, "cochange/shop/auth.py")
    set_status(session, cochange, "reject")
    session.commit()

    again = learn_repository(session, repo, checkout=fixture_repo.path, mirror=fixture_repo.path,
                             commit=repo.last_commit_sha, embedder=embedder)
    assert again["added"] == 0 and again["staled"] == 0 and again["embedded"] == 0
    assert again["unchanged"] == first["added"]
    session.refresh(cochange)
    assert cochange.status == "rejected"  # a learning run never overrides a human


def test_stale_and_rollback(session, learned):
    repo, _ = learned
    evidence = [{"kind": "commit", "sha": repo.last_commit_sha, "date": "2026-01-01", "subject": "x"}]
    cand = Candidate(key="naming/demo", kind="convention", title="t", body="b", evidence=evidence, support=30,
                     confidence=1.0, source="code", eligible=True)
    writer = MemoryWriter(session, repo.id, repo.last_commit_sha, "run-a")
    writer.apply([cand])
    session.commit()
    item = _item(session, repo, "naming/demo")
    assert item.status == "active"

    writer = MemoryWriter(session, repo.id, "c2", "run-b")
    writer.retire({"naming"}, derived_keys=set())
    session.commit()
    session.refresh(item)
    assert item.status == "stale" and item.invalidated_at_commit == "c2"  # invalidated, never deleted

    assert rollback_run(session, "run-b") >= 1
    session.commit()
    session.refresh(item)
    assert item.status == "active" and item.invalidated_at_commit is None
    rollback_run(session, "run-a")
    session.commit()
    session.refresh(item)
    assert item.status == "archived"


def test_context_leads_with_memory_for_the_retrieved_files(session, learned, embedder):
    repo, _ = learned
    req = ContextRequest(query="verify a user's password against the stored hash", repository=repo.url,
                         include_code=False)
    out = assemble_context(session, embedder, req)
    assert any(c["path"] == "shop/auth.py" for c in out["chunks"])
    keys = {i["key"] for i in out["memory"]["items"]}
    assert "cochange/shop/auth.py" in keys
    assert not any(k.startswith("history/") for k in keys)  # history only when the query asks
    text = out["context_text"]
    assert text.index("repository brief") < text.index("Learned about the retrieved code") < text.index("## [1]")

    off = assemble_context(session, embedder, ContextRequest(query=req.query, repository=repo.url,
                                                             include_code=False, include_memory=False))
    assert off["memory"] == {"briefs": [], "items": [], "skills": []}
    assert "Learned about" not in off["context_text"]
    assert [c["chunk_id"] for c in off["chunks"]] == [c["chunk_id"] for c in out["chunks"]]  # ranking untouched


def test_search_memory(session, learned, embedder):
    repo, _ = learned
    results = search_memory(session, embedder, "which files change with auth.py", [repo.id])
    assert results and results[0]["key"] == "cochange/shop/auth.py"
    history = search_memory(session, embedder, "when was the plugins module added", [repo.id], kinds=["history"])
    assert all(r["kind"] == "history" for r in history)


def test_learning_jobs(session, learned, fixture_repo, embedder, monkeypatch):
    repo, _ = learned
    session.execute(RepoBrief.__table__.delete())
    session.commit()
    queued = queue_unlearned(session)
    assert [j.repository_id for j in queued] == [repo.id]
    job, created = submit_learning(session, repo)
    assert not created and job.id == queued[0].id  # one active job per repository

    claimed = jobs.claim(session, job.id, "test-worker", LearningJob)
    assert claimed is not None and claimed.status == "running"
    assert jobs.claim(session, job.id, "other", LearningJob) is None
    done = run_learning_job(session, claimed, embedder)
    assert done.status == "succeeded" and done.stats["ungrounded"] == 0
    assert session.execute(select(RepoBrief).where(RepoBrief.repository_id == repo.id)).scalar_one()


def test_learning_job_fails_cleanly_for_a_stale_commit(session, learned, embedder):
    repo, _ = learned
    job, _ = submit_learning(session, repo, commit="0" * 40)
    claimed = jobs.claim(session, job.id, "w", LearningJob)
    done = run_learning_job(session, claimed, embedder)
    assert done.status == "failed" and "index is at" in done.error


@pytest.fixture
def learned_api(api, learned):
    return api, learned[0]


def test_memory_api_scopes(learned_api, session):
    api, repo = learned_api
    read = auth(READ_TOKEN)
    brief = api.get("/api/v1/memory/brief", params={"repository": repo.url}, headers=read)
    assert brief.status_code == 200 and brief.json()["briefs"][0]["text"].startswith("# ")
    items = api.get("/api/v1/memory/items", params={"repository": repo.url}, headers=read).json()["items"]
    assert any(i["key"] == "cochange/shop/auth.py" for i in items)
    found = api.post("/api/v1/memory/search", json={"query": "files changed with auth", "repository": repo.url},
                     headers=read)
    assert found.status_code == 200, found.text
    assert found.json()["results"]
    assert api.get("/api/v1/memory/skills", headers=read).json()["skills"][0]["name"] == "add-shop-plugins-py"
    level2 = api.get("/api/v1/memory/skills/add-shop-plugins-py", params={"level": 2}, headers=read).json()
    assert "resources" in level2 and "body" in level2

    target = items[0]["id"]
    assert api.patch(f"/api/v1/memory/items/{target}", params={"action": "reject"}, headers=read).status_code == 403
    done = api.patch(f"/api/v1/memory/items/{target}", params={"action": "reject"}, headers=auth(ADMIN_TOKEN))
    assert done.status_code == 200 and done.json()["status"] == "rejected"

    assert api.post(f"/api/v1/repositories/{repo.id}/learn", headers=read).status_code == 403
    queued = api.post(f"/api/v1/repositories/{repo.id}/learn", headers=auth(ADMIN_TOKEN))
    assert queued.status_code == 202 and queued.json()["job"]["status"] == "queued"
    assert api.get("/api/v1/learning/jobs", headers=read).json()[0]["status"] == "queued"


def _mcp(api, name, arguments):
    headers = {**auth(READ_TOKEN), "Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": arguments}}
    return json.loads(api.post("/mcp/", json=body, headers=headers).json()["result"]["content"][0]["text"])


def test_mcp_memory_tools(learned_api):
    api, repo = learned_api
    assert _mcp(api, "get_repo_brief", {"repository": repo.url})["briefs"][0]["commit_sha"] == repo.last_commit_sha
    assert _mcp(api, "search_memory", {"query": "auth.py co-change", "repository": repo.url})["results"]
    skills = _mcp(api, "list_skills", {"repository": repo.url})["skills"]
    assert skills[0]["name"] == "add-shop-plugins-py" and "body" not in skills[0]
    assert "Steps" in _mcp(api, "get_skill", {"name": "add-shop-plugins-py", "repository": repo.url})["body"]
    context = _mcp(api, "retrieve_context", {"query": "verify password", "repository": repo.url,
                                             "include_code": False, "include_memory": False})
    assert context["memory"]["items"] == []
