"""Query-embedding server for the owner's machine (the "edge").

The free production instance (512 MB) can embed queries itself, but with
granite-embedding-english-r2 that costs ~200 MB of its memory. With
``EMBEDDING_BACKEND=edge-onnx`` it asks this server first and loads its own
copy of the model only while the edge is unreachable (see ``EdgeFirstEmbedder``).

    python -m app.codeintel.edge_server      # 127.0.0.1:8790, model from EMBEDDING_ONNX_DIR

Binds loopback only; publish it with ``tailscale funnel`` (see
backend/deployment/mac/). Every request but ``GET /health`` needs
``Authorization: Bearer $EDGE_EMBED_TOKEN`` (constant-time compare). Inputs are
bounded (texts per request, characters per text, body size) and rate-limited,
so a leaked URL cannot be used for bulk embedding. Texts are embedded exactly
as given (``encode_raw``): the client adds the model's query prefix. Nothing
is logged but counts.

``POST /embed/batch`` ``{"texts": [...]}`` -> ``{"model_id": ..., "embeddings": [...]}``
"""

from __future__ import annotations

import hmac
import json
import logging
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .embeddings import Embedder, OnnxEmbedder

logger = logging.getLogger(__name__)

MAX_TEXTS = 16
MAX_TEXT_CHARS = 4000
MAX_BODY_BYTES = 128 * 1024
RATE_PER_SECOND = 10.0
BURST = 30


class _Bucket:
    def __init__(self, rate: float, burst: int):
        self.rate, self.burst, self.tokens, self.at = rate, burst, float(burst), time.monotonic()
        self.lock = threading.Lock()

    def take(self) -> bool:
        with self.lock:
            now = time.monotonic()
            self.tokens = min(self.burst, self.tokens + (now - self.at) * self.rate)
            self.at = now
            if self.tokens >= 1:
                self.tokens -= 1
                return True
            return False


def make_handler(embedder: Embedder, token: str, bucket: _Bucket | None = None):
    bucket = bucket or _Bucket(RATE_PER_SECOND, BURST)
    expected = f"Bearer {token}".encode()
    lock = threading.Lock()  # one inference at a time: bounded memory and CPU

    class Handler(BaseHTTPRequestHandler):
        server_version = "pharos-edge"

        def log_message(self, *_args):  # no request logging (queries are private)
            return

        def _send(self, status: int, payload: dict) -> None:
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/health":
                return self._send(200, {"ok": True, "model_id": embedder.model_id})
            return self._send(404, {"error": "not_found"})

        def do_POST(self):
            if self.path != "/embed/batch":
                return self._send(404, {"error": "not_found"})
            if not hmac.compare_digest((self.headers.get("Authorization") or "").encode(), expected):
                return self._send(401, {"error": "unauthorized"})
            if not bucket.take():
                return self._send(429, {"error": "rate_limited"})
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0 or length > MAX_BODY_BYTES:
                return self._send(413, {"error": "body_too_large_or_empty"})
            try:
                texts = json.loads(self.rfile.read(length))["texts"]
            except (ValueError, KeyError, TypeError):
                return self._send(400, {"error": "invalid_json"})
            if (not isinstance(texts, list) or not texts or len(texts) > MAX_TEXTS
                    or not all(isinstance(t, str) and 0 < len(t) <= MAX_TEXT_CHARS for t in texts)):
                return self._send(400, {"error": f"texts must be 1-{MAX_TEXTS} strings of 1-{MAX_TEXT_CHARS} chars"})
            with lock:
                vectors = embedder.encode_raw(texts)
            return self._send(200, {"model_id": embedder.model_id, "embeddings": vectors})

    return Handler


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    token = os.getenv("EDGE_EMBED_TOKEN", "")
    if len(token) < 32:
        raise SystemExit("EDGE_EMBED_TOKEN must be set (at least 32 characters)")
    model_dir = os.getenv("EMBEDDING_ONNX_DIR")
    if not model_dir:
        raise SystemExit("EMBEDDING_ONNX_DIR must point at the model (scripts/fetch_onnx_model.py)")
    embedder = OnnxEmbedder(model_dir, os.getenv("EMBEDDING_MODEL_ID") or None, batch_size=MAX_TEXTS)
    embedder.encode_raw(["warm up"])  # load before accepting requests
    host, port = "127.0.0.1", int(os.getenv("EDGE_EMBED_PORT", "8790"))
    server = ThreadingHTTPServer((host, port), make_handler(embedder, token))
    logger.info("edge embed server on %s:%s, model %s", host, port, embedder.model_id)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
