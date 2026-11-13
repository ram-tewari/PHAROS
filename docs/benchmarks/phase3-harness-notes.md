# Phase 3 evaluation harness: how to run it

The harness implements the [Phase 3 protocol](phase3-eval-protocol.md). The code is
[`backend/benchmarks/agent_eval.py`](../../backend/benchmarks/agent_eval.py) (arms, preparation,
agent runs, report), [`ccrab.py`](../../backend/benchmarks/ccrab.py) (lock checks, c-CRAB data,
Docker grading) and [`agent_eval_worker.py`](../../backend/benchmarks/agent_eval_worker.py)
(indexing and learning inside an arm's own PHAROS code).

## What you need

- A copy of the [c-CRAB dataset repository](https://github.com/c-CRAB-Benchmark/dataset) at commit
  `856dfa31` (`--ccrab`). The harness reads `results_pipeline_funnel/stage4_agent_resolved.jsonl`
  and `raw_results_compressed/testgen_combined.zip` and checks both against the hashes in the lock
  file. It never runs anything from that copy.
- Docker that can run `linux/amd64` images (on an Apple Mac, Colima with Rosetta). Images are pulled
  from `ghcr.io/c-crab-benchmark/` as needed; each is about 3 GB on disk.
- PostgreSQL with pgvector, reachable over TCP (`--pg`, without a database name). The harness creates
  and drops databases named `pharos_bench_s1_*` and refuses any other name.
- The Claude Code CLI, signed in (`claude auth status`). It is found through `PHAROS_CLAUDE_PATH`,
  then `PATH`, then the newest VS Code extension; `--claude` overrides.
- An embedding model for PHAROS (`--embedder onnx=<dir>`; `hash` is fast but not semantic).
- Git mirrors under `~/.cache/pharos/git` (`--mirrors`). `agent_eval.py mirror --set dev` fills
  them. It reads only ids and commits from the lock file, so it may be run for the test set too.

## The gold self-check (no LLM)

```bash
cd backend
python benchmarks/agent_eval.py gold --set dev --ccrab <c-CRAB copy> --out <file> \
    --workers 2 --remove-images
```

For every instance it grades `head_commit` unchanged (every comment test must fail) and
`merged_commit` (every test must pass), in the instance's image. It refuses the test set: the locked
run does this as its first step.

On 13 November 2026 all 50 dev instances reproduced (61 of 61 tests fail at `head_commit` and pass
at `merged_commit`). Grading both commits took a median of 68 s per instance after a median 53 s
image pull.

## A dev run

```bash
python benchmarks/agent_eval.py run --set dev --arms P0,A,B-new \
    --instances <id> <id> ... --ccrab <c-CRAB copy> --out <file> --workdir <scratch dir> \
    --pg postgresql+psycopg2://postgres@127.0.0.1:55450 \
    --embedder onnx=<model dir>
python benchmarks/agent_eval.py report --out <file>
```

Rerunning the same command resumes. A finished agent run or grade is never repeated. An
infrastructure failure is recorded under `infra` and retried on the next run, at most three times
(`--infra-attempts`). A usage limit stops the run with exit code 75. Transcripts are kept next to the
checkpoint (`<file stem>.transcripts/`).

## The locked run

```bash
python benchmarks/agent_eval.py run --set test --locked-run --sealed-out <path outside the repository> \
    --ccrab <c-CRAB copy> --workdir <scratch dir> --pg <server> --embedder onnx=<model dir>
```

- Without `--locked-run` the test set is refused, and `--sealed-out` must be outside the repository.
- It runs all four arms, on all 105 instances, with no subset flags and no `--pr-diff`.
- Step 1 grades every instance's gold commits. Then it prepares, runs and grades instance by
  instance.
- It prints progress counts only. The report is written into the sealed file only when every
  instance is graded in every arm. `report --sealed-out <file>` refuses to show scores before that.

## How an instance is prepared

1. The mirror gets `base_commit` and `head_commit` (fetched by SHA or from `refs/pull/<n>/head` when
   they are not on a branch).
2. Two new repositories are fetched from it by SHA: one at `head_commit`, one at `base_commit`
   (`base_commit` is not always an ancestor of `head_commit`, so it is fetched from the mirror). Each
   has a fresh object store, one branch and no tags or remote, so nothing later than its commit
   exists in it. The harness checks this (every ref at the commit, later commits absent, the commit
   count equal to the commit's ancestors) and records the result.
3. Per arm a *serving* (a PHAROS code version and how its memory is learned) gets its own database.
   The index is built from the base clone at `base_commit`, once per distinct indexing code, and
   copied as a template. When an earlier instance of the same repository has one, it starts from a
   copy of that and indexes incrementally (`--no-reuse-index` turns this off). Memory is learned at
   `base_commit` from the base clone, with network access blocked (a dead proxy and
   `GIT_ALLOW_PROTOCOL=file`). The database's repository is then pointed at the head clone and
   indexed at `head_commit`; memory stays.
4. The leakage check runs on the learned memory: every brief is for `base_commit`; every review
   comment the learner could read (its cache, read after learning) was created before the pull
   request and is not on it; every cited review is one of those; every cited commit is an ancestor of
   `base_commit`. A failure stops the run.
5. Each arm's agent works in its own copy of the head clone.

The arms are the `SERVINGS` and `ARMS` tables at the top of `agent_eval.py`. Later stages edit them:

| Arm | Serving | Code | Memory | MCP tools |
|---|---|---|---|---|
| P0 | none | | | none |
| A | `retrieval` | this branch | none learned | `retrieve_context`, `search_code`, `find_symbol` |
| B-old | `phase2` | tag `phase2-baseline` | deterministic tier | A's, plus `get_repo_brief`, `search_memory`, `list_skills`, `get_skill` |
| B-new | `phase3` | this branch | deterministic tier (for now) | as B-old until Phase 3 adds its tools |

Arm A uses the same code as B-new over a database with no memory, so B-new − A measures memory alone.
`--code name=path` serves a code version from another checkout.

## The test agent

Each run is one `claude -p` process in the agent's checkout, with the prompt on stdin: the
repository name, the pull request's title and description, and the protocol's instruction. The flags:

| Flag | Why |
|---|---|
| `-p --output-format stream-json --verbose` | headless; the stream gives the tool list, every tool call and the final usage |
| `--model claude-sonnet-5-5` | the protocol's test model |
| `--max-turns 60` | the same turn limit in every arm (the protocol fixes that it is equal, not its value) |
| `--restricted` | removes every built-in tool that runs commands or code and WebFetch, confines file tools to the working directory, ignores user and project settings |
| `--tools Read,Glob,Grep,Edit,Write` | file read, search and edit only |
| `--strict-mcp-config --mcp-config <file>` | only the arm's PHAROS server (an empty config in P0) |
| `--permission-mode dontAsk --allowedTools <tools>` | approves exactly the arm's tools and denies anything else without a prompt |
| `--disallowedTools Bash,WebFetch,WebSearch,mcp__pharos__<tools not in the arm>` | belt and braces, and hides the PHAROS tools the arm does not get |
| `--no-session-persistence --disable-slash-commands` | nothing is saved; no skills or commands |

`ANTHROPIC_API_KEY` and `ANTHROPIC_AUTH_TOKEN` are removed from its environment, so it runs on the
subscription login. The harness compares the tool list the CLI reports at start with the arm's
expected list and stops on any difference. An arm with PHAROS whose server is not connected is an
infrastructure failure.

## Grading

As c-CRAB's `agent_resolver.py`: in the instance's image, `git checkout --force <head_commit>` and
`git clean -fd`, `pip install -e . --no-deps`, `git apply` the agent's diff (taken with `git add -A`
and `git diff --cached --binary <head_commit>`, so new files count), reinstall, then each comment's
test is copied in as `/workspace/test_review_comment_<i>.py` and run with
`python -m pytest <file> -x -v --tb=short --no-header -c /dev/null -p no:cacheprovider`, 120 s per
test. JavaScript tests run with `npx jest --no-coverage`. An agent that changes nothing resolves
nothing, as in c-CRAB. Files go into containers through `docker cp` with a tar stream, because Colima
shares only the home folder.

## Known limits

- The agent has no shell, so it cannot read git history or diff the pull request; it sees the tree at
  `head_commit` and the PR text only. `--pr-diff` (dev only, refused in the locked run) adds the
  `base_commit..head_commit` diff to the prompt for experiments.
- Learning from review comments is not wired: no current learner reads them for a local repository.
  A serving with `"reviews": True` stops with an error until stage S3 adds a review source. The
  leakage check already inspects the learner's review cache.
- The CLI's built-in plugins load in every arm, and it makes small calls to a Haiku model of its own
  (titles and summaries). Both are the same in every arm. Usage is taken from the CLI's result, which
  counts the main model's tokens; its cost figure is an estimate, not a bill.
- Indexing with the ONNX model is the slowest step, and the move to `head_commit` is repeated in each
  serving's database. Each instance's databases are kept so a resume does not rebuild them; drop
  `pharos_bench_s1_*` when done. `EMBEDDING_ONNX_THREADS` is passed through when set.
- `base_commit` can be newer than the pull request: in `ManimCommunity__manim-1140` it is a day
  after `created_at` and not an ancestor of `head_commit`. The harness records both facts per
  instance (`prep.history`). Learning still happens at `base_commit`, as the protocol says.
