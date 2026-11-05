"""Failure modes: bad input, platform junk, determinism, schema."""
import json
import shutil
import tempfile
from pathlib import Path

import networkx as nx
from helpers import FIXTURES, edges, graph

from aegis import (LineIndex, build_graph, check_invariants, collapse, graph_digest, load_graph,
                   save_graph)
from aegis import export


def test_invariants_hold_on_all_fixtures():
    for name in ("tiny_repo", "feature_repo"):
        assert check_invariants(graph(name)) == []


def test_build_is_deterministic():
    a = graph_digest(build_graph(FIXTURES / "feature_repo"))
    b = graph_digest(build_graph(FIXTURES / "feature_repo"))
    assert a == b


def test_json_roundtrip_preserves_graph():
    G = graph("feature_repo")
    p = Path(tempfile.mkdtemp()) / "g.json"
    save_graph(G, p)
    assert graph_digest(load_graph(p)) == graph_digest(G)


def test_syntax_errors_binaries_and_mac_junk_do_not_crash():
    d = Path(tempfile.mkdtemp())
    (d / "ok.py").write_text("def f():\n    return 1\n")
    (d / "bad.py").write_text("def (:\n")
    (d / "._ok.py").write_bytes(b"\x00\x05\x16\x07 apple double")
    (d / "__MACOSX").mkdir()
    (d / "__MACOSX" / "x.py").write_bytes(b"\x00\x01")
    (d / "nul.py").write_bytes(b"x = 1\x00\n")
    G = build_graph(d)
    files = {n for n, dd in G.nodes(data=True) if dd["type"] == "file"}
    assert files == {"ok.py"}
    assert sorted(G.graph["parse_error_files"]) == ["bad.py", "nul.py"]
    assert check_invariants(G) == []


def test_empty_repo_and_missing_path():
    d = Path(tempfile.mkdtemp())
    G = build_graph(d)
    assert G.number_of_nodes() == 0 and check_invariants(G) == []
    try:
        build_graph(d / "nope")
        assert False, "expected FileNotFoundError"
    except FileNotFoundError:
        pass


def test_name_collisions_between_script_dirs_pick_the_closest_module():
    d = Path(tempfile.mkdtemp())
    for sub in ("a", "b"):
        (d / sub).mkdir()
        (d / sub / "util.py").write_text(f"def f():\n    return '{sub}'\n")
        (d / sub / "main.py").write_text("import util\n\ndef go():\n    return util.f()\n")
    G = build_graph(d)
    assert G.has_edge("a/main.py::go", "a/util.py::f", key="calls")
    assert G.has_edge("b/main.py::go", "b/util.py::f", key="calls")


def test_syntax_new_python_features_parse():
    d = Path(tempfile.mkdtemp())
    (d / "m.py").write_text(
        "import dataclasses\n"
        "@dataclasses.dataclass\n"
        "class P:\n    x: int = 0\n    def inc(self) -> 'P':\n        return P(self.x + 1)\n"
        "def f(v):\n    match v:\n        case P(x=1):\n            return P(1).inc()\n        case _:\n            return None\n"
        "async def g():\n    async with open_it() as h:\n        return await h.read()\n")
    G = build_graph(d)
    assert G.graph["stats"]["parse_errors"] == 0
    assert G.has_edge("m.py::f", "m.py::P.inc", key="calls")


def test_line_index_maps_diff_lines_to_nodes():
    G = graph("tiny_repo")
    idx = LineIndex(G)
    assert idx.at("pkg/core.py", 14) == "pkg/core.py::Engine.step"      # `return helper(1)`
    assert idx.at("pkg/core.py", 7) == "pkg/core.py::Engine.__init__"
    assert idx.at("pkg/core.py", 1) == "pkg/core.py"                      # import line -> file
    assert idx.at_range("pkg/utils.py", 1, 2) == {"pkg/utils.py::helper"}
    assert idx.at_range("pkg/utils.py", 5, 6) == {"pkg/utils.py::unused"}
    # lines 3-4 are blank lines between the two functions: they belong to the module
    assert idx.at_range("pkg/utils.py", 1, 5) == {"pkg/utils.py::helper", "pkg/utils.py", "pkg/utils.py::unused"}


def test_collapse_gives_reverse_impact_graph():
    G = graph("feature_repo")
    R = collapse(G, ("calls",), reverse=True)
    impacted = nx.descendants(R, "src/shop/util.py::helper")
    assert "src/shop/star.py::go" in impacted and "src/shop/util.py::outer" in impacted
    assert "src/shop/plugins/a.py::run" in impacted


def test_exports_write_every_file():
    G = graph("tiny_repo")
    out = export.write_all(G, Path(tempfile.mkdtemp()) / "o")
    for f in ("graph.json", "nodes.csv", "edges.csv", "graph.graphml", "summary.json", "report.md"):
        assert (out / f).stat().st_size > 0, f
    s = json.loads((out / "summary.json").read_text())
    assert s["nodes"] == 15 and nx.read_graphml(out / "graph.graphml").number_of_nodes() == 15
