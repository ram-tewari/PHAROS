from decimal import Decimal

from shop.cart import Cart


def test_total_with_percentage_discount():
    cart = Cart(discount_code="SAVE10")
    cart.add_item("book", Decimal("20.00"), 2)
    assert cart.total() == Decimal("36.00")
