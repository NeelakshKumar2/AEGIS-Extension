# AEGIS graph specification (schema v2)

The graph is a `networkx.MultiDiGraph`. Later phases rely on this contract; `aegis check` enforces
the structural parts of it (`src/aegis/validate.py`).

## Nodes

| id | type | meaning |
|---|---|---|
| `pkg/core.py` | `file` | one parsed Python file (id = path relative to the repo root, `/` separators) |
| `pkg/core.py::Engine` | `class` | class (id = `path::qualname`) |
| `pkg/core.py::Engine.run` | `function` | function or method |
| `tests/test_core.py::test_x` | `test` | function in a test file whose name starts with `test` |

Functions nested inside other *functions* are not nodes: their calls are attributed to the
enclosing function. Redefinitions (property setters, `if/else` variants, `@overload`) are one node
with several `spans`.

| attribute | on | meaning |
|---|---|---|
| `path`, `name`, `qualname` | definitions | location and name |
| `lineno`, `end_lineno` | definitions | `def` line and last line |
| `spans` | definitions | list of `[start, end]` incl. decorators; **use this to map diff lines to nodes** |
| `body_hash` | definitions | hash of the AST (ignores formatting/comments): equal hash = unchanged entity |
| `decorators`, `doc` | definitions | decorator names, first docstring line |
| `in_test_file` | definitions | defined under a test path |
| `is_method`, `is_async`, `is_generator`, `nparams` | functions | |
| `ext_bases`, `unresolved_bases` | classes | bases outside the repo / that could not be resolved |
| `sha1`, `loc`, `module`, `modules`, `is_test` | files | content hash (detect changed files), line count, dotted import names |

## Edges (key = type)

| type | from -> to | meaning |
|---|---|---|
| `contains` | file/class -> class/function | definition tree, each non-file node has exactly one parent |
| `imports` | file -> file | import statement resolved to a repo file |
| `calls` | owner -> definition | **certain** call. Includes implicit calls: `@property` access and assignment, `with` (`__enter__/__exit__`), `obj[k]` (`__getitem__/__setitem__`), `for x in obj`, `x in obj`, operators, `len()/list()/...` on repo objects, decorator application, and class instantiation (class + `__new__` + `__init__`) |
| `tests` | test -> definition; test file -> imported file | what the tests exercise |
| `inherits` | class -> class | base class in the repo |
| `overrides` | method -> method | overridden base method (use it so a change to `Sub.m` reaches callers of `Base.m`) |
| `references` | owner -> class/function | named without being called: callbacks, annotations, `isinstance`, `from m import f` |
| `maybe_calls` | owner -> method | **heuristic.** Receiver type unknown, method name defined in at most 6 repo classes (common builtin names excluded). `ncand` = number of candidates. Never mix with `calls` without weighting. |

Every edge has `count` and `lines` (up to 20 source lines). The "owner" of a call is the innermost
definition containing it; module-level code belongs to the file node, class-body code to the class.

`aegis.STRICT_EDGE_TYPES` = everything except `maybe_calls`.

## Graph metadata (`G.graph`)

`schema_version`, `repo`, `builder_version`, `head` (git commit if any), `parse_error_files`,
`build_seconds`, `unresolved_reasons` and `stats`:

| stat | meaning |
|---|---|
| `calls_total` | call expressions seen |
| `calls_resolved` / `calls_external` / `calls_local` / `calls_unresolved` | outcome of each (sums to `calls_total`) |
| `calls_implicit` | extra calls inferred from syntax (counted on top of `calls_total`) |
| `calls_unresolved_with_candidates` | unresolved calls that received `maybe_calls` edges |
| `decorators_*`, `bases_*`, `imports_*`, `references_total`, `overrides_total` | same idea for other constructs |
| `files_parsed`, `loc_total`, `parse_errors` | |

`unresolved_reasons` says why calls stayed unresolved (`untyped_param`, `loop_var`, `conflict`,
`callable_param`, `attr_unknown`, `subscript`, ...). It is the to-do list for improving the graph.

## How the resolver decides (summary)

Local, flow-insensitive type inference: constructor calls, annotations (incl. `Optional`, `X | None`,
string forward references, `Self`, `list[X]`, `dict[K, X]`), `self.attr = ...` field types, return
types (annotation first, otherwise all `return` expressions), `super()`, `cls`, `type(x)`, MRO (C3),
import chains and re-exports (`__init__.py`, `import a.b.c`, relative, star, aliases), `with ... as`,
`except E as e`, loop variables over typed collections, parameter shadowing. If a variable is
assigned different types, or anything is unknown, the result is *unknown* and **no `calls` edge is
created**. Precision is preferred over recall; `maybe_calls` and `references` carry the rest.

## Not modelled (by design)

Dynamic dispatch through `getattr`/`setattr`/`__getattr__`, metaclasses, monkey patching, callbacks
stored in data structures, argument types inferred from call sites, `isinstance` narrowing, pytest
fixtures, `importlib`, code in non-`.py` files, Python 2 syntax (such files are listed in
`parse_error_files`).
