# Phase 3 (memory that learns how maintainers work) evaluation protocol — locked on merge

> **Status:** locked when the pull request that adds this file is merged. No Phase 3 feature code
> exists yet. Changes after that go under [Amendments](#amendments), each written before the results
> it could affect.
>
> The Phase 2 protocols and results ([version 1](phase2-memory-2026-11-01.md),
> [version 2, stopped](phase2-memory-v2-partial-2026-11-01.md)) stay as they are. Their test sets are
> spent and become development data.

## The question

Phase 3 rebuilds repository memory so that a coding agent changes a repository the way its
maintainers would. The test: an agent is about to submit a real pull request. Before any human
reviews it, can the agent fix what the maintainers then asked for in review?

## Benchmark: c-CRAB

[c-CRAB](https://arxiv.org/abs/2603.23448) ([data](https://github.com/c-CRAB-Benchmark/dataset),
commit `856dfa31`) is built from real pull requests. Each instance has:

- the repository at the pull request's pre-review commit (`head_commit`), in a published Docker image;
- the maintainers' review comments on that pull request;
- one test per comment, which **fails at `head_commit` and passes at the merged commit**.

So a comment counts as resolved when its test passes. Grading runs tests and uses no LLM judge.

**Why not SWE-Gate.** The plan first named SWE-Gate. Before this protocol was written, its data
showed that review constraints are taken from ten seed repositories and attached to tasks in other
repositories. Memory learned from a repository's own history could not know them, so it does not test
what PHAROS claims. c-CRAB's comments come from the same repository as the task.

## Locked data

[`backend/benchmarks/datasets/ccrab_phase3.json`](../../backend/benchmarks/datasets/ccrab_phase3.json),
SHA-256 `8784fbdf…4427`. It holds instance ids, repositories, commits and counts, and no comment text.

| Set | Rule | Repositories | Instances | Review comments |
|---|---|---|---|---|
| **Test** | repositories with 4 or more instances | 16 | 105 | 135 |
| **Dev** | repositories with 2 or 3 instances | 22 | 50 | 61 |
| **Reserve** | repositories with exactly 1 instance | 29 | 29 | 38 |

- The split is by repository, so no repository is in two sets. Every instance of a chosen repository
  is included. The largest test repositories have 15 instances each (ansible, pandas).
- The reserve is not run in Phase 3. It is kept for a later test.
- All instances are Python. Other languages are covered only by the precision measure.

**What was seen when choosing.** Field names, per-repository counts and creation dates. No review
comment, test file or patch was read. To check that the benchmark runs on this machine, one test
instance (`networkx__networkx-7159`) had its test executed at `head_commit` (failed) and at the merged
commit (passed). Only the pass and fail lines were read.

## The task

For each instance the agent gets:

- a checkout at `head_commit`, with git history up to that commit and nothing later;
- the pull request's title and description;
- this instruction, the same in every arm: *"You wrote this change and are about to ask the
  maintainers of this repository to review it. Revise it so that they would accept it. Do not weaken
  or delete existing tests."*

The agent never sees the review comments, the generated tests, the merged commit or the pull request
page. Web access is off. The agent's final working tree is graded with each comment's test, run in
the instance's Docker image as c-CRAB runs it.

## Arms

| Arm | The agent has |
|---|---|
| **P0** | Claude Code alone: file read, search and edit tools |
| **A** | P0 plus PHAROS retrieval tools (`retrieve_context`, `search_code`, `find_symbol`), memory off |
| **B-old** | A plus memory as built at tag `phase2-baseline`, deterministic tier only |
| **B-new** | A plus Phase 3 memory and its tools |

- **Test agent:** `claude -p` with model `claude-sonnet-5-5`. The system is built with a different
  model (Opus 5.5). The model, prompt, tool permissions and turn limit are identical in every arm
  apart from the tools listed above.
- One attempt per instance per arm. No retries on a poor result. A run that crashes for an
  infrastructure reason (container, network, usage limit) is repeated, and the report counts these.
- B-old has no model-extracted rules, because in Phase 2 those needed a human-reviewed Codex pass.
  This may understate the old system, and the report says so.
- In B-new, no human reviews memory. Which items become active is decided by a rule fixed on the dev
  set and frozen before the test run.

## Learning and leakage

- Memory is learned at each instance's `base_commit`, from history reachable from that commit.
- Only review comments created before that pull request's `created_at` are read, and none from that
  pull request. An automatic check asserts both for every instance, and the report gives its result.
- The retrieval index is built at `head_commit`.
- If learning at every instance proves too costly in the dev pilot, an amendment made before any test
  run may switch to learning once per repository, at the `base_commit` of its earliest test instance.
  The rule may only move in that direction (older memory), never to a later commit.
- **Not controlled:** these are public pull requests from 2016 to 2025, so the test model may have
  seen them in training. That is the same in every arm.

## Measures

Statistics use the instance as the unit: the share of that instance's comments resolved. Differences
are paired bootstraps over instances, 5,000 resamples, seed 1.

| Measure | Target |
|---|---|
| **1. Primary: resolved share, B-new − A** | 95% CI lower bound above 0, over all 105 instances |
| 2. Precision of active checkable rules | at least 90% (below) |
| 3. Grounding | 100% of items cite evidence that exists at the learned commit |
| 4. Guard: size of the agent's revision | B-new's median changed lines no more than twice A's |
| 5. Reported: B-new − P0 | does PHAROS beat a plain agent |
| 6. Reported: B-new − B-old, A − P0 | what Phase 3 added; what retrieval alone adds |
| 7. Reported: cost | tokens, turns and wall time per instance, per arm |
| 8. Reported: leave-one-repository-out on measure 1 | the range of the difference with each repository removed |

Phase 3 **passes** only if measures 1 to 4 all pass.

**Precision.** A checkable rule is one PHAROS can evaluate against a commit. For each test
repository, rules are learned at the earliest test instance's `base_commit`. They are then checked
against the next 200 first-parent commits after it (fewer if the repository has fewer). Precision is
the share of (active rule, commit) pairs where the rule applies and the commit satisfies it, pooled
over repositories. No LLM is involved. Rules that are prose only are reported separately: a sample of
40 is judged against its evidence by the test model and 20 of those by the owner, and that figure is
reported but does not gate.

## Running it

- The locked test set is run **once**, after all tuning on dev, with every arm in the same run.
- The run may pause at usage limits and resume from its checkpoint. A paused run is not looked at.
- Test-set results are written outside the repository until the run is complete.
- **A stopped run has no verdict.** If the run is cancelled before all 105 instances are scored in
  arms A and B-new, the report says so and gives what was measured, as in Phase 2 version 2.
- The result is reported whether it passes or not.

## Development data

- The c-CRAB dev set above.
- Everything from Phases 1 and 2: `codeqa_v1`, `dev_synth_v1`, `utility_dev_v1`, and the now-spent
  `utility_v1`, `utility_v2`, `repoqa_v1`, `repoqa_v2`.
- `heldout_v1` and `heldout_v2` stay locked for retrieval. Phase 3 must leave retrieval ranking
  unchanged; if it changes ranking, those sets are run once more and reported.

## Disclosures

- Claude wrote this protocol, builds the system and is the test agent. The grading is by executed
  tests, the test model differs from the building model, and the test set stays sealed until the run.
- c-CRAB's tests were generated by a model and kept only when an agent could pass them from the
  comment alone. Its authors report 84% agreement that a test is faithful to its comment. A valid fix
  that differs from the maintainer's can fail a test. This affects every arm alike.
- Review comments cover design, correctness and testing as well as conventions. Memory can address
  only part of them, so a small effect is the realistic expectation.

## Amendments

None.
