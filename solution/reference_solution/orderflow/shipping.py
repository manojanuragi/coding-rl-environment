"""Shipping cost lookup. Deliberately dumb -- flat rate per region, no
weight/dimension logic yet (that's ORDF-118, not this ticket)."""

from decimal import Decimal

from .models import Order

REGION_RATES = {
    "domestic": Decimal("5.99"),
    "domestic_expedited": Decimal("14.99"),
    "international": Decimal("24.99"),
}

FREE_SHIPPING_THRESHOLD = Decimal("75.00")


def compute_shipping(order: Order, subtotal: Decimal) -> Decimal:
    """Flat rate by region, waived once the pre-discount subtotal clears
    FREE_SHIPPING_THRESHOLD. Note: it's the pre-discount subtotal that's
    checked against the threshold -- a customer with a $80 cart and a 50%-off
    code still ships free, because the free-shipping promise was made based
    on cart size, not on what they end up paying. This part already matches
    the spec; it's not what you're here to fix.
    """
    if subtotal >= FREE_SHIPPING_THRESHOLD:
        return Decimal("0.00")
    return REGION_RATES.get(order.shipping_region, REGION_RATES["domestic"])
