"""Tiny manual-testing CLI.

    python -m orderflow.cli path/to/order.json

Expects a JSON file shaped like:

    {
      "order_id": "A-1001",
      "shipping_region": "domestic",
      "items": [
        {"sku": "SKU1", "name": "Widget", "unit_price": "19.99", "quantity": 2, "category": "general"}
      ],
      "discounts": [
        {"code": "SAVE10", "kind": "PERCENT", "value": "10"}
      ]
    }

Not used by any tests -- it's here because it's a lot faster to poke at a
weird order by hand this way than to write a throwaway script every time
support forwards us a ticket.
"""

import json
import sys
from decimal import Decimal

from .models import LineItem, Discount, Order
from .engine import price_order


def _load_order(path: str) -> Order:
    with open(path) as f:
        data = json.load(f)

    items = [
        LineItem(
            sku=i["sku"],
            name=i["name"],
            unit_price=Decimal(str(i["unit_price"])),
            quantity=int(i["quantity"]),
            category=i.get("category", "general"),
        )
        for i in data["items"]
    ]
    discounts = [
        Discount(code=d["code"], kind=d["kind"], value=Decimal(str(d["value"])))
        for d in data.get("discounts", [])
    ]
    return Order(
        order_id=data["order_id"],
        items=items,
        shipping_region=data.get("shipping_region", "domestic"),
        discounts=discounts,
    )


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if len(argv) != 1:
        print("usage: python -m orderflow.cli <order.json>", file=sys.stderr)
        return 2

    order = _load_order(argv[0])
    priced = price_order(order)
    print(json.dumps(priced.__dict__, default=str, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
