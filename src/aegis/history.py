"""Phase 3a: co-change history mined from git.

Two files "co-change" when they appear in the same commit. For a file s that changes, the
confidence that f changes too is  conf(s -> f) = commits(s and f) / commits(s).

Leakage rule: an index is only ever used for a commit AFTER the commits it was built from
(`pipeline` adds a commit to the index after that commit has been scored).
"""
from collections import Counter, defaultdict

from . import gitutil

MAX_FILES_PER_COMMIT = 30     # larger commits (mass renames, reformatting) carry no pairing signal


def log(repo, n=300, rev="HEAD", py_only=True):
    """[(sha, unix_time, [files])] for the last n non-merge commits reachable from rev, OLDEST first."""
    out = gitutil.git(repo, "-c", "core.quotepath=off", "log", "--no-merges", "--no-renames",
                      f"--max-count={n}", "--name-only", "--format=%x01%H %ct", rev)
    commits = []
    for block in out.split("\x01")[1:]:
        lines = block.strip("\n").split("\n")
        sha, ts = lines[0].split()
        files = [l for l in lines[1:] if l.strip() and (l.endswith(".py") or not py_only)]
        commits.append((sha, int(ts), files))
    commits.reverse()
    return commits


class CoChange:
    def __init__(self, max_files=MAX_FILES_PER_COMMIT):
        self.max_files = max_files
        self.n = Counter()                       # file -> commits touching it
        self.pair = defaultdict(Counter)         # file -> {other: commits touching both}
        self.commits = 0

    def add(self, files):
        files = sorted(set(files))
        if not files or len(files) > self.max_files:
            return
        self.commits += 1
        for a in files:
            self.n[a] += 1
            for b in files:
                if a != b:
                    self.pair[a][b] += 1

    def partners(self, seed_files, top=50):
        """{file: (confidence, support)}: best over the seed files, strongest `top` only."""
        best = {}
        for s in seed_files:
            total = self.n.get(s, 0)
            if not total:
                continue
            for f, c in self.pair.get(s, {}).items():
                conf = c / total
                if f not in best or (conf, c) > best[f]:
                    best[f] = (conf, c)
        ranked = sorted(best.items(), key=lambda kv: (-kv[1][0], -kv[1][1], kv[0]))
        return dict(ranked[:top])
