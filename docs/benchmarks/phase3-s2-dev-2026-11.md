# Phase 3, stage S2: rules that prove themselves (development report, November 2026)

> Development data only. The 16 repositories of the locked c-CRAB test set were not learned from,
> backtested on or looked at. These numbers are not the protocol's verdict; that comes from the final
> run (stage S6).

## Summary

- A convention is now a **predicate** that can be run on a commit or a diff. An item becomes active
  only if the same rule, learned 600 first-parent commits earlier, held on those 600 commits.
- On the 15 development mirrors, checked on each mirror's **last 200 first-parent commits** (never used
  for tuning), pooled precision of active checkable rules went from **67.2%** (951 rules, Phase 2
  activation) to **94.2%** (42 rules, 1,285 of 1,364 rule–commit pairs).
- That is above the protocol's 90% target, **with few rules**: 42 requirements over 15 repositories,
  and 4 repositories (ky, requests, attrs, anyhow) have none. Most per-file rules (co-change, test
  homes, playbook steps) do not apply often enough in 600 commits to be tested, and stay proposed.
- Rules that are real but weak are kept as **observations**: served on request, never in the default
  context. Counted as rules, the 56 observations would hold in 43.2% of the commits they apply to.

## What changed

**Predicates** (`backend/app/learning/checks.py`). Each has `applies(change)`, `holds(change)`, a one-line
rendering and a JSON form stored on the item (`memory_items.predicate`). A change is the files a commit
or a `git diff` adds, modifies, deletes or renames, with their added and removed lines, and the message
when there is one.

| Kind | Applies when the change … | Holds when … | Learned by |
|---|---|---|---|
| `companion` | touches A (optionally: and a test file), at most N files | it also touches B | co-change, test homes, changelog |
| `new_file_companion` | adds a file matching P | it also changes F, or adds a file matching Q | playbook steps (`addition/…`) |
| `new_test_location` | adds a test file | each new test file matches the usual patterns | where tests live |
| `naming` | adds a definition of a new multi-word name | the name has the repository's case style | naming |
| `signature` | adds a one-line Python definition | it declares a return type | type hints |
| `message` | has a message and is not a merge | the subject or trailer has the shape | commit style (one item per shape) |
| `forbidden` | adds an import line (or code) in scope | no added line matches | dropped dependencies, deprecated API |
| `added_pattern` | adds a line about deprecation | it uses the project's marker or `stacklevel` | deprecation style |
| `new_file_contains` | adds a Python module of 5 or more lines | it imports `from __future__ import annotations` | future annotations |

**Backtest** (`backend/app/learning/backtest.py`). To learn at commit C, the miners also run at S, 600
first-parent commits before C, on history reachable from S. Each rule found at S is checked on S..C.
A first-parent commit is diffed against its first parent, so a merged pull request is one change.
Renames inside the window are followed back to the learned names.

**Activation** (`checks.decide`, used by `MemoryWriter`). A rule learned at C uses the record of the
same rule learned at S. If the rule at S was different or absent, it is untested.

| Record at S (Wilson 95% lower bound on held / applied) | Status | Strength | Served |
|---|---|---|---|
| applied ≥ 10 and lower bound ≥ 0.6 | active | requirement | in the default context, as "do this" |
| applied ≥ 10 and lower bound ≥ 0.2 | active | observation | only by `search_memory` or `GET /memory/items` |
| applied < 10, or no matching rule at S | proposed | — | no |
| lower bound < 0.2 | stale | — | no; the record and reason are kept |

Items with no predicate keep the Phase 2 rule and are marked **advisory**. A human accept, reject or
archive still wins over a learning run. A playbook is served only while one of its steps is a
requirement. The served text ends with what the hold-out test measured: *"Checked on the 600
first-parent commits after `<commit>`, the rule "`<rule>`" applied N times and held M times."*

**Storage** (migration `0005_memory_checks`): `predicate`, `holdout` (window, applied, held, lower
bound, up to 5 counter-example commits, outcome, reason, thresholds), `strength`, and the counters
`served`, `complied` and `helped` (0 until a later stage fills them).

## Data and method

- **Mirrors:** flask, click, ky, cobra, curl, requests, attrs, rich, echo, libuv, gin, urfave/cli, httpx,
  anyhow and itsdangerous, as fetched in `~/.cache/pharos/git` (heads from June to October 2026).
- **Tuning point:** learn 400 first-parent commits before each mirror's head, check on the next 200.
  The thresholds were chosen here. itsdangerous has 369 first-parent commits and is not in it.
- **Report point:** learn 200 first-parent commits before the head, check on the last 200. It was run
  once, after the thresholds were fixed.
- **Measure:** the protocol's precision. Every checkable rule is checked on every commit of the window.
  Precision is held over applied, pooled over (rule, commit) pairs across repositories.
- **Before:** the rules Phase 2 would have activated (`eligible`), checked the same way.
- Raw results: [`backend/benchmarks/results/phase3_s2_dev_2026-11-13.json`](../../backend/benchmarks/results/phase3_s2_dev_2026-11-13.json).
  One run of all 15 mirrors takes about 2.5 minutes on the owner's Mac.

## Choosing the threshold (tuning point)

Precision against the number of active rules, for three window sizes and a minimum of 10 applications.
The Phase 2 rule activates 917 checkable rules here, at 68.0%.

| Lower bound ≥ | Window 200: rules | precision | Window 400: rules | precision | Window 600: rules | precision |
|---|---|---|---|---|---|---|
| 0.0 | 73 | 69.1% | 119 | 66.7% | 120 | 67.2% |
| 0.3 | 55 | 80.3% | 73 | 81.3% | 79 | 74.7% |
| 0.4 | 46 | 86.0% | 63 | 87.7% | 67 | 79.5% |
| 0.5 | 35 | 92.2% | 49 | 95.4% | 58 | 93.8% |
| **0.6** | 33 | 92.4% | 40 | 96.6% | **47** | **96.4%** |
| 0.7 | 26 | 94.8% | 37 | 96.8% | 43 | 96.8% |
| 0.8 | 15 | 96.7% | 29 | 96.8% | 31 | 96.9% |

With window 600 and a lower bound of 0.6, the minimum number of applications matters little: 5 gives
55 rules at 96.2%, 10 gives 47 at 96.4%, 20 gives 34 at 96.4%.

**Chosen: window 600, at least 10 applications, lower bound 0.6.** The reasons:

- A longer window tests more of the per-file rules. 600 gave the most rules at each precision level.
- Precision jumps between 0.4 and 0.5 and is flat above 0.6, so 0.6 is the knee.
- At least 10 applications, because a rule that applied 3 or 5 times proves little, even at 100%.
  With 10, a requirement needs at least 10 of 10, 10 of 11, 17 of 20, or about 70 of 100.

After the choice, the report point showed what a lower bound of 0.5 would have given: 58 rules at
87.7%. That was not used to change anything; it says the margin above 0.5 is needed.

## Results (report point)

| Repository | Learned at | Active items before | of them checkable | Precision before | Active items after | Requirements | Observations | Precision after | Pairs |
|---|---|---|---|---|---|---|---|---|---|
| flask | `cd1b68cf` | 62 | 39 | 70.2% (250/356) | 27 | 2 | 2 | 100% | 13 |
| click | `2aecb2d7` | 54 | 34 | 66.3% (342/516) | 23 | 3 | 0 | 100% | 42 |
| ky | `5a3fc90c` | 26 | 9 | 49.1% (227/462) | 18 | 0 | 1 | – | 0 |
| cobra | `68b6b24f` | 36 | 18 | 80.0% (300/375) | 20 | 2 | 0 | 100% | 25 |
| curl | `e84f95a6` | 670 | 387 | 80.7% (497/616) | 296 | 6 | 7 | 95.7% | 423 |
| requests | `88128125` | 50 | 31 | 57.4% (159/277) | 19 | 0 | 0 | – | 0 |
| attrs | `269b9f5c` | 59 | 30 | 65.9% (89/135) | 33 | 0 | 4 | – | 0 |
| rich | `c7d6215c` | 145 | 78 | 54.5% (182/334) | 81 | 4 | 10 | 100% | 22 |
| echo | `822d11a4` | 98 | 55 | 59.3% (208/351) | 53 | 4 | 6 | 90.5% | 63 |
| libuv | `885613f1` | 193 | 94 | 62.7% (408/651) | 112 | 7 | 6 | 81.4% | 258 |
| gin | `7a1b6550` | 125 | 60 | 82.0% (505/616) | 73 | 5 | 3 | 97.1% | 244 |
| urfave/cli | `eac452b9` | 92 | 49 | 63.9% (216/338) | 49 | 2 | 4 | 100% | 34 |
| httpx | `8a6ef6ed` | 64 | 40 | 72.6% (320/441) | 41 | 6 | 11 | 100% | 232 |
| anyhow | `d30b0275` | 27 | 15 | 49.7% (78/157) | 14 | 0 | 2 | – | 0 |
| itsdangerous | `3ca36c12` | 24 | 12 | 65.2% (45/69) | 13 | 1 | 0 | 100% | 8 |
| **Pooled** | | 1,725 | 951 | **67.2%** (3,826/5,694) | 872 | 42 | 56 | **94.2%** (1,285/1,364) | 1,364 |

- "Active items" counts every active item. The 774 advisory items (facts with no predicate) are the
  same before and after.
- The mean of per-repository precision, over the 11 repositories with a requirement, is 96.8%.
- At the tuning point, the chosen rule gives 47 requirements at 96.4%, in 13 of 14 repositories.
- **libuv is below 90%** (81.4%). Its commit-subject rule ('area: change') held in 552 of 600 commits
  before and in 157 of the last 200: release commits ("2026.02.11, Version 1.52.0 (Stable)") and
  "Add SHA to ChangeLog" do not fit it. That one rule is 200 of libuv's 258 pairs.

By family (report point):

| Family | Checkable | Before: rules, precision | After: rules, precision | Requirement / observation / untested / not derived or changed / failed |
|---|---|---|---|---|
| co-change | 619 | 609, 46.7% | 2, 94.1% (16/17) | 2 / 36 / 353 / 205 / 23 |
| playbook steps (`addition/`) | 207 | 148, 59.3% | 7, 96.0% (48/50) | 7 / 1 / 167 / 31 / 1 |
| test homes | 137 | 120, 67.8% | 3, 78.4% (29/37) | 3 / 10 / 32 / 91 / 1 |
| naming | 34 | 30, 99.6% | 20, 99.5% (203/204) | 20 / 2 / 10 / 1 / 1 |
| commit messages | 16 | 9, 83.7% | 5, 93.6% (936/1,000) | 5 / 3 / 0 / 7 / 1 |
| test layout | 15 | 14, 85.7% | 2, 88.9% (24/27) | 2 / 1 / 4 / 8 / 0 |
| type hints | 9 | 5, 94.3% | 2, 100% (21/21) | 2 / 1 / 1 / 2 / 3 |
| dropped dependencies | 7 | 7, 100% | 1, 100% (8/8) | 1 / 0 / 0 / 6 / 0 |
| changelog | 5 | 5, 50.0% | 0 | 0 / 2 / 0 / 3 / 0 |
| deprecation style and calls | 5 | 4, 97.0% (128/132) | 0 | 0 / 0 / 0 / 5 / 0 |

What this shows:

- **Co-change is the bulk of Phase 2's rules and the weakest.** 609 active co-change rules held in
  46.7% of the commits they applied to. Two survive.
- **Repository-wide rules hold.** Naming, commit-message shape and type hints are most of the surviving
  rules and most of the pairs. Commit-message rules alone are 1,000 of the 1,364 pairs.
- **Per-file rules mostly cannot be tested.** A co-change rule about one file needs that file to change
  10 times in 600 commits. 353 co-change rules applied less often and stay proposed.
- **"Not derived or changed" is the second loss.** Rules learned at S and C must be the same predicate.
  A dependency dropped inside the window, or a new partner file, makes them differ.
- **Changelog rules are observations.** In flask and rich, a source change came with a changelog
  entry in about 60% of the activation window's commits (156 of 262, 179 of 302). That is
  information, not a requirement.

## The five worst active rules per repository, with counter-examples

flask, click, cobra, urfave/cli and itsdangerous: every active rule held on every commit it applied to
(naming rules, and itsdangerous's dropped `six`). ky, requests, attrs and anyhow have no active rule.

| Repository | Rule (activation record → last 200 commits) | Counter-examples |
|---|---|---|
| curl | Subjects start with the area ('area: change') (593/600 → 196/200) | `fa83ab1f19` Revert "cw-out: avoid nested flush…"; `8868dec7c3` Revert "GHA: update openldap…" |
| curl | Messages carry a `Closes:` trailer (571/600 → 186/200) | `601b38ea80` mailmap: add Zheng Yu; `98979fe46b` RELEASE-NOTES: synced |
| curl | A new `tests/data/test*` changes `tests/data/Makefile.am` (66/66 → 17/17) | none |
| curl | A new `tests/libtest/lib*.c` changes `tests/data/Makefile.am` (21/21 → 2/2) | none |
| curl | A new `tests/libtest/lib*.c` changes `tests/libtest/Makefile.inc` (21/21 → 2/2) | none |
| rich | New functions and methods declare a return type (53/56 → 10/10); three naming rules (all held) | none |
| echo | A change to `bind.go` that touches tests touches `bind_test.go` (28/30 → 7/11) | `ce0b12ae53` chore: fix some typos in comment (#2735); `b1d65e40fe` perf: optimize core hot paths |
| echo | New test files go in `*_test.go` or `middleware/*_test.go` (22/22 → 15/17) | `f071367e3c` V5 changes; `8d1ae9d336` fix(static): reject encoded path separators… |
| echo | Two Go naming rules (all held) | none |
| libuv | Subjects start with the area (552/600 → 157/200) | `b556c0629d` 2026.02.11, Version 1.52.0 (Stable); `bcad447de5` Add SHA to ChangeLog |
| libuv | A change to `include/uv/version.h` touches `configure.ac` (18/18 → 5/6) | `8fa343442c` Now working on version 1.52.1 |
| libuv | A new `test/*.c` changes `test/test-list.h` (11/11 → 8/9) | `2cadaa4016` win: fix unique named pipes to work inside Windows AppContainer |
| libuv | A new `test/*.c` changes `Makefile.am` (11/11 → 8/9) | `2cadaa4016` (the same commit) |
| libuv | New test files go in `test/*.c` or `test/*.h` (11/11 → 9/10) | `b2fe7d8469` freertos: initial support (#5388) |
| gin | A change to `debug.go` that touches tests touches its test file (13/14 → 3/4) | `848e1cdd0d` refactor: replace interface{} with any in type declarations |
| gin | A change to `context.go` that touches tests touches its test file (42/46 → 19/22) | `c221133ee8` docs(context): fix some comments (#4396); `d1a15347b1` refactor(utils): move util functions to utils.go (#4467) |
| gin | Subjects end with the pull-request number (556/556 → 197/200) | `f3a5e78719` docs: update feature documentation instructions…; `38e7651192` feat(context): implemented Delete method |
| gin | Two Go naming rules (25/26 and 30/30 → all held) | none |
| httpx | Subjects end with the pull-request number (597/600 → 200/200); return types (59/62 → 11/11); `__version__.py` changes with `CHANGELOG.md` (30/31 → 11/11); two naming rules | none |

## What is not checkable and stays advisory

These items keep their evidence path and the Phase 2 activation, marked `advisory`:

- history facts: file origins, directory moves, runtime version changes, and each dropped dependency
  as a fact (the rule "do not import it again" is a separate, checkable item per manifest);
- documentation coverage and docstring style, exception hierarchies, C name prefixes, the tooling summary;
- deprecation style where no `stacklevel` is used, and the commit-style summary when no shape is shared
  by 30% of commits;
- model-extracted (L2) rules, which still need a human to accept them.

## How the protocol's precision definition was read

The protocol says: *"Precision is the share of (active rule, commit) pairs where the rule applies and
the commit satisfies it, pooled over repositories."* The implementation reads it as follows:

1. **Denominator:** the pairs where the rule applies. Read literally, the share could be taken over all
   pairs, which would count every commit a rule does not apply to as a miss.
2. **Pooled:** over pairs, so repositories and rules that apply more often weigh more. The mean of
   per-repository precision is reported next to it.
3. **Active rule:** an active **requirement**. Observations are active but are not served as rules, so
   they are not counted; their own figure (43.2%) is reported.
4. **"The next 200 first-parent commits after it":** the first-parent chain of the mirror's default
   branch, from the learned commit. If that commit is not on the chain, the first-parent commits that
   descend from it.
5. **A merge commit on that chain** is one change: its diff against its first parent. Commit-message
   rules do not apply to merges, whose messages the forge writes.
6. **Learned as the pipeline learns:** including its activation backtest, which reads only history
   before the learned commit. The benchmark parses the tree with the indexer's parsers and exclusions
   instead of reading a database index.
7. **Renamed files:** a rule about a path follows that file through renames in the window.
8. **Large changes:** a change of more than 60 files has no line-level evaluation, so line rules do not
   apply to it; companion rules apply only to changes of at most 30 files (60 for the changelog).

## Limitations

- **Few rules.** 42 requirements in 15 repositories is a small memory. Whether it helps an agent is
  for the c-CRAB run to show.
- **The default context loses most per-file items.** Test homes and co-change items led
  `retrieve_context` in Phase 2. Most are now proposed or observations, so they are not in it. Ranking
  is unchanged.
- **Thresholds were chosen on 14 repositories at one time point.** The report point is later in the
  same repositories, not new repositories.
- **Definitions in added lines are found by regular expressions.** JavaScript and TypeScript methods
  are not detected, so those naming rules never apply. C function definitions are matched at column 0.
- **The two learning points share history.** The rule must be the same predicate at both, which is
  strict: a rule whose partner file changed is untested, even if it would have held.
- The activation backtest costs a second mining pass at the older commit. A whole benchmark run takes
  seconds for most repositories and about a minute for curl.

## Reproduce

```
cd backend
python benchmarks/rule_precision.py --mirrors ~/.cache/pharos/git --repo pallets_click --repo spf13_cobra \
    --back 200 --window 600 --out /tmp/precision.json --curve
```

`--back 400` gives the tuning point. Each `--repo` takes `name@commit` to learn at a given commit.
The script refuses repositories of the locked c-CRAB test set unless `--test-set` is given.
