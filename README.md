# Bristol Food Network

A local food marketplace connecting independent producers in the Bristol
region with customers, built for **UFCFTR-30-3 (Distributed & Enterprise
Software Development)** — solo resit, 2025/26.

Producers list produce, customers browse and check out (including
multi-producer orders split automatically into per-producer sub-orders),
producers fulfil and get paid out weekly, and network admins can see the
whole picture across a commission report.

---

## What it does

- **Catalogue & search** — producers list products with price, unit,
  stock, harvest date, organic certification, allergen info, and an
  optional discount; customers browse, search, and filter by category or
  organic-only.
- **Seasonal availability** — products can be restricted to a recurring
  month range (e.g. "June–August"); out-of-season stock disappears from
  the catalogue automatically, no manual toggling required.
- **Cart & multi-producer checkout** — a single order can span several
  producers' products. Checkout splits it into one `ProducerSubOrder`
  per producer, each with its own delivery date and status lifecycle.
- **Producer fulfilment** — producers move each sub-order through
  `Pending → Confirmed → Ready → Delivered` independently of the rest of
  the order.
- **Weekly settlements** — producers are paid out 95% of the subtotal of
  everything they've *delivered* that week; the network keeps the
  remaining 5% commission. Both a settlement summary and a downloadable
  CSV report are available.
- **Admin commission reporting** — staff/superuser accounts get a
  dashboard with platform-wide stats, an activity feed, and a
  date-filterable commission report, also exportable as CSV.
- **Food miles** — an approximate straight-line distance between
  producer and customer postcodes, calculated with the Haversine
  formula.
- **Surplus deals** — producers can flag near-expiry stock as a
  time-limited discount (10–50% off, with an expiry time); customers can
  filter the catalogue to surplus deals only, and a deal disappears from
  that filter automatically once it expires.
- **Low-stock alerts** — producers set a restock threshold per product;
  a dashboard filter surfaces everything currently at or below it, live,
  with no separate notification job involved.
- **Community/bulk orders** — customers can register with an
  organisation name and a segment (community group, restaurant, etc.),
  and attach delivery instructions to an order that producers see
  alongside their sub-order — useful for institutional buyers where "who
  is this really for" and "where exactly does it go" matter more than
  for an ordinary household order.
- **Product reviews** — customers can rate and review a product once
  it's actually been delivered to them (one review each, verified
  against their own delivery history, not just against having ordered
  it); the catalogue shows the resulting average rating and review
  count per product.
- **AI microservice** — a separate FastAPI service that Django calls
  over HTTP for personalised recommendations, per-producer demand
  forecasts, and rule-based quality grading (see note below on what this
  is and isn't).

---

## Tech stack

| Layer | Technology |
|---|---|
| Backend | Django 5 + Django REST Framework |
| Frontend | Server-rendered Django templates + vanilla JS (`fetch`, no framework) |
| Database | PostgreSQL 16 |
| External service | A small FastAPI microservice (recommendations, demand forecast, quality grading) |
| Containerisation | Docker Compose — three services: `db`, `ai_service`, `backend` |
| CI | GitHub Actions — installs dependencies, migrates, and runs the pytest suite on every push/PR ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) |

The FastAPI service under `ai_service/` is a lightweight stand-in used to
satisfy this module's *External Services Integration* criterion — it is
**not** the Advanced AI coursework (UFCFUR-15-3). That is a separate,
much larger computer-vision project in its own repository. Concretely,
it means the endpoints are deliberately simple (seeded-random
recommendations/forecasts, a rule-based quality grader on
days-since-harvest and a defect score) rather than trained models — each
endpoint's docstring says what a production version would do instead.

---

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (includes Docker Compose)
- Nothing else — Python, PostgreSQL, and all dependencies run inside the containers.

---

## Running the project

```powershell
git clone https://github.com/g2-cereska/bristol-food-network.git
cd bristol-food-network
docker-compose up
```

Wait for all three services to settle:

- `db-1` → becomes `healthy`
- `ai_service-1` → `Uvicorn running on http://0.0.0.0:8001`
- `backend-1` → `Watching for file changes with StatReloader`

The backend container automatically runs database migrations and seeds
demo data (see below) every time it starts — there is nothing else to set
up manually.

Then open **http://localhost:8000/market/** in a browser.

To stop everything:

```powershell
docker-compose down
```

Add `--remove-orphans` if you've previously run an older version of the
compose file.

### Environment variables

`.env.example` at the repo root already contains working defaults for
local development and is read directly by `docker-compose.yml` — you do
**not** need to copy it to `.env` or edit anything to get started. If you
want to override a value (e.g. `SECRET_KEY` for a non-local deployment),
either edit that file or export the equivalent environment variable
before running `docker-compose up`.

### Making a model change

`docker-compose up` only *applies* migrations that already exist as
files — it won't generate a new one for you. If you've added, removed,
or changed a field in `models.py`, you need to create the migration
yourself first:

```powershell
docker-compose exec backend bash -c "cd backend && python manage.py makemigrations marketplace"
```

That creates a new file under `backend/marketplace/migrations/` (Django
names it automatically, e.g. `0005_order_special_instructions.py`) and
prints a summary of what it's adding. Then either apply it directly:

```powershell
docker-compose exec backend bash -c "cd backend && python manage.py migrate"
```

or just restart the stack, since `docker-compose up` applies any
pending migration automatically on startup anyway:

```powershell
docker-compose up
```

To check a migration's actually been applied (`[X]`) rather than still
pending (`[ ]`):

```powershell
docker-compose exec backend bash -c "cd backend && python manage.py showmigrations marketplace"
```

If `makemigrations` says "No changes detected," the model file you
edited probably isn't saved, or isn't the one the container actually
sees — worth double-checking before assuming something's broken.

---

## Demo accounts

All seeded automatically, password **`Password123!`** for every account:

| Username | Role | Notes |
|---|---|---|
| `producer_jane` | Producer | Bristol Valley Farm |
| `producer_dairy` | Producer | Hillside Dairy |
| `customer_robert` | Customer | Ordinary household account |
| `customer_school` | Customer | Community group — "St Mary's School" |
| `admin_1` | Network admin | `is_staff` + `is_superuser` |

Seeded catalogue: 4 products from Bristol Valley Farm (carrots, tomatoes,
apples, courgettes) and 2 from Hillside Dairy (milk, cheddar), across 5
categories (Vegetables, Fruit, Dairy, Bakery, Meat).

To re-seed manually at any point (safe to run repeatedly — it uses
`get_or_create`, so it won't duplicate data):

```powershell
docker-compose exec backend python manage.py seed_demo_data
```

---

## A five-minute walkthrough

**As a customer** (`customer_robert`) — browse the catalogue at
`/market/`, filter by category or organic, add products from more than
one producer to the cart, and check out. The order confirmation shows
the automatic per-producer split, food miles, and the 5% commission.
Log in as `customer_school` instead to see the community-group flow —
checkout has an optional delivery-instructions field, and the order
shows up flagged on the producer's side as coming from an organisation,
not just an individual.

**As a producer** (`producer_jane` or `producer_dairy`) — visit
`/market/producer/` to see incoming sub-orders and move them through
`Pending → Confirmed → Ready → Delivered`. Once something's delivered,
the settlement tab shows the 95/5 payout for the current week, with a
CSV export. Once you've done that, log back in as the customer who
placed it and visit **My Orders** — the delivered item now has a
"Write a review" link; the resulting rating shows up on that product's
catalogue card.

**As an admin** (`admin_1`) — visit `/market/admin-dash/` for
platform-wide stats, a recent-activity feed, and a date-filterable
commission report (also exportable as CSV).

---

## Where things are

| What | URL |
|---|---|
| Marketplace (customer view) | http://localhost:8000/market/ |
| Producer dashboard | http://localhost:8000/market/producer/ |
| Admin dashboard | http://localhost:8000/market/admin-dash/ |
| Browsable REST API | http://localhost:8000/api/ |
| Django admin site | http://localhost:8000/django-admin/ |
| AI microservice docs | http://localhost:8001/docs |

The Django REST Framework browsable API is the fastest way to poke at any
endpoint directly (e.g. `/api/products/`, `/api/orders/`) without needing
a REST client — every endpoint renders an HTML form for GET/POST/PATCH
requests in a normal browser tab.

A more detailed manual API walkthrough (used during development to keep
the request/response shapes fresh ahead of the demo) is in
[`docs/API_TESTING_GUIDE.md`](docs/API_TESTING_GUIDE.md).

### API reference

All paths below are relative to `/api/`. "Owner" means the authenticated
producer/customer this resource belongs to; every ownership check is
enforced server-side, not just hidden in the UI.

| Method | Endpoint | Access |
|---|---|---|
| GET | `health/` | Anyone |
| GET | `csrf/` | Anyone — fetches the CSRF cookie for the JS frontend |
| POST | `auth/login/` | Anyone |
| POST | `auth/logout/` | Authenticated |
| POST | `producers/register/` | Anyone |
| POST | `customers/register/` | Anyone |
| GET | `categories/` | Anyone |
| GET | `products/` | Anyone — supports `?search=`, `?category=`, `?producer=`, `?organic_only=true`, `?visible_only=true`, `?surplus_only=true`, `?low_stock_only=true` |
| POST | `products/` | Producers only |
| GET / PATCH | `products/<id>/` | GET: anyone · PATCH: owning producer only |
| GET / POST | `products/<id>/reviews/` | GET: anyone · POST: customer with a delivered order for this product |
| GET | `cart/<customer_id>/` | Owning customer |
| POST | `cart/add/` | Customers only (customer taken from the session, not the request body) |
| PATCH / DELETE | `cart/items/<item_id>/` | Owning customer |
| POST | `orders/create/` | Customers only |
| GET | `orders/` | Own orders (customer) or all orders (staff) |
| GET | `producer-orders/<producer_id>/` | Owning producer or staff |
| PATCH | `producer-suborders/<suborder_id>/status/` | Owning producer or staff |
| POST | `settlements/<producer_id>/` | Owning producer or staff |
| GET | `settlements/<producer_id>/export/` | Owning producer or staff — downloads a CSV |
| GET | `ai/recommend/<customer_id>/` | Owning customer |
| GET | `ai/forecast/<producer_id>/` | Owning producer or staff |
| GET | `admin-dashboard/` | Staff/superuser only — supports `?start_date=`, `?end_date=`, `?status=`, `?producer=` |
| GET | `admin-dashboard/export/` | Staff/superuser only — downloads a CSV, same filters as above |

---

## Project structure

```
bristol-food-network/
├── ai_service/            FastAPI external service (recommend / forecast / quality-grade)
├── backend/
│   ├── core/               Django project settings, root URLconf
│   └── marketplace/        The Django app — models, views, serializers,
│                            templates, static files, migrations
│       ├── services/       Business logic kept out of views.py
│       │                    (settlements, admin commission reports,
│       │                     food-miles calculation, AI client)
│       ├── templates/      Server-rendered pages (catalogue, cart,
│       │                    orders, producer dashboard, admin dashboard)
│       ├── tests/           pytest suite — one file per feature area
│       └── static/         Shared CSS/JS
├── docs/                   API testing notes, test coverage rationale
├── .github/workflows/      CI pipeline (migrate + pytest on every push/PR)
├── docker-compose.yml
├── Dockerfile.backend
├── Dockerfile.ai
└── requirements.txt
```

---

## Architecture notes worth knowing

- **Multi-producer orders.** A single customer order can span several
  producers. Each producer gets their own `ProducerSubOrder` with an
  independent status lifecycle (`Pending → Confirmed → Ready →
  Delivered`), independent delivery date, and independent 95% payout —
  so one producer can be finished with their portion while another is
  still preparing theirs.
- **Order status vs. sub-order status.** `Order.status` is set once at
  creation and is not updated afterwards — only each producer's
  `ProducerSubOrder.status` actually progresses. The admin commission
  report derives a real overall status from the sub-orders rather than
  relying on the (static) order-level field.
- **Settlements vs. commission report.** Producers are paid out weekly
  only for sub-orders that have actually been *delivered*
  (`services/settlements.py`). The network's admin-facing commission
  report (`services/admin_reports.py`) reflects the 5% commission
  *earned* at the point of sale, independent of delivery status — these
  are deliberately two different ledgers tracking two different things.
- **CSV exports mirror their on-screen reports exactly.** The producer
  settlement export and the admin commission export both reuse the same
  query-building functions as the pages they export from (rather than a
  separately-maintained export query), so the download can't drift out
  of sync with what's on screen — and the admin export respects the same
  `start_date` / `end_date` / `status` / `producer` filters as the
  dashboard.
- **Seasonal availability** (`season_start_month` /
  `season_end_month`) is modelled as recurring calendar months (1–12)
  rather than one-off dates, since a season like "strawberries: June to
  August" repeats every year rather than needing re-entry annually. The
  range can wrap across the year boundary (e.g. 11–2 for
  November–February). `Product.is_visible` folds this in automatically,
  so an out-of-season product disappears from the catalogue and is
  blocked from being added to a cart without any extra checks elsewhere
  in the codebase.
- **Food miles is a deliberately small lookup table.** `services/food_miles.py`
  covers 19 Bristol-area postcode sectors with a fuzzy sector/district
  fallback and a default distance for anything outside it — enough to
  demonstrate the Haversine calculation working end-to-end without
  shipping a full postcode database.
- **Surplus deals and low-stock alerts are computed properties, not
  scheduled jobs.** There's no task queue in this project (no Celery,
  no cron), so rather than a background process flipping a status flag
  when a deal expires or stock drops, `Product.is_surplus_active` and
  `Product.is_low_stock` are evaluated fresh on every read. A surplus
  deal past its `surplus_expires_at` simply stops matching
  `?surplus_only=true` the moment it's queried — nothing has to run to
  "notice" the expiry. Same idea for low stock: it's a live comparison
  against `low_stock_threshold`, not an alert that was raised once and
  might now be stale.

---

## Known limitations

- **Penny-level rounding on multi-producer orders.** Each producer's
  commission is rounded independently, so the sum of (commission + all
  producer payouts) on a multi-vendor order can be a penny off the order
  total in either direction. Single-producer orders reconcile exactly.
  This is a documented, accepted trade-off rather than a bug.
- **The AI service is a demonstration stand-in, not a trained model.**
  Recommendations and forecasts are generated from a seeded random
  process (deterministic per customer/producer ID, so demos are
  repeatable) rather than learned from `UserInteraction` history, and
  quality grading is a simple rule on two input numbers rather than a
  computer-vision classifier. This is intentional scope for this
  module — see the AI microservice note above.
- **Deliberately out of scope for this resit**, per the brief's
  allowance to scope out Medium/Low-priority items under time
  constraints: recurring/subscription orders (TC-018) and farm
  stories/recipes (TC-020). Neither has model support in this codebase.
  (Surplus deals, low-stock alerts, community/bulk orders, and product
  reviews were originally scoped out here too, but have since been
  implemented — see "What it does" above.)

---

## Testing

Automated backend/API tests live in `backend/marketplace/tests/` (pytest +
pytest-django, already in `requirements.txt`). They run against a real
Django test database (created and torn down automatically) and hit the
actual API endpoints — no mocking of the request/response layer. The same
suite runs automatically on every push and pull request via
[GitHub Actions](.github/workflows/ci.yml).

```powershell
docker-compose exec backend bash -c "cd backend && pytest"
```

or, without Docker running, from inside `backend/`:

```powershell
pytest
```

Coverage by test case (23 of the 25 have automated backend tests, 110
individual test functions across 16 files):

| Test case | File |
|---|---|
| TC-001, TC-002 | `test_registration.py` |
| TC-003, TC-004, TC-005, TC-011, TC-014 | `test_products.py` |
| TC-006 | `test_cart.py` |
| TC-007, TC-008 | `test_checkout.py` |
| TC-009, TC-010 | `test_producer_orders.py` |
| TC-012 | `test_settlements.py` |
| TC-013 (partial — order-level only) | `test_food_miles.py` |
| TC-015 (backend only — see note in file) | `test_allergens.py` |
| TC-016 | `test_seasonal_availability.py` |
| TC-017 | `test_bulk_orders.py` |
| TC-019 | `test_surplus_deals.py` |
| TC-021 | `test_order_history.py` |
| TC-022 | `test_security.py` |
| TC-023 | `test_low_stock_alerts.py` |
| TC-024 | `test_reviews.py` |
| TC-025 | `test_admin_dashboard.py` |

The remaining test cases are either inherently visual/UI checks
(allergen badge colour, category browsing visuals — verified manually
in-browser during development) or explicitly scoped out per the
"Known limitations" section above.

For a plain-English explanation of *why* each test proves what it
claims to (not just a list of names), see
[`docs/TEST_COVERAGE.md`](docs/TEST_COVERAGE.md).