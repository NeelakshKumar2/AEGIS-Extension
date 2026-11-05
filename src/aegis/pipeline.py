"""Phase 2 + 3 end to end: for each commit (oldest first) build the graph, map the diff to seeds,
expand to candidates, attach co-change evidence from EARLIER commits only, and write one JSON
line per usable commit. `evaluate` then splits these records by time.
"""
import json
from pathlib import Path

from . import diff_mapper, gitutil, history, impact, rank
from .parser import build_graph


def _usable(files, cfg):
    n = len([f for f in files if f.endswith(".py")])
    return 0 < n <= cfg.max_files


def build_ranking_dataset(repo, out_path, n=300, cfg: impact.Config = impact.Config(),
                          graph_opts=None, progress=None):
    log = history.log(repo, n)
    index = history.CoChange()
    kept = skipped = 0
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for i, (sha, ts, files) in enumerate(log):
            rec = {"commit": sha, "time": ts, "n_py_files": len(files)}
            try:
                if i == 0:
                    rec["skipped"] = "first commit of the window (no parent in range)"
                elif not _usable(files, cfg):
                    rec["skipped"] = "no python files or too many"
                else:
                    rec.update(_score_commit(repo, sha, cfg, graph_opts, index))
            except (gitutil.GitError, OSError) as e:
                rec["skipped"] = f"error: {e}"
            if "skipped" in rec:
                skipped += 1
            else:
                kept += 1
            f.write(json.dumps(rec) + "\n")
            index.add(files)                       # AFTER scoring: no leakage
            if progress:
                progress(i + 1, len(log), kept)
    return kept, skipped


def _score_commit(repo, sha, cfg, graph_opts, index):
    changes = diff_mapper.changed_lines(repo, sha)
    with gitutil.worktree(repo, sha) as wt:
        G = build_graph(wt, **(graph_opts or {}))
        out = impact.impact_from_graph(G, changes, cfg)
        if not out["seeds"]:
            return {"skipped": "no non-test seeds"}
        if not out["truth_files"]:
            return {"skipped": "no other changed files to predict"}
        rows, graph_size = rank.features(G, out, index)
    return {"seeds": out["seeds"], "seed_files": out["seed_files"], "truth_files": out["truth_files"],
            "graph_size": graph_size, "candidates": rows, "history_commits": index.commits}


def rank_commit(repo, rev, n_history=300, cfg: impact.Config = impact.Config(), graph_opts=None,
                weights: rank.Weights = rank.Weights()):
    """Ranked impact list for ONE commit, using history strictly before it."""
    sha = gitutil.rev_parse(repo, rev)
    index = history.CoChange()
    for _, _, files in history.log(repo, n_history, rev=sha + "^"):
        index.add(files)
    rec = _score_commit(repo, sha, cfg, graph_opts, index)
    if "skipped" in rec:
        return rec
    order = rank.rank_aegis(rec["candidates"], weights=weights)
    by = {r["file"]: r for r in rec["candidates"]}
    rec["ranking"] = [by[f] for f in order]
    return rec
