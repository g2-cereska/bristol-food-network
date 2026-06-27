# Running & Testing the Bristol Food Network API

A personal practice reference. Re-do this drill from time to time so the
whole flow stays fresh for the demo Q&A.

---

## 1. Start the stack

```powershell
cd C:\Users\Gytis\Desktop\bristol-food-network
docker-compose up
```

Wait for all three lines to settle:
- `db-1` → `Healthy`
- `backend-1` → `Watching for file changes with StatReloader`
- `ai_service-1` → `Uvicorn running on http://0.0.0.0:8001`

Stop everything with `Ctrl+C`, then optionally:
```powershell
docker-compose down --remove-orphans
```

---

## 2. The three things running

| Service | URL | What it is |
|---|---|---|
| Django backend | http://localhost:8000 | Main API + page templates |
| FastAPI AI service | http://localhost:8001/docs | Recommendation/forecast/quality endpoints |
| PostgreSQL | (not browser-accessible) | Database, only reachable from other containers |

---

## 3. Browsable API — the easy way to test

Django REST Framework auto-generates an HTML test page for every endpoint.
Just visit the URL in a normal browser tab.

**GET endpoints** (just load the page, no form needed):
- `http://localhost:8000/api/products/` — list all products
- `http://localhost:8000/api/categories/` — list categories
- `http://localhost:8000/api/health/` — should always return `{"status": "ok"}`

**POST endpoints with a nice HTML form** (DRF builds the form automatically
for `CreateAPIView` views):
- `http://localhost:8000/api/customers/register/`
- `http://localhost:8000/api/producers/register/`

**POST endpoints WITHOUT a nice form** (plain `APIView` — DRF only shows a
raw JSON text box at the bottom, labelled "Content"):
- `http://localhost:8000/api/auth/login/`
- `http://localhost:8000/api/auth/logout/`

For these, paste raw JSON into the **Content** box and click **POST**. Example:
```json
{"username": "test_customer2", "password": "TestPass123"}
```

**How to tell if you're logged in:** look at the top-right corner of the
page. It says "Login" when logged out, and shows your username when an
active session exists. This is the fastest visual check.

---

## 4. Demo accounts (from `seed_demo_data.py`)

All demo accounts share the password: `Password123!`

| Username | Role | Notes |
|---|---|---|
| `producer_jane` | Producer | Bristol Valley Farm |
| `producer_dairy` | Producer | Hillside Dairy |
| `customer_robert` | Customer | |
| `admin_1` | Staff/Admin | `is_staff=True` |

Re-run the seed command any time (safe to repeat, uses `get_or_create`):
```powershell
docker-compose run backend python backend/manage.py seed_demo_data
```

---

## 5. Common test sequence (registration → login → logout)

1. **Register** at `/api/customers/register/` or `/api/producers/register/`
   using the HTML form. Expect `201 Created` with a `role` field in the response.
2. **Login** at `/api/auth/login/` using raw JSON:
   ```json
   {"username": "your_username", "password": "your_password"}
   ```
   Expect `200 OK`. Top-right corner should now show your username.
3. **Logout** at `/api/auth/logout/` — POST with empty content `{}`.
   Expect `200 OK` with `"detail": "Logged out successfully."`. Top-right
   corner should revert to "Login".
4. **Verify logout actually worked**: POST to `/api/auth/logout/` again
   immediately. Since `LogoutView` requires `IsAuthenticated`, it should now
   fail (401/403) — that confirms the session was genuinely destroyed, not
   just visually changed.

---

## 6. Testing the AI service directly

Visit `http://localhost:8001/docs` — this is FastAPI's automatic Swagger UI.
Click any endpoint, then **"Try it out"**, fill in a parameter (e.g.
`customer_id: 1`), and click **Execute**. The response appears inline,
no curl needed.

---

## 7. PowerShell gotcha — `curl` is not curl

PowerShell aliases `curl` to `Invoke-WebRequest`, which uses different syntax
(headers as a hashtable, not a string). Either:

- Use `curl.exe` explicitly to get the real curl binary, or
- Use proper PowerShell syntax:
  ```powershell
  $body = @{ username = "x"; password = "y" } | ConvertTo-Json
  Invoke-WebRequest -Uri "http://localhost:8000/api/auth/login/" -Method POST -Body $body -ContentType "application/json"
  ```

For quick manual testing, the browsable API (Section 3) is far less fiddly
than either of these.

---

## 8. Quick sanity checklist before a demo run-through

- [ ] `docker-compose up` — all three containers healthy
- [ ] `/api/products/` returns seeded products
- [ ] Register a fresh test customer — 201
- [ ] Login with that customer — 200, username shows top-right
- [ ] Logout — 200, reverts to "Login"
- [ ] `/api/auth/logout/` again while logged out — fails correctly
- [ ] `localhost:8001/docs` loads and endpoints respond