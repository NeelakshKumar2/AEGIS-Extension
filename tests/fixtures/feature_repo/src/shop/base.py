def register(cls):
    return cls


class Entity:
    def __init__(self):
        self.ready = True

    def label(self):
        return "entity"

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def __getitem__(self, k):
        return k
