# AEGIS Phase 1 graph report: click

- builder version: 2.0   schema: 2
- git HEAD: n/a
- files parsed: 17 (11117 lines), parse errors: 0
- build time: 0.4 s

## Nodes

| type | count |
|---|---|
| file | 17 |
| class | 72 |
| function | 461 |
| test | 0 |

## Edges

| type | count | meaning |
|---|---|---|
| contains | 533 | file -> class -> method |
| imports | 62 | file imports file |
| calls | 567 | resolved call (certain) |
| tests | 0 | test -> code under test |
| inherits | 38 | class -> base class |
| overrides | 77 | method -> overridden method |
| references | 501 | uses a name without calling it |
| maybe_calls | 19 | HEURISTIC name-based call |

## Call resolution

| outcome | calls | share |
|---|---|---|
| resolved to a repo definition | 576 | 31.4% |
| external / builtin | 1087 | 59.3% |
| nested function or lambda | 30 | 1.6% |
| unresolved | 139 | 7.6% |

Implicit calls found (properties, `with`, `obj[k]`, iteration, operators): 34

### Why calls stayed unresolved

| reason | calls |
|---|---|
| call_result_unknown | 24 |
| cycle | 23 |
| unpack | 23 |
| callable_param | 18 |
| conflict | 18 |
| loop_var | 10 |
| nested_param | 9 |
| annotation | 4 |
| annotation_any | 3 |
| subscript | 3 |

## Most depended-on definitions (calls + references + inherits)

| node | fan-in |
|---|---|
| `click/core.py::Context` | 120 |
| `click/core.py::Parameter` | 51 |
| `click/core.py::Command` | 31 |
| `click/types.py::ParamType` | 30 |
| `click/utils.py::echo` | 23 |
| `click/shell_completion.py::CompletionItem` | 21 |
| `click/exceptions.py::UsageError` | 18 |
| `click/core.py::Group` | 15 |
| `click/formatting.py::HelpFormatter` | 12 |
| `click/core.py::Option` | 11 |

## Reading this report

`calls` edges are only created when the target is certain; everything else is counted with a reason above. `maybe_calls` edges are heuristic and must be weighed, not trusted.
