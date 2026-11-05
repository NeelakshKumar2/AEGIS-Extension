from pkg.utils import helper
from pkg.core import Engine


def test_helper():
    assert helper(2) == 3


def test_engine_builds():
    Engine()
