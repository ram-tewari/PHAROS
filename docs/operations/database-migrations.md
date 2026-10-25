# Database migrations

Run all commands from `backend/`:

```bash
alembic -c config/alembic.ini upgrade head      # apply migrations   (make migrate)
alembic -c config/alembic.ini current           # what the database is at
alembic -c config/alembic.ini check             # do the models and migrations agree?
python -m app.cli doctor                        # reports "schema: at head" or what is wrong
```

`DATABASE_URL` selects the database. The driver (psycopg2) and `sslmode` are handled for you.

## The 2026-10 squash

The old migration chain (53 revisions, five unmerged heads) could not build a database from
scratch. It is archived under `alembic/archive/versions_pre_2026_10/` and is no longer loaded;
see `alembic/archive/README.md` for the reasons. It was replaced by:

| Revision | Contents |
|---|---|
| `0001_baseline` | The schema as the ORM defined it in 2026-10 (all existing tables), the `vector` extension and the resource HNSW index |
| `0002_codeintel` | Code index: `ingestion_jobs`, `code_edges`, new columns on `document_chunks`, `repositories` and `resources`, the chunk HNSW and full-text GIN indexes |

**New databases** need nothing special: `upgrade head`.

**An existing database built with the old chain** has an `alembic_version` row such as
`20260123_add_mcp_sessions`, `20260116_add_version_column`, `20260101_add_auth_tables`,
`5c33b1ef37a0` or `f3a1b2c4d5e6`. Alembic cannot find those revisions any more, so
`upgrade head` stops with `Can't locate revision …` **and changes nothing**. The API container
and the Render `preDeployCommand` fail the same safe way, and the previous deploy stays live.
Moving such a database onto the new chain is a one-time manual step.

> **Requires the owner's approval and a backup.** It changes the production schema. Do not run it
> from CI or from an automated agent.

1. **Back up.** On Neon, create a branch or snapshot of the production database. Elsewhere, run
   `pg_dump -Fc`. Do the remaining steps on the copy first, then repeat them for real.

2. **Compare the schema with the baseline.** Build a scratch database at `0001_baseline` and
   diff the two schema dumps:

   ```bash
   createdb pharos_baseline
   DATABASE_URL=postgresql://…/pharos_baseline alembic -c config/alembic.ini upgrade 0001_baseline
   pg_dump --schema-only --no-owner --no-privileges "$PROD_URL"            > prod.sql
   pg_dump --schema-only --no-owner --no-privileges postgresql://…/pharos_baseline > baseline.sql
   diff -u baseline.sql prod.sql | less
   ```

   Expect small differences: index names, a few nullable or server-default flags, and tables the
   old chain created that the models no longer use. Anything the baseline has and production lacks
   must be added by hand before stamping. A missing table or column would otherwise surface later
   as a runtime error. Extra old tables can stay; nothing reads them.

3. **Stamp the baseline.** This records that the database is at `0001_baseline` without running
   it:

   ```bash
   DATABASE_URL="$PROD_URL" alembic -c config/alembic.ini stamp --purge 0001_baseline
   ```

   `--purge` clears the old revision rows first. That's needed because the old chain left several
   heads.

4. **Upgrade.** This applies `0002_codeintel`. It adds tables, nullable columns and indexes, plus
   two `NOT NULL` columns with constant defaults on `repositories` (`source_type`,
   `index_status`). On PostgreSQL 11+ those are metadata-only changes, so existing rows are not
   rewritten. Building the HNSW and GIN indexes takes a lock on `document_chunks` for as long as
   they take to build.

   ```bash
   DATABASE_URL="$PROD_URL" alembic -c config/alembic.ini upgrade head
   DATABASE_URL="$PROD_URL" python -m app.cli doctor      # expect: schema: at head (0002_codeintel)
   ```

5. **Re-index repositories.** Chunks written by the old pipeline carry no `repository_id` and
   are not visible to the code search API. Submit each repository again with
   `POST /api/v1/repositories`.

## Writing new migrations

- Change the models, then run `alembic -c config/alembic.ini revision --autogenerate -m "…"`. Read
  the generated file before committing it; autogenerate misses some changes (renames, server
  defaults).
- Keep migrations forward-only and safe on a live database: add nullable columns, backfill,
  then tighten constraints in a later release.
- PostgreSQL-only DDL (pgvector, GIN, `CREATE EXTENSION`) must be guarded with
  `if op.get_bind().dialect.name == "postgresql"`. The test suite builds the schema on SQLite too.
- `tests/codeintel/test_migrations.py` runs upgrade → downgrade → upgrade from scratch and
  `alembic check` on both SQLite and PostgreSQL. CI fails if models and migrations drift.
