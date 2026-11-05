"""Small AST helpers shared by the parser and resolver."""
import ast

FUNC = (ast.FunctionDef, ast.AsyncFunctionDef)
_COMPOUND_NAMES = ("If", "For", "AsyncFor", "While", "With", "AsyncWith", "Try", "TryStar", "Match")
COMPOUND = tuple(getattr(ast, n) for n in _COMPOUND_NAMES if hasattr(ast, n))


def dotted(node):
    """'a.b.c' for a pure Name/Attribute chain, else None."""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return None


def chain_root(node):
    """Strip Attribute layers: for ``a.b(c).d`` returns the Call; for ``a.b.c`` the Name a."""
    while isinstance(node, ast.Attribute):
        node = node.value
    return node


def header_exprs(st):
    """Expressions evaluated by a compound statement itself (not its nested bodies)."""
    if isinstance(st, (ast.If, ast.While)):
        return [st.test]
    if isinstance(st, (ast.For, ast.AsyncFor)):
        return [st.iter]
    if isinstance(st, (ast.With, ast.AsyncWith)):
        return [i.context_expr for i in st.items]
    if hasattr(ast, "Match") and isinstance(st, ast.Match):
        return [st.subject] + [c.guard for c in st.cases if c.guard is not None]
    # Try / TryStar
    return [h.type for h in getattr(st, "handlers", []) if h.type is not None]


def sub_bodies(st):
    if isinstance(st, (ast.If, ast.While, ast.For, ast.AsyncFor)):
        return [st.body, st.orelse]
    if isinstance(st, (ast.With, ast.AsyncWith)):
        return [st.body]
    if hasattr(ast, "Match") and isinstance(st, ast.Match):
        return [c.body for c in st.cases]
    return [st.body] + [h.body for h in st.handlers] + [st.orelse, st.finalbody]


def iter_block(body):
    """Walk a module/class body, descending into if/try/with/for/while/match.

    Yields ("func", node) | ("class", node) | ("expr", node) for compound-statement
    headers | ("stmt", node) for every other statement. Definitions that sit inside
    ``if``/``try`` (very common: compat shims, version switches) are therefore seen.
    """
    for st in body:
        if isinstance(st, FUNC):
            yield "func", st
        elif isinstance(st, ast.ClassDef):
            yield "class", st
        elif isinstance(st, COMPOUND):
            for e in header_exprs(st):
                yield "expr", e
            for sub in sub_bodies(st):
                yield from iter_block(sub)
        else:
            yield "stmt", st


def decorator_names(node):
    out = []
    for d in node.decorator_list:
        target = d.func if isinstance(d, ast.Call) else d
        out.append(dotted(target) or "<expr>")
    return out


def span_of(node):
    start = node.lineno
    for d in getattr(node, "decorator_list", []):
        start = min(start, d.lineno)
    return start, getattr(node, "end_lineno", node.lineno)


def has_yield(fnode):
    """True if the function body itself (not nested defs/lambdas) contains yield."""
    stack = list(fnode.body)
    while stack:
        n = stack.pop()
        if isinstance(n, (ast.Yield, ast.YieldFrom)):
            return True
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
            continue
        stack.extend(ast.iter_child_nodes(n))
    return False


def return_values(fnode):
    """Return statements' values (None for bare return) of the function body itself."""
    out = []
    stack = list(fnode.body)
    while stack:
        n = stack.pop()
        if isinstance(n, ast.Return):
            out.append(n.value)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
            continue
        stack.extend(ast.iter_child_nodes(n))
    return out[::-1]
