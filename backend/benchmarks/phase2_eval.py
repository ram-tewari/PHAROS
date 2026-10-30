"""Phase 2 evaluation: memory precision, grounding, utility A/B and Repo QA.

Implements docs/benchmarks/phase2-eval-protocol.md. For each repository in
the dataset:

1. a worktree of its full mirror is checked out at the cutoff C0, indexed
   into a scratch database (``pharos_bench*``) and learned (L1, plus L2 when
   ``--codex-learn-calls`` > 0);
2. Repo QA questions for it are answered at C0, without (A) and with (B)
   memory;
3. grounding is checked for every memory item, and a precision sample is
   prepared;
4. utility tasks run in date order: the worktree moves to each task's parent
   and is re-indexed incrementally (memory stays as learned at C0), and Codex
   proposes the change from ``retrieve_context`` without and with memory.

Then the blinded judge runs over the utility proposals, the Repo QA answers
and the precision sample, and the report is computed. Every Codex answer is
checkpointed in ``--out`` as it arrives; rerunning the same command resumes
without spending a call twice. Locked datasets are run once (see the
protocol); development datasets as often as needed::

    python benchmarks/phase2_eval.py --dataset benchmarks/datasets/utility_dev_v1.json \\
        --database-url postgresql+psycopg2://postgres@127.0.0.1:55432/pharos_bench \\
        --embedder onnx=models/granite-embedding-english-r2-int8 --mirrors ~/.cache/pharos/git \\
        --workdir /tmp/p2 --out benchmarks/results/phase2_dev.json
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
from collections import Counter
from pathlib import Path

from sqlalchemy import create_engine, select
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
JUDGE_BATCH = 4
QA_JUDGE_BATCH = 10
PRECISION_BATCH = 10

PROPOSE_INSTRUCTIONS = """You are a software engineer making a change in the repository described below. You
cannot open files: work only from the context PHAROS retrieved for the change request. Decide which existing
files you would modify (or delete) and which new files you would create, as repository-relative paths, including
tests, documentation and changelogs where this repository would expect them. Then give the new or changed
code for each file (only the parts that change). Follow the repository's own conventions."""

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


def context(factory, embedder, repo: Repository, query: str, memory: bool) -> dict:
    with factory() as db:
        return assemble_context(db, embedder, ContextRequest(query=query, repository=repo.url, include_memory=memory))


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
    ap.add_argument("--codex-budget", type=int, default=400, help="hard cap on Codex calls for this run")
    ap.add_argument("--activate-l2", action="store_true",
                    help="treat L2 proposals as accepted (an upper bound for the approval gate)")
    ap.add_argument("--repos", nargs="*", help="only these repositories")
    ap.add_argument("--max-tasks", type=int, help="at most this many tasks per repository (dev runs)")
    args = ap.parse_args(argv)

    if "bench" not in args.database_url.rsplit("/", 1)[-1]:
        raise SystemExit("refusing a database whose name does not contain 'bench'")
    dataset = json.loads(Path(args.dataset).read_text())
    qa = json.loads(Path(args.qa).read_text()) if args.qa else {"questions": []}
    out = Path(args.out)
    ck = Checkpoint(out)
    ck.put({"dataset": Path(args.dataset).name, "dataset_sha256": hashlib.sha256(Path(args.dataset).read_bytes()).hexdigest(),
            "qa": Path(args.qa).name if args.qa else None,
            "qa_sha256": hashlib.sha256(Path(args.qa).read_bytes()).hexdigest() if args.qa else None,
            "codex_learn_calls": args.codex_learn_calls, "activate_l2": args.activate_l2}, "run")
    llm = CodexCLI(effort="medium", timeout=420, max_calls=args.codex_budget)
    judge = CodexCLI(effort="high", timeout=600, max_calls=args.codex_budget)
    if not llm.ready():
        raise SystemExit("codex is not ready (codex login)")
    embedder = make_embedder(args.embedder)
    if not ck.get("db_ready"):
        reset_database(args.database_url)
        ck.put(True, "db_ready")
    engine = create_engine(args.database_url)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    workdir = Path(args.workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(SEED)

    def spent() -> int:
        return llm.usage.calls + judge.usage.calls

    for repo_spec in dataset["repositories"]:
        name = repo_spec["name"]
        if args.repos and name not in args.repos:
            continue
        mirror = Path(args.mirrors).expanduser() / repo_spec.get("mirror", re.sub(r"^https://github\.com/", "",
                                                                                 repo_spec["url"]).replace("/", "_"))
        wt = worktree_at(mirror, workdir / name, repo_spec["cutoff_commit"])
        repo = index(factory, embedder, wt)
        if not ck.get("learned", name):
            with factory() as db:
                row = db.get(Repository, repo.id)
                stats = learn_repository(db, row, checkout=wt, mirror=wt, commit=row.last_commit_sha,
                                         embedder=embedder, llm=llm if args.codex_learn_calls else None,
                                         max_llm_calls=args.codex_learn_calls, progress=print)
                if args.activate_l2:
                    for item in db.execute(select(MemoryItem).where(MemoryItem.repository_id == repo.id,
                                                                    MemoryItem.tier == "L2",
                                                                    MemoryItem.status == "proposed")).scalars():
                        item.status = "active"
                    db.commit()
            ck.put(stats, "learned", name)
        styles = dominant_styles(factory, repo)
        ck.put(styles, "styles", name)

        # Repo QA at C0.
        for q in [q for q in qa["questions"] if q["repo"] == name]:
            for arm, memory in (("A", False), ("B", True)):
                if ck.get("qa", q["id"], arm):
                    continue
                ctx = context(factory, embedder, repo, q["question"], memory)
                prompt = f"Repository: {name}\nQuestion: {q['question']}\n\n# Context\n{ctx['context_text']}"
                if memory:
                    with factory() as db:
                        hits = search_memory(db, embedder, q["question"], [repo.id], k=8)
                    prompt += "\n\n# Memory search results\n" + "\n".join(
                        f"- {h['title']}: {h['body']} [{', '.join(cite(e) for e in h['evidence'][:2])}]" for h in hits)
                answer = llm.complete(QA_INSTRUCTIONS, prompt, QA_SCHEMA)
                ck.put({"answer": answer.get("answer", ""), "context_chars": len(prompt)}, "qa", q["id"], arm)

        # Grounding (every item) and the precision sample (active items), at C0.
        if not ck.get("grounding", name):
            with factory() as db:
                row = db.get(Repository, repo.id)
                snap = load_snapshot(db, row, wt, wt, row.last_commit_sha)
                check = _grounding(snap, repo_spec["url"])
                items = db.execute(select(MemoryItem).where(MemoryItem.repository_id == repo.id)).scalars().all()
                bad = [i.key for i in items if not all(check(e) for e in i.evidence or [])]
                active = sorted((i for i in items if i.status == "active"), key=lambda i: i.key)
                sample = random.Random(SEED).sample(active, min(PRECISION_SAMPLE, len(active)))
                sample_out = [{"id": str(i.id), "key": i.key, "tier": i.tier, "source": i.source,
                               "claim": f"{i.title}: {i.body}", "evidence": i.evidence} for i in sample]
            ck.put({"items": len(items), "ungrounded": bad}, "grounding", name)
            ck.put(sample_out, "precision_sample", name)

        # Utility tasks, in date order, each at its parent commit.
        tasks = sorted((t for t in dataset["tasks"] if t["repo"] == name), key=lambda t: t["date"])
        for task in tasks[:args.max_tasks] if args.max_tasks else tasks:
            if ck.get("utility", task["id"], "B"):
                continue
            worktree_at(mirror, wt, task["parent"])
            repo = index(factory, embedder, wt)
            for arm, memory in (("A", False), ("B", True)):
                if ck.get("utility", task["id"], arm):
                    continue
                if spent() >= args.codex_budget:
                    raise SystemExit(f"Codex budget of {args.codex_budget} calls reached; rerun to resume")
                ctx = context(factory, embedder, repo, task["task"], memory)
                prompt = f"Repository: {name}\n\n# Change request\n{task['task']}\n\n# Context\n{ctx['context_text']}"
                proposal = llm.complete(PROPOSE_INSTRUCTIONS, prompt, PROPOSE_SCHEMA)
                ck.put({"proposal": proposal, "context_chars": len(ctx["context_text"]),
                        "memory_items": len(ctx["memory"]["items"]), "scores": file_scores(task, proposal),
                        "naming": naming(proposal, styles)}, "utility", task["id"], arm)
        worktree_at(mirror, wt, repo_spec["cutoff_commit"])

    # Blinded judging.
    all_tasks = {t["id"]: t for t in dataset["tasks"]}
    pending = [tid for tid in ck.data.get("utility", {}) if not ck.get("judge", tid)]
    for start in range(0, len(pending), JUDGE_BATCH):
        batch, blocks, order = pending[start:start + JUDGE_BATCH], [], {}
        for tid in batch:
            task = all_tasks[tid]
            spec = next(r for r in dataset["repositories"] if r["name"] == task["repo"])
            mirror = Path(args.mirrors).expanduser() / spec.get("mirror", spec["url"].split("github.com/")[-1].replace("/", "_"))
            diff = git(mirror, "diff", task["parent"], task["commit"])[:8000]
            flip = rng.random() < 0.5
            order[tid] = flip
            x, y = ("B", "A") if flip else ("A", "B")
            blocks.append(f"## Task {tid}\n{task['task']}\n\n### Real change\n{diff}\n\n### Proposal X\n"
                          f"{render_proposal(ck.get('utility', tid, x)['proposal'])}\n\n### Proposal Y\n"
                          f"{render_proposal(ck.get('utility', tid, y)['proposal'])}")
        answer = judge.complete(JUDGE_INSTRUCTIONS, "\n\n".join(blocks), JUDGE_SCHEMA)
        for v in answer.get("verdicts", []):
            if v.get("task") in order:
                flip = order[v["task"]]
                a_key, b_key = ("y", "x") if flip else ("x", "y")
                better = {"X": "B" if flip else "A", "Y": "A" if flip else "B", "tie": "tie"}[v["better"]]
                ck.put({"A_match": v[f"{a_key}_match"], "A_conventions": v[f"{a_key}_conventions"],
                        "B_match": v[f"{b_key}_match"], "B_conventions": v[f"{b_key}_conventions"],
                        "better": better, "x_was": "B" if flip else "A"}, "judge", v["task"])

    answers = [(qid, arm) for qid, arms in ck.data.get("qa", {}).items() for arm in arms if not ck.get("qa_grade", qid, arm)]
    rng.shuffle(answers)
    questions = {q["id"]: q for q in qa["questions"]}
    for start in range(0, len(answers), QA_JUDGE_BATCH):
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

    for name, sample in (ck.data.get("precision_sample") or {}).items():
        todo = [s for s in sample if not ck.get("precision", name, s["id"])]
        spec = next(r for r in dataset["repositories"] if r["name"] == name)
        wt = workdir / name
        for start in range(0, len(todo), PRECISION_BATCH):
            batch = todo[start:start + PRECISION_BATCH]
            labels = {f"m{i}": s for i, s in enumerate(batch)}
            prompt = "\n\n".join(f"## {label}\nClaim: {s['claim']}\nEvidence:\n{evidence_text(s, wt, spec['url'].split('github.com/')[-1].replace('/', '_'))}"
                                 for label, s in labels.items())
            audited = judge.complete(PRECISION_INSTRUCTIONS, prompt, PRECISION_SCHEMA)
            for a in audited.get("audits", []):
                if a.get("id") in labels:
                    ck.put({"verdict": a["verdict"], "reason": a.get("reason", "")}, "precision", name,
                           labels[a["id"]]["id"])

    ck.put(report(ck.data, dataset, qa), "report")
    ck.put({"propose": vars(llm.usage) | {"per_call": len(llm.usage.per_call)},
            "judge": vars(judge.usage) | {"per_call": len(judge.usage.per_call)}}, "codex_usage_last_run")
    print(json.dumps(ck.data["report"], indent=1))
    return 0


def report(data: dict, dataset: dict, qa: dict) -> dict:
    out: dict = {}
    tasks = [t for t in dataset["tasks"] if (data.get("utility") or {}).get(t["id"], {}).get("B")]
    if tasks:
        def arm(metric, a):
            return [data["utility"][t["id"]][a]["scores"][metric] for t in tasks]
        src = [t for t in tasks if data["utility"][t["id"]]["A"]["scores"]["source_recall"] is not None]
        sa = [data["utility"][t["id"]]["A"]["scores"]["source_recall"] for t in src]
        sb = [data["utility"][t["id"]]["B"]["scores"]["source_recall"] for t in src]
        out["utility"] = {
            "tasks": len(tasks), "tasks_with_existing_source": len(src),
            "source_recall": {"A": round(sum(sa) / len(sa), 4), "B": round(sum(sb) / len(sb), 4),
                              "B_minus_A": paired_delta(sb, sa)} if src else None,
            "all_recall": {"A": round(sum(arm("all_recall", "A")) / len(tasks), 4),
                           "B": round(sum(arm("all_recall", "B")) / len(tasks), 4),
                           "B_minus_A": paired_delta(arm("all_recall", "B"), arm("all_recall", "A"))},
            "precision": {"A": round(sum(arm("precision", "A")) / len(tasks), 4),
                          "B": round(sum(arm("precision", "B")) / len(tasks), 4),
                          "B_minus_A": paired_delta(arm("precision", "B"), arm("precision", "A"))},
        }
        for a in ("A", "B"):
            ok = sum(data["utility"][t["id"]][a]["naming"][0] for t in tasks)
            total = sum(data["utility"][t["id"]][a]["naming"][1] for t in tasks)
            out["utility"].setdefault("naming_adherence", {})[a] = {"ok": ok, "total": total,
                                                                    "rate": round(ok / total, 4) if total else None}
        judged = [data["judge"][t["id"]] for t in tasks if (data.get("judge") or {}).get(t["id"])]
        if judged:
            wins = sum(j["better"] == "B" for j in judged)
            losses = sum(j["better"] == "A" for j in judged)
            out["utility"]["judge"] = {
                "judged": len(judged), "B_better": wins, "A_better": losses, "ties": len(judged) - wins - losses,
                "sign_test_p": round(sign_test(wins, losses), 4),
                "match_B_minus_A": paired_delta([j["B_match"] for j in judged], [j["A_match"] for j in judged]),
                "conventions_B_minus_A": paired_delta([j["B_conventions"] for j in judged],
                                                      [j["A_conventions"] for j in judged]),
            }
        out["utility"]["by_repo"] = {}
        for name in {t["repo"] for t in tasks}:
            ts = [t for t in src if t["repo"] == name]
            if ts:
                out["utility"]["by_repo"][name] = {
                    "A": round(sum(data["utility"][t["id"]]["A"]["scores"]["source_recall"] for t in ts) / len(ts), 4),
                    "B": round(sum(data["utility"][t["id"]]["B"]["scores"]["source_recall"] for t in ts) / len(ts), 4),
                    "n": len(ts)}
    grades = data.get("qa_grade") or {}
    qs = [q for q in qa["questions"] if grades.get(q["id"], {}).get("A") and grades[q["id"]].get("B")]
    if qs:
        correct = {a: [grades[q["id"]][a]["verdict"] == "correct" for q in qs] for a in ("A", "B")}
        b_only = sum(b and not a for a, b in zip(correct["A"], correct["B"], strict=True))
        a_only = sum(a and not b for a, b in zip(correct["A"], correct["B"], strict=True))
        out["repoqa"] = {
            "questions": len(qs),
            "correct": {a: sum(correct[a]) for a in ("A", "B")},
            "partial": {a: sum(grades[q["id"]][a]["verdict"] == "partial" for q in qs) for a in ("A", "B")},
            "mcnemar_exact_p": round(sign_test(b_only, a_only), 4), "B_only_correct": b_only, "A_only_correct": a_only,
            "by_category": {c: {a: sum(grades[q["id"]][a]["verdict"] == "correct" for q in qs if q["category"] == c)
                                for a in ("A", "B")} | {"n": sum(q["category"] == c for q in qs)}
                            for c in sorted({q["category"] for q in qs})},
        }
    prec = data.get("precision") or {}
    if prec:
        out["precision"] = {}
        for name, audits in prec.items():
            verdicts = Counter(a["verdict"] for a in audits.values())
            sample = {s["id"]: s for s in data["precision_sample"][name]}
            by_tier = Counter((sample[i]["tier"], a["verdict"]) for i, a in audits.items() if i in sample)
            out["precision"][name] = {"audited": len(audits), **verdicts,
                                      "precision": round(verdicts["supported"] / len(audits), 4),
                                      "by_tier": {f"{t}/{v}": n for (t, v), n in sorted(by_tier.items())}}
    g = data.get("grounding") or {}
    if g:
        total = sum(v["items"] for v in g.values())
        bad = sum(len(v["ungrounded"]) for v in g.values())
        out["grounding"] = {"items": total, "ungrounded": bad, "rate": round(1 - bad / total, 4) if total else None}
    return out


if __name__ == "__main__":
    sys.exit(main())
