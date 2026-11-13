"""Precision of active checkable rules: the Phase 3 protocol's measure 2, with no LLM.

Implements "Precision" in docs/benchmarks/phase3-eval-protocol.md. For each repository, rules are
learned at a commit exactly as the learning pipeline learns them (the miners, then the activation
backtest on the ``--window`` first-parent commits before that commit), and every checkable rule is then
checked on the next ``--n`` first-parent commits after it. Precision is the share of (active rule, commit)
pairs where the rule applies and the commit satisfies it, pooled over repositories.

The table shows, per repository, the Phase 2 activation rule (``eligible``, "before") next to the
hold-out rule ("after"). The JSON written to ``--out`` keeps every checkable rule with its activation
record and its protocol-window result, so other thresholds can be scored afterwards (``--curve``)::

    python benchmarks/rule_precision.py --mirrors ~/.cache/pharos/git \\
        --repo pallets_click --repo spf13_cobra@<commit> --back 200 --out /tmp/precision.json

Without ``@commit`` a repository is learned ``--back`` first-parent commits before its mirror's HEAD.
Repositories of the locked c-CRAB test set are refused unless ``--test-set`` is given (the final run).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.learning.backtest import first_parent, pooled, protocol_precision  # noqa: E402
from app.learning.checks import DEFAULT_ACTIVATION, REQUIREMENT, Activation, decide  # noqa: E402

SEALED = BACKEND / "benchmarks" / "datasets" / "ccrab_phase3.json"


def sealed_mirrors() -> set[str]:
    data = json.loads(SEALED.read_text())
    return {name.replace("/", "_").lower() for name in data.get("test", {})}


def rescore(rules: list[dict], activation: Activation) -> list[dict]:
    """The rules a different activation rule would serve as requirements (from the stored records)."""
    out = []
    for r in rules:
        record = None if r["inner"] is None else {"check": "same", **r["inner"]}
        d = decide("same", record, activation)
        if d.status == "active" and d.strength == REQUIREMENT:
            out.append(r)
    return out


def table(results: dict) -> str:
    head = (f"{'repository':22} {'commit':10} {'later':>5} {'checkable':>9} | {'before: active':>14} "
            f"{'precision':>9} | {'after: active':>13} {'precision':>9} {'pairs':>6} | {'obs':>4}")
    lines = [head, "-" * len(head)]

    def fmt(p):
        return "-" if p is None else f"{100 * p:.1f}%"

    for name, r in results.items():
        lines.append(f"{name[:22]:22} {r['commit'][:10]:10} {r['later_commits']:>5} {r['checkable']:>9} | "
                     f"{r['before']['active']:>14} {fmt(r['before']['precision']):>9} | "
                     f"{r['after']['active']:>13} {fmt(r['after']['precision']):>9} {r['after']['applied']:>6} | "
                     f"{r['observations']['rules']:>4}")
    before = pooled(x for r in results.values() for x in r["rules"] if x["eligible"])
    after = pooled(x for r in results.values() for x in r["rules"]
                   if x["status"] == "active" and x["strength"] == REQUIREMENT)
    lines.append("-" * len(head))
    lines.append(f"{'pooled':22} {'':10} {'':>5} {sum(r['checkable'] for r in results.values()):>9} | "
                 f"{before['rules']:>14} {fmt(before['precision']):>9} | {after['rules']:>13} "
                 f"{fmt(after['precision']):>9} {after['applied']:>6} |")
    return "\n".join(lines)


def curve(results: dict, grid_applied: list[int], grid_lower: list[float]) -> list[dict]:
    rows = []
    for k in grid_applied:
        for lb in grid_lower:
            act = Activation(window=DEFAULT_ACTIVATION.window, min_applied=k, min_lower=lb)
            chosen = [x for r in results.values() for x in rescore(r["rules"], act)]
            p = pooled(chosen)
            rows.append({"min_applied": k, "min_lower": lb, "rules": p["rules"], "applied_pairs": p["applied"],
                         "precision": p["precision"],
                         "repos_with_rules": sum(bool(rescore(r["rules"], act)) for r in results.values())})
    return rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mirrors", required=True, help="directory of full git mirrors")
    ap.add_argument("--repo", action="append", required=True, help="mirror name, optionally @commit")
    ap.add_argument("--back", type=int, default=200,
                    help="without @commit: learn this many first-parent commits before the mirror's HEAD")
    ap.add_argument("--n", type=int, default=200, help="first-parent commits checked after the learned commit")
    ap.add_argument("--window", type=int, default=DEFAULT_ACTIVATION.window, help="activation hold-out commits")
    ap.add_argument("--min-applied", type=int, default=DEFAULT_ACTIVATION.min_applied)
    ap.add_argument("--min-lower", type=float, default=DEFAULT_ACTIVATION.min_lower)
    ap.add_argument("--observe-lower", type=float, default=DEFAULT_ACTIVATION.observe_lower)
    ap.add_argument("--out", help="write every rule's records here (JSON)")
    ap.add_argument("--curve", action="store_true", help="also print precision against active rules for a grid")
    ap.add_argument("--test-set", action="store_true", help="allow repositories of the locked c-CRAB test set")
    args = ap.parse_args(argv)

    activation = Activation(window=args.window, min_applied=args.min_applied, min_lower=args.min_lower,
                            observe_lower=args.observe_lower)
    sealed = sealed_mirrors()
    out_path = Path(args.out) if args.out else None
    results = json.loads(out_path.read_text()).get("repositories", {}) if out_path and out_path.exists() else {}
    for spec in args.repo:
        name, _, commit = spec.partition("@")
        if name.lower() in sealed and not args.test_set:
            raise SystemExit(f"{name} is in the locked c-CRAB test set; refusing without --test-set")
        mirror = Path(args.mirrors).expanduser() / name
        if not commit:
            chain = first_parent(mirror, "HEAD", args.back + 1)
            if len(chain) <= args.back:
                print(f"{name}: fewer than {args.back + 1} first-parent commits, skipped", file=sys.stderr)
                continue
            commit = chain[args.back]
        key = f"{name}@{commit[:12]}"
        if key in results and results[key].get("activation") == vars(activation):
            continue
        print(f"{name}: learning at {commit[:12]}", file=sys.stderr, flush=True)
        r = protocol_precision(mirror, commit, n=args.n, activation=activation,
                               progress=lambda m, name=name: print(f"  {name} {m}", file=sys.stderr, flush=True))
        results[key] = r | {"repository": name, "activation": vars(activation)}
        if out_path:
            out_path.write_text(json.dumps({"activation": vars(activation), "repositories": results}, indent=1))
    print(table(results))
    if args.curve:
        rows = curve(results, [3, 5, 10, 15, 20, 30], [0.0, 0.3, 0.5, 0.6, 0.7, 0.75, 0.8, 0.85, 0.9])
        print("\nmin_applied min_lower  rules  pairs  precision  repos")
        for row in rows:
            p = "-" if row["precision"] is None else f"{100 * row['precision']:.1f}%"
            print(f"{row['min_applied']:>11} {row['min_lower']:>9} {row['rules']:>6} {row['applied_pairs']:>6} "
                  f"{p:>10} {row['repos_with_rules']:>6}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
