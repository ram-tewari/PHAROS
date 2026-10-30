"""Generate a synthetic *dev* retrieval set with Codex: questions written from function bodies.

For each pinned repository, samples source functions and methods (not tests,
docs or examples), strips their doc comments and comments, and asks Codex for
one behaviour question per function that paraphrases what the body does
without naming identifiers. Each question's only label is its function (grade 2).

Synthetic questions are for tuning only. They follow the body, so they favour
methods that embed the body: never report them as a result, and confirm every
change on the hand-written, locked test sets (heldout_v1, heldout_v2).

    cd backend
    python -m benchmarks.make_synthetic --spec benchmarks/datasets/dev_synth_v1.spec.json \\
        --workdir /tmp/pharos-dev --out benchmarks/datasets/dev_synth_v1.json
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.codeintel.parsers import parse_file  # noqa: E402
from app.learning.llm import CodexCLI, LLMUnavailable  # noqa: E402
from benchmarks.retrieval_eval import is_noise_path, pinned_clone  # noqa: E402

FUNCTION_KINDS = {"function", "method"}
BATCH = 8  # 20 bodies per call ran past 4 minutes; 5 took about 10 s

INSTRUCTIONS = """You write search questions for a code-retrieval benchmark.
For each numbered function you get its language and body (comments and docs removed).
Write ONE question a developer might ask when looking for this code without knowing its name:
describe what it does or what problem it solves, in plain words, 8 to 20 words.
Never use identifiers from the code (function, variable, type, file names), never quote code,
and never mention the programming language. If a function is too trivial to describe
(a getter, a one-line wrapper), set "skip" to true for it.
Answer for every id you were given and no others."""

SCHEMA = {
    "type": "object",
    "properties": {"items": {"type": "array", "items": {
        "type": "object",
        "properties": {"id": {"type": "string"}, "question": {"type": "string"}, "skip": {"type": "boolean"}},
        "required": ["id", "question", "skip"]}}},
    "required": ["items"],
}

_COMMENT = re.compile(r"^\s*(#|//|/\*|\*|\*/|///|--)")
_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def body_without_docs(lines: list[str], symbol, language: str) -> str:
    body = lines[symbol.start_line - 1:symbol.end_line]
    text = "\n".join(line for line in body if not _COMMENT.match(line))
    if language == "python" and symbol.docstring:
        text = re.sub(r'("""|\'\'\')(.|\n)*?\1', "", text, count=1)
    return text[:1500]


def leaks_identifier(question: str, body: str, name: str) -> bool:
    """True when the question names the function or repeats a compound identifier from the body."""
    q = question.lower()
    if name.lower() in q:
        return True
    compound = {t.lower() for t in _IDENT.findall(body) if len(t) >= 5 and ("_" in t or re.search(r"[a-z][A-Z]", t))}
    return any(t in q for t in compound)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--spec", required=True, help="JSON: {name, repositories: [...], per_repo, seed}")
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    spec = json.loads(Path(args.spec).read_text())
    rng = random.Random(spec.get("seed", 0))
    llm = CodexCLI(effort="low", timeout=240, max_calls=spec.get("max_calls", 60))
    queries, skipped, leaked, failed = [], 0, 0, 0
    for repo in spec["repositories"]:
        root = pinned_clone(repo, Path(args.workdir), by_commit=True)
        candidates = []
        for path in sorted(p for p in root.rglob("*") if p.is_file() and ".git" not in p.parts):
            rel = path.relative_to(root).as_posix()
            if is_noise_path(rel):
                continue
            try:
                source = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            parsed = parse_file(rel, source)
            if parsed is None or parsed.parser == "line-fallback":
                continue
            lines = source.splitlines()
            for sym in parsed.symbols:
                if sym.kind in FUNCTION_KINDS and sym.end_line - sym.start_line >= 4:
                    candidates.append((sym, body_without_docs(lines, sym, parsed.language), parsed.language))
        picked = rng.sample(candidates, min(spec.get("per_repo", 40), len(candidates)))
        print(f"{repo['name']}: {len(candidates)} candidate functions, {len(picked)} sampled", flush=True)
        for start in range(0, len(picked), BATCH):
            batch = picked[start:start + BATCH]
            issued = {f"F{start + i + 1}": item for i, item in enumerate(batch)}
            prompt = "\n\n".join(f"## {fid} ({lang})\n{body}" for fid, (_, body, lang) in issued.items())
            try:
                answer = llm.complete(INSTRUCTIONS, prompt, SCHEMA)
            except LLMUnavailable as exc:
                failed += len(batch)
                print(f"   batch {start // BATCH + 1} dropped: {exc}", flush=True)
                continue
            for item in answer.get("items", []):
                if item.get("id") not in issued:
                    continue
                sym, body, _ = issued.pop(item["id"])
                question = (item.get("question") or "").strip()
                if item.get("skip") or not question:
                    skipped += 1
                elif leaks_identifier(question, body, sym.name):
                    leaked += 1
                else:
                    queries.append({"id": f"{repo['name']}-s{len(queries) + 1:03d}", "repo": repo["name"],
                                    "category": "behavior", "query": question,
                                    "relevant": {sym.qualified_name: 2}})
    out = {"name": spec["name"], "version": 1, "created": spec.get("created"),
           "labeling": ("Synthetic dev set for tuning only. Codex wrote one behaviour question per sampled source "
                        "function from its body with comments and docs removed; the function is the only label "
                        f"(grade 2). Dropped: {skipped} skipped as trivial, {leaked} that named an identifier, "
                        f"{failed} in failed Codex batches. "
                        "Questions follow the body, so they favour body-aware methods; confirm every change on "
                        "the hand-written locked test sets."),
           "repositories": spec["repositories"], "queries": queries,
           "generation": {"model": llm.model or "codex default", "calls": llm.usage.calls,
                          "input_tokens": llm.usage.input_tokens, "output_tokens": llm.usage.output_tokens}}
    Path(args.out).write_text(json.dumps(out, indent=1) + "\n")
    print(f"wrote {len(queries)} questions ({skipped} skipped, {leaked} leaked identifiers) to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
