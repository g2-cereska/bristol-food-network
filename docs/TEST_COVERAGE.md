# Test coverage — what's actually being proven

This is a companion to the pytest suite in `backend/marketplace/tests/` —
not a restatement of the test output (the actual pytest run is stronger
evidence than any summary of it), but a plain-English explanation of
*why* each group of tests demonstrates what it claims to, for Q&A prep
and personal reference.

Run the real thing with `pytest -v` from `backend/`. This document exists
so you can explain any of it without re-reading the code under pressure.

## Quick reference

One line per test case, taken from the docstring on the test class
itself rather than paraphrased, so this table can't drift out of sync
with what the tests actually assert.

| TC | What it proves | File | Tests |
|---|---|---|---|
| TC-001 | Producer registration | `test_registration.py` | 5 |
| TC-002 | Customer registration | `test_registration.py` | 3 |
| TC-003 | Producers list products; linked to the authenticated producer only | `test_products.py` | 3 |
| TC-004 | Browse by category; unavailable/out-of-stock items hidden | `test_products.py` | 4 |
| TC-005 | Search by name/description/producer, case-insensitive | `test_products.py` | 4 |
| TC-006 | Add to cart, modify quantities, view cart contents, stock-aware | `test_cart.py` | 8 |
| TC-007 | Checkout, single producer, correct 5%/95% commission split | `test_checkout.py` | 5 |
| TC-008 | Checkout spanning multiple producers, independent sub-orders | `test_checkout.py` | 3 |
| TC-009 | Producers see their incoming orders, own only | `test_producer_orders.py` | 2 |
| TC-010 | Producers update sub-order status one step at a time | `test_producer_orders.py` | 4 |
| TC-011 | Producers update stock/availability, own products only | `test_products.py` | 3 |
| TC-012 | Weekly settlement counts only delivered sub-orders, correct 95/5 split | `test_settlements.py` | 3 |
| TC-013 (partial) | Food miles calculated correctly at order level | `test_food_miles.py` | 2 |
| TC-014 | Filter by organic certification | `test_products.py` | 2 |
| TC-015 (backend only) | Allergen info stored and returned correctly | `test_allergens.py` | 3 |
| TC-016 | Seasonal availability, including year-boundary wraparound | `test_seasonal_availability.py` | 8 |
| TC-017 | Community group registers with an organisation/segment; special delivery instructions travel through to the producer | `test_bulk_orders.py` | 6 |
| TC-019 | Producers mark surplus stock as a discounted, time-limited deal | `test_surplus_deals.py` | 6 |
| TC-021 | Customer sees own order history, and only their own | `test_order_history.py` | 3 |
| TC-022 | Password policy, login/session handling, role-based access control | `test_security.py` | 12 |
| TC-023 | Producers get notified when a product's stock runs low | `test_low_stock_alerts.py` | 6 |
| TC-024 | Customers rate and review products they've actually had delivered | `test_reviews.py` | 8 |
| TC-025 | Admin commission report — accurate, filterable, exportable | `test_admin_dashboard.py` | 7 |

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

(The username-enumeration check technically belongs to login, not
registration — see TC-022, Part 2, below.)

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

- **`test_producer_cannot_see_another_producers_orders`** is worth
  knowing precisely because it *doesn't* assert what most of the other
  ownership checks in this suite assert. It expects `200` with an empty
  list (`resp.json() == []`), not a `403`. That's because
  `ProducerOrderView` is a `ListAPIView` that filters via
  `get_queryset()` rather than an `APIView` doing an explicit ownership
  check — `get_queryset()` just returns `ProducerSubOrder.objects.none()`
  for a producer that isn't you, so the response looks identical to "you
  have permission, there's nothing here." Every other producer/admin
  object view in the codebase (cart, settlements, AI forecast, this same
  file's status-update test below) returns an explicit `403` with a
  `detail` message instead. Both behaviours are deliberately tested (this
  test and its near-duplicate in `test_security.py`,
  `test_producer_cannot_view_another_producers_order_details`, assert the
  same thing), so it's a real, if minor, inconsistency in the API rather
  than a bug — but it's the kind of detail worth having straight before
  someone asks "what status code does that return" and you guess wrong.
- **`test_cannot_skip_a_status_step`** sends `pending → ready` directly
  (skipping `confirmed`) and asserts `400`. This is the test that proves
  the `STATUS_ORDER.index(current) + 1` check in
  `UpdateSubOrderStatusSerializer` actually enforces one-step-at-a-time,
  rather than just accepting any status in the choices list.
- **`test_other_producer_cannot_update_suborder_status`** — a second
  producer, unrelated to the order, tries to advance someone else's
  sub-order and gets `403`. Unlike the `ProducerOrderView` case above,
  `UpdateProducerSubOrderStatusView` is a plain `APIView` that checks
  ownership explicitly and returns a real `403` — the more common pattern
  in this codebase.

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

The file is three classes, each covering a distinct part of TC-022 —
worth knowing the split exists, since "security" is broad enough that
being able to name the three sub-areas on request is more convincing
than one vague answer:

- **Part 1 — password policy** (`TestPasswordSecurity`, 3 tests). Weak
  (`'123'`) and all-lowercase passwords are both rejected at
  registration, and — same check as `test_registration.py` — the stored
  value never equals the plaintext password.
- **Part 2 — login and session handling** (`TestLoginSecurity`,
  4 tests). Two worth knowing in detail:
  - **`test_error_does_not_reveal_whether_username_exists`** compares the
    JSON body of a failed login for a real username against a fake one
    and asserts they're byte-for-byte identical. That's what actually
    satisfies "without revealing if a user exists" — not just "login
    fails", but that the failure looks the same either way.
  - **`test_logout_ends_session`** deliberately does *not* use
    `force_authenticate` (which bypasses Django's session machinery
    entirely and would make this test meaningless). It uses
    `api_client.login()` / `.logout()` — a real session cookie cycle —
    then proves a request after logout is rejected. This is the one test
    in the suite doing genuine session-based auth rather than DRF's test
    shortcut.
- **Part 3 — role-based access control** (`TestAuthorisation`, 5 tests).
  Customers are blocked from producer-only actions (creating a product)
  and from the admin dashboard; producers are also blocked from the
  admin dashboard; anonymous requests are blocked from the cart. One of
  these five, `test_producer_cannot_view_another_producers_order_details`,
  is the same assertion as `test_producer_orders.py`'s
  `test_producer_cannot_see_another_producers_orders` — see the TC-009
  note above for why that one specifically expects `200`/`[]` rather
  than the `403` you'd get everywhere else in this file.

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

## TC-017 — Community/bulk orders (`test_bulk_orders.py`, 6 tests)

- **`test_registration_accepts_organisation_name_and_segment`** and
  **`test_segment_defaults_to_household_when_not_given`** are really
  testing two different things at once: that a community group *can*
  register with its identity intact, and that an ordinary household
  registration is completely unaffected — `segment` quietly defaulting
  to `'household'` rather than being required is what keeps this feature
  additive rather than a breaking change to registration.
- **`test_producer_sees_customer_organisation_and_instructions`** is the
  one that actually matters for TC-017's acceptance criteria. Setting
  `is_surplus` correctly and having the API accept `special_instructions`
  proves nothing on its own if a producer fulfilling the order never
  actually sees any of it — this test places the order as the customer,
  then re-authenticates as the *producer* and asserts the organisation
  name, segment, and instructions all appear in what the producer reads
  back, not just what the customer submitted.
- **`test_bulk_multi_producer_order_splits_correctly`** is deliberately
  not testing new checkout logic — it's confirming that a "bulk" order
  is just an ordinary multi-vendor order (TC-008) at a larger quantity,
  with instructions attached. Nothing about order size needed special
  handling, which is really the point: the feature is additive metadata
  on top of an order, not a parallel checkout path.

## TC-019 — Surplus deals (`test_surplus_deals.py`, 6 tests)

- **`test_discount_outside_ten_to_fifty_percent_rejected`** and
  **`test_surplus_expiry_in_the_past_rejected`** are the two tests
  actually doing the interesting work here — proving the acceptance
  criteria's numeric constraints are enforced server-side, not just
  suggested by the `min`/`max` attributes on the form's number input
  (which a request that skips the form entirely wouldn't be bound by).
- **`test_surplus_only_filter_excludes_expired_deals`** is the one worth
  being able to explain precisely: it creates a product with
  `is_surplus=True` and an expiry in the *past*, directly via the ORM
  rather than the API, specifically to prove expiry is enforced by
  `?surplus_only=true`'s query even for a row that still has
  `is_surplus=True` sitting in the database. Nothing ever flips that
  flag back to `False` — see the architecture note in the README on why
  that's a deliberate choice, not an oversight.
- **`test_producer_cannot_mark_another_producers_product_surplus`** is
  the same ownership pattern as the rest of the suite (`403`, via
  `ProductDetailView.update`'s existing check) — included mainly to
  confirm the new fields didn't accidentally bypass it.

## TC-023 — Low stock alerts (`test_low_stock_alerts.py`, 6 tests)

- **`test_checkout_pushing_stock_below_threshold_triggers_the_flag`** is
  the one that actually matters. The other tests in this file set
  `stock_quantity` directly; this one places a real order through
  `/api/orders/create/` and lets the normal checkout flow decrement
  stock, then checks the alert reflects it — proving the alert is
  reading live data rather than something that only gets recalculated
  when a producer happens to edit the product.
- **`test_low_stock_only_filter_scoped_to_one_producer`** creates a
  second producer with their own low-stock product specifically to
  prove `?low_stock_only=true&producer=<id>` doesn't leak across
  producers — same shape as every other ownership-adjacent filter test
  in this suite, just for a field that's new.
- **`test_no_threshold_set_never_flags_as_low_stock`** — a product with
  `stock_quantity=0` but no threshold set must *not* be flagged. This is
  the test that would fail if `is_low_stock` were ever accidentally
  implemented as "stock is low" instead of "stock is at or below a
  threshold the producer actually chose" — the two are easy to conflate
  and mean very different things.

## TC-024 — Reviews (`test_reviews.py`, 8 tests)

- **`_deliver_a_product_to()`** isn't a test itself — it's a helper every
  test in this file calls first, since a review needs a genuinely
  delivered order to exist. It runs a real order through
  `/api/orders/create/` and then advances the resulting sub-order
  through `confirmed → ready → delivered` via the actual status
  endpoint, the same lifecycle `test_producer_orders.py` exercises —
  reusing the real progression rather than writing directly to
  `suborder.status` in the test setup, so a review can never be tested
  against a state checkout/fulfilment couldn't actually produce.
- **`test_cannot_review_a_product_that_was_never_delivered`** is the one
  that actually proves TC-024's "review system verifies purchase before
  allowing submission" acceptance criterion. It's deliberately not
  testing "never ordered" (that's the next test) — it places a real
  order and leaves it at `pending`, proving the check is specifically
  about *delivery*, not merely about the order existing.
- **`test_average_rating_and_review_count_reflect_delivered_reviews`**
  creates a second customer from scratch specifically so two different
  people can review the same product — worth knowing why: `Review`'s
  `unique_together = ('product', 'customer')` would silently make a
  same-customer test pass for the wrong reason (there'd only ever be one
  review possible), so this test needs a genuinely different customer to
  prove the average is actually averaging, not just echoing a single
  row back.
- **`test_product_with_no_reviews_has_null_average_not_zero`** — a
  product nobody's reviewed should read as "no rating," not "a 0-star
  rating." Those mean very different things on a catalogue card, and
  it's an easy distinction to lose if `average_rating` were ever
  reimplemented with `or 0` instead of checking for `None`.
- **`test_reviews_are_publicly_readable`** explicitly logs out
  (`force_authenticate(user=None)`) before hitting the reviews endpoint
  — reviews are meant to help a browsing customer decide what to buy,
  so they need to be readable by someone who isn't logged in at all, not
  just by other authenticated accounts.

---

## Not covered by this suite, and why

- **TC-013 (display), TC-015 (display), TC-016 (display)** — inherently
  visual checks (badge colours, catalogue layout, the "Available: June –
  August" text placement) that don't have a meaningful API-level
  assertion. Verified manually in-browser instead.
- **TC-018, TC-020** — no model support exists for these; explicitly
  scoped out per the brief's Medium/Low-priority allowance. Nothing to
  test because nothing was built, by design. (TC-019, TC-023, TC-017,
  and TC-024 were originally in this scoped-out list too, but have
  since been implemented — see the sections above.) Per the actual
  brief (`Test_Cases.pdf`), these two map to: TC-018
  recurring/subscription orders, TC-020 farm stories/recipes —
  confirmed against the brief itself, not inferred from matching list
  lengths.