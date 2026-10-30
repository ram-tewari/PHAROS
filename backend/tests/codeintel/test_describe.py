"""Contextual descriptions: grounded, cached per file version, re-embedded, reused by the indexer."""

import re

from sqlalchemy import select

from app.codeintel.describe import describe_repository, grounded
from app.codeintel.indexer import CodeIndexer
from app.codeintel.text import with_description
from app.database.models import ChunkDescription, DocumentChunk, Repository


class FakeLLM:
    model = "fake-1"

    def __init__(self):
        self.prompts = []

    def complete(self, instructions, prompt, schema):
        self.prompts.append(prompt)
        ids = re.findall(r"^## (C\d+) ", prompt, re.M)
        items = [{"id": i, "description": f"Checks things for snippet {i}."} for i in ids]
        if items:  # one hallucinated identifier: must be rejected
            items[0]["description"] = "Calls made_up_helper() to finish."
        return {"items": items + [{"id": "C999", "description": "not issued"}]}


def test_grounding_rejects_identifiers_the_code_lacks():
    code = "def verify_password(pw, stored):\n    return hmac.compare_digest(hash_pw(pw), stored)"
    assert grounded("Compares a password hash with the stored one using compare_digest.", code)
    assert grounded("Checks a password against the stored hash.", code)
    assert not grounded("Delegates to check_secret() for the comparison.", code)


def test_description_goes_before_the_body():
    summary = '[python] a.py :: f\ndef f(x):\n    """Doc."""\n    return x\n    calls: [g]'
    assert with_description(summary, "Returns x.").split("\n")[3] == "    purpose: Returns x."
    block = "[c] lib/a.c\n  int x = 1;"
    assert with_description(block, "Sets x.").split("\n")[1] == "    purpose: Sets x."


def test_describe_caches_reembeds_and_survives_reindexing(session, indexed, fixture_repo, embedder):
    ref, _ = indexed
    repo = session.execute(select(Repository).where(Repository.url == ref.canonical_url)).scalar_one()
    llm = FakeLLM()
    stats = describe_repository(session, repo.id, fixture_repo.path, llm, embedder, limit=5)
    assert stats.candidates == 5 and stats.rejected == 1 and stats.described == 4 and stats.reembedded == 4
    assert all("C999" not in p for p in llm.prompts)  # only issued ids are sent
    cached = session.execute(select(ChunkDescription)).scalars().all()
    assert len(cached) == 4 and {c.model for c in cached} == {"fake-1"}
    described = session.execute(select(DocumentChunk).where(DocumentChunk.symbol_name == cached[0].symbol_name)
                                ).scalar_one()
    assert "purpose: Checks things" in described.semantic_summary
    assert "made_up_helper" not in str([c.description for c in cached])

    # A second run skips what is cached; a forced re-index keeps the descriptions in the summaries.
    again = describe_repository(session, repo.id, fixture_repo.path, FakeLLM(), embedder, limit=5)
    assert not {c.symbol_name for c in cached} & {e["symbol"] for e in again.examples}
    CodeIndexer(session, embedder).index(ref, force=True)
    rebuilt = session.execute(select(DocumentChunk).where(DocumentChunk.symbol_name == cached[0].symbol_name)
                              ).scalar_one()
    assert "purpose: Checks things" in rebuilt.semantic_summary
