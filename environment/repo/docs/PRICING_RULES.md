# Pricing rules

This is the actual policy, agreed with Finance and Legal in the Q3 promo
audit. If the code and this doc ever disagree, this doc wins and the code has
a bug  that's happened before (see ORDF-204).

## Order of operations

1. **Subtotal**  sum of `unit_price * quantity` across line items.
2. **Discounts**  applied to the subtotal only. Shipping is never
   discounted, under any combination of codes. (Legal was very specific
   about this one: a promo code is marketing spend against the *merchandise*
   price, not a subsidy on our carrier contracts.)
3. **Shipping**  flat rate by region, added after discounting. Waived
   above the free-shipping threshold, checked against the pre-discount
   subtotal (see `shipping.py`).
4. **Tax**  applied to the discounted subtotal, using the blended rate
   across the order's line items. Shipping is not taxed. Tax is computed
   after discounting, since customers should pay tax on what they actually
   paid for the merchandise, not the pre-discount sticker price.
5. **Total** = discounted subtotal + shipping + tax.

## Discount stacking

We support two kinds of discount:

- **FLAT**  a fixed dollar amount off. These always stack: if an order has
  three FLAT discounts on it, all three apply, summed.
- **PERCENT**  a percentage off. **Only one PERCENT discount may ever apply
  to an order, even if more than one is attached to it.** If more than one is
  present, apply whichever single one saves the customer the most money, and
  ignore the rest. Percent discounts do not stack with each other, and they
  do not compound.

When both kinds are present on the same order: apply all FLAT discounts
first (summed straight off the subtotal), then apply the one eligible
PERCENT discount to what's left. Floor the result at $0  a discount can
never make a line item or order go negative.

(Why can an order even end up with two PERCENT discounts attached, if only
one is supposed to apply? Because the cart service doesn't enforce
single-use-per-order for promo codes  that's a known gap, tracked
separately as ORDF-231. Pricing has to defend against it either way, because
by the time an `Order` reaches this package, validating what *should* have
happened upstream is too late. Assume the discount list you're handed can
contain anything the `Discount` dataclass allows.)

## Rounding

All money in this codebase is `decimal.Decimal`. Round to the nearest cent
with `ROUND_HALF_UP` at each of: discount amount, tax, and total. Never use
`float` for money  Finance will notice, and they will email the whole
engineering list about it again.

## Worked example

Order: two line items, `$40.00` general-category merchandise and `$30.00`
apparel-category merchandise (`$70.00` subtotal). Domestic shipping
(`$5.99`, since `$70 < $75` free-shipping threshold). Two discounts attached:
a `$5` FLAT code and a `10%` PERCENT code.

1. Subtotal: `$70.00`
2. Discounts: FLAT first -> `$70.00 - $5.00 = $65.00`. Then the one PERCENT
   code -> `$65.00 - 10% = $58.50`. Discount amount taken: `$70.00 - $58.50 =
   $11.50`.
3. Shipping: `$5.99` (added, not discounted).
4. Tax: blended rate is `(40*0.07 + 30*0.05) / 70 = 0.061428571...`, applied
   to the *discounted* subtotal: `$58.50 * 0.061428571... = $3.5935714...`,
   which rounds to `$3.59`.
5. Total: `$58.50 + $5.99 + $3.59 = $68.08`.
