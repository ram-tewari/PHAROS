# PHAROS documentation

Start with the [project README](../README.md): what PHAROS is, the quick start, the API, the
benchmark summary and the limitations.

## Current

| Document | |
|---|---|
| [benchmarks/retrieval-2026-10.md](benchmarks/retrieval-2026-10.md) | Retrieval quality, latency, indexing throughput and storage, measured on pinned repositories; includes negative results |
| [operations/database-migrations.md](operations/database-migrations.md) | Running migrations, and the one-time procedure for databases created before the 2026-10 squash |
| [security/credential-exposure-2026-10.md](security/credential-exposure-2026-10.md) | Credentials found in Git history and the owner's rotation checklist |
| [../SECURITY.md](../SECURITY.md) | Threat model, mitigations and how to report vulnerabilities |
| [../CONTRIBUTING.md](../CONTRIBUTING.md) | Development setup, tests, lint, conventions |
| [../backend/config/.env.example](../backend/config/.env.example) | Every configuration setting |

## Historical

These are kept for context and are **not** maintained. Figures in them, such as "17× storage
reduction" and latency or coverage claims, were not reproduced unless the benchmark report says so.

- [`../backend/docs/`](../backend/docs/): status reports, phase write-ups and guides for components
  that have since been replaced. This includes JWT/OAuth authentication, Celery, Qdrant and the
  pre-2026-10 ingestion pipeline.
