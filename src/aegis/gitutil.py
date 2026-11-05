"""Thin wrappers around the git command line (no extra dependencies)."""
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path


class GitError(RuntimeError):
    pass


def git(repo, *args, check=True):
    p = subprocess.run(["git", "-C", str(repo), *args], capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    if check and p.returncode != 0:
        raise GitError(f"git {' '.join(args)} failed: {p.stderr.strip()}")
    return p.stdout


def rev_parse(repo, rev):
    return git(repo, "rev-parse", "--verify", rev + "^{commit}").strip()


def parent_of(repo, rev):
    """First parent hash, or None for a root commit."""
    out = git(repo, "rev-parse", "--verify", "-q", rev + "^", check=False).strip()
    return out or None


def commit_time(repo, rev):
    return int(git(repo, "show", "-s", "--format=%ct", rev).strip())


def commit_subject(repo, rev):
    return git(repo, "show", "-s", "--format=%s", rev).strip()


@contextmanager
def worktree(repo, rev):
    """Check out `rev` into a throw-away directory (the user's clone is not touched)."""
    tmp = tempfile.mkdtemp(prefix="aegis_wt_")
    dest = Path(tmp) / "wt"
    git(repo, "worktree", "add", "--detach", "-q", str(dest), rev)
    try:
        yield dest
    finally:
        git(repo, "worktree", "remove", "--force", str(dest), check=False)
        git(repo, "worktree", "prune", check=False)
        shutil.rmtree(tmp, ignore_errors=True)
