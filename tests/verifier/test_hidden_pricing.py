"""Grading suite for ORDF-247. This file is not part of the repository the
agent works in -- the grading harness drops a fresh copy of it into the
container at grading time (see grade.py), after the agent is done, so
nothing the agent did to *this* file (or to environment/repo/tests/) has any
effect on the score. It imports orderflow the same way any other test would;
it doesn't reach into private/underscored attributes or otherwise assume
anything about how the fix is implemented internally.

Every expected number below was computed independently with plain Decimal
arithmetic (see the comment above each case) rather than by running
whichever version of the code happened to be sitting in the repo at the
time, precisely so that a correct-looking-but-coincidentally-matching
implementation can't slip through.
"""

import itertools
import uuid
from decimal import Decimal

import pytest

from orderflow.models import LineItem, Discount, Order
from orderflow.engine import price_order

# Every order built by _order() gets its own random-ish, per-run id rather
# than a fixed literal. A submission that special-cased on a known order_id
# (or on the specific instance count) instead of actually fixing the pricing
# logic gets nothing predictable to key off of -- see
# analysis/grader_attacks.md, attack #2.
_ID_PREFIX = uuid.uuid4().hex[:8]
_id_counter = itertools.count(1)


def _order(items, discounts=None, region="domestic"):
    return Order(
        order_id=f"{_ID_PREFIX}-{next(_id_counter)}",
        items=items,
        shipping_region=region,
        discounts=discounts or [],
    )


# ---------------------------------------------------------------------------
# Regression: the suite that shipped with the repo. Re-stated here from
# scratch (not imported from environment/repo/tests) so that weakening or
# deleting the original test file doesn't help.
# ---------------------------------------------------------------------------


def test_regression_no_discount():
    order = _order([LineItem("SKU1", "Widget", Decimal("100.00"), 1, "general")])
    priced = price_order(order)
    assert priced.shipping == Decimal("0.00")
    assert priced.tax == Decimal("7.00")
    assert priced.total == Decimal("107.00")


def test_regression_single_flat_discount():
    order = _order(
        [LineItem("SKU1", "Widget", Decimal("50.00"), 1, "general")],
        discounts=[Discount("TENOFF", "FLAT", Decimal("10"))],
    )
    priced = price_order(order)
    assert priced.total == Decimal("48.79")


def test_regression_discount_floors_at_zero():
    order = _order(
        [LineItem("SKU1", "Cheap thing", Decimal("10.00"), 1, "general")],
        discounts=[Discount("HUGE", "FLAT", Decimal("50"))],
    )
    priced = price_order(order)
    assert priced.discount_amount == Decimal("10.00")
    assert priced.total == Decimal("5.99")


# ---------------------------------------------------------------------------
# Bug 1, isolated: two PERCENT discounts must not compound or sum. Cart is
# kept above the free-shipping threshold on purpose, so a solution that only
# fixed the shipping bug (bug 2) and left percent-stacking broken cannot
# pass this one by accident -- shipping is $0 either way here.
# ---------------------------------------------------------------------------


def test_percent_discounts_use_best_only_not_compounded():
    order = _order(
        [LineItem("SKU1", "Widget", Decimal("200.00"), 1, "general")],
        discounts=[
            Discount("10PCT", "PERCENT", Decimal("10")),
            Discount("40PCT", "PERCENT", Decimal("40")),
        ],
    )
    priced = price_order(order)
    assert priced.discount_amount == Decimal("80.00")
    assert priced.shipping == Decimal("0.00")
    assert priced.tax == Decimal("8.40")
    assert priced.total == Decimal("128.40")


def test_three_percent_discounts_still_picks_a_single_best():
    # Kept under the free-shipping threshold on purpose (unlike the test
    # above) so this case also still exercises bug 2 -- two independent
    # checks in one scenario, tie-breaking between equal-value PERCENT
    # discounts plus "don't discount shipping."
    order = _order(
        [LineItem("SKU1", "Widget", Decimal("60.00"), 1, "general")],
        discounts=[
            Discount("A", "PERCENT", Decimal("20")),
            Discount("B", "PERCENT", Decimal("20")),
            Discount("C", "PERCENT", Decimal("5")),
        ],
    )
    priced = price_order(order)
    assert priced.discount_amount == Decimal("12.00")
    assert priced.shipping == Decimal("5.99")
    assert priced.tax == Decimal("3.36")
    assert priced.total == Decimal("57.35")


# ---------------------------------------------------------------------------
# Bug 2, isolated: shipping must never be discounted. Cart is kept under the
# free-shipping threshold (so shipping is actually charged and can actually
# be wrongly discounted), with only a single discount so bug 1 can't be the
# thing making this pass or fail.
# ---------------------------------------------------------------------------


def test_shipping_is_never_discounted():
    order = _order(
        [LineItem("SKU1", "Widget", Decimal("50.00"), 1, "general")],
        discounts=[Discount("HALF", "PERCENT", Decimal("50"))],
    )
    priced = price_order(order)
    # If shipping had been folded into the discountable amount, a 50% code
    # would have cut the $5.99 shipping down too. It must arrive untouched.
    assert priced.shipping == Decimal("5.99")
    assert priced.discount_amount == Decimal("25.00")
    assert priced.tax == Decimal("1.75")
    assert priced.total == Decimal("32.74")


def test_free_shipping_threshold_uses_pre_discount_subtotal():
    # $75 pre-discount subtotal clears the free-shipping threshold even
    # though a steep discount brings what's actually paid well under it.
    order = _order(
        [LineItem("SKU1", "Widget", Decimal("75.00"), 1, "general")],
        discounts=[Discount("BIG", "PERCENT", Decimal("90"))],
    )
    priced = price_order(order)
    assert priced.shipping == Decimal("0.00")


# ---------------------------------------------------------------------------
# Both bugs at once, plus a same-order sanity check on totals: this is
# closest to the actual customer complaint that opened ORDF-247 (multiple
# codes stacked, order under the free-shipping line).
# ---------------------------------------------------------------------------


def test_both_bugs_combined_realistic_cart():
    order = _order(
        [LineItem("SKU1", "Widget", Decimal("40.00"), 1, "general")],
        discounts=[
            Discount("15PCT", "PERCENT", Decimal("15")),
            Discount("25PCT", "PERCENT", Decimal("25")),
        ],
    )
    priced = price_order(order)
    assert priced.discount_amount == Decimal("10.00")
    assert priced.shipping == Decimal("5.99")
    assert priced.tax == Decimal("2.10")
    assert priced.total == Decimal("38.09")


# ---------------------------------------------------------------------------
# FLAT + PERCENT interaction (order of operations from the spec doc), across
# mixed tax categories -- also pins down the blended tax rate calculation,
# which is correct in the starting repo but easy to break while refactoring
# discounts.py/engine.py.
# ---------------------------------------------------------------------------


def test_flat_and_percent_combined_matches_spec_worked_example():
    order = _order(
        [
            LineItem("SKU1", "General thing", Decimal("40.00"), 1, "general"),
            LineItem("SKU2", "Apparel thing", Decimal("30.00"), 1, "apparel"),
        ],
        discounts=[
            Discount("FIVE", "FLAT", Decimal("5")),
            Discount("TENPCT", "PERCENT", Decimal("10")),
        ],
    )
    priced = price_order(order)
    assert priced.discount_amount == Decimal("11.50")
    assert priced.shipping == Decimal("5.99")
    assert priced.tax == Decimal("3.59")
    assert priced.total == Decimal("68.08")


def test_multiple_flat_discounts_stack_with_one_percent_mixed_categories():
    order = _order(
        [
            LineItem("SKU1", "Grocery thing", Decimal("20.00"), 1, "grocery"),
            LineItem("SKU2", "Apparel thing", Decimal("20.00"), 1, "apparel"),
        ],
        discounts=[
            Discount("A", "FLAT", Decimal("3")),
            Discount("B", "FLAT", Decimal("5")),
            Discount("C", "PERCENT", Decimal("25")),
        ],
    )
    priced = price_order(order)
    assert priced.discount_amount == Decimal("16.00")
    assert priced.tax == Decimal("0.60")
    assert priced.total == Decimal("30.59")


# ---------------------------------------------------------------------------
# Region / free-shipping boundary handling.
# ---------------------------------------------------------------------------


def test_exactly_at_free_shipping_threshold_international():
    order = _order(
        [LineItem("SKU1", "Widget", Decimal("75.00"), 1, "general")],
        region="international",
    )
    priced = price_order(order)
    assert priced.shipping == Decimal("0.00")
    assert priced.total == Decimal("80.25")


def test_just_under_free_shipping_threshold_international():
    order = _order(
        [LineItem("SKU1", "Widget", Decimal("74.99"), 1, "general")],
        region="international",
    )
    priced = price_order(order)
    assert priced.shipping == Decimal("24.99")
    assert priced.total == Decimal("105.23")


# ---------------------------------------------------------------------------
# Low-tax category, unrelated to either bug -- catches an over-eager fix
# that hardcodes the "general" 7% rate somewhere while restructuring
# discounts.py/engine.py.
# ---------------------------------------------------------------------------


def test_digital_category_tax_rate_and_percent_discount():
    order = _order(
        [LineItem("SKU1", "E-book", Decimal("30.00"), 1, "digital")],
        discounts=[Discount("HALF", "PERCENT", Decimal("50"))],
    )
    priced = price_order(order)
    assert priced.tax == Decimal("0.30")
    assert priced.total == Decimal("21.29")


# ---------------------------------------------------------------------------
# Validation still has to work -- a fix that loosens LineItem/Discount
# validation to make some other test pass should not be rewarded.
# ---------------------------------------------------------------------------


def test_negative_unit_price_still_rejected():
    with pytest.raises(ValueError):
        LineItem("SKU1", "Widget", Decimal("-1.00"), 1, "general")


def test_percent_discount_over_100_still_rejected():
    with pytest.raises(ValueError):
        Discount("BAD", "PERCENT", Decimal("150"))


def test_unknown_discount_kind_still_rejected():
    order = _order(
        [LineItem("SKU1", "Widget", Decimal("10.00"), 1, "general")],
    )
    # Constructing a Discount with a bad kind is already rejected by
    # __post_init__; to exercise apply_discounts' own guard we bypass the
    # dataclass validation the way a deserialization bug upstream could.
    bad_discount = Discount.__new__(Discount)
    bad_discount.code = "BAD"
    bad_discount.kind = "BOGO"
    bad_discount.value = Decimal("1")
    order.discounts.append(bad_discount)

    from orderflow.discounts import apply_discounts

    with pytest.raises(ValueError):
        apply_discounts(Decimal("10.00"), order.discounts)
