# orderflow

Pricing engine used by checkout and by the nightly reconciliation job. Pure
Python, no I/O, no framework -- you hand it an `Order`, you get back a
`PricedOrder`.

## Setup

```
make install
make test
```

## Bug report (ORDF-247)

Support has been getting tickets since Tuesday about order totals looking
wrong when a customer has more than one promo code on their cart, and a
couple of tickets that look unrelated but might not be -- a customer in
Canada complained their total was lower than it should've been given the
shipping quote they were shown at checkout.

`tests/test_pricing.py::test_two_percent_discounts_do_not_compound` is
failing on `main` right now, which is presumably at least part of it. Take a
look at `docs/PRICING_RULES.md` for what's actually supposed to happen.

Nobody's had time to dig further than that -- reconciliation flagged about
0.3% of yesterday's orders as "total doesn't match rules," which lines up
with "orders that had 2+ discount codes attached," but that's as far as
anyone got before shipping it to you.
