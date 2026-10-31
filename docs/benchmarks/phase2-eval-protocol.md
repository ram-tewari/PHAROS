# Phase 2 (learning) evaluation protocol — locked 30 October 2026

This protocol is fixed before any Phase 2 memory code exists, like the retrieval test sets. It says what is measured, on which data, with which statistics, and what counts as a pass. Results go in a separate report. Changes to this file after results exist are listed under [Amendments](#amendments) with their reasons, never made silently.

## Locked data

| File | What | SHA-256 |
|---|---|---|
| [`utility_v1.json`](../../backend/benchmarks/datasets/utility_v1.json) | 80 utility tasks: 20 real commits each from click, requests, cobra and curl | `5b972d24a0178b28249a358d5e2fa04cdd7f5e1fe436767bdde7411d41ab73ce` |
| [`repoqa_v1.json`](../../backend/benchmarks/datasets/repoqa_v1.json) | 30 hand-written questions about history, conventions and procedures | `0dd77fbbe91a2d2904e8057b170a2016ff1b4558ade5855ed3a86423f2fe40eb` |

Development data (used for tuning, never reported as a result):
- [`utility_dev_v1.json`](../../backend/benchmarks/datasets/utility_dev_v1.json): 20 tasks, 10 each from flask and ky, chosen by the same rules. SHA-256 `cf93e9299f36701013d8d41af78e7af0c7e78ec05905e3cf31323921050920f8`.
- The memory learned for flask, ky, anyhow and jq may be read and tuned against freely. Memory for the four test repositories is not inspected until it is evaluated.

### How the utility tasks were chosen

[`make_utility_tasks.py`](../../backend/benchmarks/make_utility_tasks.py) walks each repository's default branch (first parent) back from the head recorded in the file, and keeps the 20 most recent commits that:
- were written by a person (no `[bot]`, dependabot, renovate or pre-commit-ci author);
- are not a revert, a release, or a merge of one branch into another;
- change 1–6 source files that PHAROS parses (`path_role == "source"`, an AST language, not under `.github/`), at most 15 files in all, and 3–400 lines in those source files.

The task text is the commit message without trailers or the pull-request number. Each repository's cutoff **C0** is the first parent of its oldest selected commit:

| Repository | Language | C0 | C0 date | Tasks span |
|---|---|---|---|---|
| click | Python | `16fc00e2` | 2026-07-02 | Jul–Oct 2026 |
| requests | Python | `00600b38` | 2026-02-13 | Feb–Jun 2026 |
| cobra | Go | `ff7c561c` | 2024-10-12 | Oct 2024–Apr 2026 |
| curl | C | `64ee53be` | 2026-10-26 | 26–29 Oct 2026 |

The rules were written before any task was read. The first run exposed two bugs, both fixed before the file was locked:
- The trailer pattern also removed subject lines of the form `area: change`, which is how curl and some cobra commits are titled.
- GitHub's security-advisory merge ("Merge commit from fork") was not recognised as a branch merge.

Human-authored dependency and version bumps (requests-u01, cobra-u15) pass the rules and stay in.

The Repo QA questions were written from git history and source at each repository's C0. Their counts:
- **By repository:** click 8, requests 7, cobra 7, curl 8.
- **By category:** 14 conventions, 7 history, 7 procedures, 2 abstentions.

Each question has a reference answer, the key facts an answer must state, and evidence.

## The system under test

- **Memory** is learned from each test repository at **C0 only**: from its code, its full git history up to C0, and its public review comments from before C0. Nothing after C0 is used, so no task's answer is in memory. It is learned once, on the owner's Mac, into a scratch database (`pharos_bench*`), with the same code and settings that will run in production.
- **Code** is indexed with granite-embedding-english-r2 int8, the production model.
- **Utility tasks** are run in chronological order per repository. Before each task, the index moves to the task's parent commit (incremental re-indexing), so the code the assistant sees is current. Memory stays as learned at C0, like a nightly memory that is a few weeks old.
- **Both arms of every comparison** use the same retrieval, the same Codex model and reasoning effort, the same prompt template and the same character budget (`retrieve_context` defaults: 8 chunks, 24,000 characters). The only difference is whether memory is included: the repository brief, conventions and playbooks scoped to the retrieved files, and for Repo QA also `search_memory`. Memory competes for the same budget, as it will in production.

## Measures

### 1. Precision of active memory (target ≥ 90%)

- **Sample:** 30 ACTIVE memory items per test repository (seed 20261030), or all of them if fewer.
- **Check:** each item is judged against the code and history its evidence cites, at C0: *supported*, *partly supported* or *unsupported*.
  - **Judge:** Codex at high effort, with a prompt separate from the extractor's. It sees only the claim and the cited lines, plus or minus 5 lines.
  - **Audit:** the author audits 10 items per repository without seeing Codex's verdict.
- **Precision** is the share judged *supported*. Both the Codex and the audited figures are reported, with their agreement. If agreement on the audited items is below 80%, the audited figure is the headline.
- Items are reported by source (code, history, review) and by miner tier (deterministic L1, Codex-extracted L2).

### 2. Grounding (target 100%, automatic)

Every memory item, active or proposed, must cite evidence that exists at the commit it was learned from:
- the file exists, and the line range lies inside it;
- the cited lines hash to the stored evidence hash;
- a cited commit exists in the history.

Any failure fails this measure.

### 3. Utility A/B on `utility_v1` (the gain must be significant)

For every task, Codex proposes the change from the task text and the `retrieve_context` output, once without memory (A) and once with it (B). The answer is strict JSON: the files to modify or create, and the new or changed code per file.

- **Primary — source-file recall:** the share of the commit's touched source files (that existed at the parent) that the proposal names.
  - Statistic: the mean paired difference B − A over 80 tasks, with a paired bootstrap 95% CI (5,000 resamples, seed 1).
  - Pass when the lower bound is above 0.
- **Secondary:**
  - **All-file recall:** every file the commit touched, including tests, docs, changelogs and new files. Memory about co-changes should show here.
  - **File precision:** must not fall significantly; a CI entirely below 0 counts as a regression.
  - **Naming adherence:** the share of identifiers defined in the proposed code (functions, methods, classes and types) whose case style matches the repository's dominant style for that kind, measured from the index at C0.
  - **Blinded judge:**
    - Codex at high effort sees the task, the real diff (up to 8,000 characters) and the two proposals as X and Y. The order is randomised per task with seed 20261030.
    - It rates each proposal 1–5 on matching the real change and 1–5 on following the repository's conventions, then states a preference or a tie. Four tasks per call.
    - Statistic: a two-sided sign test on preferences, ties excluded, and the mean paired difference in each rating.
- **Lint is not measured.** Proposals are code fragments, not patches that apply, so a linter cannot run on them. The judge's convention rating and naming adherence stand in for it.
- **Pass:** the primary measure passes, and no secondary measure is significantly worse with memory.
- Results are reported per repository too. With 20 tasks each, per-repository differences are descriptive only.

### 4. Repo QA on `repoqa_v1`

- **Answering:** Codex answers each question from `retrieve_context` for the question, without memory (A) and with memory (B: context plus `search_memory`).
- **Scoring:**
  - A blinded Codex judge scores each answer against its key facts, as defined in the dataset: correct, partial or wrong.
  - A confident claim that contradicts a key fact counts as wrong.
  - Abstention questions are correct only if the answer says the repository does not do the thing.
- **Statistics:**
  - **Reported:** accuracy per arm, overall and by category.
  - **Significance:** an exact McNemar test on *correct* answers.
- **Caveat:** these repositories are public and well known, so Codex may answer some questions from training. Both arms share that advantage.

### 5. No regression in retrieval

- **Conventions stage (L1, L2):** memory does not change ranking. This is verified on the dev set codeqa_v1: hits must be identical with memory on and off. The locked retrieval sets are not rerun for a stage that does not touch ranking.
- **Session reflector (L3):** it changes ranking through retrieval hints, so it is tuned on dev replays. heldout_v1 and heldout_v2 are then run once.
  - The pass rule: the paired nDCG@10 difference has a 95% CI whose lower bound is above −0.02, and its point estimate is not negative by more than 0.01.

## Discipline

- Each measure runs **once** on the locked data, after every choice has been fixed on development data. A later rerun, for a bug or a new phase, is reported next to the first result, never in its place.
- Labels are never edited after results are seen. A label found to be wrong is reported as a dataset defect, as anyhow-10 was in Phase 1.
- **Codex budget:** these runs are separate from the nightly learning budget (40 calls a night).
  - **Estimate:** about 260 calls and 3–5 M input tokens in all: 160 proposals, 20 judge calls, 60 Repo QA answers, 8 Repo QA judge calls and about 12 precision calls.
  - **Approval:** the owner approves the run before it starts.
- **Caveats carried from Phase 1:**
  - One annotator, who also builds the system, wrote the Repo QA labels and audits precision.
  - With 80 tasks and 30 questions, the samples are small, and differences inside the intervals are noise.

## Amendments

**1. 30 October 2026, before any test-repository memory existed: the approval gate.**

L2 (Codex) items start `proposed`, and only accepted items reach the assistant. So each comparison
runs three arms instead of two, all with the same retrieval, prompts and budget:

| Arm | Memory |
|---|---|
| A | none |
| B (production flow) | L1 plus the L2 proposals the owner accepted |
| C (upper bound) | L1 plus every L2 proposal, as if all were accepted |

How the arms are run and reported:
- **Run order:**
  1. The four test repositories are learned at C0, with L1 and L2. L2 gets at most 10 Codex calls per
     repository.
  2. The run stops while the owner reviews the L2 proposals.
  3. The rest of the run uses the owner's decisions as they stand.
- **Who sees the proposals:** the person running the harness does not read them before the run.
- **Shared answers:** when arms B and C receive identical context, C reuses B's answer and judge
  verdict instead of asking again.
- **Reporting:** B − A is the pass/fail result defined above. C − A is reported next to it, and so are
  the counts of proposals accepted and rejected.
- **Precision:** reported for the active memory of arm B, as defined above, and separately for a sample
  of up to 15 L2 proposals per repository, whatever their review outcome.

**2. 31 October 2026, after learning at C0 and before any proposal was read: who reviews L2.**

The owner delegated the L2 review to Claude, who also runs the harness. This replaces Amendment 1's
rule that the person running the harness does not read the proposals. To keep arm B from being tuned
to the test tasks, the review follows a fixed rule, committed before any proposal was opened:

- **Each proposal is judged on its own text and cited evidence only.** The reviewer does not open
  `utility_v1.json` or `repoqa_v1.json` during the review and does not consider which tasks an item
  might help.
- **Accept** a proposal when all of these hold:
  1. its cited evidence (document section or maintainer review comment) states or clearly implies the
     claim;
  2. it is a lasting convention, constraint or fact about the repository that a contributor would need
     in more than one change, not advice about one pull request;
  3. it is specific to this repository: it is not general programming advice;
  4. it does not merely repeat an L1 item.
- **Reject** everything else, including proposals whose claim goes beyond their evidence.
- The counts accepted and rejected per repository are reported with the results, and arm C (every
  proposal) is unaffected by the review.

The primary measure is unchanged: source-file recall, as locked. All-file recall stays a secondary
measure. The owner did not choose to amend it, so dev results did not change what counts as passing.
