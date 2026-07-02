# Test coverage — what's actually being proven

This is a companion to the pytest suite in `backend/marketplace/tests/` —
not a restatement of the test output (the actual pytest run is stronger
evidence than any summary of it), but a plain-English explanation of
*why* each group of tests demonstrates what it claims to, for Q&A prep
and personal reference.

Run the real thing with `pytest -v` from `backend/`. This document exists
so you can explain any of it without re-reading the code under pressure.

---

## TC-001 / TC-002 — Registration (`test_registration.py`, 8 tests)

The interesting assertions aren't "does registration return 201" — that's
the easy part. The ones worth being able to explain:

- **`test_password_is_hashed_not_plaintext`** — checks `user.password !=
  'GrowFresh2026'` *and* `user.check_password('GrowFresh2026')` returns
  `True`. Both matter: the first alone would also pass if the password
  were stored reversibly encrypted rather than hashed; the second proves
  it's still verifiable, i.e. genuinely hashed, not just mangled.
- **`test_postcode_is_normalised`** — this one actually caught my own
  wrong assumption while writing it. `.upper().strip()` only trims
  *outer* whitespace; `'bs1 4dj'` becomes `'BS1 4DJ'`, not `'BS14DJ'`. I
  had the test asserting the wrong thing until pytest told me so.
- **`test_error_does_not_reveal_whether_username_exists`** (in
  `test_security.py`, but same idea) — compares the JSON body of a
  failed login for a real username against a fake one and asserts
  they're byte-for-byte identical. That's what actually satisfies TC-022's
  "without revealing if user exists" — not just "login fails", but that
  failure looks the same either way.

## TC-003 / TC-004 / TC-005 / TC-011 / TC-014 — Products (`test_products.py`, 16 tests)

Four separate concerns living in one file because they all revolve
around the same `ProductListCreateView`:

- **Creation is producer-scoped, not client-supplied.** The API payload
  never includes `producer` — the view injects
  `request.user.producer_profile.id` itself. The test proves this by
  asserting the *created* product's `.producer` equals the fixture, even
  though the test never sent that field.
- **Visibility is a derived property, not a stored flag.** `is_visible`
  combines availability status *and* stock count. Two separate tests
  (`out_of_stock`, `unavailable_status`) each flip only one of those two
  inputs and confirm the product still disappears — proving the OR logic
  actually works, not just that *a* condition works.
- **Cross-producer edit protection** (`test_producer_cannot_update_another_producers_product`)
  asserts both the `403` *and* that the stock value in the database is
  unchanged — a permission check that returns the right status code but
  still mutates the object would be a real, dangerous bug that a
  status-code-only test would miss.
- **Organic filter** — asserts `all(p['organic_certified'] for p in
  data)` across the whole filtered response, not just "the one organic
  product is present". That distinction matters: a filter that's silently
  a no-op would still make the weaker version of this test pass.

## TC-006 — Cart (`test_cart.py`, 8 tests)

- **`test_cannot_exceed_stock_cumulatively_across_two_additions`** is the
  one worth remembering. It adds `stock - 2` in one request (succeeds),
  then adds `5` more in a second request. Neither request alone exceeds
  stock, but together they would. This is specifically testing that the
  stock check looks at *what's already in the cart plus the new
  quantity*, not just the new quantity in isolation — the actual
  overselling bug that got fixed earlier in development.

## TC-007 / TC-008 — Checkout (`test_checkout.py`, 8 tests)

- **Commission math is asserted to the penny**, not just "some commission
  was charged". £2.50 × 4 = £10.00 total, £0.50 commission (exactly 5%),
  £9.50 payout (exactly 95%). For the multi-vendor case: £5.00 +
  £4.20 = £9.20 total, £0.46 commission.
- **`test_checkout_rejects_delivery_date_before_lead_time`** — the
  producer fixture has a 48-hour lead time; the test requests delivery
  *today*. This proves the lead-time validation is a real constraint
  being enforced, not just present in the form as a UI hint.
- **`test_each_suborder_has_independent_subtotal`** — the real point of
  TC-008. Splitting a multi-vendor cart into separate sub-orders is easy
  to get subtly wrong (e.g. accidentally sharing a running total across
  producers). This asserts each producer's subtotal matches *only their
  own* items.

## TC-009 / TC-010 — Producer orders & status (`test_producer_orders.py`, 6 tests)

- **`test_cannot_skip_a_status_step`** sends `pending → ready` directly
  (skipping `confirmed`) and asserts `400`. This is the test that proves
  the `STATUS_ORDER.index(current) + 1` check in
  `UpdateSubOrderStatusSerializer` actually enforces one-step-at-a-time,
  rather than just accepting any status in the choices list.
- **`test_other_producer_cannot_update_suborder_status`** — a second
  producer, unrelated to the order, tries to advance someone else's
  sub-order and gets `403`.

## TC-012 — Settlements (`test_settlements.py`, 3 tests)

- **`test_settlement_only_counts_delivered_suborders`** is the direct
  regression test for the bug this whole feature started from. It
  creates one `delivered` sub-order and one `pending` sub-order for the
  *same* producer, then asserts the settlement total only reflects the
  delivered one. Worth knowing: I originally wrote this test putting
  both sub-orders under the same producer *and* the same order, which
  the database rejected — `ProducerSubOrder` has a
  `unique_together = ('order', 'producer')` constraint, since one
  producer can only appear once per order. Fixed by using two different
  producers, which is the realistic scenario anyway.

## TC-025 — Admin dashboard (`test_admin_dashboard.py`, 7 tests)

- **`test_commission_split_correct_for_multi_vendor_order`** checks the
  *per-producer* commission figures inside a single order's breakdown
  (£80 → £4.00, £70 → £3.50), not just the order-level total — this is
  what actually proves the "producer payment per supplier" requirement
  from the brief, which is easy to satisfy only partially (order totals
  right, per-producer breakdown wrong).
- **`test_derived_status_is_delivered_when_all_suborders_delivered`** —
  after asserting the report shows `'delivered'`, it *also* asserts
  `order.status == 'pending'` on the underlying database row. That
  second assertion is the important one: it proves the report is
  correctly ignoring the stale `Order.status` field and computing status
  from the sub-orders instead, rather than coincidentally agreeing with
  it.

## TC-022 — Security (`test_security.py`, 12 tests)

- **`test_logout_ends_session`** deliberately does *not* use
  `force_authenticate` (which bypasses Django's session machinery
  entirely and would make this test meaningless). It uses
  `api_client.login()` / `.logout()` — a real session cookie cycle — then
  proves a request after logout is rejected. This is the one test in the
  suite doing genuine session-based auth rather than DRF's test shortcut.

## TC-013 (partial) — Food miles (`test_food_miles.py`, 2 tests)

This is intentionally partial — see the README's "Known limitations"
section for what's *not* covered (per-product display on the catalogue
page). What *is* tested:

- Two postcodes that look like they should be "the same area" (`BS1
  4DJ` and `BS1 5JG`) actually resolve to two different entries in the
  lookup table (`BS14` and `BS15` are both real, distinct keys), so the
  correct result is a real computed distance (4.66 miles), not a
  same-sector shortcut. I got this wrong on the first attempt — assumed
  same-sector, pytest disagreed, checked the actual lookup table, fixed
  the test.
- A second test deliberately uses postcodes that *do* share the same
  4-character sector, to prove the same-sector shortcut path also works
  correctly when it's the genuinely correct behaviour.

## TC-015 (backend portion only) — Allergens (`test_allergens.py`, 3 tests)

Covers the data layer only: blank input defaults to "No common allergens
declared.", explicit input is preserved verbatim, and the field is
present in the catalogue API response. The actual customer-facing
display (the red warning badge vs. the quieter "none declared" state)
was verified manually in-browser during that feature's development —
that part is inherently visual and isn't meaningfully testable at the
API layer.

## TC-021 — Order history (`test_order_history.py`, 3 tests)

Standard ownership-scoping pattern, same shape as several other tests in
this suite: create data as one customer, assert a *different* customer
sees none of it.

## TC-016 — Seasonal availability (`test_seasonal_availability.py`, 8 tests)

- **Every date-dependent test is written relative to the real current
  month** (`timezone.localdate().month`), not a hard-coded one. A test
  asserting "July is in season" would silently rot the day this suite is
  run in August — these compute "a month definitely not the current one"
  on the fly instead, so the suite stays correct indefinitely.
- **`test_season_wraps_correctly_across_year_end`** checks the
  Nov–Feb-style wraparound directly against the model property rather
  than trying to fake a specific "today" — it computes the mathematically
  expected answer for *whatever* today actually is and compares. This
  is deliberately less exciting than freezing time to a fixed date, but
  doesn't require a mocking library the project doesn't otherwise use.
- **`test_customer_cannot_add_out_of_season_product_to_cart`** is the
  one that actually proves the brief's acceptance criterion
  ("customers cannot order out-of-season products"), not just that the
  product disappears from a browse page. It sets a product's season to
  a month that isn't the current one, then asserts the *cart* endpoint
  itself rejects adding it — proving the restriction is enforced at the
  point of purchase, via the same `is_visible` check
  `AddCartItemSerializer` already used for stock/availability, not a
  separate bolt-on rule that could drift out of sync.
- **`test_out_of_stock_still_hides_regardless_of_season`** confirms the
  three visibility conditions (availability status, stock, season) are
  combined with AND, not accidentally OR — a product that's in season
  but has zero stock must still be hidden.

---

## Not covered by this suite, and why

- **TC-013 (display), TC-015 (display), TC-016 (display)** — inherently
  visual checks (badge colours, catalogue layout, the "Available: June –
  August" text placement) that don't have a meaningful API-level
  assertion. Verified manually in-browser instead.
- **TC-017–020, TC-023, TC-024** — no model support exists for these;
  explicitly scoped out per the brief's Medium/Low-priority allowance.
  Nothing to test because nothing was built, by design.