# ORDF-247: order totals wrong when multiple discount codes are applied

You're working in the `orderflow` repo (it's checked out at the root of your
working directory). It's a small, dependency-free Python package that prices
orders: subtotal, discounts, shipping, tax, total. It's called by the
checkout service and by a nightly job that re-derives what every order
*should* have cost and flags mismatches.

## The report

Support started getting complaints a few days ago about order totals being
off whenever a customer has more than one promo code attached to their
cart. Separately -- and it's not obvious yet whether this is the same bug or
a second one -- a customer shipping to Canada said their total came out
lower than the shipping quote they were shown at checkout would suggest.
Reconciliation flagged about 0.3% of yesterday's orders as "total doesn't
match rules," and that rate roughly tracks with "orders that had 2+ discount
codes on them," but nobody's dug past that.

`tests/test_pricing.py::test_two_percent_discounts_do_not_compound` is
currently failing on `main`, which is presumably related. It might not be
the whole story.

## What to do

1. Get the test suite actually running. It doesn't currently -- take a look
   at why before you assume the one failing test above is the only problem.
2. Read `docs/PRICING_RULES.md`. That document is the actual, agreed pricing
   policy. Where the code and that doc disagree, the doc is right and the
   code has a bug.
3. Find and fix whatever is causing order totals to come out wrong. Don't
   assume there's exactly one bug just because there's exactly one failing
   test.
4. Don't change the pricing *policy* -- if something in the code looks
   deliberate but you can't tell whether it's correct, check it against
   `docs/PRICING_RULES.md` rather than guessing.

## Definition of done

- `pytest` runs cleanly from the repo root (right now it can't even start).
- Every test in `tests/test_pricing.py` passes.
- Order totals match `docs/PRICING_RULES.md` in general, not just for the
  cases that happen to already have a test written for them -- correctness
  will be checked against a broader set of scenarios than what's in the
  repo, so fixing the letter of the one failing test without fixing the
  underlying rule won't hold up.
- You haven't weakened or removed the input validation that's already there
  (negative prices, bad quantities, out-of-range discount percentages, etc.
  should still be rejected the same way they are now).
- You haven't changed `docs/PRICING_RULES.md` itself to match whatever the
  code happens to do -- if you think the doc is genuinely wrong, say so, but
  don't just edit it into agreement.

You have shell access inside this working directory and can run whatever
commands you need (`pytest`, `python -m orderflow.cli`, etc.). Everything
you need is either already in the repo or in `docs/`.
