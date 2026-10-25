# Contributing

## Setup

```bash
python -m venv .venv && . .venv/bin/activate      # Python 3.11+
make install                                       # dev lock, hash-checked
make demo                                          # sanity check, no database needed
make db-up                                         # PostgreSQL + pgvector and Redis (docker compose)
```

## Before you open a pull request

```bash
make lint isolation test      # what CI gates on (CI also runs the PostgreSQL suite)
make test-pg                  # the same suite with the PostgreSQL parametrisations
```

- **Tests** live in `backend/tests/`. The code-intelligence core has its own suite in
  `tests/codeintel/`. Most of its tests are parametrised over SQLite and PostgreSQL: set
  `PHAROS_TEST_DATABASE_URL` (as `make test-pg` does) to run both. Tests that need the internet are
  marked `network` and run only with `PHAROS_NETWORK_TESTS=1`. Optional or edge-only dependencies
  (torch, gensim, GitPython) are skipped with a stated reason when absent.
- **No silent skips or weakened assertions.** A known gap gets
  `pytest.mark.xfail(strict=True, reason=…)`, so the test fails loudly once the gap is fixed.
- **Migrations:** after changing a model, generate a revision and run
  `pytest tests/codeintel/test_migrations.py`; it fails if models and migrations drift. See
  [docs/operations/database-migrations.md](docs/operations/database-migrations.md).
- **Dependencies:** edit `backend/requirements-*.in`, then `make lock` (needs
  [uv](https://docs.astral.sh/uv/)), and commit both the `.in` and the regenerated `.txt` files.
- **Module boundaries:** `app/modules/*` must not import each other except through
  `app.shared`, `app.codeintel` or events. `scripts/check_module_isolation.py` fails on new
  cross-module imports, and on allowlist entries that are no longer needed.
- **Secrets:** never commit real tokens, passwords or connection strings; use placeholders. CI runs
  `detect-secrets` against `.secrets.baseline`. A new finding fails the build. If it's a false
  positive, audit it and update the baseline with
  `detect-secrets scan --baseline .secrets.baseline` followed by `detect-secrets audit .secrets.baseline`.
- **Benchmarks:** any change to retrieval or ranking should be measured with
  `python -m benchmarks.retrieval_eval`. Do not tune weights on `codeqa_v1`, which is the test set;
  add a separate development set first.

## Commit style

Use short imperative subjects with a scope prefix (`codeintel:`, `api:`, `db:`, `bench:`, `docs:`,
`fix:`). In the body, say what changed and why, and what was run to verify it.
