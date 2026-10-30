# System evaluation — 29 October 2026

> **Follow-up:** the search recommendations below (default mode, Rust summaries, test/doc/example noise, body text, model) were acted on in [Retrieval, phase 1](retrieval-phase1-2026-10-30.md): held-out nDCG@10 rose from 0.394 / 0.463 to 0.697 / 0.726. The learning findings still stand; that is phase 2.

This evaluates PHAROS one stage at a time: indexing, the call graph, search, context assembly, the pattern-learning engine and the MCP surface. It runs against master `0b017297` and the free production deployment (one Render free instance, Neon free Postgres, all-MiniLM-L6-v2 through ONNX on CPU). The working tree also held an uncommitted change to TypeScript import resolution in `graph.py`. It affects only graph edges for ky, and graph expansion does not change ranking (see [Call graph](#call-graph)).

Raw results:
- [`codeqa_v1_2026-10-29.json`](../../backend/benchmarks/results/codeqa_v1_2026-10-29.json): rerun of the October benchmark.
- [`heldout_v1_2026-10-29.json`](../../backend/benchmarks/results/heldout_v1_2026-10-29.json): new question set, scored locally.
- [`heldout_v1_prod_2026-10-29.json`](../../backend/benchmarks/results/heldout_v1_prod_2026-10-29.json): the same questions, scored against production over HTTP.

New dataset: [`heldout_v1.json`](../../backend/benchmarks/datasets/heldout_v1.json).

## Verdict by stage

| Stage | Verdict | Evidence |
|---|---|---|
| Indexing: parsing and chunking | **Solid** | Chunk boundaries correct for 100% of 10,578 named chunks. 2.8% of C files and 1 of 37 Rust files fall back to line windows. Incremental re-indexing is exact. |
| Indexing: what gets embedded | **Weak for Rust** | Rust doc comments are dropped when attributes sit between the comment and the `fn` (0 of 10 kept). `macro_rules!` is never extracted. |
| Indexing: throughput on the free tier | **Slow but bounded** | About 4 chunks/s, 95% of it embedding. curl (8,636 chunks) took 38 min. Memory peaked at 404–406 MB of 512. |
| Call graph | **Precise, uneven coverage, no ranking value** | 39 of 40 sampled edges correct. 98% of calls to in-repo names linked in curl, 76% in click. Graph mode changes nDCG by −0.001. |
| Search | **Good on known repos, mediocre on new ones** | Dense nDCG@10 is 0.675 on codeqa_v1 but 0.461 on the held-out set. The default `auto` mode is significantly worse than dense on the held-out set. |
| Context assembly | **Solid** | 100% of returned code verified against the git blob. Stays within its character budget. p50 54 ms locally. |
| Pattern learning (profiles) | **Not trustworthy** | Python only. Several headline claims are wrong or misleading: "repository pattern", "46% type hints", and patterns marked abandoned with 0.95 confidence that are still in the code. |
| Pattern learning (rule loop) | **Not wired** | Nothing enqueues extraction jobs. Production has 0 rules. The manual propose/accept path works. |
| MCP and API | **Works** | All 4 MCP tools succeed on production. Auth scoping is correct. Cold start is 52–83 s on the free tier. |

## Search

### Reproducibility

Rerunning codeqa_v1 (75 questions over flask and cobra) on current master reproduces the 25 October numbers:

| Mode (MiniLM) | Recall@10 | MRR | nDCG@10 | 25 Oct nDCG@10 |
|---|---|---|---|---|
| keyword | 0.649 | 0.471 | 0.486 | 0.488 |
| dense | 0.838 | 0.661 | 0.675 | 0.675 |
| hybrid | 0.769 | 0.638 | 0.628 | 0.632 |
| graph (`auto`) | 0.769 | 0.637 | 0.627 | 0.631 |

The 25 October run used Chroma's ONNX export and pgvector 0.6.0. This run used the Hugging Face export pinned in `scripts/fetch_onnx_model.py`, on PostgreSQL 17.11 with pgvector 0.8.7. Dense results are identical, so it is the same model.

### Held-out set

codeqa_v1 was the only labelled set, and its two repositories (flask, cobra) informed every earlier conclusion. heldout_v1 adds 51 questions (43 behavior, 8 identifier) with 127 graded labels. They cover four repositories in four languages that codeqa_v1 has none of, pinned at the commits production indexed:

| Repository | Language | Commit | Questions |
|---|---|---|---|
| pallets/click | Python | `2247b35e` | 13 |
| sindresorhus/ky | TypeScript | `35418888` | 13 |
| dtolnay/anyhow | Rust | `bb1b0f9a` | 11 |
| curl/curl | C | `87c4c6d6` | 14 |

Labels were written from the source and checked against parser output only, and the file was hashed before any retrieval ran on it. One label was corrected at that stage because `macros.rs` has no symbols (see [Indexing](#indexing)). The final file's SHA-256 is `bdb021fc…10b`.

| Mode (MiniLM) | Recall@10 | MRR | nDCG@10 [95% CI] | Success@1 | Tests/docs/examples in top 5 |
|---|---|---|---|---|---|
| keyword | 0.425 | 0.320 | 0.317 [0.215, 0.424] | 0.216 | 28.6% |
| **dense** | **0.585** | **0.521** | **0.461 [0.358, 0.567]** | **0.294** | **15.7%** |
| hybrid | 0.474 | 0.438 | 0.395 [0.282, 0.509] | 0.275 | 19.6% |
| graph (`auto`) | 0.469 | 0.438 | 0.393 [0.281, 0.508] | 0.275 | 20.0% |

Production returned the same scores for every mode: dense 0.461, `auto` 0.395. So the free deployment (batch size 4, a single ONNX thread, Neon) costs no quality.

Paired bootstrap on nDCG@10, 5,000 resamples:
- **Dense beats keyword** by +0.144 [+0.060, +0.226], with 30 wins and 7 losses. This replicates codeqa_v1.
- **Hybrid is worse than dense** by −0.066 [−0.134, −0.002], with 11 wins and 19 losses. On codeqa_v1 this gap was inside the noise. With both sets pointing the same way, the current default (`auto` = hybrid + graph) is the wrong choice for natural-language questions.
- **Graph matches hybrid**, at −0.001 on both sets.

By question type, behavior questions favour dense and identifier questions favour hybrid:

| Mode | behavior (n=43) | identifier (n=8) |
|---|---|---|
| keyword | 0.203 | 0.928 |
| dense | **0.380** | 0.897 |
| hybrid | 0.284 | **0.987** |

By repository (dense nDCG@10): click 0.594, curl 0.499, ky 0.480, anyhow **0.234**. The Rust score is explained by the doc-comment bug below. Dense gets zero recall@10 on 11 of the 51 questions, and 4 of those are anyhow questions.

**Held-out is much harder than codeqa_v1** (0.461 against 0.675). Possible reasons, none tested separately:
- the questions cover more languages and larger repositories (curl has 8,636 chunks);
- C functions mostly carry their behaviour in the body, not in a docstring;
- codeqa_v1's paraphrases may sit closer to its repositories' docstrings.

### A routing rule that helps on both sets

The rule: send a query to hybrid if it is identifier-shaped, and to dense otherwise. Identifier-shaped means it matches the existing `_IDENTIFIER_SHAPE_RE` or has at most two words. It looks only at the query text, never at the category labels.

| Dataset | `auto` (current default) | dense | routed | routed − `auto` [95% CI] |
|---|---|---|---|---|
| codeqa_v1 | 0.627 | 0.675 | 0.687 | +0.060 [−0.004, +0.130] |
| heldout_v1 | 0.393 | 0.461 | 0.475 | +0.082 [+0.020, +0.147] |

Caveat: the "two words or fewer" condition was chosen after seeing codeqa_v1's identifier questions, so codeqa_v1 is not an independent test of it. heldout_v1 is. A third set should confirm the rule before it becomes the default.

### Test, doc and example files crowd the results

15–29% of top-5 results are tests, docs or examples, depending on mode. They match a query's words, and nothing in retrieval down-weights them. In production, "TLS certificate verification" on curl returned `docs/examples/*-tls.c` above `lib/vtls`.

### ANN quality

On pgvector 0.8.7, every filtered dense query returned all 50 requested candidates, with HNSW recall 1.000 against an exact scan. The candidate shortfall reported for pgvector 0.6.0 does not appear here. The production Neon pgvector version was not checked.

## Context assembly

Measured on heldout_v1 with defaults (8 chunks, 24,000-character budget):
- **Size:** p50 5,906 characters (about 1,500 tokens by the chars/4 heuristic), p95 18,076, maximum 24,000 (exactly the budget).
- **Verification:** 100% of returned code verified against the git blob SHA.
- **Latency:** p50 54 ms and p95 132 ms locally, including fetching source from raw.githubusercontent.com. In production, MCP `retrieve_context` took 1.8 s with a cold source cache.

## Indexing

**Parse coverage**, over 2,788 indexed source files from click, ky, anyhow, curl, redis, libuv and jq:

| Language | Files | Line-window fallback |
|---|---|---|
| C | 2,323 | 66 (2.8%, `parse_error`, macro-heavy files) |
| Python | 206 | 0 |
| TypeScript | 98 | 0 |
| Rust | 37 | 1 (`src/macros.rs`) |
| Ruby | 9 | 9 (`unsupported_language`) |

A file falls back only when tree-sitter reports errors *and* yields no symbols, which is the right threshold.

**Chunk boundaries.** All 10,578 named chunks (function, method, class and so on) in click, ky, anyhow and curl start at their definition.
- An automatic check first flagged 199. All were chunks that correctly start at a decorator, or one of 5 empty `__init__.py` files.
- No chunk stores code: GitHub repositories keep summaries only, and code is fetched and verified when it is retrieved.

**What gets embedded.** A chunk's vector comes from its summary (signature, doc comment, resolved calls), so a missing doc comment directly hurts dense search.

| Repository | Functions with a doc comment directly above | Doc text in the summary |
|---|---|---|
| curl (C) | 1,000 | 996 (99.6%) |
| ky (TypeScript) | 58 | 58 (100%) |
| anyhow (Rust) | 14 | 4 (29%) |

**Bug:** in Rust, when `#[...]` attributes sit between the `///` comment and the `fn`, the comment is lost (0 of 10 kept). An example is `Error::root_cause`, whose summary is only its signature and calls. This is common in idiomatic Rust (`#[must_use]`, `#[cfg]`, `#[inline]`).

**Gap:** Rust `macro_rules!` definitions are not extracted as symbols. In anyhow that hides the public API (`anyhow!`, `bail!`, `ensure!`), and `macros.rs` ends up as 60-line windows. C function-like macros were not checked.

**Incremental re-indexing** (click with one file edited, one deleted and one added):
- The same commit again is a no-op.
- After the change, 2 files were re-indexed and 89 skipped as unchanged, and the deleted file's chunks were removed.
- A renamed function replaced the old name, and the new function was the top search hit.

**Throughput and resources:**

| Setting | Repository | Chunks | Time | Breakdown |
|---|---|---|---|---|
| Production (0.1 CPU) | curl | 8,636 | 38 min | Embedding 2,177 s of 2,292 s (95%) |
| Production (0.1 CPU) | click | 1,517 | 409 s | — |
| This Mac | curl | 8,636 | 71 s | Embedding 37 s, database write 31 s |

- **Memory:** production peaked at 404–406 MB of 512 MB whatever the repository size.
- **Storage:** about 10 KB per chunk on Neon. Six repositories with 12,984 chunks use 164.5 MB of the 0.5 GB free tier.

## Call graph

**Precision.** 40 resolved call edges were sampled (seed 20261029), 20 each from click and curl, and stratified by how each was resolved. 39 are correct: 97.5%, Wilson 95% CI about 87–99.6%.
- The error: `err.getvalue()` on a `BytesIO` in a test was linked to `HelpFormatter.getvalue`, because that is the repository's only method with that name.
- This is the inherent risk of `unique_name` resolution for method calls. That strategy accounts for 1,149 of click's 1,863 resolved edges.

**Coverage**, measured over calls whose name some function in the repository defines:

| Repository | Linked | Unlinked |
|---|---|---|
| curl (C) | 98.2% | Mostly names defined twice under different `#ifdef` branches |
| click (Python) | 76.1% | Almost all method calls on names several classes define (`self.invoke`, `ctx.get_usage`), which would need the receiver's type |

**Retrieval value.** None for ranking, on both sets (Δ nDCG −0.001). The graph's value is the callers and callees it adds to context, which no metric here measures.

**TypeScript imports.** Before the fix in the working tree, ESM imports written as `./x.js` for `x.ts` resolved to nothing: ky had 0 import edges. With the fix it has 164. Call edges barely changed (605 to 609), because named imports are not used for call resolution.

## Pattern learning

### Profiles (`POST /api/patterns/learn`)

Run on click from its GitHub URL (200-commit clone, 11.7 s). The analyzer reads `.py` files only, so it has nothing to say about TypeScript, Rust or C repositories.

Each headline claim was checked against the source:

| Claim | Check | Holds? |
|---|---|---|
| snake_case functions, PascalCase classes, no async, no bare `except`, 17 custom exceptions | Consistent with the source | yes |
| "Uses the repository pattern" | Triggered by a filename containing "repo": `examples/repo/repo.py`, an example CLI | **no** |
| "Factory pattern" | Triggered by at least two functions named `make_*` or `create_*` | weak heuristic |
| "Type-hint coverage 46%" | Recomputed: `src/click` parameters are 100% annotated, tests 3.6%. The figure averages library and tests together | **misleading** |
| `groups_imports: false` | Hard-coded to `False` in `ast_analyzer.py` | **not measured** |
| 13 "abandoned" patterns, most at 0.95 confidence, "removed during bugfix" | The `except Exit`, `except Abort` and `except ClickException` handlers are in `core.py` at `2247b35e`, the branch head indexed earlier the same day, and `_NumberRangeBase` there has exactly the "abandoned" method list. The history analysis used a slightly newer clone, which was not inspected | **false, as far as checked** |

An assistant given this profile as coding guidance would be told things about click that are not true.

### Rules loop

The design is:
1. Something enqueues diffs on the Redis queue `pharos_extraction_jobs`.
2. A local GPU worker runs an LLM (Ollama) over each diff and posts proposed rules to `/api/patterns/propose`.
3. A human accepts the rule.
4. `retrieve_context` includes ACTIVE rules for that repository.

- **Step 1 does not exist.** No code writes to that queue, and `FEEDBACK_REDIS_QUEUE` is defined but never read.
- **Production** has no Redis and no LLM, and holds 0 rules and 0 profiles.
- **Steps 2–4, driven by hand, work locally:**
  - propose and accept need the admin token (the read token gets 403);
  - pending rules stay out of context;
  - an accepted rule appears in the repository's context and in the rendered text;
  - it does not leak into other repositories.

## MCP and operations

- **MCP:** server `pharos` 1.30.0, protocol `2025-06-18`. All four tools succeed:
  - `retrieve_context`: 1.8 s
  - `search_code`: 341 ms
  - `find_symbol`: 584 ms
  - `list_repositories`: 240 ms
- **Search latency in production:** server-side p50 29–98 ms depending on mode. Client-side p50 260–330 ms, measured from the US East Coast to Oregon.
- **Cold start:** 52–83 s after the instance sleeps.
- **Auth:** missing token → 401, read token on admin routes → 403. Ingestion, proposing rules and accepting rules all require admin.

## Recommendations, by expected impact

1. **Change the default search mode.**
   - **What:** route identifier-shaped queries to hybrid and everything else to dense.
   - **Why:** +0.06 to +0.08 nDCG@10 over the current `auto` on both sets.
   - **Before making it the default:** confirm on a third question set.
2. **Fix Rust summaries.** Attach `///` comments across attribute lines, and extract `macro_rules!` as symbols. anyhow is the weakest repository (dense 0.234), and its main API is invisible to symbol lookup.
3. **Down-weight tests, docs and examples** unless the query asks for them. They are 15–29% of top-5 results.
4. **Embed part of the function body.** This was already suggested in October; 11 of 51 held-out questions get zero recall@10 with dense, mostly behaviour that lives only in the body.
5. **Learning: mark it experimental, or rebuild it.**
   - **Why:** the profile heuristics produce confident false claims, and the rule loop has no producer.
   - **Minimum fixes:**
     - judge patterns by path role (separate library, tests and examples);
     - drop the filename-substring checks;
     - check "abandoned" patterns against the current code.
6. **Call graph.** It is precise enough, but has no ranking value. Python method resolution by receiver type would raise click's coverage, but matters only if callers and callees in context prove useful, which needs its own measurement.

## Caveats

- **Labels:** one annotator, who also ran the system, wrote every label in the held-out set, from the source and before any retrieval. That limits bias but does not remove it.
- **Sample sizes:** small (n=51 and n=75). Differences inside the intervals are noise.
- **Graph checks:** edge precision rests on a 40-edge sample, and coverage counts only calls to names the repository defines.
- **Learning checks:** one repository (click).
- **Model:** MiniLM is a general sentence model, not a code model. All conclusions about dense search are about this model.
