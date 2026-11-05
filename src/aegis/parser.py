"""Phase 1 parser: turn a Python repository into a typed structural graph.

Pipeline (all standard-library ``ast``, no code is executed):
  1. discover + parse files, register definitions (classes, functions, methods),
     including those under if/try/with at module and class level
  2. resolve imports to repository files and record name bindings
  3. walk every body once with a small static type resolver and emit edges:
     calls, references, inherits, overrides, tests, and heuristic maybe_calls

Anything that cannot be resolved with confidence is NOT turned into a ``calls`` edge.
It is counted with a reason, so the limitation is measured instead of hidden.
"""
import ast
import hashlib
import os
import subprocess
import sys
import time
import warnings
from collections import Counter, defaultdict
from pathlib import Path

from . import graph as g
from .astutil import (FUNC, chain_root, decorator_names, dotted, has_yield, iter_block, span_of)
from .index import FileInfo, RepoIndex
from .resolver import BUILTIN_NAMES, Resolver, is_unk

BUILDER_VERSION = "2.0"
SKIP_DIRS = {"__MACOSX", ".git", ".hg", ".svn", "__pycache__", "site-packages", "node_modules",
             ".tox", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".eggs", "__pypackages__"}
CONDITIONAL_SKIP = {"build", "dist"}      # skipped only when they are not packages
VENV_NAMES = {"venv", ".venv", "env"}     # skipped only when they hold pyvenv.cfg

# receiver-unknown reasons for which a name-based heuristic edge is offered
MAYBE_REASONS = {"untyped_param", "loop_var", "unpack", "conflict", "subscript",
                 "call_result_unknown", "attr_unknown", "with_unknown", "exc_unknown",
                 "cycle", "property_unknown", "base_unresolved", "getattr", "binop"}
COMMON_METHOD_NAMES = set()
for _t in (str, bytes, list, dict, set, tuple, int, float, object, frozenset, bytearray):
    COMMON_METHOD_NAMES |= set(dir(_t))
COMMON_METHOD_NAMES |= {"read", "write", "close", "flush", "seek", "tell", "readline",
                        "readlines", "open", "send", "recv", "connect", "run", "start",
                        "stop", "wait", "join", "acquire", "release", "put", "get_nowait",
                        "put_nowait", "submit", "result", "cancel", "done", "emit",
                        "info", "debug", "warning", "error", "exception", "critical",
                        "log", "match", "search", "sub", "group", "groups", "findall",
                        "parse", "load", "loads", "dump", "dumps", "encode", "decode"}
MAX_MAYBE_CANDIDATES = 6
# syntax that silently calls a method of a repository class
BINOP_DUNDER = {ast.Add: "__add__", ast.Sub: "__sub__", ast.Mult: "__mul__", ast.Div: "__truediv__",
                ast.FloorDiv: "__floordiv__", ast.Mod: "__mod__", ast.Pow: "__pow__",
                ast.MatMult: "__matmul__", ast.BitOr: "__or__", ast.BitAnd: "__and__",
                ast.BitXor: "__xor__", ast.LShift: "__lshift__", ast.RShift: "__rshift__"}
ITER_CONSUMERS = {"list", "tuple", "set", "frozenset", "sorted", "enumerate", "zip", "map",
                  "filter", "any", "all", "sum", "min", "max", "dict"}
LEN_HINT = {"list", "tuple", "dict", "set", "frozenset"}
BUILTIN_DUNDER = {"len": "__len__", "iter": "__iter__", "next": "__next__", "str": "__str__",
                  "repr": "__repr__", "bool": "__bool__", "hash": "__hash__"}


def is_test_file(rel_path: str) -> bool:
    p = Path(rel_path)
    name = p.name
    return (name.startswith("test_") or name.endswith("_test.py") or name == "conftest.py"
            or "tests" in p.parts or "test" in p.parts)


def _iter_py_files(repo: Path):
    for root, dirs, fnames in os.walk(repo):
        keep = []
        for d in sorted(dirs):
            if d in SKIP_DIRS or d.startswith(".") or d.endswith(".egg-info"):
                continue
            full = Path(root) / d
            if d in CONDITIONAL_SKIP and not (full / "__init__.py").exists():
                continue
            if d in VENV_NAMES and (full / "pyvenv.cfg").exists():
                continue
            keep.append(d)
        dirs[:] = keep
        for fn in sorted(fnames):
            if fn.endswith(".py") and not fn.startswith("._"):   # "._x.py" = macOS AppleDouble junk
                yield Path(root) / fn


def _git_head(repo: Path):
    try:
        out = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                             capture_output=True, text=True, timeout=10)
        return out.stdout.strip() if out.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def _hash(node):
    return hashlib.sha1(ast.dump(node, annotate_fields=False).encode()).hexdigest()[:12]


def _doc(node):
    d = ast.get_docstring(node)
    return d.strip().splitlines()[0][:120] if d and d.strip() else ""


# ---------------------------------------------------------------- pass 1
def _register_defs(G, info, body, prefix, owner_id, cls_nid):
    for kind, node in iter_block(body):
        if kind not in ("func", "class"):
            continue
        qual = f"{prefix}{node.name}"
        nid = f"{info.rel}::{qual}"
        start, end = span_of(node)
        if kind == "func":
            ntype = "test" if (info.is_test and node.name.startswith("test")) else "function"
        else:
            ntype = "class"
        if nid in G:                                    # redefinition: property setters, if/else
            d = G.nodes[nid]
            d["spans"].append([start, end])
            d["end_lineno"] = max(d["end_lineno"], end)
            d["body_hash"] = hashlib.sha1((d["body_hash"] + _hash(node)).encode()).hexdigest()[:12]
            d["decorators"] = sorted(set(d["decorators"]) | set(decorator_names(node)))
            if "is_generator" in d:
                d["is_generator"] = d["is_generator"] or has_yield(node)
            info.ast_defs.setdefault(nid, []).append(node)
        else:
            attrs = dict(name=node.name, qualname=qual, path=info.rel, lineno=node.lineno,
                         end_lineno=end, spans=[[start, end]], decorators=decorator_names(node),
                         body_hash=_hash(node), doc=_doc(node), in_test_file=info.is_test)
            if kind == "func":
                a = node.args
                attrs.update(is_method=cls_nid is not None, is_async=isinstance(node, ast.AsyncFunctionDef),
                             is_generator=has_yield(node),
                             nparams=len(a.posonlyargs) + len(a.args) + len(a.kwonlyargs)
                             + bool(a.vararg) + bool(a.kwarg))
            g.add_node(G, nid, ntype, **attrs)
            g.add_edge(G, owner_id, nid, "contains")
            info.ast_defs[nid] = [node]
        info.defs[qual] = nid
        if not prefix:
            info.top[node.name] = nid
        if kind == "class":
            info.class_nodes[nid] = node
            _register_defs(G, info, node.body, f"{qual}.", nid, nid)


# ---------------------------------------------------------------- pass 2
def _module_vars(info):
    for kind, st in iter_block(info.tree.body):
        if kind != "stmt":
            continue
        if isinstance(st, ast.Assign):
            for t in st.targets:
                Resolver._bind_target(info.mod_vars, t, ("expr", st.value))
                if isinstance(t, ast.Name) and t.id == "__all__":
                    names = _static_str_list(st.value)
                    if names is not None:
                        info.all_names = set(names)
        elif isinstance(st, ast.AnnAssign) and isinstance(st.target, ast.Name) and st.value is not None:
            info.mod_vars[st.target.id].append(("annexpr", st.annotation, st.value))
        elif isinstance(st, ast.AugAssign) and isinstance(st.target, ast.Name) \
                and st.target.id == "__all__" and info.all_names is not None:
            names = _static_str_list(st.value)
            if names is not None:
                info.all_names |= set(names)


def _static_str_list(node):
    if isinstance(node, (ast.List, ast.Tuple)) and all(
            isinstance(e, ast.Constant) and isinstance(e.value, str) for e in node.elts):
        return [e.value for e in node.elts]
    return None


def _process_imports(G, info, index, stats):
    def edge(target, line):
        if target and target != info.rel:
            g.add_edge(G, info.rel, target, "imports", line)

    for node in ast.walk(info.tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                full = a.name
                f = index.resolve_module(full, info.rel)
                root = full.split(".")[0]
                if a.asname:
                    if f:
                        edge(f, node.lineno)
                        info.bindings[a.asname].append(("mod", f))
                        stats["imports_resolved"] += 1
                    elif index.ns_dir(full, info.rel) is not None:
                        info.bindings[a.asname].append(("mod", index.ns_dir(full, info.rel)))
                        stats["imports_resolved"] += 1
                    else:
                        info.bindings[a.asname].append(("ext", full))
                        stats["imports_external"] += 1
                else:
                    top = index.resolve_module(root, info.rel)
                    if f:
                        edge(f, node.lineno)
                    if top:
                        info.bindings[root].append(("mod", top))
                        stats["imports_resolved"] += 1
                    elif f or index.ns_dir(root, info.rel) is not None:
                        d = index.ns_dir(root, info.rel)
                        if d is not None:
                            info.bindings[root].append(("mod", d))
                            stats["imports_resolved"] += 1
                        else:
                            info.bindings[root].append(("ext", root))
                            stats["imports_external"] += 1
                    else:
                        info.bindings[root].append(("ext", root))
                        stats["imports_external"] += 1
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                f, d = index.relative_target(info.rel, node.level, node.module or "")
                in_repo = f is not None or d is not None
                label = "." * node.level + (node.module or "")
            else:
                f = index.resolve_module(node.module or "", info.rel) if node.module else None
                d = None
                if f is None and node.module:
                    d = index.ns_dir(node.module, info.rel)
                elif f is not None and f.rsplit("/", 1)[-1] == "__init__.py":
                    d = index.files[f].dir
                in_repo = f is not None or d is not None
                label = node.module or ""
            if f:
                edge(f, node.lineno)
            for a in node.names:
                if a.name == "*":
                    if f:
                        info.stars.append(f)
                    elif not in_repo:
                        info.ext_star = True
                    continue
                local = a.asname or a.name
                sub = index.submodule(d, a.name) if d is not None else None
                if sub:
                    if sub.endswith(".py"):
                        edge(sub, node.lineno)
                    info.bindings[local].append(("mod", sub))
                    stats["imports_resolved"] += 1
                elif f:
                    info.bindings[local].append(("sym", f, a.name))
                    stats["imports_resolved"] += 1
                elif in_repo:                      # namespace dir without that symbol
                    info.bindings[local].append(("sym", d, a.name))
                    stats["imports_resolved"] += 1
                else:
                    info.bindings[local].append(("ext", label))
                    stats["imports_external"] += 1
                    if node.level:
                        stats["imports_unresolved_relative"] += 1


# ---------------------------------------------------------------- pass 3
class Emitter:
    def __init__(self, G, R, stats, reasons, methods_by_name, call_log=None):
        self.G, self.R = G, R
        self.call_log = call_log
        self.stats, self.reasons = stats, reasons
        self.methods_by_name = methods_by_name
        self.owner = None
        self.scope = None
        self.owner_is_test = False

    def set_owner(self, owner, scope):
        self.owner, self.scope = owner, scope
        self.owner_is_test = self.G.nodes[owner]["type"] == "test"

    # -- edge helpers
    def _edge(self, target, etype, line):
        if target == self.owner:
            return
        g.add_edge(self.G, self.owner, target, etype, line)

    def _call_edges(self, targets, line):
        for t in targets:
            self._edge(t, "calls", line)
            if self.owner_is_test:
                self._edge(t, "tests", line)

    # -- visiting
    def visit(self, node):
        if node is None:
            return
        if isinstance(node, ast.Call):
            self.on_call(node)
            self._visit_callee(node.func)
            for a in node.args:
                self.visit(a)
            for k in node.keywords:
                self.visit(k.value)
        elif isinstance(node, (ast.Name, ast.Attribute)) and isinstance(node.ctx, ast.Load):
            self.on_ref(node)
            self._property_calls(node, include_last=True)
            root = chain_root(node)
            if not isinstance(root, ast.Name):
                self.visit(root)
        elif isinstance(node, FUNC):
            self.visit_funcdef_header(node)
            for st in node.body:
                self.visit(st)
        else:
            self.on_protocol(node)
            for ch in ast.iter_child_nodes(node):
                self.visit(ch)

    def _visit_callee(self, func):
        self._property_calls(func, include_last=False)
        root = chain_root(func)
        if not isinstance(root, ast.Name):
            self.visit(root)

    # -- implicit calls: properties and operator/protocol syntax
    def _implicit(self, recv, dunder, line):
        if recv[0] != "inst":
            return
        m = self.R.member(recv[1], dunder, True, None)
        if m[0] == "func":
            self.stats["calls_implicit"] += 1
            self._call_edges([m[1]], line)

    def _property_calls(self, node, include_last):
        n, first = node, True
        while isinstance(n, ast.Attribute):
            if include_last or not first:
                nid = self.R.property_target(self.R.eval(n.value, self.scope), n.attr)
                if nid:
                    self.stats["calls_implicit"] += 1
                    self._call_edges([nid], n.lineno)
            first = False
            n = n.value

    def on_protocol(self, node):
        R, sc = self.R, self.scope
        if isinstance(node, (ast.With, ast.AsyncWith)):
            a = "a" if isinstance(node, ast.AsyncWith) else ""
            for it in node.items:
                t = R.eval(it.context_expr, sc)
                self._implicit(t, f"__{a}enter__", node.lineno)
                self._implicit(t, f"__{a}exit__", node.lineno)
        elif isinstance(node, ast.Attribute) and isinstance(node.ctx, (ast.Store, ast.Del)):
            nid = R.property_target(R.eval(node.value, sc), node.attr)        # property setter
            if nid:
                self.stats["calls_implicit"] += 1
                self._call_edges([nid], node.lineno)
        elif isinstance(node, ast.Subscript):
            name = {ast.Load: "__getitem__", ast.Store: "__setitem__", ast.Del: "__delitem__"}[type(node.ctx)]
            self._implicit(R.eval(node.value, sc), name, node.lineno)
        elif isinstance(node, (ast.For, ast.AsyncFor)):
            self._implicit(R.eval(node.iter, sc), "__aiter__" if isinstance(node, ast.AsyncFor) else "__iter__", node.lineno)
        elif isinstance(node, ast.BinOp):
            d = BINOP_DUNDER.get(type(node.op))
            if d:
                self._implicit(R.eval(node.left, sc), d, node.lineno)
        elif isinstance(node, ast.Compare):
            for op, comp in zip(node.ops, node.comparators):
                if isinstance(op, (ast.In, ast.NotIn)):
                    self._implicit(R.eval(comp, sc), "__contains__", node.lineno)

    def visit_funcdef_header(self, node):
        for d in node.decorator_list:
            self.on_decorator(d)
        a = node.args
        for dflt in a.defaults + [x for x in a.kw_defaults if x is not None]:
            self.visit(dflt)
        for arg in a.posonlyargs + a.args + a.kwonlyargs + [x for x in (a.vararg, a.kwarg) if x]:
            self.visit_annotation(arg.annotation)
        self.visit_annotation(node.returns)

    def visit_annotation(self, ann):
        if ann is None:
            return
        if isinstance(ann, ast.Constant) and isinstance(ann.value, str):
            try:
                parsed = ast.parse(ann.value.strip(), mode="eval").body
            except (SyntaxError, ValueError):
                return
            self.R._keep.append(parsed)
            self.visit(parsed)
        else:
            self.visit(ann)

    def on_decorator(self, d):
        if isinstance(d, ast.Call):
            self.visit(d)
            self._implicit(self.R.eval(d, self.scope), "__call__", d.lineno)   # @Deco(args) instance
            return
        t = self.R.eval(d, self.scope)
        kind, targets, reason = self.R.outcome_of(t)
        self.stats["decorators_total"] += 1
        self.stats[f"decorators_{kind}"] += 1
        self._call_edges(targets, d.lineno)
        root = chain_root(d)
        if not isinstance(root, ast.Name):
            self.visit(root)

    def on_ref(self, node):
        t = self.R.eval(node, self.scope)
        if t[0] in ("func", "cls"):
            self._edge(t[1], "references", node.lineno)
            self.stats["references_total"] += 1

    def on_call(self, call):
        kind, targets, reason = self.R.call_outcome(call, self.scope)
        self.stats["calls_total"] += 1
        self.stats[f"calls_{kind}"] += 1
        line = call.lineno
        if isinstance(call.func, ast.Name) and call.func.id in BUILTIN_DUNDER and len(call.args) == 1 \
                and kind == "external":
            self._implicit(self.R.eval(call.args[0], self.scope), BUILTIN_DUNDER[call.func.id], line)
        if isinstance(call.func, ast.Name) and call.func.id in ITER_CONSUMERS and kind == "external":
            for a in call.args:
                t = self.R.eval(a, self.scope)
                self._implicit(t, "__iter__", line)
                if call.func.id in LEN_HINT:
                    self._implicit(t, "__len__", line)
        if self.call_log is not None:
            try:
                text = ast.unparse(call.func)[:80]
            except Exception:
                text = "?"
            self.call_log.append((self.owner, line, kind, reason, text, list(targets)))
        if kind == "resolved":
            self._call_edges(targets, line)
        elif kind == "unresolved":
            self.reasons[reason] += 1
            f = call.func
            if isinstance(f, ast.Attribute) and reason in MAYBE_REASONS:
                name = f.attr
                if not (name.startswith("__") and name.endswith("__")) \
                        and name not in COMMON_METHOD_NAMES:
                    cands = [c for c in self.methods_by_name.get(name, ())
                             if self.owner_is_test or not self.G.nodes[c]["in_test_file"]]
                    if 0 < len(cands) <= MAX_MAYBE_CANDIDATES:
                        self.stats["calls_unresolved_with_candidates"] += 1
                        for c in cands:
                            if c != self.owner:
                                g.add_edge(self.G, self.owner, c, "maybe_calls", line,
                                           ncand=len(cands))


def _emit_file(G, R, em, info):
    mscope = R.module_scope(info)
    # symbols imported by name are references from the file
    em.set_owner(info.rel, mscope)
    for name, bs in sorted(info.bindings.items()):
        for b in bs:
            if b[0] == "sym":
                t = R.module_attr(b[1], b[2])
                if t[0] in ("func", "cls"):
                    em._edge(t[1], "references", None)
                    em.stats["references_total"] += 1

    def walk(body, scope, owner, prefix, cls_nid):
        for kind, node in iter_block(body):
            if kind in ("stmt", "expr"):
                em.set_owner(owner, scope)
                em.visit(node)
            elif kind == "func":
                qual = f"{prefix}{node.name}"
                nid = info.defs[qual]
                fscope = R.func_scope(info, node, cls_nid, qual)
                em.set_owner(nid, scope)             # decorators/defaults live in the def scope
                em.visit_funcdef_header(node)
                em.set_owner(nid, fscope)
                for st in node.body:
                    em.visit(st)
            else:
                qual = f"{prefix}{node.name}"
                nid = info.defs[qual]
                em.set_owner(nid, scope)
                for d in node.decorator_list:
                    em.on_decorator(d)
                for b in node.bases:
                    em.visit(b.value if isinstance(b, ast.Subscript) and False else b)
                for kw in node.keywords:
                    em.visit(kw.value)
                cscope = R.class_scope(info, node, nid, qual)
                walk(node.body, cscope, nid, f"{qual}.", nid)

    walk(info.tree.body, mscope, info.rel, "", None)


def _emit_class_edges(G, R, stats, info):
    for cnid in sorted(n for n in info.class_nodes):
        bases = R.class_bases(cnid)
        ext, unres = [], []
        for b in bases:
            stats["bases_total"] += 1
            if b[0] == "cls":
                g.add_edge(G, cnid, b[1], "inherits", info.class_nodes[cnid].lineno)
                stats["bases_resolved"] += 1
            elif b[0] == "ext":
                ext.append(b[1])
                stats["bases_external"] += 1
            else:
                unres.append(b[1])
                stats["bases_unresolved"] += 1
        G.nodes[cnid]["ext_bases"] = ext
        G.nodes[cnid]["unresolved_bases"] = unres
        qual = G.nodes[cnid]["qualname"]
        mro = R.mro(cnid)[1:]
        for kind, st in iter_block(info.class_nodes[cnid].body):
            if kind != "func":
                continue
            mnid = info.defs[f"{qual}.{st.name}"]
            for e in mro:
                if e[0] != "cls":
                    continue
                other = R.files[G.nodes[e[1]]["path"]]
                base_m = other.defs.get(f"{G.nodes[e[1]]['qualname']}.{st.name}")
                if base_m and G.nodes[base_m]["type"] in ("function", "test"):
                    g.add_edge(G, mnid, base_m, "overrides", st.lineno)
                    stats["overrides_total"] += 1
                    break


# ---------------------------------------------------------------- entry point
def build_graph(repo_path, maybe_calls=True, keep_call_log=False):
    sys.setrecursionlimit(max(sys.getrecursionlimit(), 6000))
    t0 = time.time()
    repo = Path(repo_path).resolve()
    if not repo.is_dir():
        raise FileNotFoundError(f"Not a directory: {repo}")

    G = g.new_graph()
    stats = Counter()
    reasons = Counter()
    files = {}
    parse_error_files = []

    # pass 1: parse + definitions
    for full in _iter_py_files(repo):
        rel = full.relative_to(repo).as_posix()
        try:
            data = full.read_bytes()
        except OSError:
            stats["read_errors"] += 1
            continue
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                tree = ast.parse(data, filename=rel)
        except (SyntaxError, ValueError, RecursionError, MemoryError, OverflowError):
            stats["parse_errors"] += 1
            parse_error_files.append(rel)
            continue
        loc = data.count(b"\n") + (1 if data and not data.endswith(b"\n") else 0)
        info = FileInfo(rel, tree, is_test_file(rel), data, loc)
        files[rel] = info
        stats["files_parsed"] += 1
        stats["loc_total"] += loc
    index = RepoIndex(files)
    for rel in sorted(files):
        info = files[rel]
        g.add_node(G, rel, "file", name=Path(rel).name, path=rel, is_test=info.is_test,
                   sha1=info.sha1, loc=info.loc, module=(info.modnames[0] if info.modnames else ""),
                   modules=info.modnames)
        _register_defs(G, info, info.tree.body, "", rel, None)

    # pass 2: imports and module-level variables
    for rel in sorted(files):
        _module_vars(files[rel])
        _process_imports(G, files[rel], index, stats)
    for u, v, k in list(G.edges(keys=True)):
        if k == "imports" and files[u].is_test and not files[v].is_test:
            g.add_edge(G, u, v, "tests")

    # pass 3: calls / references / inheritance
    R = Resolver(G, index)
    methods_by_name = defaultdict(list)
    if maybe_calls:
        for n, d in G.nodes(data=True):
            if d["type"] in ("function", "test") and d.get("is_method"):
                methods_by_name[d["name"]].append(n)
    call_log = [] if keep_call_log else None
    em = Emitter(G, R, stats, reasons, methods_by_name, call_log)
    for rel in sorted(files):
        try:
            _emit_file(G, R, em, files[rel])
            _emit_class_edges(G, R, stats, files[rel])
        except RecursionError:
            stats["recursion_errors"] += 1

    for key in ("calls_total", "calls_resolved", "calls_external", "calls_local", "calls_implicit",
                "calls_unresolved", "calls_unresolved_with_candidates", "references_total",
                "bases_total", "overrides_total", "decorators_total", "imports_resolved",
                "imports_external", "imports_unresolved_relative", "parse_errors",
                "files_parsed", "loc_total", "recursion_errors"):
        stats.setdefault(key, 0)
    G.graph.update(
        repo=repo.name, builder_version=BUILDER_VERSION, head=_git_head(repo),
        parse_error_files=parse_error_files,
        stats=dict(stats), unresolved_reasons=dict(reasons.most_common()),
        build_seconds=round(time.time() - t0, 2))
    G.graph["stats"]["unresolved_reasons"] = dict(reasons.most_common())
    if call_log is not None:
        G.graph["call_log"] = call_log      # debug only; not written by save_graph
    return G
