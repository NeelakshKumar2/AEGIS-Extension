# AEGIS Phase 1 graph report: markdown

- builder version: 2.0   schema: 2
- git HEAD: n/a
- files parsed: 33 (8330 lines), parse errors: 0
- build time: 0.49 s

## Nodes

| type | count |
|---|---|
| file | 33 |
| class | 111 |
| function | 373 |
| test | 0 |

## Edges

| type | count | meaning |
|---|---|---|
| contains | 484 | file -> class -> method |
| imports | 103 | file imports file |
| calls | 557 | resolved call (certain) |
| tests | 2 | test -> code under test |
| inherits | 90 | class -> base class |
| overrides | 143 | method -> overridden method |
| references | 281 | uses a name without calling it |
| maybe_calls | 32 | HEURISTIC name-based call |

## Call resolution

| outcome | calls | share |
|---|---|---|
| resolved to a repo definition | 603 | 28.0% |
| external / builtin | 1224 | 56.9% |
| nested function or lambda | 11 | 0.5% |
| unresolved | 315 | 14.6% |

Implicit calls found (properties, `with`, `obj[k]`, iteration, operators): 23

### Why calls stayed unresolved

| reason | calls |
|---|---|
| loop_var | 72 |
| untyped_param | 57 |
| call_result_unknown | 42 |
| unpack | 32 |
| cycle | 31 |
| conflict | 24 |
| subscript | 22 |
| nested_param | 15 |
| callable_param | 13 |
| annotation_any | 5 |

## Most depended-on definitions (calls + references + inherits)

| node | fan-in |
|---|---|
| `markdown/extensions/__init__.py::Extension` | 60 |
| `markdown/core.py::Markdown` | 51 |
| `markdown/blockprocessors.py::BlockProcessor` | 40 |
| `markdown/inlinepatterns.py::InlineProcessor` | 30 |
| `markdown/treeprocessors.py::Treeprocessor` | 29 |
| `markdown/util.py::AtomicString` | 19 |
| `markdown/extensions/__init__.py::Extension.__init__` | 16 |
| `markdown/util.py::Registry` | 15 |
| `markdown/preprocessors.py::Preprocessor` | 14 |
| `markdown/blockparser.py::BlockParser` | 12 |

## Reading this report

`calls` edges are only created when the target is certain; everything else is counted with a reason above. `maybe_calls` edges are heuristic and must be weighed, not trusted.
