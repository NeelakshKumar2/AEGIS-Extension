# AEGIS Phase 1 graph report: flask

- builder version: 2.0   schema: 2
- git HEAD: n/a
- files parsed: 24 (9199 lines), parse errors: 0
- build time: 0.32 s

## Nodes

| type | count |
|---|---|
| file | 24 |
| class | 46 |
| function | 326 |
| test | 0 |

## Edges

| type | count | meaning |
|---|---|---|
| contains | 372 | file -> class -> method |
| imports | 102 | file imports file |
| calls | 351 | resolved call (certain) |
| tests | 0 | test -> code under test |
| inherits | 18 | class -> base class |
| overrides | 37 | method -> overridden method |
| references | 303 | uses a name without calling it |
| maybe_calls | 7 | HEURISTIC name-based call |

## Call resolution

| outcome | calls | share |
|---|---|---|
| resolved to a repo definition | 261 | 22.0% |
| external / builtin | 797 | 67.0% |
| nested function or lambda | 8 | 0.7% |
| unresolved | 123 | 10.3% |

Implicit calls found (properties, `with`, `obj[k]`, iteration, operators): 48

### Why calls stayed unresolved

| reason | calls |
|---|---|
| call_result_unknown | 22 |
| callable_param | 18 |
| unpack | 17 |
| loop_var | 16 |
| annotation_any | 9 |
| subscript | 7 |
| attr_unknown | 7 |
| lambda_param | 7 |
| nested_param | 6 |
| getattr | 4 |

## Most depended-on definitions (calls + references + inherits)

| node | fan-in |
|---|---|
| `flask/sansio/scaffold.py::setupmethod` | 45 |
| `flask/app.py::Flask` | 36 |
| `flask/wrappers.py::Response` | 27 |
| `flask/sansio/app.py::App` | 20 |
| `flask/app.py::Flask.ensure_sync` | 20 |
| `flask/json/tag.py::JSONTag` | 19 |
| `flask/wrappers.py::Request` | 16 |
| `flask/sessions.py::SessionMixin` | 13 |
| `flask/sansio/scaffold.py::Scaffold` | 11 |
| `flask/sansio/blueprints.py::Blueprint` | 10 |

## Reading this report

`calls` edges are only created when the target is certain; everything else is counted with a reason above. `maybe_calls` edges are heuristic and must be weighed, not trusted.
