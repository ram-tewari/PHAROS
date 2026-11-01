# Repository memory, phase 2 (conventions stage) — 1 November 2026

The locked evaluation of repository memory, run once under the [protocol](phase2-eval-protocol.md) fixed
before any memory code existed. Memory was tuned on the development repositories (flask, ky) only.

## Result: it does not pass

| Measure | Target | Result | |
|---|---|---|---|
| 1. Precision of active memory | ≥ 90% | **55%** audited (Codex: 70%) | fail |
| 2. Grounding | 100% | 100% (867 of 867 items) | pass |
| 3. Utility, primary: source-file recall B − A | CI lower bound > 0 | −0.004 [−0.035, +0.031] | fail |
| 3. Utility, no secondary measure significantly worse | none worse | none worse | pass |
| 4. Repo QA, correct answers | reported | 5 → 14 of 30, McNemar p = 0.012 | better |
| 5. Retrieval ranking unchanged | identical | identical by construction (memory is added after ranking) | pass |

Memory makes Codex much better at **answering questions about a repository**. It also makes the
files Codex proposes to touch more complete and more precise once tests, docs and changelogs are
counted. Its proposals follow the repository's conventions better, according to the blinded judge.
It does **not** help Codex find more of the *source* files a change touches, which is the measure the
protocol fixed as the pass/fail result. Most memory items are not fully established by the evidence
they cite.

## Utility A/B (`utility_v1`, 80 tasks, 4 repositories)

Codex proposed each change from the task text and `retrieve_context`, without memory (A) and with it
(B: deterministic L1 memory plus the 66 accepted L2 items).

| | A | B | B − A [95% CI] | Better / worse |
|---|---|---|---|---|
| **Source-file recall (primary)** | 0.827 | 0.823 | −0.004 [−0.035, +0.031] | 3 / 4 |
| All-file recall | 0.609 | 0.698 | **+0.089 [+0.041, +0.138]** | 24 / 5 |
| File precision | 0.634 | 0.775 | **+0.140 [+0.089, +0.194]** | 33 / 5 |
| Naming adherence | 96.9% (185/191) | 94.6% (174/184) | Fisher p = 0.31 | |

Blinded judge (Codex at high effort, the real diff, order randomised):

| | |
|---|---|
| Preference | B 34, A 22, tie 24 (sign test p = 0.14) |
| Matching the real change, 1–5 | +0.04 [−0.14, +0.20] |
| Following the repository's conventions, 1–5 | **+0.25 [+0.06, +0.44]** |

Source-file recall per repository (descriptive only, 20 tasks each):

| Repository | A | B |
|---|---|---|
| click | 0.803 | 0.837 |
| cobra | 0.883 | 0.858 |
| curl | 0.842 | 0.833 |
| requests | 0.779 | 0.763 |

Without memory, Codex already names 83% of the source files a commit touched (64% on the dev
repositories), so there was little room on the primary measure. The gain is in what memory adds
around the source change: the existing test files to extend, the changelog, and fewer files that
the commit did not touch. This matches the dev result that motivated the `testhome` miner. The
primary measure was not changed after the dev results (Amendment 2), so this run fails.

## Repo QA (`repoqa_v1`, 30 questions)

A blinded Codex judge graded each answer against its key facts.

| Category | n | A correct | B correct |
|---|---|---|---|
| Convention | 14 | 4 | 6 |
| History | 7 | 0 | 2 |
| Procedure | 7 | 0 | 4 |
| Abstention | 2 | 1 | 2 |
| **All** | **30** | **5** | **14** |

Partial answers went from 6 to 10. Ten questions were correct only with memory and one only without
it (exact McNemar p = 0.012).

## Precision

**Sample:** 30 active items per repository (seed 20261030).
- **Codex:** judged every item against the cited evidence.
- **Author audit:** 10 items per repository, judged without seeing Codex's verdicts. The audit used
  the first 10 of each seeded sample, and the rule was written down before the audit started.

| Repository | Codex: supported / 30 | Author: supported / 10 |
|---|---|---|
| click | 19 (63%) | 4 |
| requests | 20 (67%) | 5 |
| cobra | 20 (67%) | 7 |
| curl | 25 (83%) | 6 |
| **All** | **84 / 120 (70%)** | **22 / 40 (55%)** |

**Agreement.** The two agreed on 29 of the 40 items (72.5%). That is below the protocol's 80%, so
the audited figure is the headline. Ten of the eleven disagreements are the same case: an aggregate
claim ("510 of 523 functions declare a return type", "changes with X in 41% of its commits")
whose evidence shows only a few examples. Codex accepted those because nothing contradicted them;
the audit counted them as *partly*, because the examples cannot establish the number.

By tier and source (Codex verdicts):

| | Supported |
|---|---|
| L1 (deterministic) | 66 / 102 (65%) |
| L2 (Codex-extracted, accepted) | 18 / 18 (100%) |
| L2 proposals, any review outcome (15 per repository) | 60 / 60 (100%) |
| Source: review comments | 16 / 16 |
| Source: history | 60 / 89 (67%) |
| Source: code | 8 / 15 (53%) |
| Co-change items | 23 / 31 |
| Test homes | 8 / 17 |

**What fails.** The L1 items are counts computed from the whole index or history. Their evidence
cites a handful of examples, so a judge can confirm the pattern but not the number. Test homes
fare worst (8 of 17 supported). They cite sweeping commits ("Fix CI and build failures") as
evidence that tests for one file go in a given test file.

**Two items looked false and are true.** "src/click/termui.py was added in 0ed40c8" and a co-change
with `CHANGES.md` were marked *unsupported* or *partly*. That cited commit adds `click/helpers.py`,
later renamed to `termui.py`, and `CHANGES.rst` became `CHANGES.md` before the cutoff. The miners
follow renames, but the evidence does not show the rename. These are evidence defects, not wrong
facts. The verdicts stand, because the protocol judges a claim on its cited evidence.

## Grounding

All 867 items in the four repositories (active and proposed) cite evidence that exists at the
learned commit. Line ranges are in range, hashes match and cited commits exist.

## L2 review

The owner delegated the review of the 94 L2 proposals to Claude, under a rule committed before any
proposal was read ([Amendment 2](phase2-eval-protocol.md#amendments)). The checked file is
[`phase2_l2_review_2026-10-31.md`](../../backend/benchmarks/results/phase2_l2_review_2026-10-31.md).

| Repository | Accepted | Rejected |
|---|---|---|
| click | 13 | 7 |
| cobra | 12 | 9 |
| requests | 12 | 7 |
| curl | 29 | 5 |
| **All** | **66** | **28** |

## Arm C was not measured (defect)

Arm C (every L2 proposal active, as an upper bound) came out identical to B on all 80 tasks and 30
questions, because of a harness bug:
- Applying the review moved the 28 unticked proposals to `rejected`.
- `_activate_l2` only activated items still `proposed`, so arm C activated nothing and reused B's
  answers.

The B − A result is unaffected. The bug is fixed in this change, and arm C would need about 140
Codex calls to rerun. It has not been rerun. If it is, it will be reported next to this result, as
the protocol requires.

## How the run went

- **Order:**
  1. Learning at C0, with 40 Codex calls.
  2. The review.
  3. One run of 266 Codex calls (the estimate was about 260):
     - 160 proposals and 20 judge calls;
     - 60 Repo QA answers and 6 grading calls;
     - 20 precision calls.
- **Interruption:** the run stopped once, at the precision step, when the ChatGPT usage limit was
  reached. It resumed from its checkpoint after the limit reset, so no call was repeated and no
  result was rerun.
- **Dataset hashes:** both match the locked files.
  - `utility_v1` sha256 `5b972d24…73ce`
  - `repoqa_v1` sha256 `0dd77fbb…40eb`
- **Caveats:**
  - Claude built the system, reviewed L2 and did the precision audit. The audit came after Codex's
    precision figure for click (not its per-item verdicts) had been seen.
  - The samples are small (80 tasks, 30 questions, 40 audited items).

Raw results: [`phase2_locked_2026-10-30.json`](../../backend/benchmarks/results/phase2_locked_2026-10-30.json).
The author audit, with its rule and a reason per item, is in [`phase2_author_audit_2026-11-01.json`](../../backend/benchmarks/results/phase2_author_audit_2026-11-01.json).

## What this suggests

Each of these is for a later phase, on development data first, with any new locked measure fixed
before it runs:

- **Memory for answering, not for choosing files.** The Repo QA gain is large. `get_repo_brief`
  and `search_memory` are where memory earns its place today.
- **Evidence that proves the claim.** An aggregate claim should cite what it counts, or be
  phrased as what its examples show. A rename-followed fact should show the rename.
- **Test homes need better evidence.** Cite only commits that add or change tests for that file,
  not repository-wide sweeps.
- **L2 is the precise tier.** 100% of the accepted items and of the raw sample were supported.
