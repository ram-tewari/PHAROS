> **Amended on approval day (13 Nov 2026), before any feature code:** the benchmark is c-CRAB, not SWE-Gate. SWE-Gate takes its review constraints from ten seed repositories and attaches them to tasks in other repositories, so memory learned from a repository's own history could not know them. Wherever this plan says SWE-Gate, read [the protocol](../docs/benchmarks/phase3-eval-protocol.md). The stopped Phase 2 version 2 run is also not resumed in workstream 2, because its scratch database no longer exists.

# PHAROS Phase 3: memory that learns how maintainers work

## Context

Phase 2 memory failed its locked evaluation (55% precision against a 90% target, no gain in
source-file recall) and the second run was stopped without a verdict. The repository also carries
about 150,000 lines of legacy code around a 9,000-line core. This phase does three things at once:
clears the legacy code, records a baseline of the current system, and rebuilds memory and
convention learning on what current research says works, ending in one locked benchmark.

Decisions already made by the owner:
- **Test agent:** Claude Code headless (`claude -p`), not Codex.
- **Cleanup:** remove all legacy code from master, keep a `legacy-2026-11` tag. Production tables are not dropped.
- **Models:** workstreams 1 and 2 run on Haiku; workstream 3 runs on Opus 5.5 at high effort.

## What the research says, and what it changes

| Finding | Source | Design consequence |
|---|---|---|
| LLM-generated context files lower task success and raise cost by 20% or more; only non-standard practices help | [Gloaguen et al., ETH](https://arxiv.org/abs/2602.11988) | Drop the always-on brief from `retrieve_context`. Serve only conventions an agent would not guess, scoped to the files in play. This also withdraws my earlier idea of emitting an `AGENTS.md`. |
| About half of test-passing agent PRs would not be merged; 34% of functionally correct repairs fail review constraints | [METR](https://metr.org/notes/2026-03-10-many-swe-bench-passing-prs-would-not-be-merged-into-main/), [SWE-Gate](https://arxiv.org/abs/2609.04167) | The target is "would a maintainer accept this", measured on SWE-Gate, whose constraints come from real review comments and whose grading is Docker tests with no LLM judge. |
| Compact experience recalled at the start, detail only when the agent struggles, then evicted, beats injecting everything (27.6% vs 24.9% resolved, 17% cheaper) | [REM](https://arxiv.org/abs/2610.27377), [SWE-ContextBench](https://arxiv.org/abs/2602.08316) | Progressive disclosure: one-line items first, evidence on request. Abstain when nothing clears a relevance bar; wrong memory hurts more than none. |
| Searchable commit history moves agents from brute-force exploration to hypothesis-driven search (Acc@5 71.6% to 76.5%) | [RepoMem](https://www.alphaxiv.org/abs/2510.01003) | Add precedent tools: find a similar past change and return its shape. |
| Corrections compiled into reusable checks cut violations far more than recalled prose | [TellOnce](https://arxiv.org/abs/2606.13174) | A convention becomes a predicate that can be run against a diff, not a sentence. |
| Skills kept or retired on downstream results beat prompt-written skills by 5 points | [CodeSkill](https://arxiv.org/abs/2605.25430) | Track whether each served item helped, and retire those that do not. |
| Memory rankings invert as history grows; write quality and provenance decide long-run recall | [Ground Truth First](https://arxiv.org/abs/2607.21962) | Keep provenance-typed evidence and commit-validity intervals; spend effort on the write path. |
| 75% of review-driven changes concern maintainability; only comments that led to a change are signal | [Beller et al.](https://repository.tudelft.nl/file/File_9eb1b79b-a0f2-4631-9e2c-d71d4081a138), [Bacchelli and Bird](https://2013.icse-conferences.org/content/expectations-outcomes-and-challenges-modern-code-review.html), Qodo and Greptile practice | Mine review comment and the fixing commit as a pair. Unresolved comments are ignored. |
| Developers in unfamiliar code spend about 35% of their time navigating, and interleave seeking, relating and collecting | [Ko et al.](https://faculty.washington.edu/ajko/papers/Ko2006SeekRelateCollect.pdf) | Shape the tools around the work cycle below. |

Vendor memory benchmarks (Mem0, Zep on LoCoMo and LongMemEval) are self-reported and conflict, so
nothing here is designed around them.

**Work cycle mapped to tools:**

| Stage of a change | What experienced developers do | PHAROS tool |
|---|---|---|
| Locate | Form a hypothesis, search | `retrieve_context`, `find_symbol` (exist) |
| Find precedent | Copy the shape of a similar past change | `find_precedent`, `examine_commit` (new) |
| Edit | Follow local norms for those files | `conventions_for(paths)` (new) |
| Complete | Add the tests, docs and changelog that go with it | companion-file rules (rebuilt) |
| Self-review | Check against what reviewers enforce | `check_change(diff)` (new) |
| Learn | Remember what was corrected | `record_outcome` (new) |

## Step 0: before the three workstreams start (main session)

1. Tag `975a38d5` as `legacy-2026-11` and `phase2-baseline`, and push the tags.
2. Write and commit `docs/benchmarks/phase3-eval-protocol.md` and lock its data **before any feature code**:
   - **Test set:** SWE-Gate instances that have a `validation_matrix.json`, from the repositories with the most instances, taken in descending order until at least 100 instances. Fixed by rule, without reading constraint text.
   - **Dev set:** up to 40 instances from other repositories. All tuning happens here.
   - **Leakage rule:** each repository is learned at the parent of its earliest test instance, and review comments are fetched with `before=` that date (`fetch_review_comments` in `backend/app/learning/reviews.py` already takes it). A check asserts no test PR's comments were read.
   - **Arms:** P0 plain Claude Code; A with PHAROS retrieval only; B-old with memory from `phase2-baseline`; B-new with Phase 3 memory. The agent is not shown the constraints.
   - **Test agent:** `claude -p` with a fixed Sonnet 5.5 model, a different model from the builder.
   - **Primary measure:** share of instances passing both functional and constraint tests, B-new minus A, paired bootstrap, lower bound above 0.
   - **Also reported:** B-new minus P0 (does PHAROS beat a plain agent), B-new minus B-old, tokens, turns and time per task.
   - **Guard:** functional pass rate not significantly worse.
   - **Precision:** pooled hold-out compliance of active checkable rules at least 90%, computed with no LLM.
3. Save this plan as `plans/003-phase3-memory.md`.

## Workstream 1: remove legacy code (Haiku, own worktree, branch `legacy-removal`)

- **Delete outright:** `frontend/`, `pharos-cli/`, `notebooklm/`, `.kiro/`, `.kiroignore`, `docs/archive/`, `docs/archive_logs/`, `docs/vision/`, `docs/PHAROS_future_steps.md`, `docs/ORGANIZATION_SUMMARY.md`, `docs/PHAROS_CODE_AUDIT_REPORT.md`, `backend/ml_results/`, `models/classification/`, `pharos-edge.ps1`, `backend/start_worker.*`, legacy pages under `backend/docs/`.
- **Delete with their tests:** `backend/app/modules/{resources,search,graph,planning,patterns,monitoring,pdf_ingestion,github,admin,ingestion}`, `backend/app/ml_monitoring/`, `backend/app/monitoring.py`, and the matching directories under `backend/tests/`. Remove their registration in `backend/app/__init__.py`.
- **Known tangles:** `backend/app/codeintel/symbols.py` and `backend/app/workers/main_worker.py` import legacy modules. `select_rules` in `backend/app/codeintel/context.py` reads `ProposedRule`, which stays.
- **Keep:** `app/codeintel`, `app/learning`, `app/modules/code`, `app/modules/mcp`, `app/workers/{ingest,learning}_worker.py`, `app/shared`, `app/database`, `alembic/`, `benchmarks/`, `scripts/demo.py`, `deployment/`.
- **Rules for the agent:**
  - Delete one module at a time, then run `pytest tests/codeintel tests/learning` and `python scripts/demo.py`.
  - If removing a module needs more than deleting imports and registrations in core code, stop and list it instead of rewriting.
  - No migrations and no table drops.
  - Update `scripts/check_module_isolation.py`, `.github/workflows/ci.yml`, the README's Limitations and layout sections, `CHANGELOG.md`, and regenerate `.secrets.baseline` with detect-secrets 1.5.0.
- **Merge first.** Master auto-deploys to Render, so after merge check `/health`, `/api/v1/system/status` and the eight MCP tools on production.

## Workstream 2: baseline of the current system (Haiku, worktree at `phase2-baseline`, branch `baseline-2026-11`)

Runs existing harnesses only. The agent never edits a harness or dataset; a failure is reported, not fixed.

1. `make test` and `python scripts/demo.py`: pass counts and time.
2. Retrieval, labelled as a reproduction: `benchmarks/retrieval_eval.py --local-checkouts` on `heldout_v1` and `heldout_v2`, with and without `--hints`, against a scratch Postgres 17 named `pharos_bench` (setup in `plans/002-phase2-learning-handoff.md` §3). Compare with 0.697 and 0.726.
3. Production: `benchmarks/prod_eval.py` on `heldout_v1` for nDCG and p50/p95, plus cold-start time.
4. Memory: resume `benchmarks/phase2_eval.py` from the v2 checkpoint with Codex (about 107 calls: precision, judges, Repo QA grading, libuv). If Codex hits its limit, stop and report what finished. Do not switch the judge.
5. Cost of learning: index and learn times, items per repository, database size.
6. Write `docs/benchmarks/baseline-2026-11.md` and commit the raw results.

## Workstream 3: build Phase 3 (Opus 5.5 high, branch per stage, each a PR gated on the dev set)

**S1. Harness.**
- `ClaudeCLI` beside `CodexCLI` in `backend/app/learning/llm.py`, same interface (`ready`, budget, usage, strict JSON). Check the headless flags against the Claude Code docs, not from memory.
- `backend/benchmarks/agent_eval.py`: runs the four arms through `claude -p` with an MCP config per arm, reuses the `Checkpoint` class and bootstrap from `phase2_eval.py`, wraps SWE-Gate's `eval_swe_if.py`, records tokens, turns and time.
- Test-set results go to a sealed file outside the repository until the final run.
- Pilot on five dev instances to size the final run.

**S2. Rules that prove themselves.**
- `backend/app/learning/checks.py`: typed predicates over a commit or diff: companion file, test home, changelog entry, naming, commit message, forbidden API or import, required tool run.
- `backend/app/learning/backtest.py`: learn from commits before a time split, then measure each rule on the commits after it. Store the hold-out rate and counter-examples on the item.
- Existing miners in `miners.py` (`mine_cochange`, `mine_test_homes`, `mine_changelog`, `mine_naming`, `mine_commits`, `mine_tests`) emit predicates. Activation in `MemoryWriter` requires the hold-out rate, replacing "confidence".
- One migration adding `check`, `holdout` and `utility` to `memory_items`.

**S3. Smarter learning.**
- **Review resolution** (extend `reviews.py` and `extract.py`): pair each review comment with the later commit in the same PR that changed the commented lines, and with applied suggestion blocks. Keep only resolved comments. Cluster recurring ones across PRs; support is the number of distinct PRs and reviewers.
- **Pitfalls:** reverts and quick follow-up fixes to the same lines.
- **Tool-enforced rules** (extend `mine_tooling`): what CI, pre-commit and lint config already enforce becomes "run this command", not prose.
- **Not-guessable filter:** drop conventions that match the ecosystem default, and promote those a no-memory agent violates on the dev set.
- **Drift:** a newer contradicting pattern supersedes the old one through the existing validity fields; evidence is weighted by recency and by maintainer role.
- Model-extracted rules are compiled to a predicate where possible; the rest stay advisory with their review evidence.

**S4. Recall shaped to the work cycle.**
- A `repo_commits` table (message, paths, dates, no code) filled by the learner, with FTS that keeps identifiers whole, plus Granite vectors.
- New MCP tools in `backend/app/modules/mcp/` and REST in `backend/app/modules/code/`: `find_precedent`, `examine_commit`, `conventions_for`, `check_change`.
- `memory_for_context` in `backend/app/learning/recall.py`: no brief by default, a relevance threshold with abstention, one-line items with evidence on request.

**S5. Upkeep and session memory.** This stage is the cut line if earlier stages slip.
- `episodes` log (tool, query, returned ids, never code) and `record_outcome`.
- Utility counters per item (served, complied, helped), decay and retirement in a curator pass.
- A reflector that needs two independent episodes, evaluated on dev only. No locked claim is made for it.

**S6. Final benchmark.** One run of all four arms on the locked set, the precision backtest, then
`docs/benchmarks/phase3-memory-<date>.md`, the README results and Limitations, and `CHANGELOG.md`.
The result is reported whether it passes or not.

## Running it

- Three agents launched together, each in its own git worktree: Haiku, Haiku, Opus at high effort.
- Workstream 3 runs as one Opus agent per stage, so each stage starts with a fresh brief and ends in a PR.
- Workstream 1 merges first; workstream 3 rebases on it and regenerates `.secrets.baseline` afterwards.
- Existing rules hold: branch, PR, all CI checks green, the owner reviews and merges.
- The final run uses the owner's Claude plan and checkpoints, so it can pause at usage limits and resume.

## Risks

- **Claude builds the system and takes the test.** Mitigated by Docker-graded results, a different model as test agent, and a sealed test set. It is disclosed in the report.
- **SWE-Gate is Python only**, and 48 of its 303 instances lack validation files. Other languages are covered only by the backtest.
- **SWE-Gate's harness is unverified by us.** S1 starts by running its gold-patch self-test. If it cannot be made to run, the fallback is a new `utility_v3` set built with `benchmarks/make_utility_tasks.py`, locked the same way.
- **Memory may still not help.** The research shows gains are small and easy to reverse. The protocol is fixed first so that a null result is a result.

## Verification

- Workstream 1: CI green on the PR; `make test`, `make demo`, Docker build; production health and MCP tool list after deploy; `git diff --stat legacy-2026-11` shows only deletions outside the files named above.
- Workstream 2: the report's retrieval numbers match the recorded ones within noise, and every figure links to a raw result file.
- Workstream 3: each stage adds tests under `backend/tests/learning` and passes on SQLite and PostgreSQL; the backtest reproduces from a clean checkout; each new MCP tool is called through `claude mcp` against a local server on an indexed repository; the final report's dataset hashes match the locked files.
