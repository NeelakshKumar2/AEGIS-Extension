# Validation

`RESULTS.md` (generated) shows how the graph was checked against real packages. Two independent
checks are used:

1. **Static invariants** (`aegis check`): ids, parents, spans, edge types, determinism, round-trip.
2. **Dynamic oracle** (`aegis oracle`): run a workload script under a call tracer and compare the
   calls that really happened with the graph (recall), and check that the graph's call edges whose
   call site ran were confirmed (precision). `workloads/` holds the scripts used here.

Reproduce (needs the packages installed; copies are made so file paths match the traced code):

    mkdir -p /tmp/vrepos && for p in requests click flask jinja2 markdown werkzeug networkx; do
      mkdir -p /tmp/vrepos/$p; cp -r "$(python -c "import $p,os;print(os.path.dirname($p.__file__))")" /tmp/vrepos/$p/$p; done
    python validation/make_results.py

For your own project: `python -m aegis oracle <repo_root> <script_that_exercises_it.py>`.
Use `python -m aegis audit <graph> <repo> -n 50` to sample edges for manual checking.

How to read the numbers: precision is a lower bound (a taken branch may simply not call the target;
`a and f()` short-circuits), recall only covers code the workload executed, and decorated callees
(e.g. networkx `@_dispatchable`) run inside wrappers, which is why `recall` and `recall+dispatch`
differ so much there.
