"""Discount application.

Only one discount is allowed per order, enforced upstream in the cart
service, so this just applies whatever list it's handed. See
docs/PRICING_RULES.md if you need the actual policy.
"""

from decimal import Decimal
from typing import List

from .models import Discount


def apply_discounts(subtotal: Decimal, discounts: List[Discount]) -> Decimal:
    result = subtotal
    for d in discounts:
        if d.kind == "PERCENT":
            result = result - (result * (d.value / Decimal(100)))
        elif d.kind == "FLAT":
            result = result - d.value
        else:
            raise ValueError(f"unknown discount kind: {d.kind!r}")
    return max(result, Decimal("0.00"))
