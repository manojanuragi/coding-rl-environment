"""Baseline regression tests. Not exhaustive -- this is the suite that was
already here before ORDF-247, not the full spec. Passing this suite is
necessary, not sufficient; read docs/PRICING_RULES.md for the actual rules.
"""

from decimal import Decimal

from orderflow.models import LineItem, Discount, Order
from orderflow.engine import price_order


def _order(items, discounts=None, region="domestic"):
    return Order(
        order_id="TEST-1",
        items=items,
        shipping_region=region,
        discounts=discounts or [],
    )


def test_no_discount_charges_full_price_and_waives_shipping_over_threshold():
    order = _order([LineItem("SKU1", "Widget", Decimal("100.00"), 1, "general")])
    priced = price_order(order)
    assert priced.shipping == Decimal("0.00")
    assert priced.tax == Decimal("7.00")
    assert priced.total == Decimal("107.00")


def test_single_flat_discount():
    order = _order(
        [LineItem("SKU1", "Widget", Decimal("50.00"), 1, "general")],
        discounts=[Discount("TENOFF", "FLAT", Decimal("10"))],
    )
    priced = price_order(order)
    assert priced.discount_amount == Decimal("10.00")
    assert priced.shipping == Decimal("5.99")
    assert priced.tax == Decimal("2.80")
    assert priced.total == Decimal("48.79")


def test_single_percent_discount():
    order = _order(
        [LineItem("SKU1", "Widget", Decimal("50.00"), 1, "general")],
        discounts=[Discount("20PCT", "PERCENT", Decimal("20"))],
    )
    priced = price_order(order)
    assert priced.discount_amount == Decimal("10.00")
    assert priced.total == Decimal("48.79")


def test_two_percent_discounts_do_not_compound():
    """A cart that somehow picked up two PERCENT codes (10% and 30%) should
    only get the better of the two (30%), not both applied one after the
    other (which would take off 37% total) and not both summed (40%).
    """
    order = _order(
        [LineItem("SKU1", "Widget", Decimal("100.00"), 1, "general")],
        discounts=[
            Discount("10PCT", "PERCENT", Decimal("10")),
            Discount("30PCT", "PERCENT", Decimal("30")),
        ],
    )
    priced = price_order(order)
    assert priced.discount_amount == Decimal("30.00")
    assert priced.total == Decimal("74.90")


def test_discount_floors_at_zero_never_goes_negative():
    order = _order(
        [LineItem("SKU1", "Cheap thing", Decimal("10.00"), 1, "general")],
        discounts=[Discount("HUGE", "FLAT", Decimal("50"))],
    )
    priced = price_order(order)
    assert priced.discount_amount == Decimal("10.00")
    assert priced.tax == Decimal("0.00")
    assert priced.total == Decimal("5.99")


def test_rejects_zero_quantity_line_item():
    import pytest

    with pytest.raises(ValueError):
        LineItem("SKU1", "Widget", Decimal("10.00"), 0, "general")
