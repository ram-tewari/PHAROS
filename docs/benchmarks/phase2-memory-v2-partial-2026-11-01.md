# Repository memory, protocol v2 (stopped run) — 1 November 2026

The second evaluation of repository memory, under [protocol v2](phase2-eval-protocol-v2.md). The owner
stopped the run before it finished ([Amendment 1](phase2-eval-protocol-v2.md#amendments)). This report
gives what was measured. Version 1's [report](phase2-memory-2026-11-01.md) stands as it was.

## Result: no verdict

The run can't pass or fail, because the protocol's primary measure is defined over all 80 tasks and only
66 were scored, and because precision and the judges never ran.

| Measure | Target | Result | |
|---|---|---|---|
| 1. Precision of active memory | ≥ 90% | not measured | no verdict |
| 2. Grounding | 100% | 100% (553 of 553 items) | pass |
| 3. Utility, primary: companion-file recall B − A | CI lower bound > 0 over 80 tasks | **+0.143 [+0.062, +0.223] over 66 tasks** | favourable, incomplete |
| 3. Utility, guards | no CI entirely below 0 | none tripped, source recall touches 0 | incomplete |
| 4. Repo QA, correct answers | reported | 90 answers, none graded | not measured |
| 5. Retrieval ranking unchanged | identical | identical by construction (memory is added after ranking) | pass |

On the scored tasks, memory helped Codex name the tests, docs and changelogs around a change. Three
things limit that finding:

- **One repository carries it.** Without rich the gain is +0.063 [−0.036, +0.165], which isn't significant.
- **It may have cost a little source recall.** Memory lost 3 tasks and gained none on that guard.
- **The C repository is mostly missing.** libuv has 6 of its 20 tasks, and they lean the other way.

Whether the new evidence fixed precision, version 1's biggest failure, is still unknown.

## Utility A/B (`utility_v2`, 66 of 80 tasks)

Codex proposed each change from the task text and `retrieve_context`, without memory (A) and with it
(B: deterministic L1 memory plus the 39 accepted L2 items).

| | A | B | B − A [95% CI] | Better / worse |
|---|---|---|---|---|
| **Companion-file recall (primary)** | 0.282 | 0.425 | **+0.143 [+0.062, +0.223]** | 23 / 3 |
| Source-file recall (guard, 65 tasks) | 0.784 | 0.753 | −0.031 [−0.069, 0.000] | 0 / 3 |
| File precision (guard) | 0.627 | 0.637 | +0.011 [−0.042, +0.063] | 16 / 13 |
| Naming adherence (guard) | 95.0% (228/240) | 91.7% (222/242) | Fisher p = 0.20 | |
| All-file recall | 0.482 | 0.555 | **+0.073 [+0.028, +0.118]** | 23 / 6 |

Companion-file recall per repository (descriptive only, as these are subsets):

| Repository | Tasks | A | B | B − A [95% CI] | Better / worse | Primary without it |
|---|---|---|---|---|---|---|
| attrs | 20 | 0.256 | 0.352 | +0.096 [+0.013, +0.213] | 4 / 0 | +0.163 [+0.055, +0.269] |
| rich | 20 | 0.215 | 0.541 | +0.326 [+0.236, +0.416] | 16 / 0 | +0.063 [−0.036, +0.165] |
| echo | 20 | 0.283 | 0.358 | +0.075 [−0.125, +0.300] | 3 / 2 | +0.172 [+0.098, +0.248] |
| libuv | 6 | 0.583 | 0.500 | −0.083 [−0.250, 0.000] | 0 / 1 | +0.165 [+0.079, +0.252] |

**The source-recall guard:** the protocol counts a regression only when the CI lies entirely below 0. This
one ends at 0.000, so it wasn't tripped, but only just. The three losses were two in rich and one in echo.
Without memory, Codex already named every source file on 45 of the 65 tasks.

**Compared with version 1:** companion recall was not measured there. All-file recall rose by a similar
amount (+0.089 then, +0.073 now). The large file-precision gain (+0.140) did not repeat (+0.011).

### What the 14 missing tasks could do

All 14 are from libuv. Tasks ran in a fixed order with libuv last, so they are the ones that hadn't run
yet, not a random sample. These what-if figures give every missing task the same change, so they are a
rough guide and not an estimate:

| If each missing task changed by | Primary over 80 tasks |
|---|---|
| 0 | +0.118 [+0.052, +0.187] |
| −0.083 (the mean of libuv's 6 scored tasks) | +0.103 [+0.036, +0.174] |
| −0.25 | +0.074 [+0.001, +0.148] |
| −0.5 | +0.030 [−0.055, +0.115] |

The lower bound stays above 0 unless libuv's remaining tasks average a loss of about 0.25. That's about
three times the loss on its scored tasks, but six tasks are too few to rule it out.

## Arm C (65 tasks)

Arm C adds every L2 proposal, including rejected ones, as an upper bound. On 31 of the 65 tasks its
context matched B's, so B's answer was reused.

| | A | C | C − A [95% CI] | Better / worse |
|---|---|---|---|---|
| Companion-file recall | 0.271 | 0.427 | +0.156 [+0.076, +0.240] | 26 / 3 |
| Source-file recall (64 tasks) | 0.781 | 0.762 | −0.019 [−0.069, +0.031] | 1 / 4 |
| File precision | 0.621 | 0.670 | +0.050 [−0.006, +0.110] | 18 / 13 |

C's A column differs from B's because it covers one task fewer. The rejected proposals didn't obviously
hurt, and the review didn't obviously help, but this is descriptive only.

## What was not measured

| Step | State | Codex calls it needed |
|---|---|---|
| Blinded judge, A vs B and A vs C | not run | about 40 |
| Repo QA grading | 90 answers saved, none graded | about 9 |
| Precision, Codex audit | 120 L1 and 46 L2 items sampled, no verdicts | about 18 |
| Precision, author audit | not done | none |
| Utility, libuv | 14 tasks unscored in A and B | about 40 |

Repo QA answers were not graded by hand. The protocol has Codex grade them, and the questions' author
grading them here would not be independent.

## Grounding

Every item that the run checked was grounded: attrs 74, rich 170, echo 102, libuv 207.

## L2 review

The review was delegated to Claude under version 1's Amendment 2 rule. The checked file is
[`phase2_v2_l2_review_2026-11-01.md`](../../backend/benchmarks/results/phase2_v2_l2_review_2026-11-01.md).

| Repository | Accepted | Rejected |
|---|---|---|
| attrs | 10 | 4 |
| rich | 14 | 10 |
| echo | 2 | 0 |
| libuv | 13 | 9 |
| **All** | **39** | **23** |

## How the run went

- **Why it stopped:** Codex hit the ChatGPT usage limit twice, the run was paused once, and the owner then
  cancelled it. Interrupted calls were repeated from the checkpoint.
- **Nobody saw results first:** before the cancellation, only progress counts were read from the
  checkpoint. No score had been looked at, so the stop could not have depended on them.
- **The analysis came afterwards:** per-repository figures, the leave-one-out check and the what-if table
  were chosen after the scores were read, so they are descriptive. The B − A figures use the protocol's
  method, and the same bootstrap with 5,000 resamples and seed 1.
- **Cost:** 31 learning calls and 246 answers, about 277 Codex calls of the 300 to 440 budgeted.

## Disclosures

- **Claude's roles:** Claude wrote the Repo QA questions, reviewed the L2 proposals, and wrote this report.
- **echo:** none of its maintainers' review comments were usable, because they appear as `CONTRIBUTOR`, so
  its L2 items come from documents only. This wasn't changed, because that would be tuning on test data.
- **Unmerged fix:** learning crashed on a libuv directory moved twice. The run used the fix in
  [#16](https://github.com/ram-tewari/PHAROS/pull/16), which was not yet merged. It affects memory items
  and no task.
- **Small numbers:** 66 tasks, with 23 better and 3 worse, and most of the better ones in one repository.

## Reproducing this

The checkpoint is
[`phase2_v2_2026-11-01.json`](../../backend/benchmarks/results/phase2_v2_2026-11-01.json). From `backend/`,
`python benchmarks/phase2_v2_partial.py` prints the utility numbers above without calling Codex.
Grounding and the L2 counts are in the checkpoint. Rerunning `phase2_eval.py` with the protocol's
arguments resumes from the checkpoint.
