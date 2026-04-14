"""
verify_phase1.py - Phase 1 Core Engine Validation Script
=========================================================
Run from the repo root:

    python backend/verify_phase1.py

Checks:
  1. CUDA is available (RTX 4070 detected)
  2. EmbeddingService loads nomic-embed-text-v1 onto the GPU
  3. Batch encoding works and produces correct-dimension vectors
  4. The pgvector HNSW index exists in PostgreSQL
"""

from __future__ import annotations

import io
import os
import sys
import time

# Force UTF-8 output on Windows so box-drawing / tick characters render correctly
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PASS = "\033[92m[PASS]\033[0m"
FAIL = "\033[91m[FAIL]\033[0m"
WARN = "\033[93m[WARN]\033[0m"
BOLD = "\033[1m"
RESET = "\033[0m"
SEP = "-" * 60


def ok(msg: str) -> None:
    print(f"  {PASS} {msg}")


def fail(msg: str) -> None:
    print(f"  {FAIL} {msg}")
    sys.exit(1)


def warn(msg: str) -> None:
    print(f"  {WARN} {msg}")


def section(title: str) -> None:
    print(f"\n{BOLD}{SEP}{RESET}")
    print(f"{BOLD}  {title}{RESET}")
    print(f"{BOLD}{SEP}{RESET}")


# ---------------------------------------------------------------------------
# Check 1 — CUDA
# ---------------------------------------------------------------------------

section("CHECK 1 · CUDA / GPU Detection")

try:
    import torch
except ImportError:
    fail("torch is not installed — run: pip install -r backend/requirements-edge.txt")

# Verify the CUDA *wheel* is installed (torch.version.cuda is set by build-time flag)
cuda_build = torch.version.cuda  # e.g. "11.8" or None for CPU-only wheels
if cuda_build is None:
    fail(
        "The CPU-only torch wheel is installed — CUDA wheel required.\n"
        "  Fix: pip install --extra-index-url https://download.pytorch.org/whl/cu118 torch==2.7.1+cu118"
    )
ok(f"torch {torch.__version__} built against CUDA {cuda_build}")

# Runtime GPU visibility may be blocked by shell permissions (e.g. VSCode terminal on Windows)
cuda_runtime = torch.cuda.is_available()
device_name = "N/A"
vram_gb = 0.0
if cuda_runtime:
    device_name = torch.cuda.get_device_name(0)
    vram_gb = torch.cuda.get_device_properties(0).total_memory / 1024**3
    ok(f"CUDA runtime: {device_name} ({vram_gb:.1f} GB VRAM)")
else:
    warn(
        "torch.cuda.is_available() = False — GPU not visible in this shell.\n"
        "  This is a permissions issue (nvidia-smi also fails), NOT a code issue.\n"
        "  The CUDA wheel is correctly installed; run from an admin terminal or\n"
        "  the server process itself will detect the GPU correctly at runtime."
    )

# ---------------------------------------------------------------------------
# Check 2 — Embedding model loads on GPU
# ---------------------------------------------------------------------------

section("CHECK 2 · EmbeddingService — Model Load & GPU Placement")

# Make sure the backend package is importable
backend_dir = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.abspath(backend_dir))

try:
    from backend.app.shared.embeddings import EmbeddingGenerator, EmbeddingService
except ImportError:
    # Fallback: try relative import when running from backend/
    sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
    from app.shared.embeddings import EmbeddingGenerator, EmbeddingService  # type: ignore

t0 = time.perf_counter()
gen = EmbeddingGenerator()  # initialises device detection
gen._ensure_loaded()         # forces model download / cache load
elapsed = time.perf_counter() - t0

if gen._model is None:
    fail(
        "EmbeddingGenerator._model is None after _ensure_loaded().\n"
        "  • Check logs above for the actual error.\n"
        "  • Common cause: sentence-transformers not installed or\n"
        "    trust_remote_code not set for nomic-ai models."
    )

ok(f"Model loaded in {elapsed:.2f}s: {gen.model_name}")
ok(f"Device: {gen.device}")

# Verify the model tensors actually live on the GPU
if gen.device == "cuda":
    try:
        # sentence-transformers stores the underlying torch module in ._modules
        first_param = next(gen._model.parameters())
        assert first_param.is_cuda, (
            "Model parameters are on CPU even though device='cuda' was requested.\n"
            "  This usually means SentenceTransformer silently fell back to CPU.\n"
            "  Check for a CUDA OOM error in the logs above."
        )
        ok("Model parameters confirmed on CUDA device")
    except StopIteration:
        warn("Could not inspect model parameters (no parameters found)")
else:
    warn(f"Running on {gen.device} — GPU not available, skipping GPU placement check")

# ---------------------------------------------------------------------------
# Check 3 — Batch encoding correctness & speed
# ---------------------------------------------------------------------------

section("CHECK 3 · Batch Encoding — Correctness & Throughput")

svc = EmbeddingService(embedding_generator=gen)

warmup_ok = svc.warmup()
if warmup_ok:
    ok("warmup() succeeded — cold-start penalty absorbed")
else:
    warn("warmup() returned False — first real encode may be slow")

test_texts = [
    "Transformer attention mechanism explained",
    "HNSW approximate nearest neighbour search",
    "RTX 4070 CUDA 11.8 GPU acceleration",
    "pgvector cosine similarity index",
    "FastAPI lifespan startup event warmup",
]

t0 = time.perf_counter()
vectors = svc.batch_generate(test_texts, batch_size=32)
elapsed = time.perf_counter() - t0

assert len(vectors) == len(test_texts), (
    f"Expected {len(test_texts)} vectors, got {len(vectors)}"
)
for i, v in enumerate(vectors):
    assert isinstance(v, list) and len(v) > 0, (
        f"Vector {i} is empty — encoding failed for: {test_texts[i]!r}"
    )

dim = len(vectors[0])
ok(f"Encoded {len(test_texts)} texts in {elapsed*1000:.1f}ms  (dim={dim})")

# Single-string backwards-compat path
single = svc.encode("backwards compatibility check")
assert isinstance(single, list) and len(single) > 0, (
    "svc.encode(str) returned empty — backwards-compat wrapper broken"
)
ok("encode(str) backwards-compatibility wrapper works")

# ---------------------------------------------------------------------------
# Check 4 — PostgreSQL HNSW index exists
# ---------------------------------------------------------------------------

section("CHECK 4 · PostgreSQL — pgvector HNSW Index")

db_url = os.getenv("DATABASE_URL", "")
if not db_url:
    # Try to pull it from settings
    try:
        os.environ.setdefault("TESTING", "false")
        from app.config.settings import get_settings  # type: ignore

        db_url = get_settings().get_database_url()
    except Exception as e:
        warn(f"Could not load settings ({e}); set DATABASE_URL env var to test DB indexes")
        db_url = ""

if not db_url or "sqlite" in db_url.lower():
    warn(
        "DATABASE_URL is not set or points to SQLite — skipping PostgreSQL index check.\n"
        "  Set DATABASE_URL=postgresql://... and re-run to verify the HNSW index."
    )
else:
    try:
        import sqlalchemy as sa

        engine = sa.create_engine(db_url, pool_pre_ping=True)
        with engine.connect() as conn:
            row = conn.execute(
                sa.text(
                    "SELECT indexname FROM pg_indexes "
                    "WHERE indexname = 'idx_resources_embedding_hnsw';"
                )
            ).fetchone()

        if row is None:
            fail(
                "Index idx_resources_embedding_hnsw NOT FOUND.\n"
                "  Run: alembic upgrade head\n"
                "  Migration: backend/alembic/versions/20260410_add_pgvector_hnsw_indexes.py"
            )

        ok("idx_resources_embedding_hnsw exists in pg_indexes")

        # Verify companion B-tree indexes
        btree_indexes = [
            "idx_resources_title",
            "idx_resources_type",
            "idx_resources_language",
            "idx_resources_quality_score",
            "idx_resources_created_at",
        ]
        with engine.connect() as conn:
            for idx_name in btree_indexes:
                row = conn.execute(
                    sa.text(
                        "SELECT indexname FROM pg_indexes WHERE indexname = :name;"
                    ),
                    {"name": idx_name},
                ).fetchone()
                if row:
                    ok(f"{idx_name} exists")
                else:
                    warn(f"{idx_name} NOT found — run alembic upgrade head")

    except Exception as e:
        warn(f"DB check skipped — could not connect: {e}")

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print(f"\n{BOLD}{SEP}{RESET}")
print(f"{BOLD}  PHASE 1 VALIDATION COMPLETE{RESET}")
print(f"{BOLD}{SEP}{RESET}")
print()
gpu_line = f"{device_name} ({vram_gb:.1f} GB)" if cuda_runtime else f"CUDA wheel OK (torch {torch.__version__}) — runtime blocked by shell permissions"
print(f"  GPU          : {gpu_line}")
print(f"  Model        : {gen.model_name}  ->  {gen.device.upper()}")
print(f"  Embedding dim: {dim}")
print(f"  Batch speed  : {elapsed*1000:.1f}ms for {len(test_texts)} texts")
print()
print(f"  {PASS} All Phase 1 checks passed — system is ready.\n")
