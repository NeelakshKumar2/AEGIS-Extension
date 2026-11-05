from . import base
from .models import Item

try:
    from json import loads as parse
except ImportError:
    def parse(s):
        return s

if True:
    def total(items):
        return len(items)
else:
    def total(items):
        return 0


def use(x):
    return x.unknown_method()


def use2(x):
    return x.render_page()


def shadow(helper):
    return helper()


def helper():
    return 1


def outer():
    def inner():
        return helper()
    return inner() + helper()


def ctx():
    with base.Entity() as e:
        return e["a"]
