from shop import Order, compute_total
from shop.models import Item


def test_order():
    o = Order().add(Item(1.0))
    assert o.total() >= 0


class TestItem:
    def test_label(self):
        assert Item.free().label() == "item"
