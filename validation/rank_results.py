#!/usr/bin/env python3
"""Build the §3 ranking evaluation table over 7 real repositories.

Usage:
    python validation/rank_results.py --repo-root /tmp/vrepos
"""
import argparse
import itertools
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "src"))

from aegis import evaluate as ev, impact, metrics as M, pipeline, rank  # noqa: E402

REPOS = ["requests", "click", "flask", "jinja2", "markdown", "werkzeug", "networkx"]
KS = (1, 3, 5)

# Ablation configs: fixed weight combos the paper compares
ABLATIONS = [
    ("structural",       rank.Weights(wg=1.0, wc=0.0, wn=0.0,  wt=0.0)),
    ("+history",         rank.Weights(wg=1.0, wc=1.0, wn=0.0,  wt=0.0)),
    ("+test",            rank.Weights(wg=1.0, wc=1.0, wn=0.0,  wt=0.1)),
    ("+n_nodes",         rank.Weights(wg=1.0, wc=1.0, wn=0.25, wt=0.1)),
]


def _run_ablation(records, label, weights, ks=KS):
    """Rank test records with one fixed weight config and return metrics dict."""
    rrs, per_k = [], {k: ([], []) for k in ks}
    for r in records:
        truth = set(r["truth_files"])
        ranked = rank.rank_aegis(r["candidates"], weights=weights)
        rrs.append(M.reciprocal_rank(ranked, truth))
        for k in ks:
            p, rc = per_k[k]
            p.append(M.precision_at_k(ranked, truth, k))
            rc.append(M.recall_at_k(ranked, truth, k))
    return {"label": label, "MRR": M.mean(rrs), "MRR_ci95": M.bootstrap_ci(rrs),
            **{f"P@{k}": M.mean(per_k[k][0]) for k in ks},
            **{f"R@{k}": M.mean(per_k[k][1]) for k in ks}}


def run_repo(repo_root, name, out_dir, n_commits=300):
    repo = repo_root / name
    if not repo.is_dir():
        return None, f"not found: {repo}"
    jsonl = out_dir / name / "ranking.jsonl"
    jsonl.parent.mkdir(parents=True, exist_ok=True)

    def prog(i, total, kept):
        if i % 50 == 0 or i == total:
            print(f"  [{name}] {i}/{total} commits, {kept} usable", flush=True)

    try:
        kept, skipped = pipeline.build_ranking_dataset(
            repo, jsonl, n=n_commits, progress=prog)
    except Exception as e:
        return None, f"pipeline error: {e}"

    if kept < 2:
        return None, f"only {kept} usable commits (need ≥2)"

    res = ev.run(jsonl, train_frac=0.5)
    # Test records for ablation
    recs, _ = ev.load(jsonl)
    _, test = ev.split(recs, 0.5)
    weights = rank.Weights(**res["weights"])

    # Ablation table
    ablation = [_run_ablation(test, lab, w) for lab, w in ABLATIONS]
    ablation.append(_run_ablation(test, "fitted", weights))

    # Scope reduction@5 for aegis
    red5_vals = [M.scope_reduction(r["graph_size"], 5) for r in test]
    res["reduction@5"] = M.mean(red5_vals)

    return {"name": name, "res": res, "ablation": ablation}, None


def fmt_table(repos_data):
    """Produce the full markdown for rank_results.md."""
    lines = ["# §3 Ranking evaluation results", "",
             "Repositories evaluated with `pipeline.build_ranking_dataset` (n≤300 commits, "
             "oldest→newest), temporal 50/50 train/test split, weights fitted on train via "
             "`evaluate.fit_weights`. Metrics computed on the held-out test split.", ""]

    h2_passes = []

    for rd in repos_data:
        name = rd["name"]
        res = rd["res"]
        t = res["test"]
        lines += [f"## {name}", "",
                  f"Commits: {res['commits_total']} mined, {res['commits_usable']} usable "
                  f"({res['n_train']} train / {t['n_commits']} test). "
                  f"Fitted weights: {res['weights']}. "
                  f"Possible-set recall: {t['possible_set_recall']:.1%}. "
                  f"Universe recall: {t['universe_recall']:.1%}.", ""]

        # Main baselines table
        lines += ["### Baselines", "",
                  "| method | MRR (95% CI) | P@1 | P@3 | P@5 | R@1 | R@3 | R@5 | reduction@5 |",
                  "|---|---|---|---|---|---|---|---|---|"]
        for m in ("random", "graph", "cochange", "aegis"):
            v = t["methods"][m]
            lo, hi = v["MRR_ci95"]
            red5 = v.get("reduction@5", res.get("reduction@5", 0))
            lines.append(f"| {m} | {v['MRR']:.3f} ({lo:.2f}–{hi:.2f}) | "
                        f"{v['P@1']:.3f} | {v['P@3']:.3f} | {v['P@5']:.3f} | "
                        f"{v['R@1']:.3f} | {v['R@3']:.3f} | {v['R@5']:.3f} | "
                        f"{red5:.0%} |")

        # Ablation table
        lines += ["", "### Ablation (fixed weight configs on test split)", "",
                  "| config | MRR (95% CI) | P@1 | P@3 | P@5 | R@1 | R@3 | R@5 |",
                  "|---|---|---|---|---|---|---|---|"]
        for ab in rd["ablation"]:
            lo, hi = ab["MRR_ci95"]
            lines.append(f"| {ab['label']} | {ab['MRR']:.3f} ({lo:.2f}–{hi:.2f}) | "
                        f"{ab['P@1']:.3f} | {ab['P@3']:.3f} | {ab['P@5']:.3f} | "
                        f"{ab['R@1']:.3f} | {ab['R@3']:.3f} | {ab['R@5']:.3f} |")

        # H2 check
        aegis = t["methods"]["aegis"]
        graph = t["methods"]["graph"]
        h2 = aegis["MRR"] > graph["MRR"] and aegis["R@5"] >= graph["R@5"]
        h2_passes.append(h2)
        verdict = "**PASS**" if h2 else "FAIL"
        lines += ["", f"**H2**: aegis MRR={aegis['MRR']:.3f} vs graph MRR={graph['MRR']:.3f}, "
                  f"aegis R@5={aegis['R@5']:.3f} vs graph R@5={graph['R@5']:.3f} → {verdict}", ""]

    # Summary
    n_pass = sum(h2_passes)
    n_total = len(h2_passes)
    overall = "**SUPPORTED**" if n_pass >= 2 else "NOT SUPPORTED"
    lines += ["---", "", "## Summary", "",
              f"H2 passes on {n_pass}/{n_total} repositories. "
              f"Requirement: ≥2. Verdict: {overall}.", ""]

    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="Build §3 ranking evaluation across 7 repos")
    ap.add_argument("--repo-root", default="/tmp/vrepos", help="directory containing the 7 repos")
    ap.add_argument("--out", default=str(HERE.parent / "outputs" / "ranking"), help="output dir for jsonl files")
    ap.add_argument("--n", type=int, default=300, help="commits to mine per repo")
    a = ap.parse_args()

    repo_root = Path(a.repo_root)
    out_dir = Path(a.out)
    results = []

    for name in REPOS:
        print(f"\n{'='*60}")
        print(f"  {name}")
        print(f"{'='*60}")
        rd, err = run_repo(repo_root, name, out_dir, a.n)
        if err:
            print(f"  SKIPPED: {err}")
        else:
            results.append(rd)
            print(f"  MRR(aegis)={rd['res']['test']['methods']['aegis']['MRR']:.3f}  "
                  f"MRR(graph)={rd['res']['test']['methods']['graph']['MRR']:.3f}")

    if not results:
        print("\nNo repos evaluated successfully. Exiting.")
        return 1

    md = fmt_table(results)
    md_path = HERE / "rank_results.md"
    md_path.write_text(md + "\n")
    print(f"\n{'='*60}")
    print(md)
    print(f"\nWritten → {md_path}")

    # Also dump raw JSON
    json_path = HERE / "rank_results.json"
    raw = {}
    for rd in results:
        raw[rd["name"]] = {
            "res": rd["res"],
            "ablation": rd["ablation"],
        }
    json_path.write_text(json.dumps(raw, indent=1, default=str))
    print(f"Written → {json_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
