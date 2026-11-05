# Phase 1 validation results

Targets: installed copies of real packages (not toy code). Graph checks: structural invariants, determinism, JSON round-trip. Behaviour checks: a traced run of a workload script (dynamic oracle).

## 1. Static call resolution, original parser (v0) vs this build (v2)

| repo | files | lines | calls | resolved | external | unresolved (v2) | unresolved (v0) | invariant problems | build s |
|---|---|---|---|---|---|---|---|---|---|
| requests | 18 | 5626 | 938 | 27.4% | 52.8% | 18.9% | 38.3% | 0 | 0.21 |
| click | 17 | 11117 | 1832 | 31.4% | 59.3% | 7.6% | 37.8% | 0 | 0.4 |
| flask | 24 | 9199 | 1189 | 22.0% | 67.0% | 10.3% | 42.8% | 0 | 0.32 |
| jinja2 | 25 | 14425 | 3057 | 46.9% | 42.7% | 8.4% | 35.3% | 0 | 0.65 |
| markdown | 33 | 8330 | 2153 | 28.0% | 56.9% | 14.6% | 60.5% | 0 | 0.49 |
| werkzeug | 52 | 21500 | 3897 | 30.4% | 55.3% | 13.2% | 40.1% | 0 | 0.94 |
| networkx | 580 | 191735 | 52071 | 44.3% | 37.6% | 16.9% | 62.8% | 0 | 9.86 |

## 2. Dynamic oracle: does the graph match what really executes?

`recall` = share of observed repo-to-repo calls that the graph contains. `recall+dispatch` also counts a call to an override when the graph has the call to the base method, and decorator/class-body calls attributed to the contained definition. `precision` = of the graph's call edges whose call site actually ran, the share confirmed by a real call there (decorated/generator callees excluded: their frames start from wrappers, so they cannot be confirmed or refuted).

| repo | observed calls | recall | recall+dispatch | +maybe_calls | precision (executed sites) | decided edges | maybe_calls precision |
|---|---|---|---|---|---|---|---|
| requests | 150 | 88.0% | 88.0% | 88.7% | 98.7% | 149 | 100.0% (n=1) |
| click | 260 | 79.6% | 88.5% | 90.8% | 99.6% | 229 | 70.0% (n=10) |
| flask | 168 | 70.8% | 83.3% | 83.9% | 99.3% | 142 | 100.0% (n=1) |
| jinja2 | 635 | 70.2% | 80.8% | 83.8% | 99.0% | 482 | 91.7% (n=24) |
| markdown | 385 | 70.1% | 73.5% | 79.0% | 100.0% | 304 | 95.5% (n=22) |
| werkzeug | 237 | 71.7% | 75.5% | 76.8% | 100.0% | 192 | 75.0% (n=4) |
| networkx | 967 | 12.9% | 69.1% | 75.4% | 100.0% | 145 | 35.3% (n=187) |
