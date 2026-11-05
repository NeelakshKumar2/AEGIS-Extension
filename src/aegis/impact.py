"""Phase 2: possible-impact set.

    commit --git diff--> changed lines --diff_mapper--> seed nodes --reverse BFS--> candidates

Impact flows against the direction of the edges: if `f` calls `g` and `g` changes, `f` is
possibly impacted. So we walk INCOMING edges from the seeds (caller of a callee, subclass of a
base class, test of the code it exercises).

Every candidate keeps the evidence Phase 3 ranks on: distance, path, edge types, edge sources.
The traversal is deterministic (sorted neighbours, fixed tie-breaks).

Evaluation definition (fixed here because Phase 4 depends on it; write it in the Methodology).
This is the standard "query one changed item, predict the rest" setup of co-change prediction:
  * query file  = the non-test .py file with the most changed lines in the commit (ties: path order)
  * seeds       = graph nodes changed inside the query file
  * truth files = ALL OTHER changed .py files of the commit (tests included)
  * candidates  = files reached from the seeds, excluding the query file
The truth never contains the query, so the answer is not leaked through the input. Commits with
fewer than two changed .py files are skipped (nothing to predict).
"""
import json
from collections import deque
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import diff_mapper, gitutil
from .diff_mapper import Changes
from . import graph as g
from .parser import build_graph

# Impact flows against these edges: callee -> caller, base -> subclass/override, code -> its tests,
# referenced -> referrer. `maybe_calls` is the heuristic edge (receiver type unknown).
STRICT = "strict"            # certain facts: calls, references, overrides, inherits, tests, imports
HEURISTIC = "heuristic"      # maybe_calls
DEFAULT_EDGE_TYPES = ("calls", "references", "overrides", "inherits", "tests", "maybe_calls")


def source_of(edge_type):
    return HEURISTIC if edge_type == "maybe_calls" else STRICT


@dataclass(frozen=True)
class Config:
    max_depth: int = 3
    edge_types: tuple = DEFAULT_EDGE_TYPES
    sources: tuple = None          # None = all; ("strict",) drops maybe_calls (ablation)
    max_files: int = 50            # skip commits touching more .py files than this


@dataclass
class Candidate:
    node: str
    file: str
    distance: int
    seed: str                      # seed that reached it first (shortest path)
    path: list                     # seed -> ... -> node
    edge_types: list               # one per hop
    sources: list                  # union of edge sources along the path
    n_seeds: int = 1               # how many seeds reach this node within max_depth
    is_test: bool = False


def _incoming(G, node, edge_types, sources):
    """Sorted [(neighbour, edge_type, (provenance,))] over incoming edges of the allowed kinds."""
    out = []
    for u, _, key in G.in_edges(node, keys=True):
        if key not in edge_types:
            continue
        src = source_of(key)
        if sources is not None and src not in sources:
            continue
        out.append((u, key, (src,)))
    return sorted(set(out))


def expand(G, seeds, cfg: Config = Config()):
    """Reverse BFS from every seed. Returns {node: Candidate} (seeds excluded)."""
    seeds = sorted(set(seeds))
    best = {}
    reach = {}
    for seed in seeds:
        dist = {seed: 0}
        info = {seed: ([seed], [], set())}
        queue = deque([seed])
        while queue:
            n = queue.popleft()
            if dist[n] == cfg.max_depth:
                continue
            for u, etype, srcs in _incoming(G, n, cfg.edge_types, cfg.sources):
                if u in dist:
                    continue
                dist[u] = dist[n] + 1
                p, t, s = info[n]
                info[u] = (p + [u], t + [etype], s | set(srcs))
                queue.append(u)
        for node, dd in dist.items():
            if node == seed:
                continue
            reach[node] = reach.get(node, 0) + 1
            cur = best.get(node)
            if cur is None or dd < cur.distance:     # seeds are sorted: ties keep the earlier seed
                p, t, s = info[node]
                best[node] = Candidate(node=node, file=G.nodes[node].get("path", node), distance=dd,
                                       seed=seed, path=p, edge_types=t, sources=sorted(s),
                                       is_test=G.nodes[node].get("type") == "test"
                                       or bool(G.nodes[G.nodes[node].get("path", node)].get("is_test")))
    for node, c in best.items():
        c.n_seeds = reach[node]
    for s in seeds:
        best.pop(s, None)
    return best


def to_files(cands, exclude=()):
    """Collapse node candidates to files: minimum distance, number of reaching nodes."""
    files = {}
    for c in cands.values():
        if c.file in exclude:
            continue
        f = files.get(c.file)
        if f is None:
            files[c.file] = {"file": c.file, "distance": c.distance, "n_nodes": 1,
                             "n_seeds": c.n_seeds, "edge_types": c.edge_types, "sources": c.sources,
                             "is_test": c.is_test, "seed": c.seed, "path": c.path}
        else:
            f["n_nodes"] += 1
            f["n_seeds"] = max(f["n_seeds"], c.n_seeds)
            if c.distance < f["distance"]:
                f.update(distance=c.distance, edge_types=c.edge_types, sources=c.sources,
                         seed=c.seed, path=c.path)
    return sorted(files.values(), key=lambda r: (r["distance"], -r["n_nodes"], r["file"]))


# --------------------------------------------------------------------------------------
# one commit
# --------------------------------------------------------------------------------------
def _is_py(p):
    return p.endswith(".py")


def query_file(G, changes):
    """The non-test .py file (present in the graph) with the most changed lines, or None."""
    best = []
    for path, ranges in changes.ranges.items():
        if _is_py(path) and path in G and not G.nodes[path].get("is_test"):
            best.append((-sum(b - a + 1 for a, b in ranges), path))
    return min(best)[1] if best else None


def impact_from_graph(G, changes, cfg: Config = Config()):
    """Query file + seeds + candidates + truth for already-parsed changes. No git access."""
    changed_py = sorted(p for p in changes.ranges if _is_py(p))
    q = query_file(G, changes)
    empty = {"seeds": [], "seed_files": [], "truth_files": [], "candidates": [],
             "n_candidate_nodes": 0, "deleted_files": list(changes.deleted_files), "module_level_files": []}
    if q is None:
        return empty
    sub = Changes(ranges={q: changes.ranges[q]})
    mapping = diff_mapper.map_changes(G, sub)
    seeds = mapping.seeds
    cands = expand(G, seeds, cfg)
    return {"seeds": seeds, "seed_files": [q], "truth_files": [p for p in changed_py if p != q],
            "candidates": to_files(cands, exclude={q}), "n_candidate_nodes": len(cands),
            "deleted_files": mapping.deleted_files, "module_level_files": mapping.module_level_files}


def impact_for_commit(repo, rev, cfg: Config = Config(), graph_opts=None):
    """Full pipeline for one commit: worktree -> graph -> diff -> seeds -> candidates."""
    sha = gitutil.rev_parse(repo, rev)
    changes = diff_mapper.changed_lines(repo, sha)
    n_py = sum(1 for p in changes.ranges if _is_py(p))
    rec = {"commit": sha, "subject": gitutil.commit_subject(repo, sha),
           "time": gitutil.commit_time(repo, sha), "n_py_files": n_py}
    if gitutil.parent_of(repo, sha) is None:
        return {**rec, "skipped": "root commit (everything is 'changed')"}
    if n_py == 0:
        return {**rec, "skipped": "no python files changed"}
    if n_py > cfg.max_files:
        return {**rec, "skipped": f"more than {cfg.max_files} python files changed"}
    with gitutil.worktree(repo, sha) as wt:
        G = build_graph(wt, **(graph_opts or {}))
        out = impact_from_graph(G, changes, cfg)
    if not out["seeds"]:
        return {**rec, "skipped": "no non-test seeds"}
    if not out["truth_files"]:
        return {**rec, "skipped": "no other changed files to predict"}
    return {**rec, **out, "config": {"max_depth": cfg.max_depth, "edge_types": list(cfg.edge_types),
                                     "sources": list(cfg.sources) if cfg.sources else None}}


def commits(repo, n, since=None):
    """Most recent non-merge commits, oldest first."""
    args = ["rev-list", "--no-merges", f"--max-count={n}"]
    if since:
        args.append(f"--since={since}")
    out = gitutil.git(repo, *args, "HEAD").split()
    return list(reversed(out))


def build_dataset(repo, out_path, n=50, cfg: Config = Config(), graph_opts=None, since=None):
    """Write one JSON record per commit (JSON Lines). Returns (kept, skipped) counts."""
    kept = skipped = 0
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for sha in commits(repo, n, since):
            try:
                rec = impact_for_commit(repo, sha, cfg, graph_opts)
            except (gitutil.GitError, OSError) as e:
                rec = {"commit": sha, "skipped": f"error: {e}"}
            if "skipped" in rec:
                skipped += 1
            else:
                kept += 1
            f.write(json.dumps(rec) + "\n")
    return kept, skipped
