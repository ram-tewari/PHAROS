# Phase 2 (learning) evaluation protocol, version 2 — locked on merge

> **Status:** the data is built and hashed below. The protocol becomes binding when the pull request that
> adds this file is merged after the owner's review. Nothing in it has been measured yet.
>
> Version 1 ([protocol](phase2-eval-protocol.md), [result](phase2-memory-2026-11-01.md)) stays as it is.
> This version is a new test on new data, not a rerun of version 1, so its results are reported next to
> version 1's, never in place of them. Changes after results exist go under Amendments, as in version 1.

## Why there is a version 2

Version 1 failed on two measures.

**Precision: 55% audited against a target of 90%.**
- Most misses were counts that their evidence showed only by example.
- Others were renamed paths whose evidence did not show the rename, and test homes that cited
  repository-wide commits.
- The miners now attach a tally of everything counted, the renames, and the lines a commit changed. They
  were tuned on development data only.

**Utility: the primary measure, source-file recall, had no room to improve.**
- Without memory, Codex already named every source file the commit touched in 59 of the 80 tasks.
- What memory adds is mostly about the files around a source change: the existing test file to extend,
  the changelog, the docs.
- Version 1 measured that only as a secondary measure. All-file recall improved by +0.089
  [+0.041, +0.138], but that was seen on test data after the fact, so it cannot count as a pass there.
- Version 2 makes the hypothesis primary and tests it on data nobody has seen.

## Locked data

| File | What | SHA-256 |
|---|---|---|
| [`utility_v2.json`](../../backend/benchmarks/datasets/utility_v2.json) | 80 utility tasks, 20 real commits each from attrs, rich, echo and libuv | `52c5dcd7c9e56a99fb5718e61f6103fb20306427f474d1fae604a0a6020cb411` |
| [`repoqa_v2.json`](../../backend/benchmarks/datasets/repoqa_v2.json) | 30 hand-written questions: 14 conventions, 7 history, 7 procedures, 2 abstentions | `12dfb08be9843466178e9e9c3bb7e59f953db7856f4eca4a46398048db59c133` |

| Repository | Language | C0 | C0 date | Removed by the companion rule |
|---|---|---|---|---|
| python-attrs/attrs | Python | `000c5634` | 2025-07-28 | 6 of 26 otherwise-eligible commits |
| Textualize/rich | Python | `1b2dada1` | 2024-08-26 | 5 of 25 |
| labstack/echo | Go | `a9ede66a` | 2026-06-13 | 11 of 31 |
| libuv/libuv | C | `7140827e` | 2026-09-01 | 18 of 38 |

In all, the companion rule removed 40 of 120 otherwise-eligible commits (33%). The tasks were built by
`make_utility_tasks.py --v2` from full clones fetched on 1 November 2026. No task has been read: only the
counts above were looked at. The Repo QA questions were written from each repository's source and
history at C0, without reading the tasks, and before any memory existed for these repositories.

## How the data was chosen

**Repositories.** Four that no phase has used for tuning or testing:
- **Not allowed:** flask, ky, anyhow, jq, click, requests, cobra, curl, chi, gson, immer and
  itsdangerous.
- **Mix:** two Python, one Go, and one C or TypeScript.
- **Each repository must have:**
  - at least 500 non-merge commits;
  - an existing test suite;
  - a changelog or release-notes file;
  - public pull-request reviews.
- **Chosen by the owner:** attrs, rich, echo and libuv. The first proposal, httpx and urfave/cli, was
  replaced after a check against the criteria, before anything was built:
  - httpx had one commit in 2026;
  - urfave/cli has no maintained changelog (its `docs/CHANGELOG.md` changed once since 2025).
- **Checked on 1 November 2026:**

  | Repository | Non-merge commits | In 2026 | Review comments | Changelog |
  |---|---|---|---|---|
  | attrs | 1,834 | 114 | about 1,400 | towncrier fragments into `CHANGELOG.md` |
  | rich | 3,387 | 116 | about 700 | `CHANGELOG.md`, 66 changes since 2025 |
  | echo | 1,772 | 147 | about 800 | `CHANGELOG.md`, 19 changes since 2025 |
  | libuv | 5,723 | 215 | about 9,400 | `ChangeLog`, written at each release |

**Utility tasks (`utility_v2.json`, 80 tasks, 20 per repository).**
- **Selection:** the same rules and script as version 1 (`make_utility_tasks.py`), with one more rule,
  fixed now: a task's commit must also change **at least one companion file that existed at its parent**.
- **Companion file:** a file that is not a source file, such as a test, documentation, a changelog or
  configuration.
- **Reported alongside:** the share of otherwise-eligible commits that the extra rule removes.
- **C0:** each repository's cutoff is the first parent of its oldest selected commit, as before.

**Repo QA (`repoqa_v2.json`, 30 questions).**
- Same categories and format as version 1.
- Written from each repository's history and source at C0, before its memory is learned.

## What changes from version 1

**Utility, primary: companion-file recall.**
- **Definition:** the share of the commit's companion files that existed at the parent and that the
  proposal names. The mean paired difference B − A is taken over all 80 tasks, with a paired bootstrap
  95% CI (5,000 resamples, seed 1).
- **Pass:** the lower bound is above 0.

**Utility, guards.** These must not be significantly worse with memory; a CI entirely below 0 is a
regression:
- source-file recall (version 1's primary);
- file precision;
- naming adherence.

All-file recall and the blinded judge are reported as in version 1.

**Utility pass:** the primary measure passes and no guard regresses.

**Precision of active memory (target ≥ 90%, unchanged).**
- **The judging standard is now explicit:** *supported* means the cited evidence establishes the whole
  claim, including its numbers and names. Evidence that is only consistent with the claim is *partly*.
- **Judge prompt:** it says so and tells the judge to check counts against tallies. The prompt is the
  one in `phase2_eval.py` at the commit that locks this file.
- **Author audit:** as before, 10 items per repository, done before Codex's verdicts are seen. If the
  author and Codex agree on fewer than 80%, the audit is the headline figure.

**Arm C** is run, now that `_activate_l2` also activates rejected proposals. B − A remains the
pass/fail result.

**L2 review:** under Amendment 2's fixed rule, unless the owner reviews it.

**Unchanged:** grounding (100%), Repo QA (McNemar on correct answers), retrieval non-regression, the
budget rules, and the discipline (each measure runs once on the locked data).

## Development data

Every choice above is checked on flask and ky (`utility_dev_v1.json`) before this file is locked:
- the tally evidence;
- the judge standard;
- the companion-recall computation in the harness.

Development numbers ([#14](https://github.com/ram-tewari/PHAROS/pull/14)):
- **Precision, stricter judge:** 52/60 (86.7%) on the first pass. After four fixes found on those same
  items it was 59/60 (98.3%), which is optimistic.
- **Grounding:** 100%.
- **Companion-file recall:** measured on the earlier dev answers, A 0.232 → B 0.455, +0.223
  [+0.040, +0.426], 8 tasks better and 1 worse (15 tasks).

## Budget

About 300 to 440 Codex calls, separate from the nightly learning budget:
- 40 for learning L2;
- about 260 for arms A and B, as in version 1;
- up to about 140 for arm C, which runs only where its context differs from B's.

The owner approves the run before it starts.
