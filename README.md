# AEGIS: Agentic Evidence-Grounded Intelligence for Software

Given a code change (a git commit), AEGIS finds what *could* be affected from a code graph
(possible-impact set) and ranks what is *probably* affected using graph structure plus git
co-change history (probable-impact set). Language: **Python 3.11+** (stdlib `ast`, NetworkX, git CLI,
pytest); the analysed repositories are Python-only.

```
repo --Phase 1--> typed graph --Phase 2--> seeds + possible-impact files --Phase 3--> ranked files --Phase 4--> metrics
        (parser, resolver)    (diff_mapper, impact)          (history, rank)           (evaluate, metrics)
```

| Phase | Modules | Result |
|---|---|---|
| 1 Graph | `index.py parser.py resolver.py graph.py validate.py oracle*.py export.py` | files, classes, functions, tests; edges contains / imports / calls / tests / inherits / overrides / references / maybe_calls (heuristic, kept apart); validated against traced runs |
| 2 Change mapping | `gitutil.py diff_mapper.py impact.py` | commit -> changed lines -> seed nodes (`LineIndex`) -> reverse BFS; every candidate keeps distance, path, edge types, provenance |
| 3 Evidence ranking | `history.py rank.py` | co-change mined from earlier commits only; rankers: random, graph, co-change, AEGIS |
| 4 Evaluation | `pipeline.py evaluate.py metrics.py` | temporal split, weights fitted on the earlier half, P@K / R@K / MRR / scope reduction with bootstrap CI |
| - Compatibility | `doctor.py` | will AEGIS work on this repo? |

## Install
```bash
python3 -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install -e .            # gives `aegis` and `python -m aegis`; otherwise: export PYTHONPATH=src
python -m pytest -q         # or: python tests/runner.py
```

## Run on any git repository (use a FULL clone, not --depth)
```bash
git clone https://github.com/pallets/flask data/repos/flask
python -m aegis doctor   data/repos/flask                       # SUPPORTED / LIMITED / NOT SUPPORTED, with reasons
python -m aegis build    data/repos/flask --out aegis_out        # Phase 1: graph files
python -m aegis impact   data/repos/flask --commit HEAD          # Phase 2: possible-impact files of one commit
python -m aegis rankdata data/repos/flask --n 500 --out outputs/flask.jsonl    # Phases 2+3 over history
python -m aegis evaluate outputs/flask.jsonl --out outputs/flask_results.json  # Phase 4 table
python -m aegis rank     data/repos/flask --commit HEAD --weights outputs/flask_results.json
```
Ablation: `--no-maybe` drops the heuristic `maybe_calls` edges; `--depth N` sets graph hops.
Phase 1 tools: `check`, `stats`, `find`, `callers`, `callees`, `at FILE:LINE`, `audit`, `oracle`.

```python
from aegis import build_graph
from aegis.impact import impact_for_commit
rec = impact_for_commit("data/repos/flask", "HEAD")      # seeds, candidates (with evidence), truth_files
```

## Evaluation protocol (fixed; copy into the Methodology)
* Query file = the non-test .py file with the most changed lines; seeds = graph nodes changed in it.
* Truth = all other .py files changed in the same commit (tests included). Candidates exclude the query file.
* Co-change counts use only commits before the scored one. Weights are fitted on the earlier half of the
  commits (by time); all reported numbers are on the later half.
* Commits with < 2 changed .py files, > 50, or no non-test file are skipped and counted.
* Co-change is a *proxy* for true impact; say so in the paper.

## What was validated (details in `validation/RESULTS.md`)

Seven real packages, 749 files and about 262k lines (requests, click, flask, jinja2, markdown,
werkzeug, networkx):

* unresolved calls fell from **35-63%** (original parser) to **8-19%**;
* of the calls observed in traced runs, the graph contains **70-88%** (six packages). Counting
  virtual dispatch and decorator attribution that is **73.5-88.5%**, and 69% for networkx, whose
  every public function runs inside an `@_dispatchable` wrapper (strict recall there is 13%);
* of the graph's call edges whose call site ran, **98.7-100%** were confirmed (a lower bound);
* invariants: 0 problems everywhere, builds are deterministic, JSON round-trips exactly;
* speed: 190k lines (networkx) in about 10 s on the test machine.

Pre-built graphs for these packages are in `graphs/` (built from installed copies, so no git HEAD).

## Honest limits

The graph is static. Dynamic features (`getattr`, callbacks in data structures, monkey patching,
metaclass magic) are not resolved; they are counted in `unresolved_reasons`, never guessed into
`calls`. `maybe_calls` edges are heuristic (precision 35-96% on samples of 10+ edges, depending on the codebase) and exist
to raise recall for impact analysis; Phase 3/4 must weight them. Run Phase 1 with a Python at least
as new as the syntax used by the target repo, or those files land in `parse_error_files`.
See `docs/GRAPH_SPEC.md` for the full contract and the list of what is not modelled.

## Tests (Phase 1 fixtures, plus Phases 2-3 on throw-away git repos)

```bash
python tests/runner.py            # no dependencies, 31 tests
python -m pytest                  # same tests under pytest
```

Fixtures in `tests/fixtures/` are small repos whose graphs were derived by hand from Python
semantics (not from the program's own output).

## Layout

```
src/aegis/  graph.py      schema, queries, LineIndex, collapse()
            index.py      files, module names, import resolution
            resolver.py   static type/target inference
            parser.py     the 3-pass build + edge emission
            validate.py   invariants + digest      oracle*.py  dynamic validation
            export.py     CSV / GraphML / report   cli.py      commands
tests/  validation/  docs/  graphs/
```

## macOS notes (Apple Silicon)

Everything is pure Python (no compiled dependency), so M1 is fine. Use Python 3.11+ (Apple's
built-in `python3` is usually older). The oracle may trigger a one-time firewall prompt for local
HTTP servers. The first `git` call without Xcode tools can open an install dialog (build still works).
`__MACOSX/` folders and `._*.py` files from Mac zips are skipped automatically.
