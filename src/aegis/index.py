"""Repository index: files, module names and import resolution.

Import resolution is path-based wherever possible (relative imports, submodules), and
name-based (dotted module names registered for every file) for absolute imports.
When a dotted name maps to several files (two ``utils.py`` in different script
directories) the file closest to the importing file wins, deterministically.
"""
import ast
import hashlib
from collections import defaultdict
from pathlib import PurePosixPath


class FileInfo:
    def __init__(self, rel, tree, is_test, data, loc):
        self.rel = rel
        self.tree = tree
        self.is_test = is_test
        self.sha1 = hashlib.sha1(data).hexdigest()
        self.loc = loc
        self.modnames = []        # dotted names this file can be imported as
        self.defs = {}            # qualname -> node id (classes, functions, methods)
        self.top = {}             # top-level name -> node id
        self.ast_defs = {}        # node id -> [ast nodes] (several for redefinitions)
        self.class_nodes = {}     # class node id -> ast.ClassDef
        self.bindings = defaultdict(list)   # local name -> [("mod",path)|("sym",path,name)|("ext",n)]
        self.stars = []           # files star-imported
        self.ext_star = False     # star-import from outside the repo
        self.all_names = None     # __all__ if statically known
        self.mod_vars = defaultdict(list)   # module-level variable -> sources
        self.dir = str(PurePosixPath(rel).parent)
        if self.dir == ".":
            self.dir = ""


def module_names_for(rel, relset):
    """All dotted names the file may be imported as (most specific first)."""
    p = PurePosixPath(rel)
    stem_parts = list(p.with_suffix("").parts)
    is_init = stem_parts[-1] == "__init__"
    if is_init:
        stem_parts = stem_parts[:-1]
    if not stem_parts:
        return []
    d = list(p.parent.parts)
    i = len(d)
    while i > 0 and "/".join(d[:i] + ["__init__.py"]) in relset:
        i -= 1
    pkgs = d[i:]
    name_parts = pkgs if is_init else pkgs + [p.stem]
    names = []
    if name_parts:
        names.append(".".join(name_parts))
    names.append(".".join(stem_parts))
    if stem_parts[0] in ("src", "lib") and len(stem_parts) > 1:
        names.append(".".join(stem_parts[1:]))
    seen, out = set(), []
    for n in names:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


def _join(*parts):
    return "/".join(p for p in parts if p)


class RepoIndex:
    def __init__(self, files):
        self.files = files
        self.relset = set(files)
        self.dirs = set()
        self.mod_files = defaultdict(list)
        for rel in sorted(files):
            parts = PurePosixPath(rel).parent.parts
            for i in range(len(parts) + 1):
                self.dirs.add("/".join(parts[:i]))
            files[rel].modnames = module_names_for(rel, self.relset)
            for n in files[rel].modnames:
                self.mod_files[n].append(rel)

    # ------------------------------------------------------------ helpers
    @staticmethod
    def _closeness(a_dir, b_dir):
        a, b = a_dir.split("/") if a_dir else [], b_dir.split("/") if b_dir else []
        n = 0
        for x, y in zip(a, b):
            if x != y:
                break
            n += 1
        return n

    def _pick(self, cands, from_rel):
        if len(cands) == 1 or from_rel is None:
            return cands[0]
        fdir = self.files[from_rel].dir if from_rel in self.files else ""
        return sorted(cands, key=lambda r: (-self._closeness(fdir, self.files[r].dir),
                                            len(r), r))[0]

    def resolve_module(self, dotted_name, from_rel=None):
        cands = self.mod_files.get(dotted_name)
        return self._pick(cands, from_rel) if cands else None

    def ns_dir(self, dotted_name, from_rel=None):
        """Directory of a namespace package (no __init__.py) that holds dotted_name.*"""
        prefix = dotted_name + "."
        cands = []
        for name, rels in self.mod_files.items():
            if name.startswith(prefix):
                n_extra = len(name.split(".")) - len(dotted_name.split("."))
                for r in rels:
                    cands.append((r, n_extra))
        if not cands:
            return None
        rel, n_extra = sorted(cands, key=lambda c: (-self._closeness(
            self.files[from_rel].dir if from_rel in self.files else "", self.files[c[0]].dir),
            len(c[0]), c[0]))[0]
        parts = list(PurePosixPath(rel).with_suffix("").parts)
        if parts[-1] == "__init__":
            parts = parts[:-1]
        keep = len(parts) - n_extra
        return "/".join(parts[:keep]) if keep >= 0 else None

    def submodule(self, dirpath, name):
        """Path of module/namespace ``name`` directly inside directory ``dirpath``."""
        f = _join(dirpath, name + ".py")
        if f in self.relset:
            return f
        init = _join(dirpath, name, "__init__.py")
        if init in self.relset:
            return init
        d = _join(dirpath, name)
        if d in self.dirs:
            return d
        return None

    def relative_target(self, from_rel, level, modname):
        """(file or None, directory or None) for ``from <dots><modname> import ...``."""
        base = self.files[from_rel].dir.split("/") if self.files[from_rel].dir else []
        up = level - 1
        if up > len(base):
            return None, None
        if up:
            base = base[:len(base) - up]
        parts = base + (modname.split(".") if modname else [])
        d = "/".join(parts)
        if modname:
            f = d + ".py"
            if f in self.relset:
                return f, None
        init = _join(d, "__init__.py")
        if init in self.relset:
            return init, d
        return None, (d if d in self.dirs or d == "" else None)
