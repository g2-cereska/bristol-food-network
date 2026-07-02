# Bristol Food Network

A local food marketplace connecting independent producers in the Bristol
region with customers, built for **UFCFTR-30-3 (Distributed & Enterprise
Software Development)** — solo resit, 2025/26.

Producers list produce, customers browse and check out (including
multi-producer orders split automatically into per-producer sub-orders),
producers fulfil and get paid out weekly, and network admins can see the
whole picture across a commission report.

> **Note on the resit context:** this repository was rebuilt from scratch,
> solo, after the original group submission for this module failed. It is
> not a fork or continuation of that group project — every commit here is
> independent work.

---

## Tech stack

| Layer | Technology |
|---|---|
| Backend | Django 5 + Django REST Framework |
| Frontend | Server-rendered Django templates + vanilla JS (`fetch`, no framework) |
| Database | PostgreSQL 16 |
| External service | A small FastAPI microservice (recommendations, demand forecast, quality grading) |
| Containerisation | Docker Compose — three services: `db`, `ai_service`, `backend` |

The FastAPI service under `ai_service/` is a lightweight stand-in used to
satisfy this module's *External Services Integration* criterion — it is
**not** the Advanced AI coursework (UFCFUR-15-3). That is a separate,
much larger computer-vision project in its own repository.

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

---

## Demo accounts

All seeded automatically, password **`Password123!`** for every account:

| Username | Role | Notes |
|---|---|---|
| `producer_jane` | Producer | Bristol Valley Farm |
| `producer_dairy` | Producer | Hillside Dairy |
| `customer_robert` | Customer | |
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
│       └── static/         Shared CSS/JS
├── docs/                   API testing notes
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
- **Seasonal availability** (`season_start_month` /
  `season_end_month`) is modelled as recurring calendar months (1–12)
  rather than one-off dates, since a season like "strawberries: June to
  August" repeats every year rather than needing re-entry annually. The
  range can wrap across the year boundary (e.g. 11–2 for
  November–February). `Product.is_visible` folds this in automatically,
  so an out-of-season product disappears from the catalogue and is
  blocked from being added to a cart without any extra checks elsewhere
  in the codebase.

---

## Known limitations

- **Penny-level rounding on multi-producer orders.** Each producer's
  commission is rounded independently, so the sum of (commission + all
  producer payouts) on a multi-vendor order can be a penny off the order
  total in either direction. Single-producer orders reconcile exactly.
  This is a documented, accepted trade-off rather than a bug.
- **Deliberately out of scope for this resit**, per the brief's
  allowance to scope out Medium/Low-priority items under time
  constraints: community bulk ordering, recurring/subscription orders, a
  dedicated surplus-deals section (the underlying discount field exists
  generically), farm stories/recipes, low-stock alerts, and product
  reviews/ratings. None have model support in this codebase.

---

## Testing

Automated backend/API tests live in `backend/marketplace/tests/` (pytest +
pytest-django, already in `requirements.txt`). They run against a real
Django test database (created and torn down automatically) and hit the
actual API endpoints — no mocking of the request/response layer.

```powershell
docker-compose exec backend bash -c "cd backend && pytest"
```

or, without Docker running, from inside `backend/`:

```powershell
pytest
```

Coverage by test case (19 of the 25 have automated backend tests):

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
| TC-021 | `test_order_history.py` |
| TC-022 | `test_security.py` |
| TC-025 | `test_admin_dashboard.py` |

The remaining test cases are either inherently visual/UI checks
(allergen badge colour, category browsing visuals — verified manually
in-browser during development) or explicitly scoped out per the
"Known limitations" section above.

For a plain-English explanation of *why* each test proves what it
claims to (not just a list of names), see
[`docs/TEST_COVERAGE.md`](docs/TEST_COVERAGE.md).