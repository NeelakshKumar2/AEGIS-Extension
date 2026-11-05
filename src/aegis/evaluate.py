"""Phase 4: temporal split, weight fitting, metrics for AEGIS and the baselines."""
import itertools
import json

from . import metrics as M
from . import rank

KS = (1, 3, 5, 10)
GRID = {"wg": (0.0, 0.25, 0.5, 1.0), "wc": (0.0, 0.25, 0.5, 1.0), "wn": (0.0, 0.25), "wt": (0.0, 0.1)}


def load(path):
    recs = [json.loads(l) for l in open(path, encoding="utf-8")]
    kept = [r for r in recs if "skipped" not in r]
    return sorted(kept, key=lambda r: r["time"]), len(recs)


def split(records, train_frac=0.5):
    cut = int(len(records) * train_frac)
    return records[:cut], records[cut:]


def _rank(method, rec, weights):
    fn = rank.METHODS[method]
    return fn(rec["candidates"], weights=weights, seed=rec["commit"])


def fit_weights(train):
    """Grid search on MRR over the earlier commits only. Ties prefer the simpler (smaller) weights."""
    best, best_key = rank.Weights(), None
    for wg, wc, wn, wt in itertools.product(*GRID.values()):
        if wg == 0 and wc == 0:
            continue
        w = rank.Weights(wg, wc, wn, wt)
        mrr = M.mean(M.reciprocal_rank(_rank("aegis", r, w), set(r["truth_files"])) for r in train)
        key = (round(mrr, 6), -(wn + wt))
        if best_key is None or key > best_key:
            best, best_key = w, key
    return best


def evaluate(records, weights, ks=KS):
    out = {}
    for method in rank.METHODS:
        rrs, per_k = [], {k: ([], [], []) for k in ks}
        for r in records:
            truth = set(r["truth_files"])
            ranked = _rank(method, r, weights)
            rrs.append(M.reciprocal_rank(ranked, truth))
            for k in ks:
                p, rc, red = per_k[k]
                p.append(M.precision_at_k(ranked, truth, k))
                rc.append(M.recall_at_k(ranked, truth, k))
                red.append(M.scope_reduction(r["graph_size"], k))
        out[method] = {
            "MRR": M.mean(rrs), "MRR_ci95": M.bootstrap_ci(rrs),
            **{f"P@{k}": M.mean(per_k[k][0]) for k in ks},
            **{f"R@{k}": M.mean(per_k[k][1]) for k in ks},
            **{f"reduction@{k}": M.mean(per_k[k][2]) for k in ks}}
    cover = M.mean(len({c["file"] for c in r["candidates"]} & set(r["truth_files"])) / len(r["truth_files"])
                   for r in records)
    graph_cover = M.mean(len({c["file"] for c in r["candidates"] if c["distance"] is not None}
                             & set(r["truth_files"])) / len(r["truth_files"]) for r in records)
    return {"n_commits": len(records), "universe_recall": cover,
            "possible_set_recall": graph_cover, "methods": out}


def run(dataset_path, train_frac=0.5):
    recs, total = load(dataset_path)
    train, test = split(recs, train_frac)
    if not train or not test:
        raise SystemExit(f"only {len(recs)} usable commits of {total}; mine more commits (--n)")
    w = fit_weights(train)
    return {"commits_total": total, "commits_usable": len(recs), "n_train": len(train),
            "weights": w.as_dict(), "test": evaluate(test, w)}


def format_report(res, ks=KS):
    t = res["test"]
    lines = [f"commits: {res['commits_total']} mined, {res['commits_usable']} usable "
             f"({res['n_train']} train / {t['n_commits']} test, split by time)",
             f"fitted weights: {res['weights']}",
             f"truth files inside the graph's possible-impact set: {t['possible_set_recall']:.1%}; "
             f"inside graph + history universe: {t['universe_recall']:.1%}", "",
             "| method | MRR (95% CI) | " + " | ".join(f"P@{k}" for k in ks) + " | "
             + " | ".join(f"R@{k}" for k in ks) + " |",
             "|---|---|" + "---|" * (2 * len(ks))]
    for m, v in t["methods"].items():
        lo, hi = v["MRR_ci95"]
        lines.append(f"| {m} | {v['MRR']:.3f} ({lo:.2f}-{hi:.2f}) | "
                     + " | ".join(f"{v[f'P@{k}']:.3f}" for k in ks) + " | "
                     + " | ".join(f"{v[f'R@{k}']:.3f}" for k in ks) + " |")
    lines += ["", "scope reduction vs possible-impact set (keep top K): "
              + ", ".join(f"K={k}: {t['methods']['aegis'][f'reduction@{k}']:.0%}" for k in ks)]
    return "\n".join(lines)
