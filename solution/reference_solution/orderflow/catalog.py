"""Tax categories. Finance owns this file in practice -- when they add a new
product category they add a line here, that's the whole process. Not part of
the bug, but you'll need to know it exists to understand engine.py."""

from decimal import Decimal

# Category -> tax rate, as a fraction (0.07 == 7%).
# Sourced from the finance team's rate sheet, last touched 2025-11-03.
TAX_RATES = {
    "general": Decimal("0.07"),
    "grocery": Decimal("0.00"),
    "apparel": Decimal("0.05"),
    "electronics": Decimal("0.07"),
    "digital": Decimal("0.02"),
}

DEFAULT_TAX_RATE = TAX_RATES["general"]


def tax_rate_for(category: str) -> Decimal:
    return TAX_RATES.get(category, DEFAULT_TAX_RATE)
