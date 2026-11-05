# AEGIS Phase 1 graph report: jinja2

- builder version: 2.0   schema: 2
- git HEAD: n/a
- files parsed: 25 (14425 lines), parse errors: 0
- build time: 0.65 s

## Nodes

| type | count |
|---|---|
| file | 25 |
| class | 159 |
| function | 712 |
| test | 0 |

## Edges

| type | count | meaning |
|---|---|---|
| contains | 871 | file -> class -> method |
| imports | 99 | file imports file |
| calls | 1251 | resolved call (certain) |
| tests | 0 | test -> code under test |
| inherits | 108 | class -> base class |
| overrides | 76 | method -> overridden method |
| references | 1018 | uses a name without calling it |
| maybe_calls | 35 | HEURISTIC name-based call |

## Call resolution

| outcome | calls | share |
|---|---|---|
| resolved to a repo definition | 1433 | 46.9% |
| external / builtin | 1306 | 42.7% |
| nested function or lambda | 60 | 2.0% |
| unresolved | 258 | 8.4% |

Implicit calls found (properties, `with`, `obj[k]`, iteration, operators): 93

### Why calls stayed unresolved

| reason | calls |
|---|---|
| conflict | 53 |
| call_result_unknown | 47 |
| nested_param | 42 |
| callable_param | 30 |
| unpack | 19 |
| subscript | 19 |
| loop_var | 14 |
| annotation | 6 |
| attr_unknown | 6 |
| cycle | 6 |

## Most depended-on definitions (calls + references + inherits)

| node | fan-in |
|---|---|
| `jinja2/nodes.py::Expr` | 88 |
| `jinja2/compiler.py::Frame` | 81 |
| `jinja2/environment.py::Environment` | 80 |
| `jinja2/runtime.py::Undefined` | 64 |
| `jinja2/visitor.py::NodeVisitor.visit` | 55 |
| `jinja2/nodes.py::Node` | 55 |
| `jinja2/compiler.py::CodeGenerator.write` | 47 |
| `jinja2/runtime.py::Context` | 45 |
| `jinja2/nodes.py::Node.__init__` | 45 |
| `jinja2/nodes.py::EvalContext` | 43 |

## Reading this report

`calls` edges are only created when the target is certain; everything else is counted with a reason above. `maybe_calls` edges are heuristic and must be weighed, not trusted.
