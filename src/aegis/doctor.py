"""`aegis doctor REPO`: will AEGIS work on this repository? Answers before you spend hours mining.

Checks (each gives a reason; the verdict is the worst of them):
  * it is a git repository with enough non-merge history (and not a truncated shallow clone)
  * it is mostly Python (AEGIS analyses Python only)
  * the Python files parse (syntax errors / syntax newer than this interpreter)
  * the graph has substance and the share of unresolved calls is known
  * enough commits are usable for ranking: >= 2 changed .py files, one non-test, not a mass change
"""
import os
from pathlib import Path

from . import gitutil, history, impact
from .parser import SKIP_DIRS, build_graph

OK, LIMITED, BAD = "SUPPORTED", "LIMITED", "NOT SUPPORTED"
_RANK = {OK: 0, LIMITED: 1, BAD: 2}
_OTHER = {".js", ".ts", ".tsx", ".java", ".go", ".rs", ".c", ".cc", ".cpp", ".h", ".cs", ".rb", ".php"}


def _lang_mix(repo):
    py = other = 0
    for root, dirs, names in os.walk(repo):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        for n in names:
            ext = os.path.splitext(n)[1].lower()
            py += ext == ".py"
            other += ext in _OTHER
    return py, other


def check(repo, window=200, min_usable=30):
    repo = Path(repo)
    findings, info = [], {}

    def add(level, text):
        findings.append((level, text))

    def done():
        if not findings:
            add(OK, "all checks passed")
        return {"verdict": max((lv for lv, _ in findings), key=_RANK.get), "findings": findings, "info": info}

    if not repo.is_dir():
        add(BAD, f"{repo} is not a directory")
        return done()
    try:
        gitutil.git(repo, "rev-parse", "--git-dir")
    except (gitutil.GitError, FileNotFoundError):
        add(BAD, "not a git repository (Phase 2/3 need commit history)")
        return done()

    shallow = gitutil.git(repo, "rev-parse", "--is-shallow-repository", check=False).strip() == "true"
    commits = history.log(repo, window)
    info.update(commits_in_window=len(commits), shallow_clone=shallow)
    if len(commits) < 50:
        add(BAD if len(commits) < 20 else LIMITED,
            f"only {len(commits)} commits available" + (" (shallow clone: re-clone without --depth)" if shallow else ""))
    elif shallow:
        add(LIMITED, "shallow clone: history is truncated at the oldest commit")

    py, other = _lang_mix(repo)
    info.update(py_files=py, other_language_files=other)
    if py == 0:
        add(BAD, "no Python files")
    elif py < 5:
        add(LIMITED, f"only {py} Python files")
    elif other > 2 * py:
        add(LIMITED, f"mostly non-Python ({py} .py vs {other} other source files): the graph covers Python only")

    if py:
        G = build_graph(repo, maybe_calls=True)
        s = G.graph["stats"]
        info.update(files_parsed=s.get("files_parsed"), parse_errors=s.get("parse_errors"),
                    functions=sum(1 for _, d in G.nodes(data=True) if d.get("type") in ("function", "test")),
                    classes=sum(1 for _, d in G.nodes(data=True) if d.get("type") == "class"),
                    call_edges=sum(1 for _, _, k in G.edges(keys=True) if k == "calls"))
        tot = max(s.get("files_parsed", 0) + s.get("parse_errors", 0), 1)
        bad = s.get("parse_errors", 0)
        if bad / tot > 0.2:
            add(BAD, f"{bad}/{tot} files fail to parse (Python 2 code, or syntax newer than this interpreter)")
        elif bad:
            add(LIMITED, f"{bad} of {tot} files fail to parse and are skipped")
        calls = s.get("calls_total", 0)
        if calls:
            un = s.get("calls_unresolved", 0) / calls
            info["unresolved_call_share"] = round(un, 3)
            if un > 0.4:
                add(LIMITED, f"{un:.0%} of calls unresolved (very dynamic code): structural evidence is weak, "
                             "co-change history carries the ranking")
        if info["functions"] < 10:
            add(LIMITED, "fewer than 10 functions: too small to rank anything")

    cfg = impact.Config()
    c = dict(usable_commits=0, no_python=0, single_file=0, tests_only=0, mass_changes=0)
    for _, _, files in commits[1:]:
        n = len(files)
        if n == 0:
            c["no_python"] += 1
        elif n > cfg.max_files:
            c["mass_changes"] += 1
        elif n == 1:
            c["single_file"] += 1
        elif all("test" in f.lower() for f in files):
            c["tests_only"] += 1
        else:
            c["usable_commits"] += 1
    info.update(c)
    usable = c["usable_commits"]
    if commits and usable < 10:
        add(BAD, f"only {usable} usable commits in the last {len(commits)}: too few to evaluate (raise --window)")
    elif commits and usable < min_usable:
        add(LIMITED, f"{usable} usable commits in the last {len(commits)}; mine more to get {min_usable}+")
    return done()


def format_report(res):
    out = [f"VERDICT: {res['verdict']}", ""]
    out += [f"  [{lv}] {t}" for lv, t in res["findings"]]
    if res["info"]:
        out += ["", "facts:"] + [f"  {k}: {v}" for k, v in res["info"].items()]
    return "\n".join(out)
