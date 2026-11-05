"""Phases 2-3 on the v2 graph: diff mapping, reverse expansion, real git repo, pipeline."""
import subprocess

from helpers import FIXTURES, graph, has  # noqa: F401  (adds src/ to sys.path)

from aegis import diff_mapper as dm
from aegis import evaluate as ev
from aegis import impact as im
from aegis import pipeline
from aegis.parser import build_graph


def _git(repo, *a):
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *a],
                   check=True, capture_output=True)


def _repo(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "pkg/__init__.py").write_text("")
    (tmp_path / "pkg/lib.py").write_text("def f():\n    return 1\n")
    (tmp_path / "pkg/use.py").write_text("from pkg.lib import f\n\n\ndef g():\n    return f()\n")
    (tmp_path / "tests/test_use.py").write_text("from pkg.use import g\n\n\ndef test_g():\n    assert g() == 1\n")
    _git(tmp_path, "init", "-q"); _git(tmp_path, "add", "-A"); _git(tmp_path, "commit", "-qm", "init")
    return tmp_path


def test_diff_lines_map_to_innermost_node(tmp_path):
    repo = _repo(tmp_path)
    G = build_graph(repo)
    m = dm.map_changes(G, dm.Changes(ranges={"pkg/lib.py": [(2, 2)], "pkg/use.py": [(1, 1)], "x.txt": [(1, 1)]}))
    assert "pkg/lib.py::f" in m.seeds
    assert "pkg/use.py" in m.module_level_files            # import line = module-level change
    assert m.unmapped_files == ["x.txt"]


def test_reverse_expansion_carries_evidence(tmp_path):
    G = build_graph(_repo(tmp_path))
    c = im.expand(G, ["pkg/lib.py::f"], im.Config(max_depth=3))
    g_ = c["pkg/use.py::g"]
    assert g_.distance == 1 and g_.edge_types == ["calls"] and g_.sources == [im.STRICT]
    assert "pkg/lib.py::f" not in c
    assert set(im.expand(G, ["pkg/lib.py::f"], im.Config(max_depth=1))) <= set(c)


def test_commit_pipeline_and_no_leakage(tmp_path):
    repo = _repo(tmp_path)
    for i in range(2, 10):
        (repo / "pkg/lib.py").write_text(f"def f():\n    return {i}\n")
        (repo / "tests/test_use.py").write_text(f"from pkg.use import g\n\n\ndef test_g():\n    assert g() == {i}\n")
        _git(repo, "commit", "-qam", f"c{i}")
    rec = im.impact_for_commit(repo, "HEAD")
    assert rec["seed_files"] == ["pkg/lib.py"] and rec["truth_files"] == ["tests/test_use.py"]
    assert any(c["file"] == "pkg/use.py" and c["distance"] == 1 for c in rec["candidates"])
    out = repo / "r.jsonl"
    kept, _ = pipeline.build_ranking_dataset(repo, out, n=20)
    recs, _ = ev.load(out)
    assert kept == len(recs) == 8
    assert [r["history_commits"] for r in recs] == list(range(1, 9))
    res = ev.run(out, 0.5)
    assert res["test"]["methods"]["aegis"]["MRR"] > 0.0
    ranked = pipeline.rank_commit(repo, "HEAD", 20)
    assert ranked["ranking"][0]["file"] == "tests/test_use.py"
