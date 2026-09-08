"""orderflow -- the pricing engine shared by the checkout service and the
nightly reconciliation job.

Everything in here is pure and synchronous on purpose: no DB calls, no HTTP.
The checkout service imports price_order() directly; the reconciliation job
re-runs it against yesterday's orders to make sure what we charged matches
what the rules say we should have charged. Keep it that way.
"""

from .models import LineItem, Discount, Order
from .engine import price_order, PricedOrder

__all__ = ["LineItem", "Discount", "Order", "price_order", "PricedOrder"]
__version__ = "0.4.2"
