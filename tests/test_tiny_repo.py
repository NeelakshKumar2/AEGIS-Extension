"""tiny_repo: a 4-file repo whose graph can be checked by hand."""
from helpers import edges, graph, has

M = "pkg/core.py"


def test_node_inventory():
    G = graph("tiny_repo")
    types = {n: d["type"] for n, d in G.nodes(data=True)}
    assert types["pkg/utils.py"] == "file"
    assert types[f"{M}::Engine"] == "class"
    assert types[f"{M}::Engine.run"] == "function"
    assert types["tests/test_core.py::test_helper"] == "test"
    assert G.number_of_nodes() == 15


def test_contains_and_spans():
    G = graph("tiny_repo")
    assert has(G, M, f"{M}::Engine", "contains")
    assert has(G, f"{M}::Engine", f"{M}::Engine.run", "contains")
    d = G.nodes["pkg/utils.py::helper"]
    assert (d["lineno"], d["end_lineno"]) == (1, 2)


def test_imports():
    G = graph("tiny_repo")
    assert has(G, "pkg/app.py", M, "imports")                # relative import
    assert has(G, M, "pkg/utils.py", "imports")              # from pkg.utils import helper
    assert has(G, "tests/test_core.py", M, "imports")
    assert not any(v.endswith("os") for _, v in edges(G, "imports"))   # stdlib: no edge


def test_calls_including_typed_local():
    G = graph("tiny_repo")
    assert has(G, f"{M}::Engine.run", f"{M}::Engine.step", "calls")       # self.step()
    assert has(G, f"{M}::Engine.step", "pkg/utils.py::helper", "calls")   # imported name
    assert has(G, f"{M}::Engine.other", "pkg/utils.py::unused", "calls")  # module.func()
    assert has(G, "pkg/app.py::main", f"{M}::Engine", "calls")            # Engine()
    assert has(G, "pkg/app.py::main", f"{M}::Engine.__init__", "calls")
    # e = Engine(); e.run()  -> resolved through local type inference (was unresolved in v0)
    assert has(G, "pkg/app.py::main", f"{M}::Engine.run", "calls")


def test_tests_edges():
    G = graph("tiny_repo")
    assert has(G, "tests/test_core.py::test_helper", "pkg/utils.py::helper", "tests")
    assert has(G, "tests/test_core.py", M, "tests")
    assert not has(G, f"{M}::Engine.run", f"{M}::Engine.step", "tests")


def test_call_statistics_are_exact():
    st = graph("tiny_repo").graph["stats"]
    assert st["calls_total"] == 8
    assert (st["calls_resolved"], st["calls_external"], st["calls_unresolved"]) == (7, 1, 0)
