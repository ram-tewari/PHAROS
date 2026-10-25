"""Retrieval modes, evidence, explicit unavailability; context with verified code."""

import pytest

from app.codeintel.context import ContextRequest, RepositoryNotFound, assemble_context
from app.codeintel.embeddings import HashEmbedder
from app.codeintel.retrieval import Filters, ModeUnavailable, Retriever


def _symbols(outcome):
    return [h.symbol for h in outcome.hits]


@pytest.mark.parametrize("mode", ["keyword", "dense", "hybrid", "graph"])
def test_every_mode_finds_the_obvious_target(session, indexed, embedder, mode):
    out = Retriever(session, embedder).search("token bucket rate limiter", mode=mode, k=3)
    assert out.mode_used == mode
    assert "tools.ratelimit.limiter.Bucket" in _symbols(out)


def test_hits_carry_pointers_and_evidence(session, indexed, embedder, fixture_repo):
    out = Retriever(session, embedder).search("check a password against the stored hash", mode="hybrid", k=5)
    top = {h.symbol: h for h in out.hits}
    hit = top["shop.auth.verify_password"]
    assert (hit.path, hit.start_line, hit.end_line) == ("shop/auth.py", 20, 24)
    assert hit.commit_sha == fixture_repo.head
    assert hit.parser == "python-ast" and hit.kind == "function"
    assert hit.evidence.keyword_rank is not None and hit.evidence.dense_rank is not None
    assert out.timings_ms["total"] > 0


def test_exact_symbol_name_is_boosted(session, indexed, embedder):
    out = Retriever(session, embedder).search("verify_password", mode="hybrid", k=3)
    assert out.hits[0].symbol == "shop.auth.verify_password"
    assert "exact_symbol_name" in out.hits[0].evidence.boosts


def test_graph_expansion_adds_callees_below_their_seed(session, indexed, embedder):
    from app.codeintel.retrieval import Evidence, Hit
    from app.database.models import DocumentChunk

    r = Retriever(session, embedder)
    seed = session.query(DocumentChunk).filter(DocumentChunk.symbol_name == "shop.api.login_handler").one()
    hits = {str(seed.id): Hit(chunk_id=str(seed.id), score=1.0, evidence=Evidence())}
    expanded = r._expand_graph(hits, Filters())
    added = {cid: h for cid, h in expanded.items() if cid != str(seed.id)}
    names = {session.get(DocumentChunk, __import__("uuid").UUID(cid)).symbol_name for cid in added}
    assert {"shop.auth.authenticate", "shop.auth.TokenSigner.issue"} <= names
    for h in added.values():
        assert h.score < 1.0  # neighbours rank below the seed that pulled them in
        assert h.evidence.graph == [{"via": str(seed.id), "relation": "calls"}]


def test_graph_mode_never_reorders_above_direct_hits(session, indexed, embedder):
    r = Retriever(session, embedder)
    hybrid = r.search("token bucket rate limiter", mode="hybrid", k=3)
    graph = r.search("token bucket rate limiter", mode="graph", k=3)
    assert graph.hits[0].symbol == hybrid.hits[0].symbol


def test_filters(session, indexed, embedder):
    r = Retriever(session, embedder)
    go_only = r.search("rate limit", mode="hybrid", k=5, filters=Filters(languages=["go"]))
    assert go_only.hits and all(h.language == "go" for h in go_only.hits)
    web_only = r.search("token", mode="keyword", k=10, filters=Filters(path_prefix="web/"))
    assert web_only.hits and all(h.path.startswith("web/") for h in web_only.hits)
    methods = r.search("token", mode="keyword", k=10, filters=Filters(kinds=["method"]))
    assert methods.hits and all(h.kind == "method" for h in methods.hits)


def test_path_prefix_wildcards_are_literal(session, indexed, embedder):
    out = Retriever(session, embedder).search("token", mode="keyword", filters=Filters(path_prefix="%"))
    assert out.hits == []


def test_tests_are_downranked(session, indexed, embedder):
    out = Retriever(session, embedder).search(
        "cart total with percentage discount", mode="hybrid", k=10, filters=Filters(path_prefix="tests/")
    )
    assert out.hits and all("test_path_penalty" in h.evidence.boosts for h in out.hits)
    impl = Retriever(session, embedder).search(
        "cart total with percentage discount", mode="hybrid", k=10, filters=Filters(path_prefix="shop/")
    )
    assert impl.hits and not any("test_path_penalty" in h.evidence.boosts for h in impl.hits)


def test_dense_modes_refuse_without_embedder(session, indexed):
    for mode in ("dense", "hybrid", "graph"):
        with pytest.raises(ModeUnavailable, match="no embedding backend"):
            Retriever(session, None).search("anything", mode=mode)


def test_dense_refuses_on_model_mismatch(session, indexed):
    class Other(HashEmbedder):
        model_id = "some-other-model"

    with pytest.raises(ModeUnavailable, match="hash-v1"):
        Retriever(session, Other()).search("cart", mode="dense")


def test_auto_degrades_visibly(session, indexed):
    out = Retriever(session, None).search("token bucket", mode="auto")
    assert out.mode_used == "keyword"
    assert any("dense retrieval unavailable" in w for w in out.warnings)
    assert out.hits


def test_auto_uses_graph_when_embeddings_exist(session, indexed, embedder):
    out = Retriever(session, embedder).search("token bucket", mode="auto")
    assert out.mode_used == "graph" and out.warnings == []


def test_unmatched_query_returns_empty_not_error(session, indexed, embedder):
    out = Retriever(session, embedder).search("zzqx", mode="keyword")
    assert out.hits == []


def test_injection_like_queries_are_harmless(session, indexed, embedder):
    r = Retriever(session, embedder)
    for q in ["'; DROP TABLE document_chunks; --", "a & b | !c", "<script>alert(1)</script>", "\\x00"]:
        r.search(q, mode="hybrid")
    assert r.search("cart", mode="keyword").hits


# ── context assembly ───────────────────────────────────────────────────────


def test_context_returns_verified_code(session, indexed, embedder, fixture_repo):
    ctx = assemble_context(session, embedder, ContextRequest(query="how is a session token verified", max_chunks=4))
    assert ctx["chunks"]
    first = ctx["chunks"][0]
    assert first["code_status"] == "resolved" and first["verified"] is True
    source = (fixture_repo.path / first["path"]).read_text().splitlines()
    assert first["code"] == "\n".join(source[first["start_line"] - 1 : first["end_line"]])
    assert f"{first['path']}:{first['start_line']}-{first['end_line']}" in ctx["context_text"]
    assert ctx["stats"]["approx_tokens"] > 0


def test_context_detects_content_mismatch(session, indexed, embedder):
    from app.database.models import Resource

    for r in session.query(Resource).filter(Resource.identifier == "shop/auth.py"):
        r.content_sha = "0" * 40  # simulate an index that no longer matches git
    session.commit()
    ctx = assemble_context(session, embedder, ContextRequest(query="verify_password", max_chunks=1))
    assert ctx["chunks"][0]["code_status"] == "unavailable:content_mismatch"
    assert ctx["chunks"][0]["code"] is None


def test_context_budget_truncates_and_says_so(session, indexed, embedder):
    ctx = assemble_context(session, embedder, ContextRequest(query="cart", max_chunks=10, max_chars=1000))
    assert len(ctx["context_text"]) <= 1000
    assert ctx["stats"]["truncated"] is True


def test_context_without_code(session, indexed, embedder):
    ctx = assemble_context(session, embedder, ContextRequest(query="cart", include_code=False))
    assert all(c["code"] is None and c["code_status"] == "not_requested" for c in ctx["chunks"])


def test_context_related_neighbours(session, indexed, embedder):
    ctx = assemble_context(session, embedder, ContextRequest(query="authenticate a user with a password", max_chunks=3))
    relations = {(r["relation"], r["symbol"]) for r in ctx["related"]}
    assert relations, "expected callers/callees of the top hits"


def test_context_includes_active_rules(session, indexed, embedder):
    from app.database.models import ProposedRule

    ref, _ = indexed
    session.add(ProposedRule(
        repository=ref.canonical_url, commit_sha="a" * 40, file_path="shop/auth.py", diff_payload="",
        rule_name="Constant-time comparisons", rule_description="Use hmac.compare_digest for secrets.",
        rule_schema={}, confidence=0.9, status="ACTIVE",
    ))
    session.add(ProposedRule(
        repository=ref.canonical_url, commit_sha="a" * 40, file_path="x", diff_payload="",
        rule_name="Pending rule", rule_description="not yet reviewed", rule_schema={}, confidence=0.5,
        status="PENDING_REVIEW",
    ))
    session.commit()
    ctx = assemble_context(session, embedder, ContextRequest(query="password", repository="tinyshop"))
    assert [r["name"] for r in ctx["rules"]] == ["Constant-time comparisons"]
    assert "Constant-time comparisons" in ctx["context_text"]


def test_context_unknown_repository_is_an_error(session, indexed, embedder):
    with pytest.raises(RepositoryNotFound):
        assemble_context(session, embedder, ContextRequest(query="x", repository="nope/nope"))
