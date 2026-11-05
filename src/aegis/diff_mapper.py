"""Phase 2: map a commit's changed lines onto graph nodes ("seeds").

The graph MUST be built from the post-change checkout of the commit, because
line numbers are taken from the new side of the diff.
"""
import re
from dataclasses import dataclass, field

from . import gitutil
from .graph import LineIndex

HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


@dataclass
class Changes:
    ranges: dict = field(default_factory=dict)   # path -> [(start, end)] on the NEW side
    deleted_files: list = field(default_factory=list)


def parse_diff(text: str) -> Changes:
    """Parse `git diff --unified=0` output.

    Added/modified lines  -> their new line range.
    Pure deletions        -> a one-line range at the line just before the deletion
                             (so a removed statement still points at its function).
    """
    ch = Changes()
    old_path = new_path = None
    for line in text.splitlines():
        if line.startswith("--- "):
            old_path = None if line[4:] == "/dev/null" else line[6:]
        elif line.startswith("+++ "):
            if line[4:] == "/dev/null":
                if old_path:
                    ch.deleted_files.append(old_path)
                new_path = None
            else:
                new_path = line[6:]
        else:
            m = HUNK.match(line)
            if m and new_path:
                start = int(m.group(3))
                count = 1 if m.group(4) is None else int(m.group(4))
                if count > 0:
                    rng = (start, start + count - 1)
                else:
                    pos = max(start, 1)
                    rng = (pos, pos)
                ch.ranges.setdefault(new_path, []).append(rng)
    return ch


def commit_diff(repo, rev, context=0):
    """Raw unified diff of a commit against its first parent (root commits supported)."""
    return gitutil.git(repo, "-c", "core.quotepath=off", "diff-tree", "-p", "--root",
                       f"--unified={context}", "--no-renames", "--no-commit-id",
                       "--src-prefix=a/", "--dst-prefix=b/", "-r", rev)


def changed_lines(repo, rev) -> Changes:
    return parse_diff(commit_diff(repo, rev, 0))


@dataclass
class SeedMapping:
    seeds: list = field(default_factory=list)              # node ids, most specific first
    module_level_files: list = field(default_factory=list)  # changed outside any def (file node used)
    unmapped_files: list = field(default_factory=list)      # not in the graph (non-Python, etc.)
    deleted_files: list = field(default_factory=list)


def map_changes(G, changes: Changes) -> SeedMapping:
    """Changed line ranges -> innermost graph nodes, via the graph's LineIndex.

    A range outside every definition maps to the file node (module-level change).
    """
    idx = LineIndex(G)
    out = SeedMapping(deleted_files=list(changes.deleted_files))
    seeds = {}
    for path, ranges in sorted(changes.ranges.items()):
        if path not in G or G.nodes[path].get("type") != "file":
            out.unmapped_files.append(path)
            continue
        for a, b in ranges:
            for n in idx.at_range(path, a, b):
                seeds[n] = G.nodes[n].get("lineno", 0)
                if n == path and path not in out.module_level_files:
                    out.module_level_files.append(path)
    out.seeds = [n for n, _ in sorted(seeds.items(), key=lambda kv: (G.nodes[kv[0]].get("path", kv[0]), kv[1], kv[0]))]
    return out
