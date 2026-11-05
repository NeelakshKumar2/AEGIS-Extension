import json

from .base import Entity, register


class Item(Entity):
    def __init__(self, price: float):
        super().__init__()
        self.price = price

    def describe(self):
        return self.label() + json.dumps({})

    def label(self):
        return "item"

    @property
    def doubled(self):
        return self.price * 2

    @staticmethod
    def make(price):
        return Item(price)

    @classmethod
    def free(cls):
        return cls(0)


@register
class Order:
    def __init__(self):
        self.items: list[Item] = []
        self.owner = Item(1.0)

    def add(self, item: Item) -> "Order":
        self.items.append(item)
        return self

    def total(self):
        return sum(i.doubled for i in self.items) + self.owner.doubled

    def describe_all(self):
        out = []
        for it in self.items:
            out.append(it.describe())
        return out

    def first(self):
        o = Order()
        return o.add(Item.make(2)).total()
