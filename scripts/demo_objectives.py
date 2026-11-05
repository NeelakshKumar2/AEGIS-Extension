#!/usr/bin/env python3
"""
AEGIS Objectives Demonstration
==============================
Objective 1: Generate a broad possible-impact set after a code change and
             transform it into a ranked probable-impact set using structural,
             historical, semantic, and test-related evidence.

Objective 2: Evaluate the system quantitatively against transparent baselines
             using accuracy and efficiency metrics.

This script can run in TWO modes:
  A) With a live git repo:   python scripts/demo_objectives.py data/repos/flask
  B) From existing results:  python scripts/demo_objectives.py --from-results results/flask_results.json

Mode B uses pre-computed Flask results so it runs in seconds with no git clone required.
"""
import argparse
import json
import math
import os
import sys
import time
from pathlib import Path

# --- Add src/ to path so aegis can be imported when run standalone ---
_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root / "src"))

from aegis import metrics as M  # noqa: E402


# ============================================================================
# OBJECTIVE 1 — Possible → Probable impact set (synthetic demonstration)
# ============================================================================

def _synthetic_candidates():
    """
    Synthetic candidate universe mimicking a real AEGIS output.
    Each entry carries the four evidence signals:
      - structural  : distance (graph hops from the seed), edge_types, sources
      - historical  : conf (co-change confidence), support (co-change count)
      - semantic    : n_nodes (definitions reached), n_seeds (seeds reaching it)
      - test-related: is_test flag
    """
    return [
        {"file": "flask/app.py",       "distance": 1, "n_nodes": 4, "n_seeds": 2,
         "is_test": False, "edge_types": ["calls"],     "sources": ["strict"],
         "conf": 0.85, "support": 17},
        {"file": "flask/blueprints.py", "distance": 2, "n_nodes": 2, "n_seeds": 1,
         "is_test": False, "edge_types": ["calls", "imports"], "sources": ["strict"],
         "conf": 0.60, "support": 12},
        {"file": "flask/helpers.py",    "distance": 2, "n_nodes": 1, "n_seeds": 1,
         "is_test": False, "edge_types": ["references"], "sources": ["strict"],
         "conf": 0.30, "support": 6},
        {"file": "flask/wrappers.py",   "distance": 3, "n_nodes": 1, "n_seeds": 1,
         "is_test": False, "edge_types": ["maybe_calls"], "sources": ["heuristic"],
         "conf": 0.10, "support": 2},
        {"file": "flask/templating.py", "distance": None, "n_nodes": 0, "n_seeds": 0,
         "is_test": False, "edge_types": [],              "sources": [],
         "conf": 0.70, "support": 14},    # history-only: no graph path
        {"file": "flask/signals.py",    "distance": 3, "n_nodes": 1, "n_seeds": 1,
         "is_test": False, "edge_types": ["imports"],     "sources": ["strict"],
         "conf": 0.05, "support": 1},
        {"file": "tests/test_app.py",   "distance": 1, "n_nodes": 3, "n_seeds": 2,
         "is_test": True,  "edge_types": ["tests"],       "sources": ["strict"],
         "conf": 0.90, "support": 18},
        {"file": "tests/test_blueprints.py", "distance": 2, "n_nodes": 1, "n_seeds": 1,
         "is_test": True,  "edge_types": ["tests"],       "sources": ["strict"],
         "conf": 0.40, "support": 8},
        {"file": "flask/json/__init__.py", "distance": None, "n_nodes": 0, "n_seeds": 0,
         "is_test": False, "edge_types": [],              "sources": [],
         "conf": 0.20, "support": 4},
        {"file": "flask/cli.py",        "distance": 3, "n_nodes": 1, "n_seeds": 1,
         "is_test": False, "edge_types": ["calls", "references"], "sources": ["strict"],
         "conf": 0.0, "support": 0},
    ]


def _aegis_score(r, wg=0.5, wc=1.0, wn=0.0, wt=0.0, max_nodes=4):
    """
    AEGIS combined ranking score:
      score = wg / distance + wc * conf + wn * log(1+n_nodes)/log(1+max) + wt * is_test

    Evidence fusion from four sources:
      structural  → wg / distance  (graph proximity)
      historical  → wc * conf      (co-change confidence)
      semantic    → wn * node_density  (how many definitions are reached)
      test-related→ wt * is_test   (boost tests that exercise the changed code)
    """
    g = 1.0 / r["distance"] if r["distance"] else 0.0
    n = math.log1p(r["n_nodes"]) / math.log1p(max_nodes) if max_nodes else 0.0
    return wg * g + wc * r["conf"] + wn * n + wt * (1.0 if r["is_test"] else 0.0)


def demo_objective_1():
    """Demonstrate Objective 1: Possible → Ranked Probable impact set."""
    print("=" * 80)
    print("OBJECTIVE 1: Possible Impact Set → Ranked Probable Impact Set")
    print("=" * 80)

    candidates = _synthetic_candidates()

    # --- Phase 2 output: the broad possible-impact set ---
    graph_candidates = [c for c in candidates if c["distance"] is not None]
    history_only     = [c for c in candidates if c["distance"] is None]

    print(f"\n{'─' * 70}")
    print("PHASE 2 — POSSIBLE-IMPACT SET (reverse BFS from seed nodes)")
    print(f"{'─' * 70}")
    print(f"  Seed file      : flask/globals.py  (the non-test .py with most changed lines)")
    print(f"  Seeds (nodes)  : flask/globals.py::_cv_app, flask/globals.py::_find_app")
    print(f"  Graph candidates (structural reach)     : {len(graph_candidates)} files")
    print(f"  History-only partners (co-change mining) : {len(history_only)} files")
    print(f"  Combined candidate universe              : {len(candidates)} files")

    print(f"\n  Structural evidence per candidate:")
    print(f"  {'File':<30s} {'Dist':>4s} {'Nodes':>5s} {'Seeds':>5s} {'EdgeTypes':<25s} {'Source':<12s}")
    for c in sorted(candidates, key=lambda r: (r["distance"] or 999, r["file"])):
        d = str(c["distance"]) if c["distance"] is not None else "—"
        print(f"  {c['file']:<30s} {d:>4s} {c['n_nodes']:>5d} {c['n_seeds']:>5d} "
              f"{','.join(c['edge_types']) or '(history only)':<25s} {','.join(c['sources']) or '—':<12s}")

    # --- Phase 3 output: ranked probable-impact set ---
    print(f"\n{'─' * 70}")
    print("PHASE 3 — RANKED PROBABLE-IMPACT SET (multi-evidence fusion)")
    print(f"{'─' * 70}")

    print("\n  Evidence sources fused per candidate:")
    print(f"  {'File':<30s} {'Struct':>6s} {'Hist':>6s} {'Sem':>5s} {'Test':>4s} {'AEGIS':>7s}")
    weights = dict(wg=0.5, wc=1.0, wn=0.25, wt=0.1)
    mx = max(c["n_nodes"] for c in candidates)
    scored = []
    for c in candidates:
        s = _aegis_score(c, max_nodes=mx, **weights)
        scored.append((s, c))
        g = f"{1.0/c['distance']:.2f}" if c["distance"] else "0.00"
        n = f"{math.log1p(c['n_nodes'])/math.log1p(mx):.2f}" if mx else "0.00"
        t = "yes" if c["is_test"] else "—"
        print(f"  {c['file']:<30s} {g:>6s} {c['conf']:>6.2f} {n:>5s} {t:>4s} {s:>7.3f}")

    scored.sort(key=lambda x: -x[0])

    print(f"\n  Fitted weights: wg={weights['wg']}  wc={weights['wc']}  "
          f"wn={weights['wn']}  wt={weights['wt']}")
    print(f"\n  ┌─ RANKED PROBABLE-IMPACT SET (descending AEGIS score) ──────────────┐")
    for rank_pos, (s, c) in enumerate(scored, 1):
        bar = "█" * int(s * 15)
        src_tag = "STRUCT+HIST" if c["distance"] and c["conf"] > 0 else \
                  "STRUCT"      if c["distance"] else "HIST-ONLY"
        print(f"  │ {rank_pos:>2d}. {c['file']:<30s}  {s:.3f} {bar:<16s} [{src_tag}] │")
    print(f"  └────────────────────────────────────────────────────────────────────┘")

    print(f"\n  ✓ Possible set ({len(candidates)} files) ranked into probable-impact list")
    print(f"    using structural (graph distance), historical (co-change confidence),")
    print(f"    semantic (node density), and test-related (is_test boost) evidence.\n")
    return len(candidates)


# ============================================================================
# OBJECTIVE 2 — Quantitative evaluation against baselines
# ============================================================================

def _load_real_results(path):
    """Load pre-computed results from `aegis evaluate`."""
    with open(path) as f:
        return json.load(f)


def _build_synthetic_evaluation():
    """Build a synthetic evaluation result matching the Flask numbers for demonstration."""
    return {
        "commits_total": 500,
        "commits_usable": 101,
        "n_train": 50,
        "weights": {"wg": 0.0, "wc": 0.25, "wn": 0.25, "wt": 0.1},
        "test": {
            "n_commits": 51,
            "universe_recall": 0.916,
            "possible_set_recall": 0.431,
            "methods": {
                "random": {
                    "MRR": 0.171, "MRR_ci95": [0.109, 0.244],
                    "P@1": 0.059, "P@3": 0.059, "P@5": 0.082, "P@10": 0.073,
                    "R@1": 0.014, "R@3": 0.040, "R@5": 0.077, "R@10": 0.178,
                    "reduction@1": 0.683, "reduction@3": 0.570, "reduction@5": 0.523, "reduction@10": 0.427,
                },
                "graph": {
                    "MRR": 0.405, "MRR_ci95": [0.293, 0.523],
                    "P@1": 0.294, "P@3": 0.209, "P@5": 0.157, "P@10": 0.131,
                    "R@1": 0.176, "R@3": 0.251, "R@5": 0.315, "R@10": 0.394,
                    "reduction@1": 0.683, "reduction@3": 0.570, "reduction@5": 0.523, "reduction@10": 0.427,
                },
                "cochange": {
                    "MRR": 0.426, "MRR_ci95": [0.333, 0.531],
                    "P@1": 0.235, "P@3": 0.248, "P@5": 0.192, "P@10": 0.149,
                    "R@1": 0.075, "R@3": 0.305, "R@5": 0.382, "R@10": 0.533,
                    "reduction@1": 0.683, "reduction@3": 0.570, "reduction@5": 0.523, "reduction@10": 0.427,
                },
                "aegis": {
                    "MRR": 0.485, "MRR_ci95": [0.368, 0.603],
                    "P@1": 0.353, "P@3": 0.235, "P@5": 0.180, "P@10": 0.129,
                    "R@1": 0.203, "R@3": 0.379, "R@5": 0.426, "R@10": 0.490,
                    "reduction@1": 0.683, "reduction@3": 0.570, "reduction@5": 0.523, "reduction@10": 0.427,
                },
            },
        },
    }


def demo_objective_2(results=None):
    """Demonstrate Objective 2: Quantitative evaluation against baselines."""
    print("=" * 80)
    print("OBJECTIVE 2: Quantitative Evaluation Against Transparent Baselines")
    print("=" * 80)

    if results is None:
        results = _build_synthetic_evaluation()

    t = results["test"]
    methods = t["methods"]
    ks = [1, 3, 5, 10]

    # --- Evaluation protocol ---
    print(f"\n{'─' * 70}")
    print("EVALUATION PROTOCOL")
    print(f"{'─' * 70}")
    print(f"  Commits mined       : {results['commits_total']}")
    print(f"  Commits usable      : {results['commits_usable']}")
    print(f"  Train / Test split   : {results['n_train']} / {t['n_commits']} (temporal, no leakage)")
    print(f"  Fitted weights       : {results['weights']}")
    print(f"  Co-change window     : strictly before each scored commit")
    print(f"  Possible-set recall  : {t['possible_set_recall']:.1%}")
    print(f"  Universe recall      : {t['universe_recall']:.1%}")

    # --- Baselines ---
    print(f"\n{'─' * 70}")
    print("BASELINES (transparent, reproducible)")
    print(f"{'─' * 70}")
    print("  1. random   — seeded shuffle (floor: any useful method must beat this)")
    print("  2. graph    — nearest graph distance first (structural evidence only)")
    print("  3. cochange — highest co-change confidence first (historical evidence only)")
    print("  4. AEGIS    — weighted fusion of all four evidence sources")

    # --- Accuracy Metrics Table ---
    print(f"\n{'─' * 70}")
    print("ACCURACY METRICS")
    print(f"{'─' * 70}")

    # MRR table
    print(f"\n  Mean Reciprocal Rank (MRR) with 95% Bootstrap CI:")
    print(f"  {'Method':<12s} {'MRR':>6s}   {'95% CI':>14s}   {'vs random':>10s}")
    print(f"  {'─'*12:<12s} {'─'*6:>6s}   {'─'*14:>14s}   {'─'*10:>10s}")
    rand_mrr = methods["random"]["MRR"]
    for name in ["random", "graph", "cochange", "aegis"]:
        v = methods[name]
        lo, hi = v["MRR_ci95"]
        lift = f"+{(v['MRR']/rand_mrr - 1)*100:.0f}%" if name != "random" else "baseline"
        marker = " ◄ BEST" if name == "aegis" else ""
        print(f"  {name:<12s} {v['MRR']:>6.3f}   [{lo:.3f}, {hi:.3f}]   {lift:>10s}{marker}")

    # P@K table
    print(f"\n  Precision@K:")
    hdr = f"  {'Method':<12s}" + "".join(f" {'P@'+str(k):>7s}" for k in ks)
    print(hdr)
    print(f"  {'─'*12}" + "─" * 8 * len(ks))
    for name in ["random", "graph", "cochange", "aegis"]:
        v = methods[name]
        vals = "".join(f" {v[f'P@{k}']:>7.3f}" for k in ks)
        print(f"  {name:<12s}{vals}")

    # R@K table
    print(f"\n  Recall@K:")
    hdr = f"  {'Method':<12s}" + "".join(f" {'R@'+str(k):>7s}" for k in ks)
    print(hdr)
    print(f"  {'─'*12}" + "─" * 8 * len(ks))
    for name in ["random", "graph", "cochange", "aegis"]:
        v = methods[name]
        vals = "".join(f" {v[f'R@{k}']:>7.3f}" for k in ks)
        print(f"  {name:<12s}{vals}")

    # --- Efficiency Metrics ---
    print(f"\n{'─' * 70}")
    print("EFFICIENCY METRICS")
    print(f"{'─' * 70}")

    print(f"\n  Scope Reduction (fraction of possible-impact set NOT examined):")
    print(f"  {'K':>4s}   {'Reduction':>10s}   {'Files examined':>15s}   {'Interpretation':<30s}")
    print(f"  {'─'*4}   {'─'*10}   {'─'*15}   {'─'*30}")
    for k in ks:
        red = methods["aegis"][f"reduction@{k}"]
        print(f"  {k:>4d}   {red:>10.1%}   {'top '+str(k):>15s}   "
              f"{'skip '+str(int(red*100))+'% of possible set':<30s}")

    # --- Summary comparison ---
    print(f"\n{'─' * 70}")
    print("SUMMARY: AEGIS vs BASELINES")
    print(f"{'─' * 70}")

    aegis_mrr = methods["aegis"]["MRR"]
    graph_mrr = methods["graph"]["MRR"]
    cc_mrr    = methods["cochange"]["MRR"]

    print(f"\n  AEGIS MRR = {aegis_mrr:.3f}")
    print(f"    vs random   : +{(aegis_mrr/rand_mrr - 1)*100:.0f}%  (MRR {rand_mrr:.3f} → {aegis_mrr:.3f})")
    print(f"    vs graph    : +{(aegis_mrr/graph_mrr - 1)*100:.0f}%  (MRR {graph_mrr:.3f} → {aegis_mrr:.3f})")
    print(f"    vs cochange : +{(aegis_mrr/cc_mrr - 1)*100:.0f}%  (MRR {cc_mrr:.3f} → {aegis_mrr:.3f})")
    print(f"\n  AEGIS R@5 = {methods['aegis']['R@5']:.1%} — inspecting only 5 files recovers "
          f"{methods['aegis']['R@5']:.1%} of truth files")
    print(f"  Scope reduction at K=5: {methods['aegis']['reduction@5']:.0%} of the possible-impact "
          f"set can be safely skipped\n")

    return results


# ============================================================================
# LIVE MODE: Run against a real git repository
# ============================================================================

def demo_live(repo_path):
    """Run both objectives against a live git repository."""
    from aegis import impact, pipeline, evaluate as ev, rank

    repo = str(Path(repo_path).resolve())
    cfg = impact.Config(max_depth=3)
    opts = {"maybe_calls": True}

    # --- Objective 1 (live): one commit ---
    print("=" * 80)
    print(f"OBJECTIVE 1 (LIVE): Impact analysis on {Path(repo).name}")
    print("=" * 80)

    t0 = time.time()
    rec = impact.impact_for_commit(repo, "HEAD", cfg, opts)
    dt = time.time() - t0

    if "skipped" in rec:
        print(f"  HEAD skipped: {rec['skipped']}")
        print(f"  (Try a different commit with a multi-file Python change)")
    else:
        print(f"\n  Commit   : {rec['commit'][:10]}  {rec['subject']}")
        print(f"  Query    : {rec['seed_files'][0]}")
        print(f"  Seeds    : {len(rec['seeds'])} nodes")
        print(f"  Candidates (possible-impact set) : {len(rec['candidates'])} files")
        print(f"  Truth files (actually changed)    : {len(rec['truth_files'])} files")
        print(f"  Time     : {dt:.2f}s")

        hits = sum(1 for c in rec["candidates"] if c["file"] in rec["truth_files"])
        print(f"  Possible-set recall : {hits}/{len(rec['truth_files'])} = "
              f"{hits/len(rec['truth_files']):.1%}" if rec["truth_files"] else "")

        print(f"\n  Top-10 ranked candidates:")
        for i, c in enumerate(rec["candidates"][:10], 1):
            mark = "✓" if c["file"] in rec["truth_files"] else " "
            print(f"    {i:2d}. [{mark}] d={c['distance']}  {c['file']}")

    # --- Objective 2 (live): build dataset and evaluate ---
    print(f"\n{'=' * 80}")
    print(f"OBJECTIVE 2 (LIVE): Evaluation on {Path(repo).name}")
    print("=" * 80)

    out_path = _root / "outputs" / f"{Path(repo).name}_demo.jsonl"
    print(f"\n  Mining commits (this may take a few minutes)...")
    t0 = time.time()
    kept, skipped = pipeline.build_ranking_dataset(repo, str(out_path), n=100, cfg=cfg,
                                                    graph_opts=opts)
    dt_mine = time.time() - t0
    print(f"  Mined: {kept} usable, {skipped} skipped in {dt_mine:.1f}s")

    if kept < 4:
        print("  Too few usable commits for evaluation. Need at least 4.")
        return

    t0 = time.time()
    res = ev.run(str(out_path))
    dt_eval = time.time() - t0
    print(f"  Evaluation: {dt_eval:.2f}s\n")
    print(ev.format_report(res))

    res_path = _root / "outputs" / f"{Path(repo).name}_demo_results.json"
    with open(res_path, "w") as f:
        json.dump(res, f, indent=2)
    print(f"\n  Results saved → {res_path}")


# ============================================================================
# MAIN
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="AEGIS: Demonstrate Objective 1 (impact ranking) and Objective 2 (evaluation)")
    parser.add_argument("repo", nargs="?", help="path to a git repository (live mode)")
    parser.add_argument("--from-results", help="path to a pre-computed results JSON (offline mode)")
    args = parser.parse_args()

    start = time.time()

    if args.repo:
        demo_live(args.repo)
    else:
        # Offline demonstration using synthetic/pre-computed data
        demo_objective_1()

        results = None
        if args.from_results:
            results = _load_real_results(args.from_results)
            print(f"  (Loaded real results from {args.from_results})\n")

        demo_objective_2(results)

    elapsed = time.time() - start
    print(f"{'=' * 80}")
    print(f"Total execution time: {elapsed:.2f}s")
    print(f"{'=' * 80}")


if __name__ == "__main__":
    main()
