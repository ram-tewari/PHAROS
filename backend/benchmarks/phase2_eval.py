"""Phase 2 evaluation: memory precision, grounding, utility A/B(/C) and Repo QA.

Implements docs/benchmarks/phase2-eval-protocol.md, including amendment 1
(arms A: no memory, B: L1 + accepted L2, C: L1 + every L2 proposal). For
each repository in the dataset:

1. a worktree of its full mirror is checked out at the cutoff C0, indexed
   into a scratch database (``pharos_bench*``) and learned (L1, plus L2 when
   ``--codex-learn-calls`` > 0). ``--stop-after-learn`` stops here so the
   owner can review the L2 proposals (``--export-review`` / ``--apply-review``);
2. Repo QA questions are answered at C0 in every arm;
3. grounding is checked for every memory item, and precision samples are
   prepared (active memory, and the raw L2 proposals);
4. utility tasks run in date order: the worktree moves to each task's parent
   and is re-indexed incrementally (memory stays as learned at C0), and Codex
   proposes the change from ``retrieve_context`` in every arm. When arms B and
   C see identical context, C reuses B's answer.

Then the blinded judge compares A with each memory arm, grades the Repo QA
answers and audits the precision samples, and the report is computed. Every
Codex answer is checkpointed in ``--out`` as it arrives; rerunning the same
command resumes without spending a call twice. Locked datasets are run once
(see the protocol); development datasets as often as needed::

    python benchmarks/phase2_eval.py --dataset benchmarks/datasets/utility_v1.json \\
        --qa benchmarks/datasets/repoqa_v1.json --upper-bound-arm \\
        --database-url postgresql+psycopg2://postgres@127.0.0.1:55432/pharos_bench \\
        --embedder onnx=models/granite-embedding-english-r2-int8 --mirrors ~/.cache/pharos/git \\
        --workdir /tmp/p2 --out benchmarks/results/phase2.json --stop-after-learn
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import re
import subprocess
import sys
import uuid
from collections import Counter
from pathlib import Path

from sqlalchemy import create_engine, func, select, update
from sqlalchemy.orm import sessionmaker

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "benchmarks"))

from retrieval_eval import make_embedder, paired_delta, reset_database  # noqa: E402

from app.codeintel.context import ContextRequest, assemble_context  # noqa: E402
from app.codeintel.git_source import parse_repo_spec  # noqa: E402
from app.codeintel.indexer import CodeIndexer  # noqa: E402
from app.codeintel.languages import detect_language  # noqa: E402
from app.codeintel.retrieval import path_role  # noqa: E402
from app.database.models import DocumentChunk, MemoryItem, Repository  # noqa: E402
from app.learning.llm import CodexCLI  # noqa: E402
from app.learning.memory import cite  # noqa: E402
from app.learning.miners import case_style  # noqa: E402
from app.learning.pipeline import _grounding, learn_repository, load_snapshot  # noqa: E402
from app.learning.recall import search_memory  # noqa: E402
from app.learning.reviews import cache_dir  # noqa: E402

SEED = 20261030
PRECISION_SAMPLE = 30
L2_SAMPLE = 15
JUDGE_BATCH = 4
QA_JUDGE_BATCH = 10
PRECISION_BATCH = 10

PROPOSE_INSTRUCTIONS = """You are a software engineer making a change in the repository described below. The
context PHAROS retrieved for the change request is all you get: there are no tools and no file access, so do
not try to inspect anything. Always give your best concrete attempt from the context, even when it is
incomplete; an empty answer is never acceptable. List the existing files you would modify (or delete) and the
new files you would create, as repository-relative paths, including tests, documentation and changelogs where
this repository would expect them. Then give the new or changed code for each file (only the parts that
change). Follow the repository's own conventions."""

PROPOSE_SCHEMA = {
    "type": "object",
    "properties": {
        "files": {"type": "array", "items": {"type": "object", "properties": {
            "path": {"type": "string"}, "action": {"type": "string", "enum": ["modify", "create", "delete"]}},
            "required": ["path", "action"]}},
        "changes": {"type": "array", "items": {"type": "object", "properties": {
            "path": {"type": "string"}, "code": {"type": "string"}}, "required": ["path", "code"]}},
    },
    "required": ["files", "changes"],
}

JUDGE_INSTRUCTIONS = """You compare two proposed implementations (X and Y) of the same change request against
the change the project actually made. For each task rate each proposal from 1 to 5 on:
- match: how closely it makes the real change (same files, same approach, correct behaviour);
- conventions: how well it follows this repository's conventions (naming, structure, error handling,
  tests/docs/changelog habits) as visible in the real change.
Then say which proposal is better overall: X, Y or tie. Judge only what is shown."""

JUDGE_SCHEMA = {"type": "object", "properties": {"verdicts": {"type": "array", "items": {"type": "object", "properties": {
    "task": {"type": "string"}, "x_match": {"type": "integer"}, "x_conventions": {"type": "integer"},
    "y_match": {"type": "integer"}, "y_conventions": {"type": "integer"},
    "better": {"type": "string", "enum": ["X", "Y", "tie"]}},
    "required": ["task", "x_match", "x_conventions", "y_match", "y_conventions", "better"]}}},
    "required": ["verdicts"]}

QA_INSTRUCTIONS = """Answer the question about the repository using only the context provided. Be specific (names,
files, versions, dates, commit or PR numbers when the context has them). If the context does not support an
answer, say so instead of guessing. At most 120 words."""
QA_SCHEMA = {"type": "object", "properties": {"answer": {"type": "string"}}, "required": ["answer"]}

QA_JUDGE_INSTRUCTIONS = """You grade answers to questions about a software repository against a reference answer
and its key facts. For each answer: list the indices (0-based) of the key facts it states, and give a verdict:
correct (states every key fact), partial (states at least one), wrong (states none, or confidently contradicts a
key fact). For abstention questions the key fact is that the repository does not do the thing: an answer is
correct only if it says so."""
QA_JUDGE_SCHEMA = {"type": "object", "properties": {"grades": {"type": "array", "items": {"type": "object", "properties": {
    "id": {"type": "string"}, "facts": {"type": "array", "items": {"type": "integer"}},
    "verdict": {"type": "string", "enum": ["correct", "partial", "wrong"]}}, "required": ["id", "facts", "verdict"]}}},
    "required": ["grades"]}

PRECISION_INSTRUCTIONS = """You audit memory items a tool learned about a software repository. Each item is a claim
plus the evidence it cites (source lines, commits, review comments). Percentages and counts were computed by the
tool over the whole git history; you cannot recompute them, so judge whether the cited evidence is consistent
with the claim and whether anything shown contradicts it. Verdict: supported, partly (some of the claim is not
backed or is overstated), unsupported (not backed, or contradicted)."""
PRECISION_SCHEMA = {"type": "object", "properties": {"audits": {"type": "array", "items": {"type": "object", "properties": {
    "id": {"type": "string"}, "verdict": {"type": "string", "enum": ["supported", "partly", "unsupported"]},
    "reason": {"type": "string"}}, "required": ["id", "verdict", "reason"]}}}, "required": ["audits"]}

DEF_PATTERNS = {
    "python": [(re.compile(r"^(\s*)(?:async\s+)?def\s+(\w+)", re.M), "function"),
               (re.compile(r"^\s*class\s+(\w+)", re.M), "class")],
    "go": [(re.compile(r"^func\s+(\([^)]*\)\s*)?(\w+)", re.M), "function"), (re.compile(r"^type\s+(\w+)", re.M), "class")],
    "c": [(re.compile(r"^(?:static\s+|inline\s+|const\s+|unsigned\s+|struct\s+)*[A-Za-z_][\w]*[\s*]+\**([A-Za-z_]\w*)\s*\([^;{]*\)?\s*$",
                      re.M), "function")],
    "typescript": [(re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s+(\w+)", re.M), "function"),
                   (re.compile(r"^\s*(?:export\s+)?class\s+(\w+)", re.M), "class")],
}


def git(path: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True, text=True,
                          errors="replace").stdout


class Checkpoint:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.data = json.loads(path.read_text()) if path.exists() else {}

    def get(self, *keys):
        node = self.data
        for k in keys:
            node = node.get(k) if isinstance(node, dict) else None
            if node is None:
                return None
        return node

    def put(self, value, *keys) -> None:
        node = self.data
        for k in keys[:-1]:
            node = node.setdefault(k, {})
        node[keys[-1]] = value
        self.path.write_text(json.dumps(self.data, indent=1))


def worktree_at(mirror: Path, path: Path, commit: str) -> Path:
    if not path.exists():
        git(mirror, "worktree", "add", "-q", "--detach", str(path), commit)
    git(path, "checkout", "-q", "--detach", commit)
    return path


def index(factory, embedder, path: Path) -> Repository:
    ref = parse_repo_spec(str(path), allowed_hosts=[], allow_local=True)
    with factory() as db:
        CodeIndexer(db, embedder).index(ref)
        return db.execute(select(Repository).where(Repository.url == ref.canonical_url)).scalar_one()


def _activate_l2(db, repository_id) -> None:
    """Arm C: every L2 proposal counts as accepted, inside the caller's transaction (rolled back).

    Rejected ones too: applying the review moves unticked proposals to ``rejected``, and arm C must not
    depend on the review (in the first locked run it did, so C was identical to B)."""
    db.execute(update(MemoryItem).where(MemoryItem.repository_id == repository_id, MemoryItem.tier == "L2",
                                        MemoryItem.status.in_(("proposed", "rejected"))).values(status="active"))


def context(factory, embedder, repo: Repository, query: str, arm: str) -> dict:
    """``retrieve_context`` for one arm: A without memory, B with it, C with every L2 proposal active."""
    with factory() as db:
        if arm == "C":
            _activate_l2(db, repo.id)
        out = assemble_context(db, embedder, ContextRequest(query=query, repository=repo.url,
                                                            include_memory=arm != "A"))
        db.rollback()
        return out


def dominant_styles(factory, repo: Repository) -> dict:
    with factory() as db:
        rows = db.execute(select(DocumentChunk.language, DocumentChunk.ast_node_type, DocumentChunk.chunk_metadata)
                          .where(DocumentChunk.repository_id == repo.id)).all()
    counts: dict[tuple, Counter] = {}
    for lang, kind, meta in rows:
        meta = meta or {}
        if path_role(meta.get("path", "")) != "source" or kind not in ("function", "method", "class"):
            continue
        style = case_style(meta.get("name") or "")
        if style:
            counts.setdefault((lang, "class" if kind == "class" else "function"), Counter())[style] += 1
    return {f"{lang}/{kind}": c.most_common(1)[0][0] for (lang, kind), c in counts.items()}


def naming(proposal: dict, styles: dict) -> tuple[int, int]:
    ok = total = 0
    for change in proposal.get("changes") or []:
        spec = detect_language(change.get("path", ""))
        lang = spec.name if spec else None
        for pattern, kind in DEF_PATTERNS.get(lang or "", []):
            for m in pattern.finditer(change.get("code") or ""):
                name = m.group(m.lastindex)
                style = case_style(name)
                want = styles.get(f"{lang}/{kind}")
                if not style or not want:
                    continue
                total += 1
                if lang == "go":
                    ok += "_" not in name.strip("_")
                else:
                    ok += style == want
    return ok, total


def file_scores(task: dict, proposal: dict) -> dict:
    proposed = {f["path"].lstrip("./") for f in proposal.get("files") or [] if f.get("path")}
    proposed |= {c["path"].lstrip("./") for c in proposal.get("changes") or [] if c.get("path")}
    real_all = {f["path"] for f in task["files"]}
    real_src = {f["path"] for f in task["files"] if f["source"] and f["status"] != "A"}
    hit_all = proposed & real_all
    return {
        "source_recall": len(proposed & real_src) / len(real_src) if real_src else None,
        "all_recall": len(hit_all) / len(real_all),
        "precision": len(hit_all) / len(proposed) if proposed else 0.0,
        "proposed": len(proposed),
    }


def render_proposal(p: dict, limit: int = 5000) -> str:
    files = ", ".join(f"{f['path']} ({f['action']})" for f in p.get("files") or [])
    code = "\n\n".join(f"--- {c['path']}\n{c['code']}" for c in p.get("changes") or [])
    return (f"files: {files}\n{code}")[:limit]


def sign_test(wins: int, losses: int) -> float:
    n = wins + losses
    if n == 0:
        return 1.0
    k = min(wins, losses)
    p = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * p)


def evidence_text(item: dict, worktree: Path, cache_name: str) -> str:
    parts = []
    for ev in item["evidence"][:4]:
        if ev["kind"] == "code":
            lines = (worktree / ev["path"]).read_text(errors="replace").splitlines()
            a, b = max(1, ev["start_line"] - 5), min(len(lines), ev["end_line"] + 5)
            parts.append(f"{ev['path']}:{a}-{b}\n" + "\n".join(lines[a - 1:b])[:1500])
        elif ev["kind"] == "file":
            parts.append(f"file {ev['path']} exists")
        elif ev["kind"] == "commit":
            parts.append(git(worktree, "show", "--stat", "--format=%h %cs %s", ev["sha"])[:1200])
        elif ev["kind"] == "review":
            cached = json.loads((cache_dir(cache_name) / "review_comments.json").read_text())
            c = next((c for c in cached if c["url"] == ev["url"]), None)
            if c:
                parts.append(f"review on PR #{c['pr']} ({c['path']}):\n{c['diff_hunk']}\nreviewer: {c['body'][:1000]}")
    return "\n\n".join(parts)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--qa", help="Repo QA dataset (repoqa_v1.json)")
    ap.add_argument("--database-url", required=True)
    ap.add_argument("--embedder", required=True)
    ap.add_argument("--mirrors", required=True)
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--codex-learn-calls", type=int, default=10, help="L2 calls per repository (0 = L1 only)")
    ap.add_argument("--codex-budget", type=int, default=500, help="hard cap on Codex calls for this run")
    ap.add_argument("--upper-bound-arm", action="store_true",
                    help="also run arm C: every L2 proposal as if accepted (protocol amendment 1)")
    ap.add_argument("--stop-after-learn", action="store_true", help="index and learn, then stop (for review)")
    ap.add_argument("--export-review", help="write the L2 proposals as a checkbox Markdown file, then stop")
    ap.add_argument("--apply-review", help="apply a reviewed checkbox file ([x] accept, [ ] reject), then stop")
    ap.add_argument("--repos", nargs="*", help="only these repositories")
    ap.add_argument("--max-tasks", type=int, help="at most this many tasks per repository (dev runs)")
    args = ap.parse_args(argv)

    if "bench" not in args.database_url.rsplit("/", 1)[-1]:
        raise SystemExit("refusing a database whose name does not contain 'bench'")
    dataset = json.loads(Path(args.dataset).read_text())
    qa = json.loads(Path(args.qa).read_text()) if args.qa else {"questions": []}
    engine = create_engine(args.database_url)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    if args.export_review:
        return export_review(factory, Path(args.export_review))
    if args.apply_review:
        return apply_review(factory, Path(args.apply_review))

    out = Path(args.out)
    ck = Checkpoint(out)
    ck.put({"dataset": Path(args.dataset).name,
            "dataset_sha256": hashlib.sha256(Path(args.dataset).read_bytes()).hexdigest(),
            "qa": Path(args.qa).name if args.qa else None,
            "qa_sha256": hashlib.sha256(Path(args.qa).read_bytes()).hexdigest() if args.qa else None,
            "codex_learn_calls": args.codex_learn_calls, "upper_bound_arm": args.upper_bound_arm}, "run")
    arms = ["A", "B"] + (["C"] if args.upper_bound_arm else [])
    llm = CodexCLI(effort="medium", timeout=420, max_calls=args.codex_budget)
    judge = CodexCLI(effort="high", timeout=600, max_calls=args.codex_budget)
    if not llm.ready():
        raise SystemExit("codex is not ready (codex login)")
    embedder = make_embedder(args.embedder)
    if not ck.get("db_ready"):
        reset_database(args.database_url)
        ck.put(True, "db_ready")
    workdir = Path(args.workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(SEED)
    specs = [r for r in dataset["repositories"] if not args.repos or r["name"] in args.repos]

    def mirror_of(spec: dict) -> Path:
        return Path(args.mirrors).expanduser() / spec.get("mirror", spec["url"].split("github.com/")[-1]
                                                           .replace("/", "_"))

    def spent() -> int:
        return llm.usage.calls + judge.usage.calls

    def guard() -> None:
        if spent() >= args.codex_budget:
            raise SystemExit(f"Codex budget of {args.codex_budget} calls reached; rerun to resume")

    # 1. Index and learn every repository at C0.
    repos: dict[str, Repository] = {}
    for spec in specs:
        name = spec["name"]
        wt = worktree_at(mirror_of(spec), workdir / name, spec["cutoff_commit"])
        repos[name] = index(factory, embedder, wt)
        if not ck.get("learned", name):
            with factory() as db:
                row = db.get(Repository, repos[name].id)
                stats = learn_repository(db, row, checkout=wt, mirror=wt, commit=row.last_commit_sha,
                                         embedder=embedder, llm=llm if args.codex_learn_calls else None,
                                         max_llm_calls=args.codex_learn_calls, progress=print)
            ck.put(stats, "learned", name)
    if args.stop_after_learn:
        with factory() as db:
            counts = {name: db.execute(select(func.count()).select_from(MemoryItem).where(
                MemoryItem.repository_id == repo.id, MemoryItem.tier == "L2")).scalar_one()
                for name, repo in repos.items()}
        print(json.dumps({"l2_proposals": counts, "codex_calls": spent()}))
        return 0
    with factory() as db:
        ck.put(dict(Counter(f"{i.status}" for i in db.execute(select(MemoryItem).where(MemoryItem.tier == "L2"))
                            .scalars())), "l2_review_outcome")

    # 2-4. Per repository: Repo QA and grounding at C0, then the utility tasks.
    for spec in specs:
        name, mirror = spec["name"], mirror_of(spec)
        wt = worktree_at(mirror, workdir / name, spec["cutoff_commit"])
        repo = index(factory, embedder, wt)
        styles = dominant_styles(factory, repo)
        ck.put(styles, "styles", name)

        for q in [q for q in qa["questions"] if q["repo"] == name]:
            for arm in arms:
                if ck.get("qa", q["id"], arm):
                    continue
                prompt = qa_prompt(factory, embedder, repo, name, q["question"], arm)
                sha = hashlib.sha256(prompt.encode()).hexdigest()
                if arm == "C" and ck.get("qa", q["id"], "B", "prompt_sha") == sha:
                    ck.put(ck.get("qa", q["id"], "B") | {"same_as": "B"}, "qa", q["id"], arm)
                    continue
                guard()
                answer = llm.complete(QA_INSTRUCTIONS, prompt, QA_SCHEMA)
                ck.put({"answer": answer.get("answer", ""), "context_chars": len(prompt), "prompt_sha": sha},
                       "qa", q["id"], arm)

        if not ck.get("grounding", name):
            with factory() as db:
                row = db.get(Repository, repo.id)
                snap = load_snapshot(db, row, wt, wt, row.last_commit_sha)
                check = _grounding(snap, spec["url"])
                items = db.execute(select(MemoryItem).where(MemoryItem.repository_id == repo.id)).scalars().all()
                bad = [i.key for i in items if not all(check(e) for e in i.evidence or [])]
                active = sorted((i for i in items if i.status == "active"), key=lambda i: i.key)
                l2 = sorted((i for i in items if i.tier == "L2"), key=lambda i: i.key)

                def pack(rows):
                    return [{"id": str(i.id), "key": i.key, "tier": i.tier, "source": i.source, "status": i.status,
                             "claim": f"{i.title}: {i.body}", "evidence": i.evidence} for i in rows]

                ck.put({"items": len(items), "ungrounded": bad}, "grounding", name)
                ck.put(pack(random.Random(SEED).sample(active, min(PRECISION_SAMPLE, len(active)))),
                       "precision_sample", name)
                ck.put(pack(random.Random(SEED).sample(l2, min(L2_SAMPLE, len(l2)))), "l2_sample", name)

        tasks = sorted((t for t in dataset["tasks"] if t["repo"] == name), key=lambda t: t["date"])
        for task in tasks[:args.max_tasks] if args.max_tasks else tasks:
            if all(ck.get("utility", task["id"], arm) for arm in arms):
                continue
            worktree_at(mirror, wt, task["parent"])
            repo = index(factory, embedder, wt)
            for arm in arms:
                if ck.get("utility", task["id"], arm):
                    continue
                ctx = context(factory, embedder, repo, task["task"], arm)
                sha = hashlib.sha256(ctx["context_text"].encode()).hexdigest()
                if arm == "C" and ck.get("utility", task["id"], "B", "context_sha") == sha:
                    ck.put(ck.get("utility", task["id"], "B") | {"same_as": "B"}, "utility", task["id"], arm)
                    continue
                guard()
                prompt = f"Repository: {name}\n\n# Change request\n{task['task']}\n\n# Context\n{ctx['context_text']}"
                proposal = llm.complete(PROPOSE_INSTRUCTIONS, prompt, PROPOSE_SCHEMA)
                ck.put({"proposal": proposal, "context_chars": len(ctx["context_text"]), "context_sha": sha,
                        "memory_items": len(ctx["memory"]["items"]), "scores": file_scores(task, proposal),
                        "naming": naming(proposal, styles)}, "utility", task["id"], arm)
        worktree_at(mirror, wt, spec["cutoff_commit"])

    # 5. Blinded judging: A against each memory arm.
    all_tasks = {t["id"]: t for t in dataset["tasks"]}
    specs_by_name = {r["name"]: r for r in dataset["repositories"]}
    for other in arms[1:]:
        pair = f"A-{other}"
        pending = []
        for tid, by_arm in (ck.data.get("utility") or {}).items():
            if other not in by_arm or ck.get("judge", pair, tid):
                continue
            if by_arm[other].get("same_as") == "B" and ck.get("judge", "A-B", tid):
                ck.put(ck.get("judge", "A-B", tid) | {"same_as": "B"}, "judge", pair, tid)
                continue
            pending.append(tid)
        for start in range(0, len(pending), JUDGE_BATCH):
            guard()
            batch, blocks, order = pending[start:start + JUDGE_BATCH], [], {}
            for tid in batch:
                task = all_tasks[tid]
                diff = git(mirror_of(specs_by_name[task["repo"]]), "diff", task["parent"], task["commit"])[:8000]
                flip = rng.random() < 0.5
                order[tid] = flip
                x, y = (other, "A") if flip else ("A", other)
                blocks.append(f"## Task {tid}\n{task['task']}\n\n### Real change\n{diff}\n\n### Proposal X\n"
                              f"{render_proposal(ck.get('utility', tid, x)['proposal'])}\n\n### Proposal Y\n"
                              f"{render_proposal(ck.get('utility', tid, y)['proposal'])}")
            answer = judge.complete(JUDGE_INSTRUCTIONS, "\n\n".join(blocks), JUDGE_SCHEMA)
            for v in answer.get("verdicts", []):
                if v.get("task") not in order:
                    continue
                flip = order[v["task"]]
                a_key, m_key = ("y", "x") if flip else ("x", "y")
                better = {"X": other if flip else "A", "Y": "A" if flip else other, "tie": "tie"}[v["better"]]
                ck.put({"A_match": v[f"{a_key}_match"], "A_conventions": v[f"{a_key}_conventions"],
                        "M_match": v[f"{m_key}_match"], "M_conventions": v[f"{m_key}_conventions"],
                        "better": "M" if better == other else better, "x_was": other if flip else "A"},
                       "judge", pair, v["task"])

    questions = {q["id"]: q for q in qa["questions"]}
    for qid, by_arm in (ck.data.get("qa") or {}).items():
        if by_arm.get("C", {}).get("same_as") == "B" and ck.get("qa_grade", qid, "B") and not ck.get(
                "qa_grade", qid, "C"):
            ck.put(ck.get("qa_grade", qid, "B") | {"same_as": "B"}, "qa_grade", qid, "C")
    answers = [(qid, arm) for qid, by_arm in (ck.data.get("qa") or {}).items() for arm in by_arm
               if not ck.get("qa_grade", qid, arm) and not (arm == "C" and by_arm[arm].get("same_as"))]
    rng.shuffle(answers)
    for start in range(0, len(answers), QA_JUDGE_BATCH):
        guard()
        batch = answers[start:start + QA_JUDGE_BATCH]
        labels = {f"a{start + i}": key for i, key in enumerate(batch)}
        prompt = "\n\n".join(
            f"## {label}\nQuestion: {questions[qid]['question']}\nCategory: {questions[qid]['category']}\n"
            f"Reference: {questions[qid]['answer']}\nKey facts: {json.dumps(questions[qid]['key_facts'])}\n"
            f"Answer: {ck.get('qa', qid, arm)['answer']}" for label, (qid, arm) in labels.items())
        graded = judge.complete(QA_JUDGE_INSTRUCTIONS, prompt, QA_JUDGE_SCHEMA)
        for g in graded.get("grades", []):
            if g.get("id") in labels:
                qid, arm = labels[g["id"]]
                ck.put({"verdict": g["verdict"], "facts": g.get("facts", [])}, "qa_grade", qid, arm)
    for qid, by_arm in (ck.data.get("qa") or {}).items():  # C answers copied from B take B's grade
        if by_arm.get("C", {}).get("same_as") == "B" and ck.get("qa_grade", qid, "B") and not ck.get(
                "qa_grade", qid, "C"):
            ck.put(ck.get("qa_grade", qid, "B") | {"same_as": "B"}, "qa_grade", qid, "C")

    # 6. Precision: active memory (arm B) and a sample of the raw L2 proposals.
    for section, result_key in (("precision_sample", "precision"), ("l2_sample", "l2_precision")):
        for name, sample in (ck.data.get(section) or {}).items():
            todo = [s for s in sample if not ck.get(result_key, name, s["id"])]
            cache_name = specs_by_name[name]["url"].split("github.com/")[-1].replace("/", "_")
            for start in range(0, len(todo), PRECISION_BATCH):
                guard()
                batch = todo[start:start + PRECISION_BATCH]
                labels = {f"m{i}": s for i, s in enumerate(batch)}
                prompt = "\n\n".join(f"## {label}\nClaim: {s['claim']}\nEvidence:\n"
                                     f"{evidence_text(s, workdir / name, cache_name)}" for label, s in labels.items())
                audited = judge.complete(PRECISION_INSTRUCTIONS, prompt, PRECISION_SCHEMA)
                for a in audited.get("audits", []):
                    if a.get("id") in labels:
                        ck.put({"verdict": a["verdict"], "reason": a.get("reason", "")}, result_key, name,
                               labels[a["id"]]["id"])

    ck.put(report(ck.data, dataset, qa, arms), "report")
    ck.put({"propose": vars(llm.usage) | {"per_call": len(llm.usage.per_call)},
            "judge": vars(judge.usage) | {"per_call": len(judge.usage.per_call)}}, "codex_usage_last_run")
    print(json.dumps(ck.data["report"], indent=1))
    return 0


def qa_prompt(factory, embedder, repo: Repository, name: str, question: str, arm: str) -> str:
    with factory() as db:
        if arm == "C":
            _activate_l2(db, repo.id)
        ctx = assemble_context(db, embedder, ContextRequest(query=question, repository=repo.url,
                                                            include_memory=arm != "A"))
        prompt = f"Repository: {name}\nQuestion: {question}\n\n# Context\n{ctx['context_text']}"
        if arm != "A":
            hits = search_memory(db, embedder, question, [repo.id], k=8)
            prompt += "\n\n# Memory search results\n" + "\n".join(
                f"- {h['title']}: {h['body']} [{', '.join(cite(e) for e in h['evidence'][:2])}]" for h in hits)
        db.rollback()
        return prompt


def export_review(factory, path: Path) -> int:
    """The L2 proposals as a checkbox list for the owner (the approval gate)."""
    with factory() as db:
        rows = db.execute(select(MemoryItem, Repository.name).join(Repository, Repository.id == MemoryItem.repository_id)
                          .where(MemoryItem.tier == "L2", MemoryItem.status == "proposed")
                          .order_by(Repository.name, MemoryItem.key)).all()
    lines = ["# L2 proposals to review", "",
             "Tick `[x]` to accept. Anything left `[ ]` is rejected when this file is applied.", ""]
    current = None
    for item, repo_name in rows:
        if repo_name != current:
            lines += ["", f"## {repo_name}", ""]
            current = repo_name
        cites = "; ".join(cite(e) if e["kind"] != "review" else f"review PR #{e['pr']} ({e['url']})"
                          for e in item.evidence)
        lines.append(f"- [ ] `{item.id}` **{item.title}** — {item.body}  \n  _evidence: {cites}_")
    path.write_text("\n".join(lines) + "\n")
    print(json.dumps({"proposals": len(rows), "file": str(path)}))
    return 0


def apply_review(factory, path: Path) -> int:
    from app.learning.memory import set_status

    decisions = {m.group(2): m.group(1).lower() == "x"
                 for m in re.finditer(r"^- \[([ xX])\] `([0-9a-f-]{36})`", path.read_text(), re.M)}
    counts = Counter()
    with factory() as db:
        for item_id, accept in decisions.items():
            item = db.get(MemoryItem, uuid.UUID(item_id))
            if item is None or item.status != "proposed":
                counts["skipped"] += 1
                continue
            set_status(db, item, "accept" if accept else "reject", actor="owner-review")
            counts["accepted" if accept else "rejected"] += 1
        db.commit()
    print(json.dumps(counts))
    return 0


def _utility_report(data: dict, tasks: list[dict], other: str) -> dict:
    tasks = [t for t in tasks if other in data["utility"][t["id"]]]
    if not tasks:
        return {}

    def col(metric: str, arm: str, ts=tasks) -> list[float]:
        return [data["utility"][t["id"]][arm]["scores"][metric] for t in ts]

    src = [t for t in tasks if data["utility"][t["id"]]["A"]["scores"]["source_recall"] is not None]
    out = {"tasks": len(tasks), "tasks_with_existing_source": len(src),
           "copied_from_B": sum(bool(data["utility"][t["id"]][other].get("same_as")) for t in tasks)}
    for metric, ts in (("source_recall", src), ("all_recall", tasks), ("precision", tasks)):
        a, m = col(metric, "A", ts), col(metric, other, ts)
        out[metric] = {"A": round(sum(a) / len(a), 4), other: round(sum(m) / len(m), 4),
                       f"{other}_minus_A": paired_delta(m, a)} if ts else None
    for arm in ("A", other):
        ok = sum(data["utility"][t["id"]][arm]["naming"][0] for t in tasks)
        total = sum(data["utility"][t["id"]][arm]["naming"][1] for t in tasks)
        out.setdefault("naming_adherence", {})[arm] = {"ok": ok, "total": total,
                                                       "rate": round(ok / total, 4) if total else None}
    judged = [(data.get("judge") or {}).get(f"A-{other}", {}).get(t["id"]) for t in tasks]
    judged = [j for j in judged if j]
    if judged:
        wins, losses = sum(j["better"] == "M" for j in judged), sum(j["better"] == "A" for j in judged)
        out["judge"] = {"judged": len(judged), f"{other}_better": wins, "A_better": losses,
                        "ties": len(judged) - wins - losses, "sign_test_p": round(sign_test(wins, losses), 4),
                        "match_delta": paired_delta([j["M_match"] for j in judged], [j["A_match"] for j in judged]),
                        "conventions_delta": paired_delta([j["M_conventions"] for j in judged],
                                                          [j["A_conventions"] for j in judged])}
    out["by_repo"] = {}
    for name in sorted({t["repo"] for t in src}):
        ts = [t for t in src if t["repo"] == name]
        out["by_repo"][name] = {"n": len(ts), "A": round(sum(col("source_recall", "A", ts)) / len(ts), 4),
                                other: round(sum(col("source_recall", other, ts)) / len(ts), 4)}
    return out


def report(data: dict, dataset: dict, qa: dict, arms: list[str]) -> dict:
    out: dict = {"l2_review_outcome": data.get("l2_review_outcome")}
    tasks = [t for t in dataset["tasks"] if (data.get("utility") or {}).get(t["id"], {}).get("B")]
    if tasks:
        out["utility"] = {f"{other}_vs_A": _utility_report(data, tasks, other) for other in arms[1:]}
    grades = data.get("qa_grade") or {}
    for other in arms[1:]:
        qs = [q for q in qa["questions"] if grades.get(q["id"], {}).get("A") and grades[q["id"]].get(other)]
        if not qs:
            continue
        correct = {a: [grades[q["id"]][a]["verdict"] == "correct" for q in qs] for a in ("A", other)}
        m_only = sum(m and not a for a, m in zip(correct["A"], correct[other], strict=True))
        a_only = sum(a and not m for a, m in zip(correct["A"], correct[other], strict=True))
        out.setdefault("repoqa", {})[f"{other}_vs_A"] = {
            "questions": len(qs), "correct": {a: sum(correct[a]) for a in ("A", other)},
            "partial": {a: sum(grades[q["id"]][a]["verdict"] == "partial" for q in qs) for a in ("A", other)},
            "mcnemar_exact_p": round(sign_test(m_only, a_only), 4), f"{other}_only_correct": m_only,
            "A_only_correct": a_only,
            "by_category": {c: {a: sum(grades[q["id"]][a]["verdict"] == "correct" for q in qs if q["category"] == c)
                                for a in ("A", other)} | {"n": sum(q["category"] == c for q in qs)}
                            for c in sorted({q["category"] for q in qs})},
        }
    for result_key, sample_key in (("precision", "precision_sample"), ("l2_precision", "l2_sample")):
        for name, audits in (data.get(result_key) or {}).items():
            verdicts = Counter(a["verdict"] for a in audits.values())
            sample = {s["id"]: s for s in data[sample_key][name]}
            by_tier = Counter((sample[i]["tier"], a["verdict"]) for i, a in audits.items() if i in sample)
            out.setdefault(result_key, {})[name] = {
                "audited": len(audits), **verdicts, "precision": round(verdicts["supported"] / len(audits), 4),
                "by_tier": {f"{t}/{v}": n for (t, v), n in sorted(by_tier.items())}}
    g = data.get("grounding") or {}
    if g:
        total = sum(v["items"] for v in g.values())
        bad = sum(len(v["ungrounded"]) for v in g.values())
        out["grounding"] = {"items": total, "ungrounded": bad, "rate": round(1 - bad / total, 4) if total else None}
    return out


if __name__ == "__main__":
    sys.exit(main())
