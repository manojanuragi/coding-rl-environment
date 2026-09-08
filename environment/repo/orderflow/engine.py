"""The actual pricing pipeline. This is the file the checkout service and the
nightly reconciliation job both call into -- see the package docstring in
__init__.py. If the two disagree, we've either got a rounding difference or
someone deployed a pricing change to one but not the other; check git blame
before assuming it's this module's fault.

Pipeline, in order: subtotal -> discounts -> shipping -> tax -> total.
Full spec: docs/PRICING_RULES.md.
"""

from decimal import Decimal, ROUND_HALF_UP
from dataclasses import dataclass

from .models import Order
from .discounts import apply_discounts
from .shipping import compute_shipping
from .catalog import tax_rate_for

CENT = Decimal("0.01")


def _round_currency(amount: Decimal) -> Decimal:
    return amount.quantize(CENT, rounding=ROUND_HALF_UP)


@dataclass
class PricedOrder:
    order_id: str
    subtotal: Decimal
    discount_amount: Decimal
    shipping: Decimal
    tax: Decimal
    total: Decimal


def compute_subtotal(order: Order) -> Decimal:
    return sum((item.line_total for item in order.items), Decimal("0.00"))


def _blended_tax_rate(order: Order, subtotal: Decimal) -> Decimal:
    """Weighted average tax rate across the order's line items, weighted by
    each item's share of the (pre-discount) subtotal. Shipping itself is not
    taxed in any region we currently operate in, so it isn't part of this.
    """
    if subtotal == 0:
        return Decimal("0.00")
    weighted = sum(
        (item.line_total * tax_rate_for(item.category) for item in order.items),
        Decimal("0.00"),
    )
    return weighted / subtotal


def price_order(order: Order) -> PricedOrder:
    subtotal = compute_subtotal(order)
    shipping_cost = compute_shipping(order, subtotal)

    # NOTE: shipping is folded in here so that a discount code can never make
    # a customer's shipping negative-cost when combined with the free
    # shipping threshold. (See the shipping.py docstring for the free
    # shipping rule.)
    discountable = subtotal + shipping_cost
    discounted = apply_discounts(discountable, order.discounts)
    discount_amount = _round_currency(discountable - discounted)

    tax_rate = _blended_tax_rate(order, subtotal)
    tax = _round_currency(discounted * tax_rate)

    total = _round_currency(discounted + tax)

    return PricedOrder(
        order_id=order.order_id,
        subtotal=_round_currency(subtotal),
        discount_amount=discount_amount,
        shipping=_round_currency(shipping_cost),
        tax=tax,
        total=total,
    )
