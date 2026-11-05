"""Command line interface:  python -m aegis <command> ..."""
import argparse
import csv
import json
import random
import sys
from pathlib import Path

from . import doctor, evaluate as ev, export, graph as g, impact, pipeline, rank
from .oracle import evaluate, run_workload
from .parser import build_graph
from .validate import check_invariants, graph_digest


def _load(arg, maybe=True):
    p = Path(arg)
    if p.is_dir() and (p / "graph.json").exists():
        return g.load_graph(p / "graph.json")
    if p.is_file() and p.suffix == ".json":
        return g.load_graph(p)
    if p.is_dir():
        return build_graph(p, maybe_calls=maybe)
    raise SystemExit(f"not a repo directory or graph.json: {arg}")


def cmd_build(a):
    repo = Path(a.repo)
    G = build_graph(repo, maybe_calls=not a.no_maybe)
    problems = check_invariants(G)
    out = export.write_all(G, Path(a.out) / (a.name or repo.resolve().name))
    s = g.summary(G)
    print(json.dumps({k: s[k] for k in ("nodes", "edges", "files_parsed", "calls_total",
                                        "calls_resolved_pct", "calls_external_pct",
                                        "calls_unresolved_pct", "parse_errors") if k in s}, indent=1))
    print(f"digest {graph_digest(G)[:16]}   invariant problems: {len(problems)}")
    print(f"written -> {out}")
    return 1 if problems else 0


def cmd_check(a):
    G = _load(a.target)
    problems = check_invariants(G)
    for p in problems[:50]:
        print("PROBLEM:", p)
    print(f"{G.number_of_nodes()} nodes, {G.number_of_edges()} edges, {len(problems)} problems")
    return 1 if problems else 0


def cmd_stats(a):
    print(json.dumps(g.summary(_load(a.target)), indent=2, sort_keys=True))


def cmd_find(a):
    G = _load(a.target)
    pat = a.pattern.lower()
    for n in sorted(G.nodes):
        if pat in n.lower():
            print(f"{G.nodes[n]['type']:9s} {n}")


def _neigh(a, direction):
    G = _load(a.target)
    types = a.types.split(",")
    if a.node not in G:
        raise SystemExit(f"unknown node {a.node}; try `find`")
    seen, frontier = {a.node}, [a.node]
    for depth in range(1, a.depth + 1):
        nxt = []
        for n in frontier:
            for m in g.neighbors(G, n, types, direction):
                if m not in seen:
                    seen.add(m)
                    nxt.append(m)
                    print(f"{'  ' * (depth - 1)}{m}  [{G.nodes[m]['type']}]")
        frontier = nxt


def cmd_callers(a):
    _neigh(a, "in")


def cmd_callees(a):
    _neigh(a, "out")


def cmd_at(a):
    G = _load(a.target)
    path, _, line = a.location.rpartition(":")
    print(g.LineIndex(G).at(path, int(line)))


def cmd_audit(a):
    """Write a random sample of edges with their source line, for hand verification."""
    G = _load(a.target)
    repo = Path(a.repo)
    rng = random.Random(a.seed)
    edges = sorted((u, v, k) for u, v, k in G.edges(keys=True) if k == a.type)
    sample = rng.sample(edges, min(a.n, len(edges)))
    with open(a.out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["type", "source", "target", "line", "source_line", "verdict(y/n)"])
        for u, v, k in sample:
            path = G.nodes[u]["path"] if G.nodes[u]["type"] != "file" else u
            lines = G[u][v][k]["lines"]
            line = lines[0] if lines else ""
            text = ""
            if line:
                try:
                    text = (repo / path).read_text(errors="replace").split("\n")[line - 1].strip()
                except OSError:
                    pass
            w.writerow([k, u, v, line, text, ""])
    print(f"{len(sample)} edges -> {a.out}  (fill the last column with y/n, precision = y / total)")


def cmd_oracle(a):
    G = build_graph(a.repo, keep_call_log=True)
    ev = evaluate(G, run_workload(a.repo, a.script), top_missing=a.examples)
    print(json.dumps(ev, indent=2, default=str))


# ---------------------------------------------------------------- Phases 2-4
def _cfg(a):
    return impact.Config(max_depth=a.depth, max_files=a.max_files,
                         sources=(impact.STRICT,) if a.no_maybe else None)


def _opts(a):
    return {"maybe_calls": not a.no_maybe}


def cmd_impact(a):
    rec = impact.impact_for_commit(a.repo, a.commit, _cfg(a), _opts(a))
    if "skipped" in rec:
        raise SystemExit(f"skipped: {rec['skipped']}")
    print(f"commit {rec['commit'][:10]}  {rec['subject']}")
    print(f"query file: {rec['seed_files'][0]}   seeds ({len(rec['seeds'])}): " + ", ".join(rec["seeds"][:6]))
    print(f"truth (other files changed in the commit): {rec['truth_files']}")
    print(f"possible-impact files ({len(rec['candidates'])}); * = actually changed:")
    for c in rec["candidates"][:a.top]:
        mark = "*" if c["file"] in rec["truth_files"] else " "
        print(f" {mark} d={c['distance']}  {c['file']}   via {'>'.join(c['edge_types'])} [{','.join(c['sources'])}]")


def cmd_rankdata(a):
    def prog(i, n, kept):
        if i % 25 == 0 or i == n:
            print(f"  {i}/{n} commits, {kept} usable", flush=True)
    kept, skipped = pipeline.build_ranking_dataset(a.repo, a.out, a.n, _cfg(a), _opts(a), prog)
    print(f"{kept} usable, {skipped} skipped -> {a.out}")


def cmd_evaluate(a):
    res = ev.run(a.dataset, a.train_frac)
    print(ev.format_report(res))
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(res, f, indent=2)
        print(f"\nsaved -> {a.out}")


def cmd_rank(a):
    w = rank.Weights(**json.load(open(a.weights))["weights"]) if a.weights else rank.Weights()
    rec = pipeline.rank_commit(a.repo, a.commit, a.history, _cfg(a), _opts(a), w)
    if "skipped" in rec:
        raise SystemExit(f"skipped: {rec['skipped']}")
    print(f"seeds: {', '.join(rec['seeds'][:6])}")
    for i, r in enumerate(rec["ranking"][:a.top], 1):
        d = "-" if r["distance"] is None else r["distance"]
        print(f"{i:3d}. {r['file']}   graph_dist={d}  cochange={r['conf']:.2f} (n={r['support']})")


def cmd_doctor(a):
    res = doctor.check(a.repo, a.window)
    print(doctor.format_report(res))
    return 0 if res["verdict"] != doctor.BAD else 1


def _common(sp):
    sp.add_argument("repo", help="path to a git repository")
    sp.add_argument("--depth", type=int, default=3, help="graph hops from the changed code")
    sp.add_argument("--no-maybe", action="store_true", help="ablation: strict edges only (no maybe_calls)")
    sp.add_argument("--max-files", type=int, default=50, help="skip commits changing more .py files")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="aegis", description="AEGIS Phase 1: repo -> graph")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("build", help="build the graph and write the output folder")
    p.add_argument("repo")
    p.add_argument("--out", default="aegis_out")
    p.add_argument("--name", default=None)
    p.add_argument("--no-maybe", action="store_true", help="skip heuristic maybe_calls edges")
    p.set_defaults(fn=cmd_build)
    p = sub.add_parser("check", help="verify graph invariants (repo dir, out dir or graph.json)")
    p.add_argument("target")
    p.set_defaults(fn=cmd_check)
    p = sub.add_parser("stats")
    p.add_argument("target")
    p.set_defaults(fn=cmd_stats)
    p = sub.add_parser("find", help="search node ids")
    p.add_argument("target")
    p.add_argument("pattern")
    p.set_defaults(fn=cmd_find)
    for name, fn, default in (("callers", cmd_callers, "calls"), ("callees", cmd_callees, "calls")):
        p = sub.add_parser(name)
        p.add_argument("target")
        p.add_argument("node")
        p.add_argument("--depth", type=int, default=1)
        p.add_argument("--types", default=default, help="comma list of edge types")
        p.set_defaults(fn=fn)
    p = sub.add_parser("at", help="which node contains file:line")
    p.add_argument("target")
    p.add_argument("location")
    p.set_defaults(fn=cmd_at)
    p = sub.add_parser("audit", help="sample edges for manual precision checking")
    p.add_argument("target")
    p.add_argument("repo")
    p.add_argument("--type", default="calls")
    p.add_argument("-n", type=int, default=50)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--out", default="audit.csv")
    p.set_defaults(fn=cmd_audit)
    p = sub.add_parser("oracle", help="validate against a traced run of a workload script")
    p.add_argument("repo")
    p.add_argument("script")
    p.add_argument("--examples", type=int, default=10)
    p.set_defaults(fn=cmd_oracle)
    p = sub.add_parser("doctor", help="will AEGIS work on this repository? (exit 1 if not)")
    p.add_argument("repo")
    p.add_argument("--window", type=int, default=200)
    p.set_defaults(fn=cmd_doctor)
    p = sub.add_parser("impact", help="Phase 2: possible-impact files of one commit")
    _common(p)
    p.add_argument("--commit", default="HEAD")
    p.add_argument("--top", type=int, default=25)
    p.set_defaults(fn=cmd_impact)
    p = sub.add_parser("rankdata", help="Phases 2+3 over history: seeds, candidates, co-change evidence")
    _common(p)
    p.add_argument("--n", type=int, default=300, help="commits to mine")
    p.add_argument("--out", default="outputs/ranking.jsonl")
    p.set_defaults(fn=cmd_rankdata)
    p = sub.add_parser("evaluate", help="Phase 4: temporal split, fit weights, metrics vs baselines")
    p.add_argument("dataset")
    p.add_argument("--train-frac", type=float, default=0.5)
    p.add_argument("--out")
    p.set_defaults(fn=cmd_evaluate)
    p = sub.add_parser("rank", help="ranked impact list for one commit")
    _common(p)
    p.add_argument("--commit", default="HEAD")
    p.add_argument("--history", type=int, default=300)
    p.add_argument("--weights", help="results JSON from `evaluate`")
    p.add_argument("--top", type=int, default=15)
    p.set_defaults(fn=cmd_rank)
    a = ap.parse_args(argv)
    return a.fn(a) or 0


if __name__ == "__main__":
    sys.exit(main())
