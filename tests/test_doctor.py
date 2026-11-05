import subprocess

import pytest  # noqa: F401

from aegis import doctor


def _git(repo, *a):
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *a],
                   check=True, capture_output=True)


def test_not_a_git_repo(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n")
    assert doctor.check(tmp_path)["verdict"] == doctor.BAD


def test_tiny_history_is_rejected_with_reason(tmp_path):
    (tmp_path / "a.py").write_text("def f():\n    pass\n")
    _git(tmp_path, "init", "-q"); _git(tmp_path, "add", "-A"); _git(tmp_path, "commit", "-qm", "i")
    res = doctor.check(tmp_path)
    assert res["verdict"] == doctor.BAD
    assert any("commits" in t for _, t in res["findings"])


def test_non_python_repo(tmp_path):
    (tmp_path / "a.js").write_text("1")
    _git(tmp_path, "init", "-q"); _git(tmp_path, "add", "-A"); _git(tmp_path, "commit", "-qm", "i")
    assert any("no Python" in t for _, t in doctor.check(tmp_path)["findings"])
