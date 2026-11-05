# AEGIS Phase 1 graph report: werkzeug

- builder version: 2.0   schema: 2
- git HEAD: n/a
- files parsed: 52 (21500 lines), parse errors: 0
- build time: 0.94 s

## Nodes

| type | count |
|---|---|
| file | 52 |
| class | 180 |
| function | 950 |
| test | 0 |

## Edges

| type | count | meaning |
|---|---|---|
| contains | 1130 | file -> class -> method |
| imports | 190 | file imports file |
| calls | 1263 | resolved call (certain) |
| tests | 0 | test -> code under test |
| inherits | 97 | class -> base class |
| overrides | 100 | method -> overridden method |
| references | 834 | uses a name without calling it |
| maybe_calls | 56 | HEURISTIC name-based call |

## Call resolution

| outcome | calls | share |
|---|---|---|
| resolved to a repo definition | 1183 | 30.4% |
| external / builtin | 2156 | 55.3% |
| nested function or lambda | 43 | 1.1% |
| unresolved | 515 | 13.2% |

Implicit calls found (properties, `with`, `obj[k]`, iteration, operators): 195

### Why calls stayed unresolved

| reason | calls |
|---|---|
| conflict | 106 |
| unpack | 80 |
| call_result_unknown | 72 |
| subscript | 53 |
| loop_var | 49 |
| callable_param | 37 |
| cycle | 33 |
| nested_param | 26 |
| getattr | 24 |
| annotation | 12 |

## Most depended-on definitions (calls + references + inherits)

| node | fan-in |
|---|---|
| `werkzeug/exceptions.py::HTTPException` | 73 |
| `werkzeug/datastructures/structures.py::MultiDict` | 57 |
| `werkzeug/datastructures/headers.py::Headers` | 48 |
| `werkzeug/utils.py::cached_property` | 44 |
| `werkzeug/wrappers/response.py::Response` | 41 |
| `werkzeug/datastructures/mixins.py::_immutable_error` | 39 |
| `werkzeug/utils.py::cached_property.__init__` | 38 |
| `werkzeug/wrappers/request.py::Request` | 35 |
| `werkzeug/exceptions.py::HTTPException.__init__` | 26 |
| `werkzeug/routing/rules.py::Rule` | 25 |

## Reading this report

`calls` edges are only created when the target is certain; everything else is counted with a reason above. `maybe_calls` edges are heuristic and must be weighed, not trusted.
