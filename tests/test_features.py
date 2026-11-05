"""feature_repo: every resolver feature, with expectations derived by hand from Python semantics."""
from helpers import edges, graph, has

S = "src/shop/"
MOD, UT, BA = S + "models.py", S + "util.py", S + "base.py"


def G():
    return graph("feature_repo")


def test_src_layout_and_module_names():
    g = G()
    assert g.nodes[MOD]["module"] == "shop.models"            # 'src' is not part of the name
    assert "shop.plugins.a" in g.nodes[S + "plugins/a.py"]["modules"]


def test_imports_relative_absolute_and_dotted():
    g = G()
    assert has(g, S + "__init__.py", MOD, "imports")
    assert has(g, UT, BA, "imports")                          # from . import base
    assert has(g, "tests/test_shop.py", S + "__init__.py", "imports")
    assert has(g, S + "plugins/a.py", MOD, "imports")         # from ..models import Item
    assert has(g, S + "plugins/a.py", S + "plugins/b.py", "imports")
    assert has(g, S + "plugins/a.py", UT, "imports")          # import shop.util
    assert has(g, S + "star.py", UT, "imports")


def test_super_inheritance_and_overrides():
    g = G()
    assert has(g, MOD + "::Item", BA + "::Entity", "inherits")
    assert has(g, MOD + "::Item.__init__", BA + "::Entity.__init__", "calls")        # super().__init__()
    assert has(g, MOD + "::Item.label", BA + "::Entity.label", "overrides")
    assert has(g, MOD + "::Item.__init__", BA + "::Entity.__init__", "overrides")


def test_static_class_methods_and_cls_call():
    g = G()
    assert has(g, MOD + "::Item.make", MOD + "::Item", "calls")
    assert has(g, MOD + "::Item.make", MOD + "::Item.__init__", "calls")
    assert has(g, MOD + "::Item.free", MOD + "::Item.__init__", "calls")              # cls(0)
    assert has(g, MOD + "::Item.describe", MOD + "::Item.label", "calls")            # self.label()


def test_typed_attributes_and_loop_variables():
    g = G()
    assert has(g, MOD + "::Order.__init__", MOD + "::Item.__init__", "calls")
    # self.items: list[Item]  ->  `for it in self.items: it.describe()`
    assert has(g, MOD + "::Order.describe_all", MOD + "::Item.describe", "calls")
    # list.append is external, so no edge may point at Item from add()
    assert not has(g, MOD + "::Order.add", MOD + "::Item.describe", "calls")


def test_property_access_is_an_implicit_call():
    g = G()
    assert has(g, MOD + "::Order.total", MOD + "::Item.doubled", "calls")   # i.doubled and self.owner.doubled


def test_return_type_chain_and_forward_reference():
    g = G()
    f = MOD + "::Order.first"
    assert has(g, f, MOD + "::Order.add", "calls")        # o = Order(); o.add(...)
    assert has(g, f, MOD + "::Item.make", "calls")
    assert has(g, f, MOD + "::Order.total", "calls")      # add() -> "Order" (string annotation)


def test_decorator_edges():
    g = G()
    assert has(g, MOD + "::Order", BA + "::register", "calls")


def test_with_statement_and_subscript_protocols():
    g = G()
    c = UT + "::ctx"
    assert has(g, c, BA + "::Entity.__enter__", "calls")
    assert has(g, c, BA + "::Entity.__exit__", "calls")
    assert has(g, c, BA + "::Entity.__getitem__", "calls")    # e is typed through __enter__ -> self


def test_redefinitions_merge_into_one_node_with_two_spans():
    g = G()
    d = g.nodes[UT + "::total"]
    assert len(d["spans"]) == 2
    assert UT + "::parse" in g                                # def inside except ImportError


def test_nested_function_and_shadowing_are_not_guessed():
    g = G()
    assert has(g, UT + "::outer", UT + "::helper", "calls")
    shadow = UT + "::shadow"
    assert not has(g, shadow, UT + "::helper", "calls")       # parameter named helper shadows the function
    assert g.graph["stats"]["calls_local"] >= 1               # inner() is a local function


def test_unknown_receivers_are_counted_not_invented():
    g = G()
    assert not [v for _, v in edges(g, "calls") if v.endswith("unknown_method")]
    assert g.graph["unresolved_reasons"].get("untyped_param", 0) >= 2


def test_heuristic_edges_are_separate_from_calls():
    g = G()
    assert has(g, UT + "::use2", S + "page.py::Page.render_page", "maybe_calls")
    assert not has(g, UT + "::use2", S + "page.py::Page.render_page", "calls")
    assert g[UT + "::use2"][S + "page.py::Page.render_page"]["maybe_calls"]["ncand"] == 1


def test_star_import_and_reexport_chain():
    g = G()
    assert has(g, S + "star.py::go", UT + "::helper", "calls")                         # from .util import *
    assert has(g, S + "plugins/a.py::run", S + "plugins/b.py::work", "calls")          # from . import b
    assert has(g, S + "plugins/a.py::run", UT + "::helper", "calls")                   # import shop.util
    t = "tests/test_shop.py::test_order"
    assert has(g, t, MOD + "::Order", "calls")      # Order re-exported by shop/__init__


def test_test_nodes_link_to_code_under_test():
    g = G()
    t, c = "tests/test_shop.py::test_order", "tests/test_shop.py::TestItem.test_label"
    assert g.nodes[t]["type"] == "test" and g.nodes[c]["type"] == "test"
    assert g.nodes["tests/test_shop.py::TestItem"]["type"] == "class"
    assert has(g, t, MOD + "::Order.add", "tests")
    assert has(g, t, MOD + "::Order.total", "tests")
    assert has(g, c, MOD + "::Item.free", "tests")
    assert has(g, c, MOD + "::Item.label", "tests")           # Item.free() returns cls(0)
