"""Dynamic oracle: validate the static graph against what actually executes.

Static analysis can be wrong in two ways: it can miss calls (recall) and invent them
(precision). Running real code under a tracer gives independent evidence for both:

  recall    of the calls observed at run time (repo -> repo), how many does the graph have?
  precision of the static call edges whose call site actually executed, how many were
            confirmed by a real call at that site? (executed-site precision; a *lower
            bound* on true precision because a taken branch may not call that target)

Covered-by-dispatch: a run-time call to an override is counted as covered when the
graph has a call to the overridden base method (virtual dispatch).
"""
import json
import os
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict


def run_workload(repo_root, script, extra_env=None, timeout=600):
    out = tempfile.NamedTemporaryFile(suffix=".json", delete=False).name
    env = dict(os.environ)
    # The driver is run as a plain file with -P so that nothing from AEGIS (which itself imports
    # networkx) is loaded before tracing starts; otherwise a networkx target would be imported
    # untraced and its import-time calls would silently vanish from the evidence.
    env["PYTHONPATH"] = os.pathsep.join(
        [str(repo_root)] + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else []))
    if extra_env:
        env.update(extra_env)
    driver = os.path.join(os.path.dirname(os.path.abspath(__file__)), "oracle_driver.py")
    r = subprocess.run([sys.executable, "-P", driver, str(repo_root), out, str(script)],
                       env=env, capture_output=True, text=True, timeout=timeout)
    with open(out) as f:
        data = json.load(f)
    os.unlink(out)
    data["stderr"] = r.stderr[-500:]
    return data


def map_code(G, rel, qual):
    """Map a code object (file, qualname) to a graph node id, or None."""
    if qual == "<module>":
        return rel if rel in G else None
    parts = qual.split(".")
    cut = len(parts)
    for i, p in enumerate(parts):
        if p.startswith("<") or p == "<locals>":
            cut = i
            break
    parts = parts[:cut]
    while parts:
        nid = f"{rel}::{'.'.join(parts)}"
        if nid in G:
            return nid
        parts = parts[:-1]
    return rel if rel in G else None


def evaluate(G, trace, top_missing=15):
    dyn = defaultdict(set)                 # (u, v) -> {lines}
    observed_at = defaultdict(set)         # (u, line) -> {callee nodes}
    for ck, line, ek, n in trace["calls"]:
        u, v = map_code(G, *ck), map_code(G, *ek)
        if u is None or v is None:
            continue
        observed_at[(u, line)].add(v)
        if G.nodes[v]["type"] in ("file", "class"):
            continue        # module / class body executing: an import or a `class` statement, not a call
        if u != v:
            dyn[(u, v)].add(line)
    executed = {(map_code(G, *s[0]), s[1]) for s in trace["sites"]}

    def edges(t):
        return {(u, v) for u, v, k in G.edges(keys=True) if k == t}

    calls, maybe, refs = edges("calls"), edges("maybe_calls"), edges("references")
    over = defaultdict(set)
    for u, v, k in G.edges(keys=True):
        if k == "overrides":
            over[u].add(v)

    def base_closure(v):
        seen, stack = set(), [v]
        while stack:
            x = stack.pop()
            for b in over.get(x, ()):
                if b not in seen:
                    seen.add(b)
                    stack.append(b)
        return seen

    # nested-owner collapse: dynamic calls whose caller or callee is a *file* node
    # (module-level code) are kept; ``calls`` has them too.
    D = set(dyn)
    covered_strict = {e for e in D if e in calls}
    covered_disp = {e for e in D if e in calls or any((e[0], b) in calls for b in base_closure(e[1]))}
    # decorators / class-body calls run in the enclosing class or module at run time, but the
    # graph attributes them to the decorated definition: count a call from a container as
    # covered when something it contains makes that call
    kids = defaultdict(list)
    for u, v, k in G.edges(keys=True):
        if k == "contains":
            kids[u].append(v)

    def descendants(u):
        out, stack = [], list(kids.get(u, ()))
        while stack:
            x = stack.pop()
            out.append(x)
            stack.extend(kids.get(x, ()))
        return out

    def owner_covered(e):
        if G.nodes[e[0]]["type"] not in ("class", "file"):
            return False
        return any((w, e[1]) in calls or any((w, b) in calls for b in base_closure(e[1]))
                   for w in descendants(e[0]))

    covered_disp |= {e for e in D if owner_covered(e)}
    covered_maybe = {e for e in D if e in covered_disp or e in maybe or
                     any((e[0], b) in maybe for b in base_closure(e[1]))}
    covered_refs = {e for e in D if e in covered_maybe or e in refs}
    n = max(len(D), 1)

    contradicted, deferred = [], []

    def edge_precision(edge_set, etype):
        conf = contra = 0
        for (u, v) in edge_set:
            lines = G[u][v][etype]["lines"]
            ran = [l for l in lines if (u, l) in executed]
            if not ran:
                continue
            seen = [observed_at.get((u, l), set()) for l in ran]
            if G.nodes[v]["type"] == "class":
                if any(c.startswith(v + ".") for s_ in seen for c in s_):
                    conf += 1                   # class without __init__: undecidable, skipped
                continue
            if any(v in s_ for s_ in seen) or any(v in base_closure(c) for s_ in seen for c in s_):
                conf += 1
            else:
                # a decorated / generator callee runs later or from inside a wrapper, so the
                # tracer never sees it called from this line: not evidence of a false edge
                nd = G.nodes[v]
                if nd.get("decorators") or nd.get("is_generator"):
                    deferred.append((u, v))
                    continue
                contra += 1
                if len(contradicted) < 40:
                    contradicted.append((u, min(ran), v, etype))
        return conf, contra

    cc, cx = edge_precision(calls, "calls")
    mc, mx = edge_precision(maybe, "maybe_calls")

    missing = D - covered_refs
    diag = Counter()
    examples = []
    log = defaultdict(list)
    for owner, line, kind, reason, text, targets in G.graph.get("call_log", ()):
        log[(owner, line)].append((kind, reason, text))
    for (u, v) in sorted(D - covered_disp):
        why = Counter()
        for l in dyn[(u, v)]:
            entries = [e for e in log.get((u, l), ()) if e[0] != "resolved"] or log.get((u, l), [("nolog", "-", "-")])
            for kind, reason, text in entries:
                why[f"{kind}:{reason}"] += 1
        top = why.most_common(1)[0][0] if why else "no-call-site"
        diag[top] += 1
        if len(examples) < top_missing and (u, v) not in covered_maybe:
            l = min(dyn[(u, v)])
            ex = [e for e in log.get((u, l), []) if e[0] != "resolved"]
            examples.append((u, l, v, ex[:2] if ex else top))
    return {
        "dynamic_edges": len(D),
        "recall_strict": len(covered_strict) / n,
        "recall_with_dispatch": len(covered_disp) / n,
        "recall_with_maybe": len(covered_maybe) / n,
        "recall_with_refs": len(covered_refs) / n,
        "calls_precision_executed": cc / max(cc + cx, 1), "calls_decided": cc + cx,
        "maybe_precision_executed": mc / max(mc + mx, 1), "maybe_decided": mc + mx,
        "static_calls": len(calls), "static_maybe": len(maybe),
        "miss_reasons": dict(diag.most_common(12)),
        "miss_examples": examples,
        "contradicted_examples": contradicted,
        "deferred_undecidable": len(deferred),
        "workload_error": trace.get("error"),
    }
