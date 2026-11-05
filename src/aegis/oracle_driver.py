"""Runs a workload script under a call tracer and records what really happened.

    python -m aegis.oracle_driver <repo_root> <out.json> <script.py> [script args]

Records, for code living under <repo_root>:
  calls : caller code -> callee code (+ the caller line of the call)
  sites : every (caller, line) at which any call (Python or C) was made
Used by ``aegis oracle`` to measure how many real calls the static graph captured.
"""
import json
import os
import runpy
import sys
import threading
from collections import defaultdict


def main():
    root = os.path.realpath(sys.argv[1]) + os.sep
    out, script = sys.argv[2], sys.argv[3]
    sys.argv = sys.argv[3:]
    calls = defaultdict(int)          # (caller_key, line, callee_key) -> n
    sites = set()
    kcache = {}

    def key(code):
        k = kcache.get(code)
        if k is None:
            fn = code.co_filename
            # compare real paths: on macOS /tmp -> /private/tmp and /var -> /private/var,
            # so co_filename and the repo root can name the same file differently
            rp = os.path.realpath(fn) if os.path.isabs(fn) else fn
            if rp.startswith(root):
                k = (rp[len(root):].replace(os.sep, "/"), code.co_qualname)
            else:
                k = False
            kcache[code] = k
        return k

    def prof(frame, event, arg):
        if event == "call":
            back = frame.f_back
            if back is None:
                return
            ck = key(back.f_code)
            if not ck:
                return
            ek = key(frame.f_code)
            line = back.f_lineno
            sites.add((ck, line))
            if ek:
                calls[(ck, line, ek)] += 1
        elif event == "c_call":
            ck = key(frame.f_code)
            if ck:
                sites.add((ck, frame.f_lineno))

    sys.setprofile(prof)
    threading.setprofile(prof)
    err = None
    try:
        runpy.run_path(script, run_name="__main__")
    except SystemExit:
        pass
    except BaseException as e:           # a workload bug must not lose the trace
        err = repr(e)
    finally:
        sys.setprofile(None)
        threading.setprofile(None)
    with open(out, "w") as f:
        json.dump({"calls": [[list(k[0]), k[1], list(k[2]), n] for k, n in calls.items()],
                   "sites": [[list(s[0]), s[1]] for s in sites], "error": err}, f)
    if err:
        print("workload error:", err, file=sys.stderr)


if __name__ == "__main__":
    main()
