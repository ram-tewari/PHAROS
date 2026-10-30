"""Learning worker: runs learning jobs on the owner's Mac.

    python -m app.workers.learning_worker --once    # queue unlearned repositories, drain, exit

Under launchd (``deployment/mac/run-learner.sh``) it runs nightly, like the
indexing worker runs hourly: each run wakes Neon, so it never polls. A
repository is queued when its indexed commit has no brief yet; the job
fetches a full mirror (``LEARNING_MIRROR_DIR``), checks out the indexed
commit and runs every miner. Jobs share the ingestion state machine
(claim, heartbeat, backoff, stale recovery) through ``app.codeintel.jobs``.

L2 (Codex) runs when the CLI is signed in, within one budget for the whole
run: ``LEARNING_MAX_CODEX_CALLS`` (default 40, the owner's nightly limit),
at most ``LEARNING_CODEX_CALLS_PER_REPO`` (default 10) per repository.
``--no-codex`` runs the deterministic miners only.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

from ..codeintel import jobs
from ..codeintel.embeddings import get_embedder
from ..codeintel.runtime import secret, session_scope
from ..config.settings import get_settings
from ..database.models import LearningJob
from ..learning.pipeline import queue_unlearned, run_learning_job

logger = logging.getLogger("pharos.learning_worker")

STALE_SECONDS = 3600


def make_llm(enabled: bool):
    if not enabled:
        return None
    from ..learning.llm import CodexCLI

    llm = CodexCLI(effort="low", timeout=420, max_calls=int(os.getenv("LEARNING_MAX_CODEX_CALLS", "40")))
    if not llm.ready():
        logger.warning("Codex is not signed in: deterministic miners only")
        return None
    return llm


def drain(worker_id: str, embedder, llm=None) -> int:
    processed = 0
    with session_scope() as db:
        jobs.recover_stale(db, STALE_SECONDS, LearningJob)
        due = jobs.next_queued_ids(db, limit=20, model=LearningJob)
    for job_id in due:
        with session_scope() as db:
            job = jobs.claim(db, job_id, worker_id, LearningJob)
            if job is None:
                continue
            job = run_learning_job(db, job, embedder, llm=llm,
                                   max_llm_calls=int(os.getenv("LEARNING_CODEX_CALLS_PER_REPO", "10")),
                                   review_token=secret(get_settings().GIT_CLONE_TOKEN))
            logger.info("learning job %s: %s %s", job.id, job.status, (job.stats or {}).get("run_id", job.error))
            processed += 1
    return processed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Pharos learning worker")
    parser.add_argument("--once", action="store_true", help="queue unlearned repositories, run due jobs, exit")
    parser.add_argument("--no-queue", action="store_true", help="only run jobs that are already queued")
    parser.add_argument("--no-codex", action="store_true", help="deterministic miners only (no L2)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if not args.once:
        parser.error("only --once is supported: schedule it (launchd) instead of polling the database")
    if not args.no_queue:
        with session_scope() as db:
            queued = queue_unlearned(db)
        logger.info("queued %d learning job(s)", len(queued))
    llm = make_llm(not args.no_codex)
    n = drain(jobs.default_worker_id(), get_embedder(), llm)
    logger.info("processed %d learning job(s)%s", n,
                f"; Codex {llm.usage.calls} calls, {llm.usage.input_tokens} input tokens" if llm else "")
    return 0


if __name__ == "__main__":
    sys.exit(main())
