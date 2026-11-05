# AEGIS Phase 1 graph report: networkx

- builder version: 2.0   schema: 2
- git HEAD: n/a
- files parsed: 580 (191735 lines), parse errors: 0
- build time: 9.86 s

## Nodes

| type | count |
|---|---|
| file | 580 |
| class | 564 |
| function | 2444 |
| test | 4332 |

## Edges

| type | count | meaning |
|---|---|---|
| contains | 7340 | file -> class -> method |
| imports | 1297 | file imports file |
| calls | 22361 | resolved call (certain) |
| tests | 15614 | test -> code under test |
| inherits | 169 | class -> base class |
| overrides | 344 | method -> overridden method |
| references | 3431 | uses a name without calling it |
| maybe_calls | 8710 | HEURISTIC name-based call |

## Call resolution

| outcome | calls | share |
|---|---|---|
| resolved to a repo definition | 23085 | 44.3% |
| external / builtin | 19565 | 37.6% |
| nested function or lambda | 626 | 1.2% |
| unresolved | 8795 | 16.9% |

Implicit calls found (properties, `with`, `obj[k]`, iteration, operators): 1853

### Why calls stayed unresolved

| reason | calls |
|---|---|
| untyped_param | 3931 |
| call_result_unknown | 1890 |
| attr_unknown | 850 |
| unpack | 569 |
| subscript | 452 |
| conflict | 372 |
| loop_var | 313 |
| nested_param | 139 |
| unknown_name | 96 |
| cycle | 58 |

## Most depended-on definitions (calls + references + inherits)

| node | fan-in |
|---|---|
| `networkx/classes/graph.py::Graph` | 1103 |
| `networkx/classes/graph.py::Graph.__init__` | 984 |
| `networkx/classes/graph.py::Graph.__new__` | 983 |
| `networkx/classes/digraph.py::DiGraph` | 958 |
| `networkx/utils/backends.py::_dispatchable` | 794 |
| `networkx/utils/backends.py::_dispatchable.__new__` | 791 |
| `networkx/classes/digraph.py::DiGraph.__new__` | 749 |
| `networkx/exception.py::NetworkXError` | 744 |
| `networkx/classes/digraph.py::DiGraph.__init__` | 732 |
| `networkx/generators/classic.py::path_graph` | 525 |

## Reading this report

`calls` edges are only created when the target is certain; everything else is counted with a reason above. `maybe_calls` edges are heuristic and must be weighed, not trusted.
