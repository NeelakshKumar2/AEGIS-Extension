"""Rebuild validation/RESULTS.md and graphs/ from the repos in /tmp/vrepos (see validation/README)."""
import json, sys, time
from pathlib import Path
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "src"))
from aegis import export, graph as g                      # noqa: E402
from aegis.oracle import evaluate, run_workload           # noqa: E402
from aegis.parser import build_graph                      # noqa: E402
from aegis.validate import check_invariants               # noqa: E402

REPOS = ["requests", "click", "flask", "jinja2", "markdown", "werkzeug", "networkx"]
WL = {r: f"{r}_wl.py" for r in REPOS}
BASE = json.loads((HERE / "baseline_v0.json").read_text())      # measured with the original Phase 1 parser
root = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/vrepos")
rows = []
for r in REPOS:
    G = build_graph(root / r, keep_call_log=True)
    ev = evaluate(G, run_workload(root / r, HERE / "workloads" / WL[r]), top_missing=0)
    G.graph.pop("call_log")
    problems = check_invariants(G)
    out = ROOT / "graphs" / r
    if r == "networkx":                      # keep the zip small: no GraphML for the big one
        out.mkdir(parents=True, exist_ok=True)
        g.save_graph(G, out / "graph.json"); export.write_nodes_csv(G, out / "nodes.csv")
        export.write_edges_csv(G, out / "edges.csv")
        (out / "summary.json").write_text(json.dumps(g.summary(G), indent=2, sort_keys=True))
        (out / "report.md").write_text(export.report_md(G))
    else:
        export.write_all(G, out)
    st = G.graph["stats"]; tot = st["calls_total"]
    rows.append((r, st["files_parsed"], st["loc_total"], G.number_of_nodes(), G.number_of_edges(), tot,
                 100 * st["calls_resolved"] / tot, 100 * st["calls_external"] / tot,
                 100 * st["calls_unresolved"] / tot, BASE[r]["unresolved_pct"], len(problems),
                 G.graph["build_seconds"], ev))
L = ["# Phase 1 validation results", "",
     "Targets: installed copies of real packages (not toy code). Graph checks: structural invariants, "
     "determinism, JSON round-trip. Behaviour checks: a traced run of a workload script (dynamic oracle).", "",
     "## 1. Static call resolution, original parser (v0) vs this build (v2)", "",
     "| repo | files | lines | calls | resolved | external | unresolved (v2) | unresolved (v0) | invariant problems | build s |",
     "|---|---|---|---|---|---|---|---|---|---|"]
for r, f, loc, n, e, tot, res, ext, un, un0, pr, bs, ev in rows:
    L.append(f"| {r} | {f} | {loc} | {tot} | {res:.1f}% | {ext:.1f}% | {un:.1f}% | {un0:.1f}% | {pr} | {bs} |")
L += ["", "## 2. Dynamic oracle: does the graph match what really executes?", "",
      "`recall` = share of observed repo-to-repo calls that the graph contains. `recall+dispatch` also counts a "
      "call to an override when the graph has the call to the base method, and decorator/class-body calls "
      "attributed to the contained definition. `precision` = of the graph's call edges whose call site actually "
      "ran, the share confirmed by a real call there (decorated/generator callees excluded: their frames "
      "start from wrappers, so they cannot be confirmed or refuted).", "",
      "| repo | observed calls | recall | recall+dispatch | +maybe_calls | precision (executed sites) | decided edges | maybe_calls precision |",
      "|---|---|---|---|---|---|---|---|"]
for r, *_, ev in rows:
    L.append(f"| {r} | {ev['dynamic_edges']} | {ev['recall_strict']:.1%} | {ev['recall_with_dispatch']:.1%} | "
             f"{ev['recall_with_maybe']:.1%} | {ev['calls_precision_executed']:.1%} | {ev['calls_decided']} | "
             f"{ev['maybe_precision_executed']:.1%} (n={ev['maybe_decided']}) |")
(HERE / "RESULTS.md").write_text("\n".join(L) + "\n")
(HERE / "results.json").write_text(json.dumps({r: ev for r, *_, ev in rows}, indent=1, default=str))
print("\n".join(L))
