"""Embedding backends.

Every chunk embedding is stored together with the ``model_id`` of the
embedder that produced it. Dense retrieval only compares a query vector with
chunk vectors of the same ``model_id`` — vectors from different models live
in unrelated spaces and comparing them returns confident nonsense.

Backends (``EMBEDDING_BACKEND``):

``hash``
    Deterministic feature-hashing of identifier-split tokens into 768 dims.
    No dependencies, no network, CPU-only. **It is a lexical model, not a
    semantic one** — it exists so the whole pipeline (indexing, pgvector,
    fusion) can be exercised offline and in CI. Its retrieval quality is
    reported separately in the benchmarks and must not be presented as
    neural dense retrieval.
``sentence-transformers``
    Local model, default ``nomic-ai/nomic-embed-text-v1`` (the production
    model). Needs ``requirements-ml.txt`` (torch). Uses CUDA when present.
``http``
    POSTs to an embedding server (the edge worker's ``/embed`` endpoint,
    reached over Tailscale in production). Optional bearer token.
``onnx``
    A sentence-transformers model exported to ONNX (``model.onnx`` +
    ``tokenizer.json`` in ``EMBEDDING_ONNX_DIR``), run with onnxruntime on
    CPU. Mean pooling + L2 normalisation.
``none``
    No embeddings: keyword retrieval only; dense/hybrid report unavailable.

Models with fewer than 768 dimensions are zero-padded to the column width.
Zero padding leaves dot products and norms unchanged, so cosine similarity
is exactly preserved.
"""

from __future__ import annotations

import hashlib
import logging
import math
import os
import threading
from abc import ABC, abstractmethod
from collections.abc import Sequence

from ..shared.vector_type import EMBEDDING_DIM
from .text import tokenize

logger = logging.getLogger(__name__)


class EmbeddingUnavailable(RuntimeError):
    """The configured embedder cannot produce vectors right now."""


def _normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0:
        return vec
    return [v / norm for v in vec]


def _pad(vec: Sequence[float], dim: int) -> list[float]:
    vec = [float(v) for v in vec]
    if len(vec) == dim:
        return vec
    if len(vec) > dim:
        raise EmbeddingUnavailable(
            f"model produces {len(vec)}-dim vectors; the index column holds {dim}"
        )
    return vec + [0.0] * (dim - len(vec))


class Embedder(ABC):
    model_id: str
    dim: int = EMBEDDING_DIM
    #: True for models that capture meaning beyond shared tokens.
    semantic: bool = True

    @abstractmethod
    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]

    def encode_raw(self, texts: list[str]) -> list[list[float]]:
        """Embed texts exactly as given (no task prefixes).

        Used by the edge embed server: :class:`HttpEmbedder` clients add the
        prefixes themselves, so the server must not add them again.
        """
        return self.embed_documents(texts)

    def describe(self) -> dict:
        return {
            "backend": type(self).__name__,
            "model_id": self.model_id,
            "dim": self.dim,
            "semantic": self.semantic,
        }


# ── hash ────────────────────────────────────────────────────────────────────


class HashEmbedder(Embedder):
    """Signed feature hashing of unigrams and bigrams (lexical, offline)."""

    model_id = "hash-v1"
    semantic = False

    def _features(self, text: str) -> dict[int, float]:
        tokens = tokenize(text)
        counts: dict[str, int] = {}
        for tok in tokens:
            counts[tok] = counts.get(tok, 0) + 1
        for a, b in zip(tokens, tokens[1:], strict=False):
            key = f"{a}_{b}"
            counts[key] = counts.get(key, 0) + 1
        features: dict[int, float] = {}
        for tok, tf in counts.items():
            digest = hashlib.blake2b(tok.encode(), digest_size=8).digest()
            bucket = int.from_bytes(digest[:4], "little") % self.dim
            sign = 1.0 if digest[4] & 1 else -1.0
            weight = (1.0 + math.log(tf)) * (0.5 if "_" in tok else 1.0)
            features[bucket] = features.get(bucket, 0.0) + sign * weight
        return features

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        out = []
        for text in texts:
            vec = [0.0] * self.dim
            for idx, val in self._features(text).items():
                vec[idx] = val
            out.append(_normalize(vec))
        return out


# ── task prefixes (nomic) ───────────────────────────────────────────────────


def _use_prefixes(model_name: str) -> bool:
    setting = os.getenv("EMBEDDING_PREFIXES", "auto").lower()
    if setting in ("1", "true", "yes", "on"):
        return True
    if setting in ("0", "false", "no", "off"):
        return False
    # nomic-embed-text was trained with task prefixes.
    return "nomic-embed-text" in model_name


class _PrefixMixin:
    model_name: str
    prefixes: bool

    def _doc(self, text: str) -> str:
        return f"search_document: {text}" if self.prefixes else text

    def _query(self, text: str) -> str:
        return f"search_query: {text}" if self.prefixes else text


# ── sentence-transformers ───────────────────────────────────────────────────


class SentenceTransformerEmbedder(_PrefixMixin, Embedder):
    def __init__(self, model_name: str, device: str | None = None, batch_size: int = 32):
        self.model_name = model_name
        self.prefixes = _use_prefixes(model_name)
        self.model_id = model_name + ("+prefix" if self.prefixes else "")
        self.batch_size = batch_size
        self._device = device
        self._model = None
        self._lock = threading.Lock()

    def _load(self):
        if self._model is not None:
            return self._model
        with self._lock:
            if self._model is None:
                try:
                    from sentence_transformers import SentenceTransformer
                except ImportError as exc:
                    raise EmbeddingUnavailable(
                        "sentence-transformers is not installed "
                        "(pip install -r requirements-ml.txt)"
                    ) from exc
                device = self._device
                if device is None:
                    try:
                        import torch

                        device = "cuda" if torch.cuda.is_available() else "cpu"
                    except ImportError:
                        device = "cpu"
                logger.info("Loading embedding model %s on %s", self.model_name, device)
                try:
                    self._model = SentenceTransformer(
                        self.model_name,
                        device=device,
                        trust_remote_code=True,
                        # Avoids a native crash seen with pytorch_model.bin on
                        # Windows + Python 3.13 (see project history).
                        model_kwargs={"use_safetensors": True},
                    )
                except Exception as exc:
                    raise EmbeddingUnavailable(f"failed to load {self.model_name}: {exc}") from exc
        return self._model

    def _encode(self, texts: list[str]) -> list[list[float]]:
        model = self._load()
        vectors = model.encode(
            texts,
            batch_size=self.batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        return [_pad(v.tolist(), self.dim) for v in vectors]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._encode([self._doc(t) for t in texts])

    def embed_query(self, text: str) -> list[float]:
        return self._encode([self._query(text)])[0]

    def encode_raw(self, texts: list[str]) -> list[list[float]]:
        return self._encode(texts)


# ── HTTP (edge embed server) ────────────────────────────────────────────────


class HttpEmbedder(_PrefixMixin, Embedder):
    """Client for the edge worker's embed server.

    Uses ``POST /embed/batch`` (``{"texts": [...]}`` -> ``{"embeddings": [...]}``)
    and falls back to the single-text ``POST /embed`` of older servers.
    """

    def __init__(self, base_url: str, model_name: str, token: str | None = None, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name
        self.prefixes = _use_prefixes(model_name)
        self.model_id = model_name + ("+prefix" if self.prefixes else "")
        self.timeout = timeout
        self._headers = {"Authorization": f"Bearer {token}"} if token else {}
        self._batch_supported: bool | None = None

    def _post(self, path: str, payload: dict) -> dict:
        import httpx

        try:
            resp = httpx.post(
                f"{self.base_url}{path}", json=payload, headers=self._headers, timeout=self.timeout
            )
        except httpx.HTTPError as exc:
            raise EmbeddingUnavailable(f"embedding server unreachable: {type(exc).__name__}") from exc
        if resp.status_code == 404 and path == "/embed/batch":
            raise FileNotFoundError
        if resp.status_code >= 400:
            raise EmbeddingUnavailable(f"embedding server returned HTTP {resp.status_code}")
        return resp.json()

    def _embed(self, texts: list[str]) -> list[list[float]]:
        if self._batch_supported is not False:
            try:
                data = self._post("/embed/batch", {"texts": texts})
                self._batch_supported = True
                return [_pad(v, self.dim) for v in data["embeddings"]]
            except FileNotFoundError:
                self._batch_supported = False
        return [_pad(self._post("/embed", {"text": t})["embedding"], self.dim) for t in texts]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._embed([self._doc(t) for t in texts])

    def embed_query(self, text: str) -> list[float]:
        return self._embed([self._query(text)])[0]


# ── ONNX (CPU, no torch) ────────────────────────────────────────────────────


class OnnxEmbedder(Embedder):
    def __init__(self, model_dir: str, model_id: str | None = None, max_length: int = 256, batch_size: int = 32):
        self.model_dir = model_dir
        self.model_id = model_id or f"onnx:{os.path.basename(os.path.normpath(model_dir))}"
        self.max_length = max_length
        self.batch_size = batch_size
        self._session = None
        self._tokenizer = None
        self._lock = threading.Lock()

    def _load(self):
        if self._session is not None:
            return
        with self._lock:
            if self._session is not None:
                return
            try:
                import onnxruntime as ort
                from tokenizers import Tokenizer
            except ImportError as exc:
                raise EmbeddingUnavailable(
                    "onnx backend needs onnxruntime and tokenizers (pip install -r requirements-onnx.txt)"
                ) from exc
            model_path = os.path.join(self.model_dir, "model.onnx")
            tok_path = os.path.join(self.model_dir, "tokenizer.json")
            if not (os.path.isfile(model_path) and os.path.isfile(tok_path)):
                raise EmbeddingUnavailable(f"{self.model_dir} must contain model.onnx and tokenizer.json")
            tokenizer = Tokenizer.from_file(tok_path)
            tokenizer.enable_truncation(max_length=self.max_length)
            tokenizer.enable_padding()
            opts = ort.SessionOptions()
            opts.intra_op_num_threads = int(os.getenv("EMBEDDING_ONNX_THREADS", "0")) or os.cpu_count() or 1
            self._session = ort.InferenceSession(model_path, opts, providers=["CPUExecutionProvider"])
            self._input_names = {i.name for i in self._session.get_inputs()}
            self._tokenizer = tokenizer

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        import numpy as np

        self._load()
        out: list[list[float]] = []
        for i in range(0, len(texts), self.batch_size):
            batch = self._tokenizer.encode_batch(texts[i : i + self.batch_size])
            ids = np.array([e.ids for e in batch], dtype=np.int64)
            mask = np.array([e.attention_mask for e in batch], dtype=np.int64)
            feeds = {"input_ids": ids, "attention_mask": mask}
            if "token_type_ids" in self._input_names:
                feeds["token_type_ids"] = np.zeros_like(ids)
            hidden = self._session.run(None, feeds)[0]  # (batch, seq, dim)
            m = mask[..., None].astype(np.float32)
            pooled = (hidden * m).sum(axis=1) / np.clip(m.sum(axis=1), 1e-9, None)
            pooled /= np.clip(np.linalg.norm(pooled, axis=1, keepdims=True), 1e-12, None)
            out.extend(_pad(v.tolist(), self.dim) for v in pooled)
        return out


# ── factory ─────────────────────────────────────────────────────────────────

_cached: dict[tuple, Embedder | None] = {}
_cache_lock = threading.Lock()


def resolve_backend(backend: str, mode: str, edge_url: str | None) -> str:
    if backend != "auto":
        return backend
    if mode == "CLOUD":
        return "http" if edge_url else "none"
    return "sentence-transformers"


def get_embedder(settings=None) -> Embedder | None:
    """Return the configured embedder (cached), or None for backend ``none``."""
    if settings is None:
        from ..config.settings import get_settings

        settings = get_settings()
    backend = resolve_backend(
        settings.EMBEDDING_BACKEND, settings.MODE, settings.EDGE_EMBEDDING_URL
    )
    token = settings.EDGE_EMBED_TOKEN.get_secret_value() if settings.EDGE_EMBED_TOKEN else None
    key = (backend, settings.EMBEDDING_MODEL_NAME, settings.EDGE_EMBEDDING_URL, settings.EMBEDDING_ONNX_DIR)
    with _cache_lock:
        if key in _cached:
            return _cached[key]
        if backend == "none":
            embedder: Embedder | None = None
        elif backend == "hash":
            embedder = HashEmbedder()
        elif backend == "sentence-transformers":
            embedder = SentenceTransformerEmbedder(settings.EMBEDDING_MODEL_NAME)
        elif backend == "http":
            if not settings.EDGE_EMBEDDING_URL:
                raise ValueError("EMBEDDING_BACKEND=http requires EDGE_EMBEDDING_URL")
            embedder = HttpEmbedder(settings.EDGE_EMBEDDING_URL, settings.EMBEDDING_MODEL_NAME, token)
        elif backend == "onnx":
            if not settings.EMBEDDING_ONNX_DIR:
                raise ValueError("EMBEDDING_BACKEND=onnx requires EMBEDDING_ONNX_DIR")
            embedder = OnnxEmbedder(settings.EMBEDDING_ONNX_DIR, settings.EMBEDDING_MODEL_ID)
        else:
            raise ValueError(f"Unknown EMBEDDING_BACKEND {backend!r}")
        _cached[key] = embedder
        return embedder


def reset_embedder_cache() -> None:
    with _cache_lock:
        _cached.clear()
