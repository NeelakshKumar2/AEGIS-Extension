"""Shared helpers for the AEGIS tests (no third-party dependencies)."""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))

from aegis.parser import build_graph  # noqa: E402

FIXTURES = HERE / "fixtures"
_cache = {}


def graph(name, **kw):
    key = (name, tuple(sorted(kw.items())))
    if key not in _cache:
        _cache[key] = build_graph(FIXTURES / name, **kw)
    return _cache[key]


def has(G, u, v, etype):
    return G.has_edge(u, v, key=etype)


def edges(G, etype):
    return {(u, v) for u, v, k in G.edges(keys=True) if k == etype}
