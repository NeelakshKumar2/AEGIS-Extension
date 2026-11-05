"""Writes one organised output folder per repository.

    <out>/<name>/
        graph.json      canonical graph (node-link JSON, loadable with aegis.load_graph)
        nodes.csv       one row per node, ready for pandas / spreadsheets
        edges.csv       one row per typed edge
        graph.graphml   for Gephi / Cytoscape / yEd
        summary.json    counts and call-resolution statistics
        report.md       human-readable overview
"""
import csv
import json
from collections import Counter
from pathlib import Path

import networkx as nx

from . import graph as g


def _fan(G):
    fin, fout = Counter(), Counter()
    for u, v, k in G.edges(keys=True):
        if k in ("calls", "references", "inherits"):
            fin[v] += 1
            fout[u] += 1
    return fin, fout


def write_nodes_csv(G, path):
    fin, fout = _fan(G)
    cols = ["id", "type", "name", "qualname", "path", "lineno", "end_lineno", "is_test_file",
            "is_method", "is_async", "decorators", "ext_bases", "body_hash", "fan_in", "fan_out", "doc"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for n in sorted(G.nodes):
            d = G.nodes[n]
            if d["type"] == "file":
                row = [n, "file", d["name"], "", d["path"], 1, d["loc"], d["is_test"], "", "", "", "",
                       d["sha1"][:12], fin[n], fout[n], ""]
            else:
                row = [n, d["type"], d["name"], d["qualname"], d["path"], d["lineno"], d["end_lineno"],
                       d["in_test_file"], d.get("is_method", ""), d.get("is_async", ""),
                       ";".join(d.get("decorators", [])), ";".join(d.get("ext_bases", [])),
                       d["body_hash"], fin[n], fout[n], d.get("doc", "")]
            w.writerow(row)


def write_edges_csv(G, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["source", "target", "type", "count", "lines", "ncand"])
        for u, v, k in sorted(G.edges(keys=True)):
            d = G[u][v][k]
            w.writerow([u, v, k, d["count"], " ".join(map(str, d["lines"])), d.get("ncand", "")])


def write_graphml(G, path):
    H = nx.MultiDiGraph()
    for n, d in G.nodes(data=True):
        H.add_node(n, **{k: (json.dumps(v) if isinstance(v, (list, dict)) else ("" if v is None else v))
                         for k, v in d.items()})
    for u, v, k, d in G.edges(keys=True, data=True):
        H.add_edge(u, v, key=k, **{a: (json.dumps(b) if isinstance(b, (list, dict)) else b)
                                  for a, b in d.items()})
    nx.write_graphml(H, path)


def report_md(G):
    s = g.summary(G)
    st = G.graph.get("stats", {})
    total = st.get("calls_total", 0) or 1
    fin, fout = _fan(G)
    L = [f"# AEGIS Phase 1 graph report: {G.graph.get('repo', '?')}", "",
         f"- builder version: {G.graph.get('builder_version')}   schema: {G.graph.get('schema_version')}",
         f"- git HEAD: {G.graph.get('head') or 'n/a'}",
         f"- files parsed: {st.get('files_parsed', 0)} ({st.get('loc_total', 0)} lines), "
         f"parse errors: {st.get('parse_errors', 0)}",
         f"- build time: {G.graph.get('build_seconds')} s", "",
         "## Nodes", "", "| type | count |", "|---|---|"]
    L += [f"| {t} | {s[f'{t}_nodes']} |" for t in g.NODE_TYPES]
    L += ["", "## Edges", "", "| type | count | meaning |", "|---|---|---|"]
    meaning = {"contains": "file -> class -> method", "imports": "file imports file",
               "calls": "resolved call (certain)", "tests": "test -> code under test",
               "inherits": "class -> base class", "overrides": "method -> overridden method",
               "references": "uses a name without calling it", "maybe_calls": "HEURISTIC name-based call"}
    L += [f"| {t} | {s[f'{t}_edges']} | {meaning[t]} |" for t in g.EDGE_TYPES]
    L += ["", "## Call resolution", "", "| outcome | calls | share |", "|---|---|---|"]
    for k, label in (("resolved", "resolved to a repo definition"), ("external", "external / builtin"),
                     ("local", "nested function or lambda"), ("unresolved", "unresolved")):
        L.append(f"| {label} | {st.get('calls_' + k, 0)} | {100 * st.get('calls_' + k, 0) / total:.1f}% |")
    L.append(f"\nImplicit calls found (properties, `with`, `obj[k]`, iteration, operators): "
             f"{st.get('calls_implicit', 0)}")
    reasons = G.graph.get("unresolved_reasons", {})
    if reasons:
        L += ["", "### Why calls stayed unresolved", "", "| reason | calls |", "|---|---|"]
        L += [f"| {r} | {n} |" for r, n in list(reasons.items())[:10]]
    L += ["", "## Most depended-on definitions (calls + references + inherits)", "",
          "| node | fan-in |", "|---|---|"]
    L += [f"| `{n}` | {c} |" for n, c in fin.most_common(10)]
    pe = G.graph.get("parse_error_files") or []
    if pe:
        L += ["", "## Files that failed to parse", ""] + [f"- `{p}`" for p in pe[:30]]
    L += ["", "## Reading this report", "",
          "`calls` edges are only created when the target is certain; everything else is counted "
          "with a reason above. `maybe_calls` edges are heuristic and must be weighed, not trusted."]
    return "\n".join(L) + "\n"


def write_all(G, outdir):
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    g.save_graph(G, out / "graph.json")
    write_nodes_csv(G, out / "nodes.csv")
    write_edges_csv(G, out / "edges.csv")
    write_graphml(G, out / "graph.graphml")
    (out / "summary.json").write_text(json.dumps(g.summary(G), indent=2, sort_keys=True))
    (out / "report.md").write_text(report_md(G))
    return out
