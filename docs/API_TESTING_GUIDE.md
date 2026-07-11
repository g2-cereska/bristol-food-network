# Running & testing the Bristol Food Network API

A personal practice reference, not user-facing documentation — the idea
is to re-do this drill every so often so the whole request/response flow
stays fresh for the demo Q&A, rather than having to re-derive it from
the code under pressure. The automated pytest suite is the actual proof
that the API works; this is for testing it *by hand* and building the
kind of muscle memory that survives being asked "what happens if you
try X" on the spot.

---

## 1. Start the stack

```powershell
cd C:\Users\Gytis\Desktop\bristol-food-network
docker-compose up
```

Three lines tell you it's ready:
- `db-1` → `healthy`
- `backend-1` → `Watching for file changes with StatReloader`
- `ai_service-1` → `Uvicorn running on http://0.0.0.0:8001`

Stop everything with `Ctrl+C`, then optionally:
```powershell
docker-compose down --remove-orphans
```

> **About those "orphan containers" warnings:** if you ever run a one-off
> command with `docker-compose run backend ...`, it spins up a brand-new
> container each time rather than reusing the existing `backend-1`
> service — those leftover containers are what triggers the "Found orphan
> containers" warning on the next `docker-compose up`. It's harmless, but
> to avoid it entirely, prefer `docker-compose exec backend ...` for
> commands against the *already-running* stack (that's what every command
> in this guide uses now), and reserve `docker-compose run` only for
> before the stack is up. `docker-compose down --remove-orphans` clears
> any that have already piled up.

If a container exits instead of settling, it's almost always one of
these two things:

- **Port already taken.** Something else on your machine is already
  listening on 8000, 8001, or 5432 — `docker-compose up` will fail loudly
  about it rather than silently picking a different port. Free the port
  or stop the other process; this compose file doesn't remap ports.
- **`backend-1` restarts in a loop right after `db-1` goes healthy.**
  This is almost always a migration failure, not a networking problem —
  scroll up in the logs past the `Waiting for db...` lines to find the
  actual traceback, which is usually further up than you'd expect
  because Compose interleaves log output from both containers.

---

## 2. The three things running

| Service | URL | What it is |
|---|---|---|
| Django backend | http://localhost:8000 | Main API + page templates |
| FastAPI AI service | http://localhost:8001/docs | Recommendation/forecast/quality endpoints |
| PostgreSQL | (not browser-accessible) | Database, only reachable from other containers |

Django talks to the AI service over the Docker network using the service
name as a hostname (`AI_SERVICE_URL=http://ai_service:8001`, set in
`.env.example`) — not `localhost`, because from inside the `backend`
container, `localhost` means the backend container itself. If you ever
see `/api/ai/recommend/...` fail with a connection error while
`localhost:8001/docs` loads fine in your browser, that's the usual
culprit: check `AI_SERVICE_URL` before assuming the AI service is down.

---

## 3. The browsable API — how it actually works

Django REST Framework auto-generates an HTML test page for every
endpoint. This is the easiest way to test by hand, but it has one rule
that trips people up (it tripped this guide's author up too, mid-session
— worth remembering):

> **Typing a URL into the address bar always sends a GET request.**
> There's no way around that — it's how browsers work, not a DRF quirk.

So:

- **GET endpoints** — just visit the URL. Done.
- **POST/PATCH/DELETE-only endpoints** — visiting the URL directly will
  show a `405 Method Not Allowed`, because you just sent a GET to
  something that doesn't accept GET. This is the API correctly rejecting
  the wrong HTTP method, **not a bug**. To actually submit a POST, PATCH,
  or DELETE, use the **form at the bottom of that same page**:
  - If the view is a `CreateAPIView` (product/customer/producer
    registration), DRF renders real labelled input fields.
  - If it's a plain `APIView` (login, logout, add-to-cart, status
    updates), DRF only renders a raw **Content** text box — paste JSON
    into it and click **POST** / **PUT** / **PATCH** / **DELETE**
    (whichever button appears).

**Worked example — the exact thing that produces a 405:**
Visiting `http://localhost:8000/api/cart/add/` directly shows:
```
HTTP 405 Method Not Allowed
Allow: POST, OPTIONS
{"detail": "Method \"GET\" not allowed."}
```
That's expected — `AddToCartView` only accepts POST. Scroll down on that
same page to the **Content** box, paste:
```json
{"product_id": 1, "quantity": 2}
```
and click **POST**. *That's* the real test of the endpoint. Note there's
no `customer_id` in that payload even though the model needs one — the
view fills it in from `request.user.customer_profile.id` itself, so
whatever you're logged in as is who the item gets added for. This is
deliberate: nothing about *whose* cart an item lands in is ever taken
from the request body.

**How to tell if you're logged in:** top-right corner of any browsable
API page. Shows your username when there's an active session, "Login"
when there isn't. The browsable API shares the exact same session cookie
as the normal site — if you're logged in at `localhost:8000/market/` in
that browser, the API pages already know who you are too.

**What a permission failure actually looks like.** Every ownership check
in this codebase (see `permissions.py` and the per-view checks) returns
a `403` with a plain-English `detail` message rather than a generic DRF
error, which makes it easy to confirm you're hitting the right branch
when testing. For example, log in as `producer_dairy` and visit
`GET /api/settlements/<producer_jane's id>/export/` — you'll get:
```json
{"detail": "You can only export your own settlements."}
```
That 403 *is* the test — it's the whole point of TC-022. If you instead
see a `200` with someone else's data, that's the bug you're looking for.

---

## 4. Demo accounts

All demo accounts share the password `Password123!`:

| Username | Role | Notes |
|---|---|---|
| `producer_jane` | Producer | Bristol Valley Farm |
| `producer_dairy` | Producer | Hillside Dairy |
| `customer_robert` | Customer | |
| `admin_1` | Staff/Admin | `is_staff=True`, `is_superuser=True` |

Re-run the seed command any time — safe to repeat, uses `get_or_create`:
```powershell
docker-compose exec backend bash -c "cd backend && python manage.py seed_demo_data"
```

---

## 5. Full endpoint reference

Everything under `/api/`. "Auth" column: **Anyone** = no login needed,
**Any logged-in** = any authenticated user, **Customer/Producer/Admin
(own)** = must be that role AND own the resource being accessed (staff
accounts bypass the ownership half of that check almost everywhere,
which is deliberate — it's how the admin dashboard's underlying views
are allowed to see everyone's data).

| Method | Endpoint | Auth | Notes |
|---|---|---|---|
| GET | `/health/` | Anyone | Always `{"status": "ok"}` |
| GET | `/csrf/` | Anyone | Sets the CSRF cookie |
| POST | `/auth/login/` | Anyone | `{"username", "password"}` → `{"user": {...}, "role": "producer"\|"customer"\|"admin"}` |
| POST | `/auth/logout/` | Any logged-in | Empty body `{}` |
| POST | `/producers/register/` | Anyone | Has a proper HTML form |
| POST | `/customers/register/` | Anyone | Has a proper HTML form |
| GET | `/categories/` | Anyone | |
| GET | `/products/` | Anyone | Filters: `?category=`, `?search=`, `?visible_only=true`, `?organic_only=true`, `?producer=` — combine freely, e.g. `?category=vegetables&organic_only=true` |
| POST | `/products/` | Producer | Creates a product owned by the logged-in producer |
| GET | `/products/<id>/` | Anyone | |
| PATCH | `/products/<id>/` | Producer (own) | |
| GET | `/cart/<customer_id>/` | Customer (own) | |
| POST | `/cart/add/` | Customer | **POST only** — see the worked example above |
| PATCH | `/cart/items/<item_id>/` | Customer (own) | `{"quantity": N}` |
| DELETE | `/cart/items/<item_id>/` | Customer (own) | |
| GET | `/orders/` | Customer | Your own order history; staff see every order |
| POST | `/orders/create/` | Customer | See checkout section below — this is the one with the most ways to get a `400` |
| GET | `/producer-orders/<producer_id>/` | Producer (own) | |
| PATCH | `/producer-suborders/<suborder_id>/status/` | Producer (own) | `{"status": "confirmed"}` — one step at a time only |
| POST | `/settlements/<producer_id>/` | Producer (own) | Generates/returns this week's settlement |
| GET | `/settlements/<producer_id>/export/` | Producer (own) | **Downloads a CSV**, doesn't render as HTML |
| GET | `/ai/recommend/<customer_id>/` | Customer (own) | Proxies to the FastAPI service |
| GET | `/ai/forecast/<producer_id>/` | Producer (own) | Proxies to the FastAPI service |
| GET | `/admin-dashboard/` | Admin | Filters: `?start_date=`, `?end_date=`, `?status=`, `?producer=` — dates default to the last 30 days if omitted |
| GET | `/admin-dashboard/export/` | Admin | **Downloads a CSV**, same filters |

**The two `/export/` endpoints are the one exception to "just visit the
URL"** — they *are* GET endpoints, so visiting them directly works, but
the browser will download a `.csv` file rather than showing you HTML.
That's correct — open the downloaded file to check its contents.

There's no `/api/products/quality-grade` or similar proxy for the AI
service's quality-grading endpoint — only `recommend` and `forecast` are
proxied through Django. Quality grading is only reachable directly
against the AI service on port 8001 (Section 7). That's not an oversight
so much as reflecting that grading is meant to run against a producer's
own submission pipeline rather than being a customer- or producer-facing
Django feature yet.

### Checkout payload shape

`POST /orders/create/`:
```json
{
  "delivery_dates": [
    {"producer_id": 1, "delivery_date": "2026-07-10"}
  ]
}
```
`customer_id` isn't needed in the body — like cart-add, `OrderCreateView`
overwrites it with the logged-in customer's own ID before validation
ever runs, so there's no way to place an order as someone else even if
you tried to. `delivery_address` is optional too; leave it out and it
falls back to the customer's profile address.

The one field worth getting right is `delivery_dates`. It needs **one
entry per producer represented in the cart**, not one date for the whole
order — a two-producer cart with only one entry in `delivery_dates` gets
a `400` naming the producer that's missing. And each date has to respect
that producer's own `lead_time_hours` (48 hours by default, i.e. 2 days'
notice): picking a date sooner than that returns something like
```json
{"non_field_errors": ["Bristol Valley Farm needs at least 48 hours' notice — earliest available delivery date is 2026-07-13."]}
```
which is worth knowing before copy-pasting a hardcoded date from an old
test run — it'll pass today and start failing in a week as "today" moves
past it.

### Other validation errors worth knowing on sight

These come up often enough in manual testing that it's worth recognising
them immediately rather than assuming something's broken:

- **Adding more to the cart than there's stock for** (`POST /cart/add/`)
  doesn't just reject the request — it tells you exactly how much room
  is left, accounting for what's already in the cart:
  `"Only 3 kg of Organic Carrots left to add (you already have 2 in your basket)"`.
- **Skipping a status step** (`PATCH /producer-suborders/<id>/status/`),
  e.g. `pending` straight to `ready`, returns
  `"Cannot move from \"pending\" to \"ready\". Status must progress one step at a time."`
  Cancelling is the one exception — a `cancelled` sub-order can be set
  from any status, but nothing can be changed *out of* `cancelled`.
- **Adding a product that's gone out of season or out of stock** fails
  with `"This product is not currently available."` even if you have its
  ID from an earlier successful response — `is_visible` is checked fresh
  on every add, not cached.

---

## 6. Common test sequences

### A. Registration → login → logout
1. **Register** at `/api/customers/register/` or `/api/producers/register/`
   using the HTML form. Expect `201 Created`.
2. **Login** at `/api/auth/login/` — paste into Content:
   ```json
   {"username": "your_username", "password": "your_password"}
   ```
   Expect `200 OK`. Top-right corner should now show your username.
3. **Logout** at `/api/auth/logout/` — POST with `{}`.
   Expect `200 OK`. Top-right corner reverts to "Login".
4. **Verify logout actually worked**: POST to `/api/auth/logout/` again
   immediately. `LogoutView` requires `IsAuthenticated`, so this should
   now fail (`401`/`403`) — confirming the session was genuinely
   destroyed, not just visually changed.

### B. Full commerce flow (browse → buy → fulfil → get paid)
1. Log in as `customer_robert` (via `/market/login/`, the normal site —
   easier than the API form for this, and sets the same session).
2. `GET /api/products/?visible_only=true` — note a product's `id` and
   its `producer` id.
3. `POST /api/cart/add/` with `{"product_id": <id>, "quantity": 2}`.
4. `POST /api/orders/create/` with the checkout payload shown above,
   using a delivery date that's actually far enough out — today plus
   at least 2 days for the seeded producers. Note the returned order's
   `suborders[0].id`.
5. Log out, log back in as the producer who owns that product.
6. `GET /api/producer-orders/<their_producer_id>/` — the new order
   should appear.
7. `PATCH /api/producer-suborders/<suborder_id>/status/` with
   `{"status": "confirmed"}`, then again with `"ready"`, then
   `"delivered"` — one step at a time, skipping a step returns `400`.
8. `POST /api/settlements/<their_producer_id>/` — the delivered
   sub-order should now show up in the totals.
9. `GET /api/settlements/<their_producer_id>/export/` — downloads a CSV
   matching step 8's numbers.

### C. Admin dashboard
1. Log in as `admin_1`.
2. `GET /api/admin-dashboard/` — shows the last 30 days by default.
3. Add `?status=delivered` or `?producer=<id>` to narrow it.
4. `GET /api/admin-dashboard/export/` (with the same query params if you
   want the filtered version) — downloads the matching CSV.

### D. Confirming you can't see someone else's stuff (TC-022)
This is worth running deliberately rather than trusting that it works
because the tests pass — it's the sequence you'd actually walk through
if someone in the room asked "show me it's actually enforced."
1. Log in as `producer_jane`, note her `producer_profile.id` from
   `/django-admin/` or the login response.
2. Log out, log in as `producer_dairy` instead.
3. `GET /api/producer-orders/<jane's producer_id>/` — this one is worth
   paying attention to, because it doesn't follow the pattern you'd
   expect: it returns `200` with an **empty list**, not a `403`.
   `ProducerOrderView.get_queryset()` quietly returns
   `ProducerSubOrder.objects.none()` for a producer that isn't you,
   rather than the view refusing the request outright. `test_security.py`
   asserts exactly this (`resp.status_code == 200`, `resp.json() == []`),
   so it's confirmed-intentional rather than an oversight — but it's
   genuinely inconsistent with almost every other ownership check in the
   codebase (cart, settlements, AI forecast, sub-order status updates all
   return an explicit `403` instead). Worth knowing which one you're
   testing before confidently predicting the status code.
4. Now try `GET /api/settlements/<jane's id>/export/` and
   `/api/ai/forecast/<jane's id>/` instead — these two *do* return `403`
   with a `detail` message, matching the object-level pattern from
   Section 3.
5. Try both again while logged in as `admin_1` — this time everything
   succeeds, since staff accounts are allowed to see everyone's data.

---

## 7. Testing the AI service directly

Visit `http://localhost:8001/docs` — FastAPI's automatic Swagger UI.
Click any endpoint, then **"Try it out"**, fill in a parameter (e.g.
`customer_id: 1`), and click **Execute**. The response appears inline,
no curl needed.

Worth knowing before you read too much into the numbers: every endpoint
here seeds Python's `random` module with the ID you pass in
(`random.seed(customer_id)`), so the same customer or producer ID always
produces the same "recommendation" or "forecast" — it's deterministic
per ID for demo repeatability, not because there's a trained model
behind it remembering anything. A `/recommend/3` response looks like:
```json
{
  "customer_id": 3,
  "model_version": "baseline-v1",
  "recommendations": [
    {
      "product_id": 2,
      "product_name": "Heritage Tomatoes",
      "producer_name": "Bristol Valley Farm",
      "confidence": 0.87,
      "explanation": "Recommended based on similarity to items customer 3 has viewed."
    }
  ]
}
```
`/quality-grade` is the one endpoint here that's genuinely rule-based
rather than random — POST `{"days_since_harvest": 1, "defect_score": 0.05}`
and it'll grade `A`; push `days_since_harvest` past 5 or `defect_score`
past 0.3 and watch it drop to `C`. Useful for demonstrating the grading
boundary live rather than just describing it.

---

## 8. PowerShell gotcha — `curl` is not curl

PowerShell aliases `curl` to `Invoke-WebRequest`, which uses different
syntax (headers as a hashtable, not a string). Either:

- Use `curl.exe` explicitly to get the real curl binary, or
- Use proper PowerShell syntax:
  ```powershell
  $body = @{ username = "x"; password = "y" } | ConvertTo-Json
  Invoke-WebRequest -Uri "http://localhost:8000/api/auth/login/" -Method POST -Body $body -ContentType "application/json"
  ```

For quick manual testing, the browsable API (Section 3) is far less
fiddly than either of these.

---

## 9. Quick sanity checklist before a demo run-through

- [ ] `docker-compose up` — all three containers healthy
- [ ] `docker-compose exec backend bash -c "cd backend && pytest"` — all passing
- [ ] `/api/products/` returns seeded products
- [ ] Register a fresh test customer — `201`
- [ ] Login with that customer — `200`, username shows top-right
- [ ] Logout — `200`, reverts to "Login"
- [ ] `/api/auth/logout/` again while logged out — fails correctly
- [ ] Full commerce flow (Section 6B) completes end-to-end, using a
      delivery date at least 2 days out
- [ ] Cross-account access attempt (Section 6D) correctly 403s
- [ ] Admin dashboard loads and both CSV exports download correctly
- [ ] `localhost:8001/docs` loads and endpoints respond