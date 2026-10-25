"""Shopping cart with percentage and fixed-amount discounts."""

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal


@dataclass
class LineItem:
    sku: str
    unit_price: Decimal
    quantity: int = 1

    def subtotal(self) -> Decimal:
        return self.unit_price * self.quantity


@dataclass
class Cart:
    """Items a customer intends to buy."""

    items: dict[str, LineItem] = field(default_factory=dict)
    discount_code: str | None = None

    def add_item(self, sku: str, unit_price: Decimal, quantity: int = 1) -> None:
        """Add a product, merging quantities for an existing SKU."""
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        if sku in self.items:
            self.items[sku].quantity += quantity
        else:
            self.items[sku] = LineItem(sku, unit_price, quantity)

    def remove_item(self, sku: str) -> None:
        """Remove a product from the cart entirely."""
        self.items.pop(sku, None)

    def total(self) -> Decimal:
        """Sum of all line items after applying the discount code, rounded to cents."""
        gross = sum((item.subtotal() for item in self.items.values()), Decimal("0"))
        net = apply_discount(gross, self.discount_code)
        return net.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


DISCOUNTS = {"SAVE10": ("percent", Decimal("10")), "FIVEOFF": ("fixed", Decimal("5"))}


def apply_discount(amount: Decimal, code: str | None) -> Decimal:
    """Apply a percentage or fixed-amount coupon, never going below zero."""
    if not code or code not in DISCOUNTS:
        return amount
    kind, value = DISCOUNTS[code]
    if kind == "percent":
        return amount * (Decimal("100") - value) / Decimal("100")
    return max(Decimal("0"), amount - value)
