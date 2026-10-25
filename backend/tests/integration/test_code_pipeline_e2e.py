"""Legacy repository-ingestion endpoints (/api/resources/ingest-repo)."""


def test_legacy_ingest_repo_endpoints_are_gone_and_point_to_the_new_api(client):
    """POST /api/resources/ingest-repo was removed with Celery; it answers 410
    with the replacement. The pipeline itself (clone -> AST -> embed -> graph
    -> retrieve) is tested end to end in tests/codeintel (test_api.py,
    test_jobs_worker.py, test_indexer.py)."""
    gone = client.post("/api/resources/ingest-repo", json={"path": "/tmp/repo"})
    assert gone.status_code == 410
    assert "POST /api/v1/repositories" in gone.json()["detail"]

    status_gone = client.get("/api/resources/ingest-repo/some-task/status")
    assert status_gone.status_code == 410
    assert "/api/v1/ingestion/jobs/" in status_gone.json()["detail"]
