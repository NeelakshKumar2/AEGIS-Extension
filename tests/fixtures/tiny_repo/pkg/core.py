import os
from pkg.utils import helper
from pkg import utils


class Engine:
    def __init__(self):
        self.base = os.getcwd()

    def run(self):
        return self.step()

    def step(self):
        return helper(1)

    def other(self):
        return utils.unused()
