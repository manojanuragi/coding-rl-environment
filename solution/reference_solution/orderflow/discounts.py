"""Discount application.

See docs/PRICING_RULES.md for the actual policy. Short version: FLAT
discounts always stack; at most one PERCENT discount ever applies (the best
one, if more than one is attached), and it's applied after the FLAT
discounts, not compounded with them.

(The cart service does not enforce single-use-per-order for promo codes --
tracked separately as ORDF-231 -- so `discounts` can contain more than one
PERCENT entry by the time it gets here. Defend against that rather than
assuming it can't happen.)
"""

from decimal import Decimal
from typing import List

from .models import Discount


def apply_discounts(subtotal: Decimal, discounts: List[Discount]) -> Decimal:
    unknown_kinds = {d.kind for d in discounts} - {"FLAT", "PERCENT"}
    if unknown_kinds:
        raise ValueError(f"unknown discount kind(s): {sorted(unknown_kinds)!r}")

    flat_total = sum(
        (d.value for d in discounts if d.kind == "FLAT"),
        Decimal("0"),
    )
    result = subtotal - flat_total

    percent_discounts = [d for d in discounts if d.kind == "PERCENT"]
    if percent_discounts:
        best = max(percent_discounts, key=lambda d: d.value)
        result = result - (result * (best.value / Decimal(100)))

    return max(result, Decimal("0.00"))
