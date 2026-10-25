# Retrieval benchmark — October 2026

Measured on 2026-10-25 against PHAROS commit `5dc651d`. Raw results:
[`backend/benchmarks/results/codeqa_v1_2026-10-25.json`](../../backend/benchmarks/results/codeqa_v1_2026-10-25.json).
Dataset: [`backend/benchmarks/datasets/codeqa_v1.json`](../../backend/benchmarks/datasets/codeqa_v1.json).
Harness: [`backend/benchmarks/retrieval_eval.py`](../../backend/benchmarks/retrieval_eval.py).

## Summary

| Mode (MiniLM embeddings) | Recall@5 | Recall@10 | MRR | nDCG@10 | p50 latency | p95 latency |
|---|---|---|---|---|---|---|
| keyword | 0.516 | 0.649 | 0.477 | 0.488 | 46 ms | 87 ms |
| **dense** | **0.789** | **0.838** | **0.661** | **0.675** | **18 ms** | **24 ms** |
| hybrid | 0.689 | 0.769 | 0.642 | 0.632 | 39 ms | 80 ms |
| graph (`auto` default) | 0.676 | 0.769 | 0.641 | 0.631 | 43 ms | 76 ms |

75 hand-labelled questions over two pinned open-source repositories, k = 10,
CPU only. Latency covers query embedding, candidate retrieval, fusion and
hydration in-process against local PostgreSQL. HTTP overhead is not included.

What the numbers say, with paired bootstrap 95% intervals:

- **Semantic dense retrieval beats keyword search clearly**: nDCG@10 +0.187
  [+0.105, +0.272]. The whole gain comes from natural-language
  ("behavior") questions: +0.236 [+0.147, +0.328], 34 wins and 9 losses.
- **Keyword wins when the question names the identifier**: on "identifier"
  questions keyword and hybrid score 0.959 nDCG versus 0.865 for dense.
- **Hybrid fusion is not better than dense overall**: −0.044 [−0.117, +0.024],
  26 wins and 25 losses. RRF gives the weak keyword ranking equal weight. That
  costs behavior questions (−0.067, not significant) and buys identifier
  questions (+0.094, not significant).
- **Graph expansion is a no-op for ranking.** Top-5 was identical to hybrid on
  73 of 75 questions (Δ nDCG −0.001). By design it only adds callers and
  callees below their seed and never boosts existing hits, so it changes what
  *context* you get, not what ranks first. No measured ranking value.
- **The lexical hash model (`hash-v1`) is not a semantic model.** Its "dense"
  mode is a second lexical ranker. It edges keyword (+0.055 [−0.007, +0.117])
  but is far behind MiniLM.
- **The "17× storage reduction" claim does not hold.** Hybrid storage saves
  about 5% of the database here, not 94%. See [Storage](#storage).

We kept `auto` (hybrid + graph) as the default instead of switching to dense.
Only identifier-style questions, where dense is weakest, separate the two;
the overall difference is inside the noise; and choosing a default by
maximising this same test set would overfit it. A held-out query set is
needed before tuning RRF weights or routing by query type.

## Method

**Corpora.** Pinned at release commits and indexed through the production
path: clone → AST parse → embed → PostgreSQL.

| Repository | Ref | Commit | Files indexed | Chunks | Lines | Source bytes |
|---|---|---|---|---|---|---|
| pallets/flask | 3.0.3 | `c12a5d87` | 82 (.py) | 973 | 17,568 | 561,493 |
| spf13/cobra | v1.8.1 | `e94f6d0d` | 36 (.go) | 621 | 15,714 | 478,352 |

Both repositories parsed with zero AST fallbacks. Together the 118 files are
1,039,845 bytes. Non-source files are skipped: 167 in flask, 30 in cobra.

**Questions and labels.** There are 64 *behavior* questions, which paraphrase
what the code does without naming identifiers (for example "keep the request
context available inside a generator that streams the response"). There are
11 *identifier* questions, which name the API the way a developer would (for
example "Config.get_namespace").

Relevance is graded per indexed symbol: 2 = the implementation asked about,
1 = closely related. The author wrote all labels by reading the source at the
pinned commits, and they were **committed before any retrieval ran on these
repositories** (commit `5dc651d`). Every label was checked against the parser
output. A single annotator who also wrote the system is a real bias risk; the
paraphrasing rule and the pre-registration limit it but do not remove it.
Treat differences inside the confidence intervals as noise.

**Metrics.** Ranking is over distinct symbols in the top 10:
- Recall@k: fraction of labelled symbols in the top k.
- MRR: reciprocal rank of the first labelled symbol.
- nDCG@10: graded gains 2^g − 1.
- Success@1: the top result has grade 2.

Confidence intervals come from a percentile bootstrap over questions (2,000
resamples per mode). Mode-to-mode comparisons use a paired bootstrap of the
per-question differences (5,000 resamples). Latency per question is the
median of 3 timed runs after one warm-up; p50 and p95 are taken over
questions.

**Embedders.**
- `all-MiniLM-L6-v2` (384-d, zero-padded to the 768-d column, which preserves
  cosine) through ONNX Runtime 1.31 on CPU. The weights are Chroma's ONNX
  export. The archive's SHA-256 (`913d7300…16ec3`) matches the hash pinned in
  `chromadb` 0.5.23's source.
- `hash-v1`, PHAROS's offline lexical hashing embedder.

MiniLM is a general-purpose sentence model, not a code model, and it is
**not** the production default (`nomic-ai/nomic-embed-text-v1`).
HuggingFace is unreachable from the benchmark environment, so nomic was not
measured.

**Machine.**

| Component | Value |
|---|---|
| CPU | Intel Xeon @ 2.80 GHz, 4 vCPU |
| Memory | 15.7 GiB |
| GPU | none |
| PostgreSQL | 16.15 |
| pgvector | 0.6.0 |
| Python | 3.13.17 |

Everything ran on one host, so absolute latencies are indicative only.

## Results by question type (nDCG@10)

| Mode | behavior (n=64), MiniLM | identifier (n=11), MiniLM | behavior, hash-v1 | identifier, hash-v1 |
|---|---|---|---|---|
| keyword | 0.407 | 0.959 | 0.407 | 0.959 |
| dense | **0.642** | 0.865 | 0.478 | 0.923 |
| hybrid | 0.575 | 0.959 | 0.506 | 0.959 |
| graph | 0.574 | 0.959 | 0.506 | 0.959 |

Per repository, MiniLM dense scores flask 0.695 and cobra 0.652, against keyword's 0.491 and 0.484.

### Where it fails

Seven questions get zero Recall@10 even with MiniLM dense. Representative failures:

- **Behaviour that lives only in the function body.** "run the persistent pre-run hooks inherited
  from parent commands" should find cobra's `Command.execute`. Chunks are embedded from a semantic
  summary (signature, docstring, resolved calls), not the body, and `execute`'s docstring
  says nothing about pre-run hooks.
- **Undocumented Go functions.** "remove flags from the argument list before looking up the
  command" should find `stripFlags`, which has no doc comment, so its summary is barely more
  than its name.
- **Broader chunks outrank the specific method.** "search the template folders of the app and every
  blueprint" returns the `DispatchingJinjaLoader` class instead of its `get_source` method; the
  tag-serialiser question returns the `flask.json.tag` module.
- **Test functions compete with implementations.** `tests.test_views.test_basic_view` ranks
  for "where is the view function … called".

Embedding a bounded slice of the body alongside the summary is the most likely
improvement. It is not implemented.

## Latency

All values are milliseconds.

| | keyword | dense | hybrid | graph |
|---|---|---|---|---|
| p50, MiniLM run | 46 | 18 | 39 | 43 |
| p95, MiniLM run | 87 | 24 | 80 | 76 |
| p50, hash run | 69 | 15 | 69 | 68 |

Query embedding is p50 4.7 ms with MiniLM and 0.1 ms with hash. Keyword p50
varied between the two runs (46 vs 69 ms) with identical SQL, so it is the
noisiest number here.

**Why keyword is slower than dense.** `EXPLAIN ANALYZE` of the candidate query
shows the GIN index lookup taking 0.1 ms, while the bitmap heap scan takes
16.5 of 16.8 ms. It recomputes `to_tsvector(search_text)` for every matched
row (264 here), for both the recheck and `ts_rank_cd`. A stored, generated
`tsvector` column would remove that work. It is not implemented yet.

**Context assembly** (`retrieve_context` defaults: 8 chunks, 24,000-char budget):
- p50 8,379 chars, p95 19,382 chars. That's about 2,100 tokens at the
  chars/4 heuristic, not a tokenizer count.
- 100% of returned code was verified against the git blob SHA.
- Latency p50 69 ms, p95 182 ms, including fetching source from
  raw.githubusercontent.com with a warm file cache. With a cold cache in the
  first run, p95 was 923 ms.

## Approximate-nearest-neighbour quality

For each question, the 50 dense candidates from the HNSW index (with the
repository filter applied) were compared with an exact scan:

| Embedder | Candidates returned (of 50) | HNSW recall vs exact (mean / worst) |
|---|---|---|
| MiniLM | 50 / 50 always | 0.9995 / 0.96 |
| hash-v1 | as few as **16** | 0.973 / **0.32** |

pgvector 0.6 applies `WHERE` filters after the HNSW graph search. With
poorly separated vectors (hash), a filtered query can come back short even
though `hnsw.ef_search` is raised to 200. Expect the same starvation with any
model once one database holds many repositories. Possible mitigations:
pgvector ≥ 0.8 iterative scans (`hnsw.iterative_scan`), per-repository
partial indexes, or exact search for small filtered sets.

Both runs' query plans used the HNSW index for dense candidates, and a
`BitmapAnd` of the GIN full-text index and the `repository_id` index for
keyword candidates.

## Indexing throughput

| Repository | Embedder | Wall time | Files/s | Chunks/s | Time split |
|---|---|---|---|---|---|
| flask | MiniLM | 30.4 s | 2.7 | 32 | embed 21.8 s (72%), DB write 7.1 s, clone 0.8 s, parse 0.5 s |
| cobra | MiniLM | 14.6 s | 2.5 | 43 | embed 10.7 s, DB write 2.5 s |
| flask | hash | 8.2 s | 10.0 | 119 | DB write 6.1 s (74%) |
| cobra | hash | 4.3 s | 8.4 | 145 | DB write 2.8 s |

With a real model on CPU, embedding dominates. Without one, row-by-row
writes, including HNSW index maintenance on every insert, are the
bottleneck at about 140 chunks/s. Batched `COPY`, or building the HNSW index
after a bulk load, are the obvious next steps for large repositories.

Parsing itself is cheap, about 1,600 symbols/s. Call-graph resolution linked
35% of call sites in flask (998 of 2,843) and 56% in cobra (1,465 of 2,607)
to an in-repository definition. Most of the rest call the standard library
or dependencies. Ambiguous names are deliberately left unlinked: 582 in
flask, 68 in cobra.

## Storage

The project's documentation claimed a "17× storage reduction (100 GB → 6 GB)"
from storing only pointers to code instead of the code itself. Measured on
this corpus, with all tables and indexes after `VACUUM FULL`:

| | Bytes |
|---|---|
| Raw source of the indexed files | 1,039,845 (1.0 MB) |
| PHAROS footprint (hybrid storage) | 18,391,040 (18.4 MB) |
| … of which the HNSW vector index on chunks | 6,537,216 |
| … of which the `document_chunks` table, mostly 3 KB vectors | 8,691,712 |
| Same rows with each chunk's code stored in `content` | 19,341,312 (+950,272) |

- **Hybrid storage reduces the footprint by a factor of 1.05**, about 5%,
  not 17×. Each chunk carries a 3,076-byte vector plus about 900 bytes of
  search text, summary and metadata. The code it points to is 1,374 bytes
  raw, or 654 bytes after PostgreSQL's TOAST compression.
- The index is about **17.7× the size of the source it describes**. That may
  be where a "17×" came from, but it describes growth, not a reduction.
- The design still has real benefits. Code is fetched at the pinned commit
  and verified against the git blob SHA, so it is never stale. Row width
  stays bounded. Source never sits in the database. It just isn't a large
  saving in space.

The documentation has been corrected to say this.

## Reproduce

```bash
cd backend
pip install -r requirements-dev.txt -r requirements-onnx.txt
createdb pharos_bench   # PostgreSQL with pgvector; the script drops and recreates its schema
# all-MiniLM-L6-v2 ONNX export (Chroma's), verify the hash before use:
curl -LO https://chroma-onnx-models.s3.amazonaws.com/all-MiniLM-L6-v2/onnx.tar.gz
echo "913d7300ceae3b2dbc2c50d1de4baacab4be7b9380491c27fab7418616a16ec3  onnx.tar.gz" | sha256sum -c
mkdir -p /tmp/minilm && tar -xzf onnx.tar.gz -C /tmp/minilm
python -m benchmarks.retrieval_eval \
  --database-url postgresql://postgres:postgres@localhost:5432/pharos_bench \
  --embedder hash --embedder onnx=/tmp/minilm/onnx --repeats 3 \
  --out benchmarks/results/my-run.json
```

The script refuses to reset any database whose name does not contain `bench`.

## Not measured

- The production embedding model (`nomic-embed-text-v1`), and any GPU path.
  The edge worker's CUDA setup is **not validated**.
- Scale: two repositories and about 1,600 chunks. Nothing here supports
  claims about thousands of repositories.
- Languages other than Python and Go. The other five AST languages are
  tested for parsing correctness but not for retrieval quality.
- End-to-end usefulness for an AI coding assistant, for example task success
  with versus without PHAROS context.
