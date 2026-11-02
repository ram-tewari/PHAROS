"""Reproduce the partial v2 numbers from the stopped run's checkpoint.

The locked v2 run was stopped before its judge, grading and audit steps, so
``phase2_eval.py`` never wrote a report. This reads the same checkpoint, applies
the same utility analysis, and adds the checks the partial data needs. It makes
no Codex calls.

    python benchmarks/phase2_v2_partial.py
"""

import json
from math import comb
from pathlib import Path

from benchmarks.phase2_eval import _utility_report, paired_delta

HERE = Path(__file__).parent
RESULT = HERE / "results" / "phase2_v2_2026-11-01.json"
DATASET = HERE / "datasets" / "utility_v2.json"
REPOS = ("attrs", "rich", "echo", "libuv")


def fisher(a_ok: int, a_total: int, b_ok: int, b_total: int) -> float:
    """Two-sided Fisher exact p for a 2×2 table."""
    ok, total = a_ok + b_ok, a_total + b_total

    def prob(k: int) -> float:
        return comb(a_total, k) * comb(b_total, ok - k) / comb(total, ok)

    seen = prob(a_ok)
    ks = range(max(0, ok - b_total), min(a_total, ok) + 1)
    return sum(prob(k) for k in ks if prob(k) <= seen * (1 + 1e-9))


def main() -> None:
    data = json.loads(RESULT.read_text())
    tasks = json.loads(DATASET.read_text())["tasks"]
    utility = data["utility"]
    scored = [t for t in tasks if "B" in utility.get(t["id"], {})]

    def recall(rows: list[dict], arm: str) -> list[float]:
        return [utility[t["id"]][arm]["scores"]["companion_recall"] for t in rows]

    for arm in ("B", "C"):
        rows = [t for t in scored if arm in utility[t["id"]]]
        print(arm, json.dumps(_utility_report(data, rows, arm)))

    naming = _utility_report(data, scored, "B")["naming_adherence"]
    print("naming Fisher p", round(fisher(naming["A"]["ok"], naming["A"]["total"],
                                          naming["B"]["ok"], naming["B"]["total"]), 4))

    for repo in REPOS:
        rows = [t for t in scored if t["repo"] == repo]
        print(repo, len(rows), round(sum(recall(rows, "A")) / len(rows), 3),
              round(sum(recall(rows, "B")) / len(rows), 3), paired_delta(recall(rows, "B"), recall(rows, "A")))
        rest = [t for t in scored if t["repo"] != repo]
        print("  without it", len(rest), paired_delta(recall(rest, "B"), recall(rest, "A")))

    missing = 80 - len(scored)
    for change in (0.0, -0.083, -0.25, -0.5):
        filled = paired_delta(recall(scored, "B") + [1.0 + change] * missing, recall(scored, "A") + [1.0] * missing)
        print(f"if the {missing} missing tasks each changed by {change}:", filled)


if __name__ == "__main__":
    main()
