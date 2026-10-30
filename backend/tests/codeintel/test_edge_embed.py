"""Edge query embedding: the server's guards, and the client's fallback to the local model."""

import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from app.codeintel.edge_server import MAX_TEXTS, _Bucket, make_handler
from app.codeintel.embeddings import EdgeFirstEmbedder, HashEmbedder

TOKEN = "t" * 40


class FakeLocal:
    """Stands in for OnnxEmbedder: same model id as the edge, counts its calls."""

    model_id = "hash-v1"
    query_prefix = document_prefix = ""
    _session = None

    def __init__(self):
        self.calls = 0

    def encode_raw(self, texts):
        self.calls += 1
        return HashEmbedder().embed_documents(texts)


@pytest.fixture
def edge():
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(HashEmbedder(), TOKEN, _Bucket(1000, 1000)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def _post(url, body, token=TOKEN):
    req = urllib.request.Request(url + "/embed/batch", data=json.dumps(body).encode(), method="POST",
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.load(resp)
    except urllib.error.HTTPError as exc:
        return exc.code, json.load(exc)


def test_server_requires_the_token_and_bounds_inputs(edge):
    assert _post(edge, {"texts": ["a"]}, token="wrong")[0] == 401
    assert _post(edge, {"texts": []})[0] == 400
    assert _post(edge, {"texts": ["x"] * (MAX_TEXTS + 1)})[0] == 400
    assert _post(edge, {"texts": [123]})[0] == 400
    status, data = _post(edge, {"texts": ["verify a password"]})
    assert status == 200 and data["model_id"] == "hash-v1" and len(data["embeddings"][0]) == 768
    with urllib.request.urlopen(edge + "/health", timeout=5) as resp:
        assert json.load(resp) == {"ok": True, "model_id": "hash-v1"}


def test_server_rate_limits():
    handler = make_handler(HashEmbedder(), TOKEN, _Bucket(rate=0.0001, burst=1))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        assert _post(url, {"texts": ["a"]})[0] == 200
        assert _post(url, {"texts": ["a"]})[0] == 429
    finally:
        server.shutdown()


def test_client_prefers_the_edge_and_never_loads_the_local_model(edge):
    local = FakeLocal()
    e = EdgeFirstEmbedder(edge, TOKEN, local)
    assert e.embed_query("verify a password") == HashEmbedder().embed_query("verify a password")
    assert (e.edge_calls, local.calls) == (1, 0)


def test_client_falls_back_and_skips_a_dead_edge_for_a_while():
    local = FakeLocal()
    e = EdgeFirstEmbedder("http://127.0.0.1:9", TOKEN, local, timeout=0.5, retry_after=60)
    e.embed_query("a")
    e.embed_query("b")  # within retry_after: straight to the local model
    assert (e.edge_calls, local.calls) == (0, 2)


def test_client_refuses_an_edge_running_another_model(edge):
    local = FakeLocal()
    local.model_id = "granite-embedding-english-r2-int8"  # edge serves hash-v1
    e = EdgeFirstEmbedder(edge, TOKEN, local)
    e.embed_query("a")
    assert (e.edge_calls, local.calls) == (0, 1)


def test_client_with_a_wrong_token_falls_back(edge):
    local = FakeLocal()
    EdgeFirstEmbedder(edge, "nope", local).embed_query("a")
    assert local.calls == 1


def test_client_reuses_one_connection(edge):
    local = FakeLocal()
    e = EdgeFirstEmbedder(edge, TOKEN, local)
    e.embed_query("a")
    first = e._client
    e.embed_query("b")
    assert e._client is first and e.edge_calls == 2 and local.calls == 0


def test_client_retries_a_dropped_connection_once_before_falling_back(edge):
    import httpx

    local = FakeLocal()
    e = EdgeFirstEmbedder(edge, TOKEN, local)
    real = e._http()

    class DropsOnce:
        def __init__(self):
            self.dropped = False

        def post(self, *args, **kwargs):
            if not self.dropped:
                self.dropped = True
                raise httpx.RemoteProtocolError("server closed the idle connection")
            return real.post(*args, **kwargs)

        def close(self):
            pass

    e._client = DropsOnce()
    e.embed_query("a")
    assert (e.edge_calls, local.calls) == (1, 0)
