import subprocess

from aegis import evaluate as ev
from aegis import history, metrics as M, pipeline, rank


def test_metrics():
    r, t = ["a", "b", "c", "d"], {"b", "d"}
    assert M.precision_at_k(r, t, 2) == 0.5 and M.recall_at_k(r, t, 2) == 0.5
    assert M.reciprocal_rank(r, t) == 0.5 and M.reciprocal_rank(["x"], t) == 0.0
    assert M.scope_reduction(10, 3) == 0.7 and M.scope_reduction(2, 5) == 0.0


def test_cochange_confidence_and_cap():
    c = history.CoChange(max_files=3)
    c.add(["a", "b"]); c.add(["a", "b"]); c.add(["a", "c"]); c.add(list("wxyz"))   # last one is too big
    p = c.partners(["a"])
    assert p["b"] == (2 / 3, 2) and p["c"] == (1 / 3, 1) and "w" not in p
    assert c.commits == 3


def test_rankers_are_deterministic_and_use_evidence():
    rows = [{"file": "near.py", "distance": 1, "n_nodes": 1, "n_seeds": 1, "is_test": False, "conf": 0.0, "support": 0},
            {"file": "hist.py", "distance": None, "n_nodes": 0, "n_seeds": 0, "is_test": False, "conf": 0.9, "support": 9},
            {"file": "far.py", "distance": 3, "n_nodes": 1, "n_seeds": 1, "is_test": False, "conf": 0.0, "support": 0}]
    assert rank.rank_graph(rows)[0] == "near.py"
    assert rank.rank_cochange(rows)[0] == "hist.py"
    assert rank.rank_random(rows, seed="s") == rank.rank_random(rows, seed="s")
    assert rank.rank_aegis(rows, weights=rank.Weights(wg=0.1, wc=1.0))[0] == "hist.py"
    assert rank.rank_aegis(rows, weights=rank.Weights(wg=1.0, wc=0.1))[0] == "near.py"


def _git(repo, *a):
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *a],
                   check=True, capture_output=True)


def test_pipeline_has_no_leakage_and_evaluates(tmp_path):
    """lib.py always changes together with docs_helper.py (no call link): history must find it, but
    only after it has been seen once."""
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg/__init__.py").write_text("")
    (tmp_path / "pkg/lib.py").write_text("def f():\n    return 0\n")
    (tmp_path / "pkg/side.py").write_text("X = 0\n")
    _git(tmp_path, "init", "-q"); _git(tmp_path, "add", "-A"); _git(tmp_path, "commit", "-qm", "init")
    for i in range(1, 9):
        (tmp_path / "pkg/lib.py").write_text(f"def f():\n    return {i}\n")
        (tmp_path / "pkg/side.py").write_text(f"X = {i}\n")
        _git(tmp_path, "commit", "-qam", f"c{i}")
    out = tmp_path / "r.jsonl"
    kept, _ = pipeline.build_ranking_dataset(tmp_path, out, n=20, graph_opts={"maybe_calls": False})
    recs, _ = ev.load(out)
    assert kept == 8 and len(recs) == 8
    assert [r["history_commits"] for r in recs] == list(range(1, 9))   # each commit sees only earlier ones
    assert any(c["file"] == "pkg/side.py" and c["conf"] > 0 for c in recs[-1]["candidates"])
    res = ev.run(out, 0.5)
    t = res["test"]["methods"]
    assert t["cochange"]["MRR"] == 1.0 and t["aegis"]["MRR"] == 1.0
    assert "MRR" in ev.format_report(res)
    ranked = pipeline.rank_commit(tmp_path, "HEAD", 20, graph_opts={"maybe_calls": False})
    assert ranked["ranking"][0]["file"] == "pkg/side.py"
