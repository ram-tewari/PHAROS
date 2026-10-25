"""Durable ingestion jobs and the worker: dedupe, atomic claims, retries, recovery."""

import uuid
from datetime import timedelta

import pytest

from app.codeintel import jobs
from app.codeintel.git_source import GitError, RepoSpecError, parse_repo_spec
from app.codeintel.runtime import run_options
from app.database.models import IngestionJob


@pytest.fixture
def ref(fixture_repo):
    return parse_repo_spec(str(fixture_repo.path), allowed_hosts=[], allow_local=True)


def _opts():
    return dict(max_file_bytes=1_000_000, max_files=1000, clone_timeout=60, clone_token=None)


def test_duplicate_submission_returns_active_job(session, ref):
    first = jobs.submit(session, ref)
    second = jobs.submit(session, ref)
    assert first.created and not second.created
    assert first.job.id == second.job.id



def test_queue_cap_counts_only_queued_jobs(session, ref):
    other = parse_repo_spec("github.com/a/other", allowed_hosts=["github.com"])
    third = parse_repo_spec("github.com/a/third", allowed_hosts=["github.com"])
    first = jobs.submit(session, ref, max_queued=1).job
    with pytest.raises(jobs.QueueFull) as exc:
        jobs.submit(session, other, max_queued=1)
    assert (exc.value.queued, exc.value.limit) == (1, 1)
    assert jobs.submit(session, ref, max_queued=1).created is False  # dedupe is never refused
    jobs.claim(session, first.id, "w")  # running jobs no longer occupy the queue
    assert jobs.submit(session, other, max_queued=1).created is True
    with pytest.raises(jobs.QueueFull):
        jobs.submit(session, third, max_queued=1)

def test_claim_is_atomic(session, ref):
    job = jobs.submit(session, ref).job
    assert jobs.claim(session, job.id, "w1") is not None
    assert jobs.claim(session, job.id, "w2") is None  # already running
    session.refresh(job)
    assert (job.status, job.worker_id, job.attempts) == ("running", "w1", 1)


def test_successful_run_reaches_terminal_state(session, ref, embedder):
    job = jobs.claim(session, jobs.submit(session, ref).job.id, "w")
    job = jobs.run(session, job, ref, embedder, **_opts())
    assert job.status == "succeeded"
    assert job.commit_sha and job.finished_at and job.repository_id
    assert job.stats["files_indexed"] == 16
    # A new submission after success creates a new job (no active one).
    again = jobs.submit(session, ref)
    assert again.created


def test_retryable_failure_requeues_with_backoff(session, ref, embedder, monkeypatch):
    def boom(*a, **k):
        raise GitError("connection reset by peer", retryable=True)

    monkeypatch.setattr("app.codeintel.indexer.open_checkout", boom)
    job = jobs.claim(session, jobs.submit(session, ref).job.id, "w")
    job = jobs.run(session, job, ref, embedder, **_opts())
    assert job.status == "queued" and job.error_kind == "git_transient"
    assert job.available_at is not None
    # Not claimable until the backoff has elapsed.
    assert jobs.claim(session, job.id, "w") is None
    assert job.id not in jobs.next_queued_ids(session)


def test_permanent_failure_is_terminal(session, ref, embedder, monkeypatch):
    def boom(*a, **k):
        raise GitError("remote: Repository not found.", retryable=False)

    monkeypatch.setattr("app.codeintel.indexer.open_checkout", boom)
    job = jobs.claim(session, jobs.submit(session, ref).job.id, "w")
    job = jobs.run(session, job, ref, embedder, **_opts())
    assert (job.status, job.error_kind) == ("failed", "git_permanent")
    assert job.finished_at is not None


def test_attempts_are_bounded(session, ref, embedder, monkeypatch):
    monkeypatch.setattr(
        "app.codeintel.indexer.open_checkout",
        lambda *a, **k: (_ for _ in ()).throw(GitError("timeout", retryable=True)),
    )
    job = jobs.submit(session, ref, max_attempts=2).job
    for _ in range(2):
        session.query(IngestionJob).filter_by(id=job.id).update({"available_at": None})
        session.commit()
        claimed = jobs.claim(session, job.id, "w")
        job = jobs.run(session, claimed, ref, embedder, **_opts())
    assert job.status == "failed" and job.attempts == 2


def test_stale_running_job_is_recovered(session, ref):
    job = jobs.claim(session, jobs.submit(session, ref).job.id, "dead-worker")
    session.query(IngestionJob).filter_by(id=job.id).update(
        {"heartbeat_at": jobs.utcnow() - timedelta(hours=1)}
    )
    session.commit()
    assert jobs.recover_stale(session, stale_after_seconds=60) == [job.id]
    session.refresh(job)
    assert job.status == "queued" and job.error_kind == "worker_lost"


def test_stale_job_with_no_attempts_left_fails(session, ref):
    job = jobs.submit(session, ref, max_attempts=1).job
    jobs.claim(session, job.id, "dead-worker")
    session.query(IngestionJob).filter_by(id=job.id).update({"heartbeat_at": jobs.utcnow() - timedelta(hours=1)})
    session.commit()
    assert jobs.recover_stale(session, 60) == []
    session.refresh(job)
    assert job.status == "failed"


def test_cancel_only_queued_jobs(session, ref):
    job = jobs.submit(session, ref).job
    assert jobs.cancel(session, job.id)
    session.refresh(job)
    assert job.status == "cancelled"
    assert not jobs.cancel(session, job.id)


def test_error_classification():
    assert jobs.classify_error(RepoSpecError("bad")) == ("invalid_repository", False)
    assert jobs.classify_error(GitError("x", retryable=True)) == ("git_transient", True)
    assert jobs.classify_error(ConnectionError()) == ("transient", True)
    assert jobs.classify_error(KeyError("bug")) == ("internal_error", False)


# ── worker ─────────────────────────────────────────────────────────────────


def test_worker_drains_queued_jobs_without_notifications(session, ref, engine, codeintel_settings):
    from app.workers.ingest_worker import Worker

    job = jobs.submit(session, ref).job
    worker = Worker()
    assert worker.notifier.name == "none"  # no Redis: DB polling only
    assert worker.drain() == 1
    session.expire_all()
    assert session.get(IngestionJob, job.id).status == "succeeded"
    assert worker.drain() == 0


def test_worker_recovers_after_crash(session, ref, engine, codeintel_settings):
    from app.workers.ingest_worker import Worker

    job = jobs.claim(session, jobs.submit(session, ref).job.id, "crashed-worker")
    session.query(IngestionJob).filter_by(id=job.id).update({"heartbeat_at": jobs.utcnow() - timedelta(hours=2)})
    session.commit()
    worker = Worker()
    worker._recover()
    assert worker.drain() == 1
    session.expire_all()
    final = session.get(IngestionJob, job.id)
    assert final.status == "succeeded" and final.attempts == 2


def test_duplicate_notifications_run_a_job_once(session, ref, engine, codeintel_settings):
    from app.workers.ingest_worker import process_job

    job = jobs.submit(session, ref).job
    from app.codeintel.embeddings import get_embedder

    statuses = [process_job(job.id, "w", get_embedder()) for _ in range(3)]
    assert statuses == ["succeeded", None, None]


def test_malformed_job_reference_fails_cleanly(session, engine, codeintel_settings):
    from app.workers.ingest_worker import process_job

    job = IngestionJob(id=uuid.uuid4(), repo_url="https://evil.example/x/y", status="queued")
    session.add(job)
    session.commit()
    assert process_job(job.id, "w", None) == "failed"
    session.expire_all()
    assert session.get(IngestionJob, job.id).error_kind == "invalid_repository"


def test_redis_notifier_round_trip():
    import redis

    from app.codeintel.notify import RedisNotifier

    try:
        redis.Redis.from_url("redis://localhost:6379/15", socket_connect_timeout=1).ping()
    except Exception:
        pytest.skip("no local Redis")
    n = RedisNotifier("redis://localhost:6379/15", "pharos:test:jobs")
    n._client.delete("pharos:test:jobs")
    assert n.notify("abc")
    assert n.wait(1) == "abc"
    assert n.wait(1) is None


def test_run_options_reflect_settings(codeintel_settings):
    opts = run_options()
    assert opts["max_file_bytes"] == codeintel_settings.CODEINTEL_MAX_FILE_BYTES
