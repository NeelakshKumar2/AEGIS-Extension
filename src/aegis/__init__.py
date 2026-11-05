"""AEGIS - Phase 1: repository -> structural graph."""
from .graph import (EDGE_TYPES, NODE_TYPES, STRICT_EDGE_TYPES, LineIndex, callees_of, callers_of,
                    collapse, load_graph, neighbors, save_graph, summary)
from .parser import BUILDER_VERSION, build_graph
from .validate import check_invariants, graph_digest

__version__ = BUILDER_VERSION
__all__ = ["build_graph", "load_graph", "save_graph", "summary", "check_invariants", "graph_digest",
           "LineIndex", "neighbors", "callers_of", "callees_of", "collapse",
           "NODE_TYPES", "EDGE_TYPES", "STRICT_EDGE_TYPES", "__version__"]
