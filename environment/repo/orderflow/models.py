"""Data classes for orders. Nothing clever here -- if you're looking for the
pricing bug, it isn't in this file."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import List


@dataclass
class LineItem:
    sku: str
    name: str
    unit_price: Decimal
    quantity: int
    category: str = "general"

    def __post_init__(self) -> None:
        if self.quantity < 1:
            raise ValueError(f"line item {self.sku!r} has non-positive quantity: {self.quantity}")
        if self.unit_price < 0:
            raise ValueError(f"line item {self.sku!r} has negative unit_price: {self.unit_price}")

    @property
    def line_total(self) -> Decimal:
        return self.unit_price * self.quantity


@dataclass
class Discount:
    code: str
    kind: str  # "PERCENT" or "FLAT"
    value: Decimal  # 15 means 15% for PERCENT, or a dollar amount for FLAT

    def __post_init__(self) -> None:
        if self.kind not in ("PERCENT", "FLAT"):
            raise ValueError(f"discount {self.code!r} has unknown kind: {self.kind!r}")
        if self.value < 0:
            raise ValueError(f"discount {self.code!r} has negative value: {self.value}")
        if self.kind == "PERCENT" and self.value > 100:
            raise ValueError(f"discount {self.code!r} is a PERCENT discount over 100%: {self.value}")


@dataclass
class Order:
    order_id: str
    items: List[LineItem]
    shipping_region: str = "domestic"
    discounts: List[Discount] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.items:
            raise ValueError(f"order {self.order_id!r} has no line items")
