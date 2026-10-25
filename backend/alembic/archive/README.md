# Archived migration chain (2025-09 → 2026-07)

These 53 revisions are the historical Neo Alexandria → Pharos migration chain.
They are **not loaded by Alembic** any more (`script_location` only reads
`alembic/versions/`).

Why archived: the chain cannot build a database from scratch — on a clean
PostgreSQL it fails at the 4th revision (`20250911_add_ingestion_status_fields`)
because revision IDs longer than 32 characters overflow
`alembic_version.version_num`, and several revisions assume SQLite-only FTS5
objects. It also has six merge heads from parallel feature branches.

It was replaced by `alembic/versions/0001_baseline.py`, generated from the ORM
models as of 2026-10, plus forward-only revisions after it. See
`docs/operations/database-migrations.md` for how an existing database that was
built with this chain is moved onto the new baseline (`alembic stamp`).
