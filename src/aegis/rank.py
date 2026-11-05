"""Phase 3b: evidence features and rankers for the candidate files of one commit.

Evidence per candidate file
    distance    shortest graph path from a seed (None = not reached by the graph)
    n_nodes     how many of its definitions the graph reaches (more = stronger structural tie)
    n_seeds     how many seeds reach it
    conf,support  co-change confidence / count from history strictly before the commit
    is_test     the file is a test file

Rankers (the first three are the baselines the paper compares against)
    graph       nearest in the graph first
    cochange    highest co-change confidence first
    random      seeded shuffle (a floor)
    aegis       weighted evidence:  wg/distance + wc*conf + wn*log(1+n_nodes)/log(1+max) + wt*is_test
                weights are fitted on the earlier part of the data (evaluate.fit_weights)
"""
import math
import random
from dataclasses import dataclass


@dataclass(frozen=True)
class Weights:
    wg: float = 0.5
    wc: float = 1.0
    wn: float = 0.0
    wt: float = 0.0

    def as_dict(self):
        return dict(self.__dict__)


def features(G, impact_out, cochange, top_partners=50):
    """Candidate universe = graph candidates + history partners that exist in this checkout."""
    seed_files = set(impact_out["seed_files"])
    rows = {c["file"]: {"file": c["file"], "distance": c["distance"], "n_nodes": c["n_nodes"],
                        "n_seeds": c["n_seeds"], "is_test": c["is_test"], "sources": c["sources"],
                        "edge_types": c["edge_types"], "conf": 0.0, "support": 0}
            for c in impact_out["candidates"]}
    graph_size = len(rows)
    for f, (conf, support) in cochange.partners(seed_files, top_partners).items():
        if f in seed_files:
            continue
        if f in rows:
            rows[f].update(conf=conf, support=support)
        elif f in G and G.nodes[f].get("type") == "file":
            rows[f] = {"file": f, "distance": None, "n_nodes": 0, "n_seeds": 0,
                       "is_test": bool(G.nodes[f].get("is_test")), "sources": [], "edge_types": [],
                       "conf": conf, "support": support}
    return list(rows.values()), graph_size


# ---------------------------------------------------------------------------- rankers
def _graph_key(r):
    return (r["distance"] if r["distance"] is not None else 10**6, -r["n_nodes"], r["file"])


def rank_graph(rows, **_):
    return [r["file"] for r in sorted(rows, key=_graph_key)]


def rank_cochange(rows, **_):
    return [r["file"] for r in sorted(rows, key=lambda r: (-r["conf"], -r["support"], r["file"]))]


def rank_random(rows, seed="0", **_):
    out = sorted(r["file"] for r in rows)
    random.Random(seed).shuffle(out)
    return out


def score(r, w: Weights, max_nodes):
    g = 1.0 / r["distance"] if r["distance"] else 0.0
    n = math.log1p(r["n_nodes"]) / math.log1p(max_nodes) if max_nodes else 0.0
    return w.wg * g + w.wc * r["conf"] + w.wn * n + w.wt * (1.0 if r["is_test"] else 0.0)


def rank_aegis(rows, weights: Weights = Weights(), **_):
    mx = max((r["n_nodes"] for r in rows), default=0)
    scored = [(-score(r, weights, mx),) + _graph_key(r) for r in rows]
    order = sorted(zip(scored, rows), key=lambda t: t[0])
    return [r["file"] for _, r in order]


METHODS = {"random": rank_random, "graph": rank_graph, "cochange": rank_cochange, "aegis": rank_aegis}
