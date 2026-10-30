# PHAROS developer tasks. Run from the repository root.
#   make install        dev dependencies from the hash-pinned lock (into the active venv)
#   make db-up migrate  local PostgreSQL+pgvector and Redis (docker compose), then schema
#   make demo           end-to-end smoke: index a polyglot fixture repo and query it
#   make test           full suite on SQLite;  make test-pg  adds the PostgreSQL runs

BACKEND := backend
PYTHON  ?= python
PG_TEST_URL ?= postgresql://pharos:pharos@localhost:5432/pharos_test
RUN := cd $(BACKEND) &&

.PHONY: help install install-onnx lock db-up db-down migrate serve worker demo test test-pg \
        lint isolation secrets audit check bench

help:
	@grep -E '^#   make' Makefile | sed 's/^#   //'
	@echo "targets: install install-onnx lock db-up db-down migrate serve worker demo test test-pg lint isolation secrets audit check bench"

install:
	$(RUN) $(PYTHON) -m pip install --require-hashes -r requirements-dev.txt

install-onnx:
	$(RUN) $(PYTHON) -m pip install --require-hashes -r requirements-onnx.txt

# Regenerate the locks after editing requirements-*.in (needs uv).
lock:
	$(RUN) uv pip compile -q --universal --python-version 3.11 --generate-hashes requirements-cloud.in -o requirements-cloud.txt
	$(RUN) uv pip compile -q --universal --python-version 3.11 --generate-hashes requirements-dev.in -o requirements-dev.txt
	$(RUN) uv pip compile -q --universal --python-version 3.11 --generate-hashes requirements-onnx.in -c requirements-cloud.txt -o requirements-onnx.txt

db-up:
	docker compose up -d db redis
	@echo "DATABASE_URL=postgresql://pharos:pharos@localhost:5432/pharos"

db-down:
	docker compose down

migrate:
	$(RUN) alembic -c config/alembic.ini upgrade head

serve:
	$(RUN) uvicorn app.main:app --reload --port 8000

worker:
	$(RUN) $(PYTHON) -m app.workers.ingest_worker

demo:
	$(RUN) $(PYTHON) scripts/demo.py

test:
	$(RUN) MODE=CLOUD $(PYTHON) -m pytest tests -q

# Creates the test database if needed; tests drop and recreate its schema.
test-pg:
	-docker compose exec -T db psql -U pharos -tc "SELECT 1 FROM pg_database WHERE datname='pharos_test'" | grep -q 1 || \
	  docker compose exec -T db createdb -U pharos pharos_test
	$(RUN) MODE=CLOUD PHAROS_TEST_DATABASE_URL=$(PG_TEST_URL) $(PYTHON) -m pytest tests -q

# Whole tree: bug-class rules (syntax errors, undefined names, bad comparisons).
# New/rewritten code: the full rule set in ruff.toml plus import order,
# bugbear and pyupgrade. Legacy modules are not style-gated yet.
STRICT_PATHS := app/codeintel app/modules/code app/shared/auth.py app/shared/db_url.py \
  app/shared/vector_type.py app/cli.py benchmarks scripts/demo.py tests/codeintel \
  app/learning app/workers/learning_worker.py tests/learning
lint:
	$(RUN) ruff check app alembic benchmarks scripts tests --select E9,F63,F7,F82
	$(RUN) ruff check --extend-select I,B,UP $(STRICT_PATHS)

isolation:
	$(RUN) $(PYTHON) scripts/check_module_isolation.py

secrets:
	detect-secrets-hook --baseline .secrets.baseline $$(git ls-files)

audit:
	$(RUN) pip-audit --strict -r requirements-cloud.txt

check: lint isolation test

bench:
	$(RUN) $(PYTHON) -m benchmarks.retrieval_eval --database-url postgresql://pharos:pharos@localhost:5432/pharos_bench \
	  --embedder hash --out benchmarks/results/local.json
