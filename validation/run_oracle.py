"""Run every workload under the dynamic oracle and print one validation table.

    python validation/run_oracle.py [repo ...]       (repos must exist in /tmp/vrepos or --root)
"""
import argparse
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))
from aegis import graph as g          # noqa: E402
from aegis.oracle import evaluate, run_workload   # noqa: E402
from aegis.parser import build_graph  # noqa: E402

WORKLOADS = {"requests": "requests_wl.py", "click": "click_wl.py", "jinja2": "jinja2_wl.py",
             "flask": "flask_wl.py", "markdown": "markdown_wl.py", "werkzeug": "werkzeug_wl.py",
             "networkx": "networkx_wl.py"}

ap = argparse.ArgumentParser()
ap.add_argument("repos", nargs="*", default=list(WORKLOADS))
ap.add_argument("--root", default="/tmp/vrepos")
ap.add_argument("--json", default=None)
ap.add_argument("--examples", type=int, default=0)
a = ap.parse_args()

rows = {}
print(f"{'repo':10s} {'dyn':>5s} {'recall':>7s} {'+disp':>7s} {'+maybe':>7s} {'+refs':>7s} "
      f"{'prec(calls)':>12s} {'prec(maybe)':>12s}")
for repo in a.repos:
    root = Path(a.root) / repo
    G = build_graph(root, keep_call_log=True)
    tr = run_workload(root, HERE / "workloads" / WORKLOADS[repo])
    ev = evaluate(G, tr, top_missing=a.examples)
    rows[repo] = ev
    print(f"{repo:10s} {ev['dynamic_edges']:5d} {ev['recall_strict']:7.1%} {ev['recall_with_dispatch']:7.1%} "
          f"{ev['recall_with_maybe']:7.1%} {ev['recall_with_refs']:7.1%} "
          f"{ev['calls_precision_executed']:7.1%} ({ev['calls_decided']:4d}) "
          f"{ev['maybe_precision_executed']:6.1%} ({ev['maybe_decided']:4d})"
          + (f"   WORKLOAD ERROR {ev['workload_error']}" if ev["workload_error"] else ""))
    if a.examples:
        print("   miss reasons:", ev["miss_reasons"])
        for ex in ev["miss_examples"]:
            print("   ", ex)
if a.json:
    Path(a.json).write_text(json.dumps(rows, indent=1, default=str))
