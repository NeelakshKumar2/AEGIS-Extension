"""Structural self-checks for a built graph. A graph that fails these must not be used
by later phases; ``aegis check`` returns a non-zero exit code when any problem is found."""
import hashlib
import json

import networkx as nx

from . import graph as g

VOLATILE_GRAPH_KEYS = {"build_seconds", "call_log", "head"}


def check_invariants(G):
    problems = []

    def bad(msg):
        if len(problems) < 200:
            problems.append(msg)

    files = {n for n, d in G.nodes(data=True) if d.get("type") == "file"}
    parent = {}
    for n, d in G.nodes(data=True):
        t = d.get("type")
        if t not in g.NODE_TYPES:
            bad(f"node {n}: bad type {t!r}")
            continue
        if t == "file":
            if d.get("path") != n:
                bad(f"file {n}: id differs from path")
            continue
        path, qual = d.get("path"), d.get("qualname")
        if path not in files:
            bad(f"{n}: path {path!r} is not a file node")
        if n != f"{path}::{qual}":
            bad(f"{n}: id does not match path::qualname")
        spans = d.get("spans") or []
        if not spans or any(s > e for s, e in spans):
            bad(f"{n}: invalid spans {spans}")
    for u, v, k, d in G.edges(keys=True, data=True):
        if u not in G or v not in G:
            bad(f"edge {u}->{v}: dangling endpoint")
            continue
        if k not in g.EDGE_TYPES or d.get("type") != k:
            bad(f"edge {u}->{v}: key/type mismatch {k!r}/{d.get('type')!r}")
        if d.get("count", 0) < 1:
            bad(f"edge {u}-{k}->{v}: count < 1")
        if u == v:
            bad(f"edge {u}: self loop of type {k}")
        tu, tv = G.nodes[u]["type"], G.nodes[v]["type"]
        if k == "contains":
            if v in parent:
                bad(f"{v}: more than one contains parent")
            parent[v] = u
            if tv == "file":
                bad(f"{v}: file node has a parent")
        elif k == "imports" and not (tu == "file" and tv == "file"):
            bad(f"imports {u}->{v} must be file->file")
        elif k == "inherits" and not (tu == "class" and tv == "class"):
            bad(f"inherits {u}->{v} must be class->class")
        elif k == "overrides" and not (tu in ("function", "test") and tv in ("function", "test")):
            bad(f"overrides {u}->{v} must be method->method")
        elif k in ("calls", "maybe_calls", "references") and tv == "file":
            bad(f"{k} {u}->{v}: target must be a definition")
        elif k == "tests" and not (G.nodes[u].get("is_test") or G.nodes[u].get("in_test_file")):
            bad(f"tests {u}->{v}: source is not in a test file")
    for n, d in G.nodes(data=True):
        if d.get("type") != "file" and n not in parent:
            bad(f"{n}: no contains parent")
    # containment: a child's first span lies inside some span of its parent
    for child, par in parent.items():
        if G.nodes[par]["type"] == "file":
            continue
        cs = G.nodes[child]["spans"][0]
        if not any(s <= cs[0] and cs[1] <= e for s, e in G.nodes[par]["spans"]):
            bad(f"{child}: span {cs} not inside parent {par}")
    contains = nx.DiGraph([(u, v) for u, v, k in G.edges(keys=True) if k == "contains"])
    if contains.number_of_nodes() and not nx.is_directed_acyclic_graph(contains):
        bad("contains edges contain a cycle")
    return problems


def graph_digest(G):
    """Order-independent fingerprint of the graph's content (nodes, edges, metadata).
    Two builds of the same repo state must give the same digest."""
    h = hashlib.sha1()
    for n in sorted(G.nodes):
        h.update(json.dumps([n, G.nodes[n]], sort_keys=True, default=str).encode())
    for u, v, k in sorted(G.edges(keys=True)):
        h.update(json.dumps([u, v, k, G[u][v][k]], sort_keys=True, default=str).encode())
    meta = {k: v for k, v in G.graph.items() if k not in VOLATILE_GRAPH_KEYS}
    h.update(json.dumps(meta, sort_keys=True, default=str).encode())
    return h.hexdigest()
