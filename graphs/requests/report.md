# AEGIS Phase 1 graph report: requests

- builder version: 2.0   schema: 2
- git HEAD: n/a
- files parsed: 18 (5626 lines), parse errors: 0
- build time: 0.21 s

## Nodes

| type | count |
|---|---|
| file | 18 |
| class | 44 |
| function | 233 |
| test | 0 |

## Edges

| type | count | meaning |
|---|---|---|
| contains | 277 | file -> class -> method |
| imports | 58 | file imports file |
| calls | 277 | resolved call (certain) |
| tests | 0 | test -> code under test |
| inherits | 32 | class -> base class |
| overrides | 7 | method -> overridden method |
| references | 154 | uses a name without calling it |
| maybe_calls | 7 | HEURISTIC name-based call |

## Call resolution

| outcome | calls | share |
|---|---|---|
| resolved to a repo definition | 257 | 27.4% |
| external / builtin | 495 | 52.8% |
| nested function or lambda | 9 | 1.0% |
| unresolved | 177 | 18.9% |

Implicit calls found (properties, `with`, `obj[k]`, iteration, operators): 22

### Why calls stayed unresolved

| reason | calls |
|---|---|
| untyped_param | 78 |
| cycle | 28 |
| call_result_unknown | 24 |
| loop_var | 15 |
| unpack | 10 |
| subscript | 9 |
| conflict | 5 |
| no_value | 5 |
| attr_unknown | 2 |
| nested_param | 1 |

## Most depended-on definitions (calls + references + inherits)

| node | fan-in |
|---|---|
| `requests/exceptions.py::RequestException` | 31 |
| `requests/exceptions.py::RequestException.__init__` | 14 |
| `requests/_internal_utils.py::to_native_string` | 12 |
| `requests/exceptions.py::ConnectionError` | 11 |
| `requests/structures.py::CaseInsensitiveDict` | 11 |
| `requests/exceptions.py::InvalidURL` | 10 |
| `requests/cookies.py::cookiejar_from_dict` | 9 |
| `requests/api.py::request` | 8 |
| `requests/sessions.py::Session.request` | 8 |
| `requests/models.py::PreparedRequest` | 7 |

## Reading this report

`calls` edges are only created when the target is certain; everything else is counted with a reason above. `maybe_calls` edges are heuristic and must be weighed, not trusted.
