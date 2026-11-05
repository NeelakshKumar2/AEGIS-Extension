"""Graph model for AEGIS Phase 1 (schema v2).

Node ids
    file      "pkg/core.py"
    class     "pkg/core.py::Engine"
    function  "pkg/core.py::Engine.run" (methods) or "pkg/utils.py::helper"
Node attribute ``type``: file | class | function | test

Edge types (also the MultiDiGraph key, so one node pair can hold several)
    contains    parent -> child definition (file -> class -> method)
    imports     file -> file it imports
    calls       caller -> callee, only when the target was resolved with confidence
    tests       test -> code under test (from resolved calls, plus file-level imports)
    inherits    class -> base class (in repo)
    overrides   method -> the base-class method it overrides
    references  owner -> class/function it names without calling it
                (callbacks, annotations, isinstance(), ``from m import f``)
    maybe_calls caller -> every repo method with that name, when the receiver type is
                unknown. HEURISTIC and kept apart from ``calls`` on purpose: it raises
                recall of the impact set at a precision cost the ranker must weigh.

Every edge carries ``count`` and ``lines`` (up to MAX_LINES source lines where it occurs).
"""
import bisect
import json

import networkx as nx

SCHEMA_VERSION = 2
NODE_TYPES = ("file", "class", "function", "test")
EDGE_TYPES = ("contains", "imports", "calls", "tests", "inherits", "overrides",
              "references", "maybe_calls")
# edge types that are certain facts about the code (no heuristics)
STRICT_EDGE_TYPES = ("contains", "imports", "calls", "tests", "inherits", "overrides",
                     "references")
MAX_LINES = 20


def new_graph() -> nx.MultiDiGraph:
    G = nx.MultiDiGraph()
    G.graph["schema_version"] = SCHEMA_VERSION
    return G


def add_node(G, node_id, ntype, **attrs):
    assert ntype in NODE_TYPES, ntype
    G.add_node(node_id, type=ntype, **attrs)


def add_edge(G, u, v, etype, line=None, **attrs):
    """Add a typed edge; repeated identical edges bump a counter and collect lines."""
    assert etype in EDGE_TYPES, etype
    if G.has_edge(u, v, key=etype):
        d = G[u][v][etype]
        d["count"] += 1
    else:
        G.add_edge(u, v, key=etype, type=etype, count=1, lines=[], **attrs)
        d = G[u][v][etype]
    if line is not None and len(d["lines"]) < MAX_LINES and line not in d["lines"]:
        d["lines"].append(line)


def save_graph(G, path):
    data = nx.node_link_data(G, edges="edges")
    data["graph"] = {k: v for k, v in data["graph"].items() if k != "call_log"}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, sort_keys=True)


def load_graph(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return nx.node_link_graph(data, edges="edges", multigraph=True, directed=True)


# ---------------------------------------------------------------- queries
def nodes_of_type(G, ntype):
    return [n for n, d in G.nodes(data=True) if d.get("type") == ntype]


def edges_of_type(G, etype):
    return [(u, v) for u, v, k in G.edges(keys=True) if k == etype]


def neighbors(G, node_id, etypes, direction="out"):
    """Sorted neighbours of ``node_id`` over the given edge types.

    direction="out": things node_id points to (callees, imports, bases...)
    direction="in" : things pointing at node_id (callers, importers, subclasses...)
    """
    etypes = {etypes} if isinstance(etypes, str) else set(etypes)
    edges = G.out_edges(node_id, keys=True) if direction == "out" else G.in_edges(node_id, keys=True)
    out = set()
    for u, v, k in edges:
        if k in etypes:
            out.add(v if direction == "out" else u)
    return sorted(out)


def callers_of(G, node_id):
    return neighbors(G, node_id, "calls", "in")


def callees_of(G, node_id):
    return neighbors(G, node_id, "calls", "out")


def collapse(G, etypes=STRICT_EDGE_TYPES, reverse=False):
    """Plain DiGraph over the chosen edge types, ready for BFS / Dijkstra / PageRank.

    Parallel edges are merged; attribute ``types`` lists the merged edge types and
    ``count`` sums their counts. ``reverse=True`` flips every edge, which is the
    direction impact flows (callee -> caller, imported -> importer).
    """
    etypes = set(etypes)
    D = nx.DiGraph()
    D.add_nodes_from(G.nodes(data=True))
    for u, v, k, d in G.edges(keys=True, data=True):
        if k not in etypes:
            continue
        a, b = (v, u) if reverse else (u, v)
        if D.has_edge(a, b):
            D[a][b]["types"].append(k)
            D[a][b]["count"] += d.get("count", 1)
        else:
            D.add_edge(a, b, types=[k], count=d.get("count", 1))
    return D


class LineIndex:
    """Maps (file, line) -> innermost graph node. Phase 2 uses this to turn diff hunks
    into changed graph nodes. Lines outside every definition map to the file node."""

    def __init__(self, G):
        per = {}
        for n, d in G.nodes(data=True):
            if d["type"] == "file":
                per.setdefault(d["path"], [])
                continue
            for s, e in d.get("spans", [[d["lineno"], d["end_lineno"]]]):
                per.setdefault(d["path"], []).append((s, e, n))
        self._by_file = {}
        for p, spans in per.items():
            spans.sort(key=lambda x: (x[0], -(x[1] - x[0])))
            self._by_file[p] = (spans, [s[0] for s in spans])

    def at(self, path, line):
        """Innermost node containing ``line`` (1-based); the file node if none does."""
        spans, starts = self._by_file.get(path, ([], []))
        best, best_len = None, None
        hi = bisect.bisect_right(starts, line)
        for s, e, n in spans[:hi]:
            if s <= line <= e:
                ln = e - s
                if best is None or ln <= best_len:
                    best, best_len = n, ln
        return best if best is not None else path

    def at_range(self, path, start, end):
        """Set of innermost nodes touched by lines start..end (inclusive)."""
        return {self.at(path, ln) for ln in range(start, end + 1)}


def summary(G) -> dict:
    out = {"nodes": G.number_of_nodes(), "edges": G.number_of_edges()}
    for t in NODE_TYPES:
        out[f"{t}_nodes"] = len(nodes_of_type(G, t))
    for t in EDGE_TYPES:
        out[f"{t}_edges"] = len(edges_of_type(G, t))
    stats = dict(G.graph.get("stats", {}))
    total = stats.get("calls_total", 0)
    if total:
        for k in ("resolved", "external", "local", "unresolved"):
            out[f"calls_{k}_pct"] = round(100.0 * stats.get(f"calls_{k}", 0) / total, 1)
    out.update(stats)
    return out
