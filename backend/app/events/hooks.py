"""Event hooks — neutralized in the Phase 2 amputation (2026-07).

Historically this module subscribed 7 event hooks that dispatched Celery tasks
(embedding regeneration, quality recompute, search-index sync, graph-edge
update, cache invalidation, author normalization, collection embeddings).

Celery was dead — no worker process ever consumed those tasks; the real
ingestion work runs synchronously inside `process_ingestion` on the edge
worker. Several of the hooks also targeted features that have been removed
(quality scoring, authority/author normalization, collections). The whole
dispatch layer was therefore pure dead weight and has been removed along with
`app/tasks/` (Celery).

`register_all_hooks()` is kept as a no-op so the startup call site in
`app/__init__.py` stays valid. If durable, cross-process derived-data
consistency is needed later, build it on the existing Redis queue +
`main_worker.py`, not Celery.
"""

import logging

logger = logging.getLogger(__name__)


def register_all_hooks() -> None:
    """No-op. See module docstring — the Celery-backed hooks were removed."""
    logger.info("Event hooks: none registered (Celery dispatch layer removed in Phase 2)")
