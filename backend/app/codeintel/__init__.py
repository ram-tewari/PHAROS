"""Pharos code-intelligence core.

Framework-free library used by the API (``app.modules.code``), the ingestion
worker and the ``pharos`` CLI:

* :mod:`.languages` / :mod:`.parsers` — language detection and AST extraction
* :mod:`.git_source` — safe repository access (clone, list, read blobs)
* :mod:`.embeddings` — pluggable embedding backends
* :mod:`.indexer` — incremental, idempotent repository indexing
* :mod:`.graph` — call / import / containment edges between chunks
* :mod:`.retrieval` — keyword, dense, hybrid and graph-expanded search
* :mod:`.source` — on-demand code resolution (hybrid storage)
* :mod:`.context` — context assembly for coding assistants
* :mod:`.jobs` — durable ingestion job state machine
"""
