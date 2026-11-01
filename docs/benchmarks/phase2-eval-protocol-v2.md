# Phase 2 (learning) evaluation protocol, version 2 — DRAFT, not locked

> **Status: draft.** This file becomes binding when it is committed with the hashes of `utility_v2.json`
> and `repoqa_v2.json` filled in. Until then nothing in it has been measured, and no v2 task or question
> exists. Version 1 ([protocol](phase2-eval-protocol.md), [result](phase2-memory-2026-11-01.md)) stays as
> it is. This version is a new test on new data, not a rerun of version 1, so its results are reported
> next to version 1's, never in place of them.

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

## Data (to be built after this file is reviewed, before any memory for these repositories exists)

**Repositories.** Four that no phase has used for tuning or testing:
- **Not allowed:** flask, ky, anyhow, jq, click, requests, cobra, curl, chi, gson, immer and
  itsdangerous.
- **Mix:** two Python, one Go, and one C or TypeScript.
- **Each repository must have:**
  - at least 500 non-merge commits;
  - an existing test suite;
  - a changelog or release-notes file;
  - public pull-request reviews.
- **Proposed:** encode/httpx, python-attrs/attrs, urfave/cli and libuv/libuv. The owner confirms or
  replaces them before anything is built.

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

The development numbers are recorded in the pull request that locks this file.

## Budget

About 300 to 440 Codex calls, separate from the nightly learning budget:
- 40 for learning L2;
- about 260 for arms A and B, as in version 1;
- up to about 140 for arm C, which runs only where its context differs from B's.

The owner approves the run before it starts.
