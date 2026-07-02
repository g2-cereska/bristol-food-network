# Running & testing the Bristol Food Network API

A personal practice reference — re-do this drill from time to time so the
whole flow stays fresh for the demo Q&A.

---

## 1. Start the stack

```powershell
cd C:\Users\Gytis\Desktop\bristol-food-network
docker-compose up
```

Wait for all three lines to settle:
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

---

## 2. The three things running

| Service | URL | What it is |
|---|---|---|
| Django backend | http://localhost:8000 | Main API + page templates |
| FastAPI AI service | http://localhost:8001/docs | Recommendation/forecast/quality endpoints |
| PostgreSQL | (not browser-accessible) | Database, only reachable from other containers |

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
and click **POST**. *That's* the real test of the endpoint.

**How to tell if you're logged in:** top-right corner of any browsable
API page. Shows your username when there's an active session, "Login"
when there isn't. The browsable API shares the exact same session cookie
as the normal site — if you're logged in at `localhost:8000/market/` in
that browser, the API pages already know who you are too.

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
(own)** = must be that role AND own the resource being accessed.

| Method | Endpoint | Auth | Notes |
|---|---|---|---|
| GET | `/health/` | Anyone | Always `{"status": "ok"}` |
| GET | `/csrf/` | Anyone | Sets the CSRF cookie |
| POST | `/auth/login/` | Anyone | `{"username", "password"}` |
| POST | `/auth/logout/` | Any logged-in | Empty body `{}` |
| POST | `/producers/register/` | Anyone | Has a proper HTML form |
| POST | `/customers/register/` | Anyone | Has a proper HTML form |
| GET | `/categories/` | Anyone | |
| GET | `/products/` | Anyone | Filters: `?category=`, `?search=`, `?visible_only=true`, `?organic_only=true`, `?producer=` |
| POST | `/products/` | Producer | Creates a product owned by the logged-in producer |
| GET | `/products/<id>/` | Anyone | |
| PATCH | `/products/<id>/` | Producer (own) | |
| GET | `/cart/<customer_id>/` | Customer (own) | |
| POST | `/cart/add/` | Customer | **POST only** — see the worked example above |
| PATCH | `/cart/items/<item_id>/` | Customer (own) | `{"quantity": N}` |
| DELETE | `/cart/items/<item_id>/` | Customer (own) | |
| GET | `/orders/` | Customer | Your own order history only |
| POST | `/orders/create/` | Customer | See checkout payload below |
| GET | `/producer-orders/<producer_id>/` | Producer (own) | |
| PATCH | `/producer-suborders/<suborder_id>/status/` | Producer (own) | `{"status": "confirmed"}` — one step at a time only |
| POST | `/settlements/<producer_id>/` | Producer (own) | Generates/returns this week's settlement |
| GET | `/settlements/<producer_id>/export/` | Producer (own) | **Downloads a CSV**, doesn't render as HTML |
| GET | `/ai/recommend/<customer_id>/` | Customer (own) | Proxies to the FastAPI service |
| GET | `/ai/forecast/<producer_id>/` | Producer (own) | Proxies to the FastAPI service |
| GET | `/admin-dashboard/` | Admin | Filters: `?start_date=`, `?end_date=`, `?status=`, `?producer=` |
| GET | `/admin-dashboard/export/` | Admin | **Downloads a CSV**, same filters |

**The two `/export/` endpoints are the one exception to "just visit the
URL"** — they *are* GET endpoints, so visiting them directly works, but
the browser will download a `.csv` file rather than showing you HTML.
That's correct — open the downloaded file to check its contents.

**Checkout payload shape** (`POST /orders/create/`):
```json
{
  "customer_id": 3,
  "delivery_dates": [
    {"producer_id": 1, "delivery_date": "2026-07-10"}
  ]
}
```
One entry in `delivery_dates` per producer represented in the cart —
multi-vendor orders need one date per producer, not one for the whole
order.

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
4. `POST /api/orders/create/` with the checkout payload shown above.
   Note the returned order's `suborders[0].id`.
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

---

## 7. Testing the AI service directly

Visit `http://localhost:8001/docs` — FastAPI's automatic Swagger UI.
Click any endpoint, then **"Try it out"**, fill in a parameter (e.g.
`customer_id: 1`), and click **Execute**. The response appears inline,
no curl needed.

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
- [ ] Full commerce flow (Section 6B) completes end-to-end
- [ ] Admin dashboard loads and both CSV exports download correctly
- [ ] `localhost:8001/docs` loads and endpoints respond