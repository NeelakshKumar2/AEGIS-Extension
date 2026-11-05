"""Type/target resolver for AEGIS Phase 1.

A deliberately small, *sound-leaning* static type inference. It answers one question:
"what repository entity does this expression denote?" and only answers when it is
sure. Everything else becomes an explicit unknown carrying a reason, so the
limitation is measurable instead of hidden.

Types are tuples:
    ("cls", nid)    a repository class object          ("inst", nid) instance of it
    ("func", nid)   a repository function / method     ("mod", path) module or namespace dir
    ("ext", name)   something outside the repo (builtins, stdlib, third party)
    ("super", nid)  result of super() inside class nid
    ("local", what) nested function / lambda defined in the same function
    ("unk", reason) unknown, with the reason it could not be resolved
"""
import ast
import builtins
import dataclasses

from . import graph as g
from .astutil import (FUNC, chain_root, decorator_names, dotted, has_yield, iter_block,
                      return_values)

BUILTIN_NAMES = set(dir(builtins)) | {
    "__file__", "__path__", "__package__", "__spec__", "__loader__", "__doc__",
    "__builtins__", "__cached__", "__annotations__", "__class__"}
SKIP = ("skip",)
EXT = ("ext", "builtins")
PROPERTY_NAMES = ("property", "cached_property", "abstractproperty")
COLL_BASES = {"list", "List", "Sequence", "Iterable", "Iterator", "Collection", "Set", "set",
              "FrozenSet", "frozenset", "MutableSequence", "MutableSet", "AbstractSet", "Deque",
              "deque", "Tuple", "tuple", "Reversible"}
MAP_BASES = {"dict", "Dict", "Mapping", "MutableMapping", "OrderedDict", "defaultdict",
             "DefaultDict", "ChainMap"}
TYPEVAR_FACTORIES = ("TypeVar", "ParamSpec", "TypeVarTuple", "NewType")


def unk(reason):
    return ("unk", reason)


def is_unk(t):
    return t[0] == "unk"


@dataclasses.dataclass
class Scope:
    kind: str                       # module | class | func
    info: object
    cls: str = None                 # enclosing class node id (methods / class bodies)
    qual: str = ""
    node: ast.AST = None
    locals: dict = None             # name -> [source]
    globals_decl: set = None


def _def_type(G, nid):
    return ("cls", nid) if G.nodes[nid]["type"] == "class" else ("func", nid)


def c3_merge(seqs):
    seqs = [list(s) for s in seqs if s]
    out = []
    while seqs:
        for s in seqs:
            head = s[0]
            if not any(head in t[1:] for t in seqs):
                break
        else:
            return None
        out.append(head)
        seqs = [[x for x in s if x != head] for s in seqs]
        seqs = [s for s in seqs if s]
    return out


class Resolver:
    def __init__(self, G, index):
        self.G = G
        self.index = index
        self.files = index.files
        self._memo = {}
        self._inprog = set()
        self._mro = {}
        self._bases = {}
        self._ret = {}
        self._inst_attrs = {}
        self._class_vars = {}
        self._modattr = {}
        self._mname = {}
        self._scopes = {}
        self._modscopes = {}
        self._keep = []             # keeps parsed string annotations alive (stable ids)
        self._star_guard = set()

    # ------------------------------------------------------------ scopes
    def module_scope(self, info, cls=None):
        key = (info.rel, cls)
        s = self._modscopes.get(key)
        if s is None:
            s = Scope("module", info, cls=cls)
            self._modscopes[key] = s
        return s

    def class_scope(self, info, node, nid, qual):
        key = id(node)
        s = self._scopes.get(key)
        if s is None:
            s = Scope("class", info, cls=nid, qual=qual, node=node, locals={}, globals_decl=set())
            for kind, st in iter_block(node.body):
                if kind != "stmt":
                    continue
                if isinstance(st, ast.Assign):
                    for t in st.targets:
                        self._bind_target(s.locals, t, ("expr", st.value))
                elif isinstance(st, ast.AnnAssign) and isinstance(st.target, ast.Name):
                    s.locals.setdefault(st.target.id, []).append(("annexpr", st.annotation, st.value))
            self._scopes[key] = s
        return s

    def func_scope(self, info, fnode, cls_nid, qual):
        key = id(fnode)
        s = self._scopes.get(key)
        if s is None:
            s = Scope("func", info, cls=cls_nid, qual=qual, node=fnode)
            s.locals, s.globals_decl = self._collect_locals(fnode, cls_nid)
            self._scopes[key] = s
        return s

    @staticmethod
    def _bind_target(locs, t, src):
        if isinstance(t, ast.Name):
            locs.setdefault(t.id, []).append(src)
        elif isinstance(t, (ast.Tuple, ast.List)):
            for e in t.elts:
                Resolver._bind_target(locs, e, ("unk", "unpack"))
        elif isinstance(t, ast.Starred):
            Resolver._bind_target(locs, t.value, ("unk", "unpack"))

    def _collect_locals(self, fnode, cls_nid):
        locs, glob = {}, set()
        deco = [d.rsplit(".", 1)[-1] for d in decorator_names(fnode)]
        selfkind = None
        if cls_nid and "staticmethod" not in deco:
            selfkind = "cls" if ("classmethod" in deco or fnode.name in (
                "__new__", "__init_subclass__", "__class_getitem__")) else "inst"
        a = fnode.args
        pos = a.posonlyargs + a.args
        defaults = [None] * (len(pos) - len(a.defaults)) + list(a.defaults)
        for i, arg in enumerate(pos):
            locs.setdefault(arg.arg, []).append(
                ("param", arg.annotation, defaults[i], selfkind if i == 0 else None))
        for arg, dflt in zip(a.kwonlyargs, a.kw_defaults):
            locs.setdefault(arg.arg, []).append(("param", arg.annotation, dflt, None))
        if a.vararg:
            locs.setdefault(a.vararg.arg, []).append(("fixed", ("ext", "varargs")))
        if a.kwarg:
            locs.setdefault(a.kwarg.arg, []).append(("fixed", ("ext", "kwargs")))

        def add_args(args, reason):
            for x in args.posonlyargs + args.args + args.kwonlyargs:
                locs.setdefault(x.arg, []).append(("unk", reason))
            for x in (args.vararg, args.kwarg):
                if x:
                    locs.setdefault(x.arg, []).append(("unk", reason))

        stack = list(fnode.body)
        while stack:
            n = stack.pop()
            stack.extend(ast.iter_child_nodes(n))
            if isinstance(n, ast.Assign):
                for t in n.targets:
                    self._bind_target(locs, t, ("expr", n.value))
            elif isinstance(n, ast.AnnAssign):
                if isinstance(n.target, ast.Name):
                    locs.setdefault(n.target.id, []).append(("annexpr", n.annotation, n.value))
            elif isinstance(n, ast.AugAssign):
                if isinstance(n.target, ast.Name):
                    locs.setdefault(n.target.id, []).append(SKIP)
            elif isinstance(n, (ast.For, ast.AsyncFor, ast.comprehension)):
                if isinstance(n.target, ast.Name):
                    locs.setdefault(n.target.id, []).append(("iter", n.iter))
                else:
                    self._bind_target(locs, n.target, ("unk", "loop_var"))
            elif isinstance(n, (ast.With, ast.AsyncWith)):
                for it in n.items:
                    if it.optional_vars is None:
                        continue
                    if isinstance(it.optional_vars, ast.Name):
                        locs.setdefault(it.optional_vars.id, []).append(("with", it.context_expr))
                    else:
                        self._bind_target(locs, it.optional_vars, ("unk", "unpack"))
            elif isinstance(n, ast.ExceptHandler):
                if n.name:
                    locs.setdefault(n.name, []).append(("exc", n.type))
            elif isinstance(n, ast.NamedExpr):
                self._bind_target(locs, n.target, ("expr", n.value))
            elif isinstance(n, FUNC):
                locs.setdefault(n.name, []).append(("fixed", ("local", "function")))
                add_args(n.args, "nested_param")
            elif isinstance(n, ast.Lambda):
                add_args(n.args, "lambda_param")
            elif isinstance(n, ast.ClassDef):
                locs.setdefault(n.name, []).append(("unk", "nested_class"))
            elif isinstance(n, ast.Global):
                glob.update(n.names)
            elif type(n).__name__ in ("MatchAs", "MatchStar") and getattr(n, "name", None):
                locs.setdefault(n.name, []).append(("unk", "match_capture"))
            elif type(n).__name__ == "MatchMapping" and getattr(n, "rest", None):
                locs.setdefault(n.rest, []).append(("unk", "match_capture"))
        return locs, glob

    # ------------------------------------------------------------ memoised eval
    def eval(self, node, scope):
        key = (id(node), id(scope))
        t = self._memo.get(key)
        if t is not None:
            return t
        if key in self._inprog:
            return unk("cycle")
        self._inprog.add(key)
        try:
            t = self._eval(node, scope)
        finally:
            self._inprog.discard(key)
        self._memo[key] = t
        return t

    def _unify(self, types):
        known = [t for t in types if t is not SKIP]
        if not known:
            return unk("no_value")
        for t in known:
            if is_unk(t):
                return t
        first = known[0]
        for t in known[1:]:
            if t != first:
                return unk("conflict")
        return first

    def _eval(self, node, scope):
        if isinstance(node, ast.Name):
            return self.eval_name(node.id, scope)
        if isinstance(node, ast.Attribute):
            return self.attr_of(self.eval(node.value, scope), node.attr, scope)
        if isinstance(node, ast.Call):
            return self._eval_call(node, scope)
        if isinstance(node, ast.Constant):
            return EXT
        if isinstance(node, (ast.List, ast.Dict, ast.Set, ast.Tuple, ast.ListComp, ast.DictComp,
                             ast.SetComp, ast.GeneratorExp, ast.JoinedStr, ast.FormattedValue,
                             ast.Compare)):
            return EXT
        if isinstance(node, ast.UnaryOp):
            return EXT if isinstance(node.op, ast.Not) else self.eval(node.operand, scope)
        if isinstance(node, ast.BinOp):
            l, r = self.eval(node.left, scope), self.eval(node.right, scope)
            return EXT if l[0] == "ext" and r[0] == "ext" else unk("binop")
        if isinstance(node, ast.BoolOp):
            return self._unify([self._none_skip(v, scope) for v in node.values])
        if isinstance(node, ast.IfExp):
            return self._unify([self._none_skip(node.body, scope), self._none_skip(node.orelse, scope)])
        if isinstance(node, ast.Await):
            return self.eval(node.value, scope)
        if isinstance(node, ast.Lambda):
            return ("local", "lambda")
        if isinstance(node, ast.NamedExpr):
            return self.eval(node.value, scope)
        if isinstance(node, ast.Subscript):
            base = self.eval(node.value, scope)
            if base[0] == "ext":
                return EXT
            if base[0] == "coll":
                return base if isinstance(node.slice, ast.Slice) else base[1]
            if base[0] == "map":
                return base[1]
            return unk("subscript")
        return unk("dynamic_expr")

    def _none_skip(self, node, scope):
        if isinstance(node, ast.Constant) and node.value is None:
            return SKIP
        return self.eval(node, scope)

    # ---- names
    def eval_name(self, name, scope):
        if scope.kind == "func":
            if name in scope.locals and name not in scope.globals_decl:
                return self.local_type(scope, name)
        elif scope.kind == "class":
            if name in scope.locals:
                return self.local_type(scope, name)
            nid = scope.info.defs.get(f"{scope.qual}.{name}")
            if nid:
                return _def_type(self.G, nid)
        return self.module_name(scope.info, name)

    def local_type(self, scope, name):
        key = ("local", id(scope), name)
        t = self._memo.get(key)
        if t is not None:
            return t
        if key in self._inprog:
            return unk("cycle")
        self._inprog.add(key)
        try:
            t = self._unify([self.src_type(s, scope) for s in scope.locals[name]])
        finally:
            self._inprog.discard(key)
        self._memo[key] = t
        return t

    def src_type(self, src, scope):
        kind = src[0]
        if kind == "skip":
            return SKIP
        if kind == "fixed":
            return src[1]
        if kind == "unk":
            return unk(src[1])
        if kind == "expr":
            return self._none_skip(src[1], scope)
        if kind == "param":
            _, ann, dflt, selfkind = src
            if ann is not None:
                return self.ann_to_type(ann, scope)
            if selfkind and scope.cls:
                return ("inst", scope.cls) if selfkind == "inst" else ("cls", scope.cls)
            if dflt is not None and isinstance(dflt, ast.Constant) and dflt.value is not None:
                return EXT
            return unk("untyped_param")
        if kind == "annexpr":
            t = self.ann_to_type(src[1], scope)
            if is_unk(t) and src[2] is not None:
                return self._none_skip(src[2], scope)
            return t
        if kind == "iter":
            t = self.eval(src[1], scope)
            return t[1] if t[0] == "coll" else unk("loop_var")
        if kind == "with":
            t = self.eval(src[1], scope)
            if t[0] == "ext":
                return t
            if t[0] == "inst":
                m = self.member(t[1], "__enter__", True, scope)
                if m[0] == "func":
                    return self.func_return(m[1])
            return unk("with_unknown")
        if kind == "exc":
            if src[1] is None:
                return unk("exc_unknown")
            t = self.eval(src[1], scope)
            if t[0] == "cls":
                return ("inst", t[1])
            return t if t[0] == "ext" else unk("exc_unknown")
        return unk("internal")

    # ---- modules
    def module_name(self, info, name):
        key = (info.rel, name)
        t = self._mname.get(key)
        if t is not None:
            return t
        t = self.module_name_local(info, name)
        if t is None:
            if name in BUILTIN_NAMES:
                t = EXT
            elif info.ext_star:
                t = ("ext", "star")
            else:
                t = unk("unknown_name")
        self._mname[key] = t
        return t

    def module_name_local(self, info, name):
        nid = info.top.get(name)
        if nid:
            return _def_type(self.G, nid)
        if name in info.bindings:
            t = self.resolve_bindings(info, info.bindings[name])
            if t is not None:
                return t
        if name in info.mod_vars:
            for src in info.mod_vars[name]:
                if src[0] == "expr" and isinstance(src[1], ast.Call) and \
                        (dotted(src[1].func) or "").rsplit(".", 1)[-1] in TYPEVAR_FACTORIES:
                    return unk("typevar")
            scope = self.module_scope(info)
            key = ("mvar", info.rel, name)
            if key in self._inprog:
                return unk("cycle")
            self._inprog.add(key)
            try:
                return self._unify([self.src_type(s, scope) for s in info.mod_vars[name]])
            finally:
                self._inprog.discard(key)
        for rel in info.stars:
            other = self.files[rel]
            allowed = (name in other.all_names) if other.all_names is not None \
                else not name.startswith("_")
            if allowed and (rel, name) not in self._star_guard:
                self._star_guard.add((rel, name))
                try:
                    t = self.module_name_local(other, name)
                finally:
                    self._star_guard.discard((rel, name))
                if t is not None and not is_unk(t):
                    return t
        return None

    def resolve_bindings(self, info, bindings):
        results = []
        for b in bindings:
            if b[0] == "ext":
                results.append(("ext", b[1]))
            elif b[0] == "mod":
                results.append(("mod", b[1]))
            else:
                results.append(self.module_attr(b[1], b[2]))
        for t in results:
            if t[0] != "ext" and not is_unk(t):
                return t
        for t in results:
            if t[0] == "ext":
                return t
        return results[0] if results else None

    def module_attr(self, path, name):
        key = (path, name)
        t = self._modattr.get(key)
        if t is not None:
            return t
        if key in self._inprog:
            return unk("cycle")
        self._inprog.add(key)
        try:
            t = self._module_attr(path, name)
        finally:
            self._inprog.discard(key)
        self._modattr[key] = t
        return t

    def _module_attr(self, path, name):
        info = self.files.get(path)
        dirpath = None
        if info is not None:
            t = self.module_name_local(info, name)
            if t is not None:
                return t
            if "__getattr__" in info.top:
                return unk("module_getattr")
            if path.rsplit("/", 1)[-1] == "__init__.py":
                dirpath = info.dir
        else:
            dirpath = path
        if dirpath is not None:
            sub = self.index.submodule(dirpath, name)
            if sub:
                return ("mod", sub)
        if info is not None and info.ext_star:
            return ("ext", "star")
        return unk("module_attr_missing")

    # ---- attributes
    def attr_of(self, t, name, scope):
        k = t[0]
        if k == "unk":
            return t
        if k == "ext":
            return t
        if k == "mod":
            return self.module_attr(t[1], name)
        if k == "cls":
            return self.member(t[1], name, False, scope)
        if k == "inst":
            return self.member(t[1], name, True, scope)
        if k == "super":
            return self.member(t[1], name, True, scope, skip_self=True)
        if k == "func":
            return ("ext", "function_attr")
        if k in ("coll", "map"):
            return ("ext", "container")
        return unk("attr_of_local")

    def class_bases(self, cnid):
        b = self._bases.get(cnid)
        if b is not None:
            return b
        self._bases[cnid] = []
        info = self.files[self.G.nodes[cnid]["path"]]
        node = info.class_nodes[cnid]
        scope = self.module_scope(info)
        out = []
        for base in node.bases:
            e = base.value if isinstance(base, ast.Subscript) else base
            t = self.eval(e, scope)
            if t == ("ext", "builtins") and dotted(e) == "object":
                continue
            if t[0] == "cls":
                out.append(t)
            elif t[0] == "ext":
                out.append(("ext", dotted(e) or "ext"))
            else:
                out.append(unk(t[1] if is_unk(t) else "base"))
        self._bases[cnid] = out
        return out

    def mro(self, cnid):
        m = self._mro.get(cnid)
        if m is not None:
            return m
        self._mro[cnid] = [("cls", cnid)]
        bases = self.class_bases(cnid)
        seqs = [self.mro(b[1]) if b[0] == "cls" else [b] for b in bases] + [list(bases)]
        merged = c3_merge(seqs)
        if merged is None:                      # inconsistent hierarchy: fall back to DFS
            merged, seen = [], set()
            for s in seqs[:-1]:
                for x in s:
                    if x not in seen:
                        seen.add(x)
                        merged.append(x)
        m = [("cls", cnid)] + merged
        self._mro[cnid] = m
        return m

    def member(self, cnid, name, inst, scope, skip_self=False):
        """Attribute ``name`` of a class (inst=False) or instance (inst=True)."""
        if inst and name == "__class__":
            return ("cls", cnid)
        entries = self.mro(cnid)
        if skip_self:
            entries = entries[1:]
        for e in entries:
            if e[0] != "cls":
                continue
            cinfo = self.files[self.G.nodes[e[1]]["path"]]
            qual = self.G.nodes[e[1]]["qualname"]
            nid = cinfo.defs.get(f"{qual}.{name}")
            if nid:
                node = self.G.nodes[nid]
                if node["type"] == "class":
                    return ("cls", nid)
                if inst and any(d.rsplit(".", 1)[-1] in PROPERTY_NAMES
                                for d in node.get("decorators", [])):
                    return self.func_return(nid)
                return ("func", nid)
            t = self.attr_type(e[1], name, inst)
            if t is not None:
                return t
        # not found anywhere in the known hierarchy
        for e in entries:
            if e[0] == "cls" and self.member_defined(e[1], "__getattr__"):
                return unk("getattr")
        if any(e[0] == "ext" for e in entries) or (skip_self and not entries):
            return ("ext", "inherited")
        if any(e[0] == "unk" for e in entries):
            return unk("base_unresolved")
        if skip_self:
            return ("ext", "object")
        return unk("attr_unknown")

    def property_target(self, recv, name):
        """Node id of the @property function that ``recv.name`` would execute, else None."""
        if recv[0] not in ("inst", "super"):
            return None
        entries = self.mro(recv[1])
        if recv[0] == "super":
            entries = entries[1:]
        for e in entries:
            if e[0] != "cls":
                continue
            cinfo = self.files[self.G.nodes[e[1]]["path"]]
            nid = cinfo.defs.get(f"{self.G.nodes[e[1]]['qualname']}.{name}")
            if nid:
                node = self.G.nodes[nid]
                if node["type"] != "class" and any(d.rsplit(".", 1)[-1] in PROPERTY_NAMES
                                                   for d in node.get("decorators", [])):
                    return nid
                return None
            if self.attr_type(e[1], name, True) is not None:
                return None
        return None

    def member_defined(self, cnid, name):
        cinfo = self.files[self.G.nodes[cnid]["path"]]
        return f"{self.G.nodes[cnid]['qualname']}.{name}" in cinfo.defs

    def init_of(self, cnid, name="__init__"):
        for e in self.mro(cnid):
            if e[0] == "cls" and self.member_defined(e[1], name):
                cinfo = self.files[self.G.nodes[e[1]]["path"]]
                return cinfo.defs[f"{self.G.nodes[e[1]]['qualname']}.{name}"]
        return None

    # ---- attribute (field) types
    def attr_type(self, cnid, name, inst):
        """Declared type of a field, from class-level assignments and self.x = ... ."""
        cv = self._get_class_vars(cnid)
        sources = []
        if name in cv:
            sources += cv[name]
        if inst:
            ia = self._get_inst_attrs(cnid)
            if name in ia:
                sources += ia[name]
        if not sources:
            return None
        key = ("attr", cnid, name, inst)
        if key in self._inprog:
            return unk("cycle")
        self._inprog.add(key)
        try:
            return self._unify([self.src_type(s, sc) for s, sc in sources])
        finally:
            self._inprog.discard(key)

    def _get_class_vars(self, cnid):
        cv = self._class_vars.get(cnid)
        if cv is None:
            info = self.files[self.G.nodes[cnid]["path"]]
            node = info.class_nodes[cnid]
            qual = self.G.nodes[cnid]["qualname"]
            scope = self.class_scope(info, node, cnid, qual)
            cv = {name: [(s, scope) for s in srcs] for name, srcs in scope.locals.items()}
            self._class_vars[cnid] = cv
        return cv

    def _get_inst_attrs(self, cnid):
        ia = self._inst_attrs.get(cnid)
        if ia is not None:
            return ia
        ia = {}
        self._inst_attrs[cnid] = ia
        info = self.files[self.G.nodes[cnid]["path"]]
        node = info.class_nodes[cnid]
        qual = self.G.nodes[cnid]["qualname"]
        for kind, st in iter_block(node.body):
            if kind != "func":
                continue
            fscope = self.func_scope(info, st, cnid, f"{qual}.{st.name}")
            selfname = None
            for pname, srcs in fscope.locals.items():
                for s in srcs:
                    if s[0] == "param" and s[3] == "inst":
                        selfname = pname
            if not selfname:
                continue
            for n in ast.walk(st):
                targets, src = [], None
                if isinstance(n, ast.Assign):
                    targets, src = n.targets, ("expr", n.value)
                elif isinstance(n, ast.AnnAssign):
                    targets, src = [n.target], ("annexpr", n.annotation, n.value)
                for t in targets:
                    cands = [t]
                    unpack = isinstance(t, (ast.Tuple, ast.List))
                    if unpack:
                        cands = list(ast.walk(t))
                    for c in cands:
                        if (isinstance(c, ast.Attribute) and isinstance(c.value, ast.Name)
                                and c.value.id == selfname):
                            ia.setdefault(c.attr, []).append(
                                (("unk", "unpack") if unpack else src, fscope))
        return ia

    # ---- annotations
    def ann_to_type(self, expr, scope):
        key = ("ann", id(expr), id(scope))
        t = self._memo.get(key)
        if t is not None:
            return t
        if key in self._inprog:
            return unk("cycle")
        self._inprog.add(key)
        try:
            t = self._ann(expr, scope)
        finally:
            self._inprog.discard(key)
        self._memo[key] = t
        return t

    def _ann(self, expr, scope):
        ascope = self.module_scope(scope.info, scope.cls)
        if isinstance(expr, ast.Constant):
            if expr.value is None:
                return ("ext", "None")
            if isinstance(expr.value, str):
                try:
                    parsed = ast.parse(expr.value.strip(), mode="eval").body
                except (SyntaxError, ValueError):
                    return unk("annotation")
                self._keep.append(parsed)
                return self.ann_to_type(parsed, scope)
            return unk("annotation")
        if isinstance(expr, (ast.Name, ast.Attribute)):
            t = self.eval(expr, ascope)
            if t[0] == "cls":
                return ("inst", t[1])
            if t[0] == "ext":
                last = (dotted(expr) or "").rsplit(".", 1)[-1]
                if last == "Self" and scope.cls:
                    return ("inst", scope.cls)
                if last in ("Any", "object"):
                    return unk("annotation_any")
                if last == "Callable":
                    return unk("callable_param")
                return t
            return unk("annotation")
        if isinstance(expr, ast.Subscript):
            base = (dotted(expr.value) or "").rsplit(".", 1)[-1]
            sl = expr.slice
            if base == "Optional":
                return self.ann_to_type(sl, scope)
            if base == "Union":
                elts = sl.elts if isinstance(sl, ast.Tuple) else [sl]
                kept = [self.ann_to_type(e, scope) for e in elts
                        if not (isinstance(e, ast.Constant) and e.value is None)]
                return self._unify(kept) if kept else ("ext", "None")
            if base in ("Annotated", "ClassVar", "Final", "Required", "NotRequired", "ReadOnly"):
                inner = sl.elts[0] if isinstance(sl, ast.Tuple) else sl
                return self.ann_to_type(inner, scope)
            if base in ("Type", "type"):
                t = self.ann_to_type(sl, scope)
                return ("cls", t[1]) if t[0] == "inst" else unk("annotation")
            if base == "Callable":
                return unk("callable_param")
            if base in COLL_BASES:
                elts = sl.elts if isinstance(sl, ast.Tuple) else [sl]
                homog = len(elts) == 1 or (len(elts) == 2 and isinstance(elts[1], ast.Constant)
                                           and elts[1].value is Ellipsis)
                if homog:
                    e = self.ann_to_type(elts[0], scope)
                    if e[0] == "inst":
                        return ("coll", e)
                return ("ext", "container")
            if base in MAP_BASES:
                if isinstance(sl, ast.Tuple) and len(sl.elts) == 2:
                    v = self.ann_to_type(sl.elts[1], scope)
                    if v[0] == "inst":
                        return ("map", v)
                return ("ext", "container")
            t = self.eval(expr.value, ascope)
            if t[0] == "cls":
                return ("inst", t[1])
            return t if t[0] == "ext" else unk("annotation")
        if isinstance(expr, ast.BinOp) and isinstance(expr.op, ast.BitOr):
            parts = [expr.left, expr.right]
            kept = [self.ann_to_type(e, scope) for e in parts
                    if not (isinstance(e, ast.Constant) and e.value is None)]
            return self._unify(kept) if kept else ("ext", "None")
        return unk("annotation")

    # ---- calls and return types
    def _eval_call(self, node, scope):
        f = node.func
        if isinstance(f, ast.Name) and f.id == "super" and scope.kind != "module" \
                and self._is_builtin_name("super", scope):
            if node.args:
                t = self.eval(node.args[0], scope)
                return ("super", t[1]) if t[0] == "cls" else unk("super")
            return ("super", scope.cls) if scope.cls else unk("super")
        if isinstance(f, ast.Name) and f.id == "type" and len(node.args) == 1 \
                and self._is_builtin_name("type", scope):
            t = self.eval(node.args[0], scope)
            return ("cls", t[1]) if t[0] == "inst" else unk("type_call")
        if isinstance(f, ast.Attribute):
            recv = self.eval(f.value, scope)
            if recv[0] == "map":
                if f.attr == "values":
                    return ("coll", recv[1])
                if f.attr in ("get", "pop", "setdefault"):
                    return recv[1]
                if f.attr == "copy":
                    return recv
            elif recv[0] == "coll":
                if f.attr == "pop":
                    return recv[1]
                if f.attr == "copy":
                    return recv
        ft = self.eval(f, scope)
        k = ft[0]
        if k == "cls":
            return ("inst", ft[1])
        if k == "func":
            return self.func_return(ft[1])
        if k == "ext":
            return ft
        if k == "inst":
            m = self.member(ft[1], "__call__", True, scope)
            return self.func_return(m[1]) if m[0] == "func" else unk("call_result_unknown")
        if k == "unk":
            return unk("call_result_unknown")
        return unk("call_result_unknown")

    def _is_builtin_name(self, name, scope):
        t = self.eval_name(name, scope)
        return t[0] == "ext" and t[1] == "builtins"

    def func_return(self, nid):
        t = self._ret.get(nid)
        if t is not None:
            return t
        if nid in self._inprog:
            return unk("cycle")
        self._inprog.add(nid)
        try:
            t = self._func_return(nid)
        finally:
            self._inprog.discard(nid)
        self._ret[nid] = t
        return t

    def _func_return(self, nid):
        node = self.G.nodes[nid]
        info = self.files[node["path"]]
        defs = info.ast_defs[nid]
        # @overload stubs only describe signatures; take the real implementation
        impl = [d for d in defs if not any(x.rsplit(".", 1)[-1] == "overload"
                                           for x in decorator_names(d))]
        fnode = (impl or defs)[0]
        qual = node["qualname"]
        cls = self._class_of(info, qual)
        scope = self.func_scope(info, fnode, cls, qual)
        if fnode.returns is not None:
            t = self.ann_to_type(fnode.returns, scope)
            if not is_unk(t):
                return t
        if has_yield(fnode):
            return ("ext", "generator")
        vals = return_values(fnode)
        types = [SKIP if (v is None or (isinstance(v, ast.Constant) and v.value is None))
                 else self.eval(v, scope) for v in vals]
        if all(t is SKIP for t in types):
            return ("ext", "None")
        return self._unify(types)

    def _class_of(self, info, qual):
        if "." not in qual:
            return None
        parent = info.defs.get(qual.rsplit(".", 1)[0])
        return parent if parent and self.G.nodes[parent]["type"] == "class" else None

    # ---- the public question
    def call_outcome(self, call, scope):
        """-> (kind, [target node ids], reason). kind: resolved|external|local|unresolved"""
        t = self.eval(call.func, scope)
        return self.outcome_of(t)

    def outcome_of(self, t):
        k = t[0]
        if k == "func":
            return "resolved", [t[1]], None
        if k == "cls":
            targets = [t[1]]
            for dunder in ("__new__", "__init__"):
                m = self.init_of(t[1], dunder)
                if m:
                    targets.append(m)
            return "resolved", targets, None
        if k == "inst":
            m = self.member(t[1], "__call__", True, None)
            if m[0] == "func":
                return "resolved", [m[1]], None
            return "unresolved", [], "instance_call"
        if k == "ext":
            return "external", [], None
        if k == "local":
            return "local", [], None
        if k == "unk":
            return "unresolved", [], t[1]
        if k == "mod":
            return "unresolved", [], "module_call"
        return "unresolved", [], "super_call"
