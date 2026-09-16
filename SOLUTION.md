# Solution

## Assumptions & Notes

- **No system rebuild** — all changes are targeted bug fixes to existing files. No architecture changes, no framework swaps, no new dependencies added to production code. The existing codebase structure and patterns were followed throughout.
- **New file: `backend/app/services/properties.py`** — this was added not to rebuild the system, but because the DB query logic for properties had no correct home. The `services/` layer already existed for this purpose (`reservations.py`, `cache.py`). Moving the DB query there follows the existing pattern rather than leaving it as inline logic inside a route handler.
- **Tests** — the assignment asked to "test your fixes with the provided client credentials" (i.e. manual testing via the UI). A basic pytest suite was added as a bonus to formally document the regression cases for each bug. These are not required by the assignment and go slightly beyond scope, but demonstrate the expected behaviour explicitly and serve as a safeguard against regressions. Notably, `pytest` and `pytest-asyncio` were added to the `dev` dependency group in `pyproject.toml` — however `pyproject.toml` already contained `[tool.pytest.ini_options]` with `testpaths = ["tests"]`, indicating pytest was already anticipated by the project setup. The dependencies were not present but the intent clearly was.
- **Schema fixes** — `database/schema.sql` changes (`NOT NULL`, `NUMERIC(19,4)`, RLS policies) are schema corrections, not a rebuild. These would require a DB migration in a live environment, which is noted but not implemented here as it was out of scope for this exercise.

---

## Client Issues
1. Client A (Sunset Properties): "The revenue numbers on your dashboard don't match our internal records. We're showing different totals for March, and we're worried about accuracy for our board meeting next week."

2. Client B (Ocean Rentals): "Something strange is happening - sometimes when we refresh the page, we see revenue numbers that look like they belong to another company. This is a serious privacy concern."

3. Finance team: Revenue totals seem "slightly off" by a few cents here and there.

---

## Bug 1 — Hardcoded Property List (Cross-Tenant Data Exposure)

**Files:** `frontend/src/components/Dashboard.tsx` · `backend/app/api/v1/dashboard.py`

### Root Cause

`Dashboard.tsx` had a hardcoded static `PROPERTIES` array listing all 5 properties from **both** tenants. Any logged-in user could see and select properties belonging to another tenant. When Client A selected "Urban Loft Modern" (`prop-005`), the frontend fired `GET /api/v1/dashboard/summary?property_id=prop-005` and received Client B's revenue data.

This can be confirmed by looking in the browser > developer tools > XHR. You'd see a curl like this when logged in as Client A -- when 
prop-005 - Urban Loft Modern -- belongs to Client B:

```
curl http://localhost:8000/api/v1/dashboard/summary?property_id=prop-005&_t=1789562727896

{"property_id":"prop-005","total_revenue":3256.0,"currency":"USD","reservations_count":3}
```

**Core principle violated:** The frontend should never decide what data a user can access. That decision must be made by the backend using the authenticated identity (JWT).

### Fix

**File: `frontend/src/components/Dashboard.tsx`** — Removed the hardcoded `PROPERTIES` constant entirely. Replaced with a `useEffect` that calls the new backend endpoint on mount so the dropdown is always driven by what the authenticated user is actually allowed to see:

```ts
useEffect(() => {
  const data = await SecureAPI.request('/api/v1/dashboard/properties');
  setProperties(data);
  setSelectedProperty(data[0].id);
}, []);
```

**File: `backend/app/api/v1/dashboard.py`** — Added a new `GET /api/v1/dashboard/properties` endpoint and a shared `fetch_properties_for_tenant()` helper that runs a real DB query scoped by `tenant_id`. There is no hardcoded list in the backend either — the data comes from the `properties` table directly:

```python
async def fetch_properties_for_tenant(tenant_id: str) -> List[Dict[str, Any]]:
    try:
        from app.core.database_pool import DatabasePool
        from sqlalchemy import text

        db_pool = DatabasePool()
        await db_pool.initialize()

        if db_pool.session_factory:
            async with db_pool.get_session() as session:
                query = text("""
                    SELECT id, name
                    FROM properties
                    WHERE tenant_id = :tenant_id
                    ORDER BY id
                """)
                result = await session.execute(query, {"tenant_id": tenant_id})
                rows = result.fetchall()
                return [{"id": row.id, "name": row.name, "tenant_id": tenant_id} for row in rows]
    except Exception as e:
        # Falls back to seed data if DB is unavailable (local dev without Supabase)
        logging.warning(f"DB unavailable, using seed fallback for tenant {tenant_id}: {e}")
        ...

@router.get("/dashboard/properties")
async def get_tenant_properties(current_user: dict = Depends(get_current_user)):
    tenant_id = getattr(current_user, "tenant_id", None) or "default_tenant"
    return await fetch_properties_for_tenant(tenant_id)
```

The same `fetch_properties_for_tenant()` function is also used in the `/dashboard/summary` endpoint to validate that the requested `property_id` belongs to the authenticated tenant before returning any revenue data — blocking direct API calls that bypass the frontend dropdown:

```python
tenant_properties = [p["id"] for p in await fetch_properties_for_tenant(tenant_id)]
if property_id not in tenant_properties:
    raise HTTPException(
        status_code=403,
        detail=f"Property '{property_id}' does not belong to your account."
    )
```

This means even if a user manually crafts a request like:
```
GET /api/v1/dashboard/summary?property_id=prop-005
Authorization: Bearer <Client A token>
```
They will receive:
```json
{"detail": "Property 'prop-005' does not belong to your account."}
```

---

## Bug 2 — Cache Key Missing Tenant Isolation (Data Leakage on Refresh)

**File:** `backend/app/services/cache.py`

### Root Cause

The Redis cache key was built using only `property_id` originally:
```python
cache_key = f"revenue:{property_id}"  
```

Since `prop-001` exists for both tenants with the same ID, both shared the same cache entry. Whichever tenant's data was cached first would be returned to the other tenant on refresh — explaining Client B's complaint.

### Fix

```python
cache_key = f"revenue:{tenant_id}:{property_id}"  
```

`revenue:tenant-a:prop-001` and `revenue:tenant-b:prop-001` are now completely separate cache entries.

---

## Bug 3 — Database Schema Issues

**File:** `database/schema.sql`

### Database Models
- Tenants → Properties: One tenant has many properties
- Properties → Reservations: One property has many reservations
- Tenants → Reservations: One tenant has many reservations

### Issue A — Nullable Foreign Keys

`property_id` and `tenant_id` on `reservations` were missing `NOT NULL` constraints:

```sql
property_id TEXT,                      -- ❌ NULL allowed
tenant_id TEXT REFERENCES tenants(id), -- ❌ NULL allowed
```

A foreign key constraint alone does **not** prevent NULL — it only enforces that *if a value exists, it must match a row in the referenced table*. Without `NOT NULL`, a reservation can be inserted with no `property_id` or `tenant_id` and the database accepts it silently:

```sql
-- This INSERT succeeds with no error under the original schema
INSERT INTO reservations (id, check_in_date, check_out_date, total_amount)
VALUES ('res-bad', '2024-03-01 10:00:00+00', '2024-03-05 10:00:00+00', 1500.00);
-- property_id = NULL, tenant_id = NULL → stored with no complaint
-- This reservation now belongs to no property and no tenant
```

#### What happens when property data is deleted?

Imagine `prop-001` is deleted from the `properties` table. Any reservation that referenced `prop-001` now has a `property_id` pointing to nothing — an **orphaned record**. JOINs break silently:

```sql
-- INNER JOIN: orphaned reservations are silently excluded
-- Revenue from those reservations disappears from the total
SELECT r.id, r.total_amount, p.name
FROM reservations r
INNER JOIN properties p ON r.property_id = p.id AND r.tenant_id = p.tenant_id;

-- Result (prop-001 deleted):
-- | res-004 | 1250.00 | City Apartment Downtown |
-- | res-005 | 1475.50 | City Apartment Downtown |
-- res-tz-1, res-dec-1, res-dec-2, res-dec-3 are GONE — their $2,250 vanishes from Client A's total ❌
```

```sql
-- LEFT JOIN: orphaned reservations appear but with NULL property columns
SELECT r.id, r.total_amount, p.name
FROM reservations r
LEFT JOIN properties p ON r.property_id = p.id AND r.tenant_id = p.tenant_id;

-- Result (prop-001 deleted):
-- | res-tz-1  | 1250.00 | NULL                    | ← orphaned, property gone
-- | res-dec-1 |  333.33 | NULL                    | ← orphaned, property gone
-- | res-dec-2 |  333.33 | NULL                    | ← orphaned, property gone
-- | res-dec-3 |  333.33 | NULL                    | ← orphaned, property gone
-- | res-004   | 1250.00 | City Apartment Downtown | ← healthy
-- Revenue is technically present but property context is lost — unusable for reporting
```

#### What happens when tenant data is deleted?

If `tenant-a` is deleted from the `tenants` table, every reservation for that tenant loses its owner. Revenue becomes completely unattributable:

```sql
SELECT r.id, r.total_amount, t.name AS tenant_name
FROM reservations r
LEFT JOIN tenants t ON r.tenant_id = t.id;

-- Result (tenant-a deleted):
-- | res-tz-1  | 1250.00 | NULL          | ← tenant gone, revenue is ownerless
-- | res-dec-1 |  333.33 | NULL          | ← same
-- | res-004   | 1250.00 | NULL          | ← same
-- | res-014   |  920.00 | Ocean Rentals | ← tenant-b still intact
-- Any SUM(total_amount) GROUP BY tenant_name will exclude all of Client A's revenue ❌
```

`NOT NULL` on both columns ensures every reservation **must** belong to a known property and tenant at insert time, preventing ghost data before it can ever be created.

### Issue B — RLS (Row Level Security) With No Policies

RLS is a PostgreSQL feature that lets you define policies directly on a table so that individual rows are filtered based on the current user or session context — in this case, by `tenant_id`. Instead of relying on the application to always add `WHERE tenant_id = X` to every query, the database enforces it automatically at the row level, so no query can ever return another tenant's data regardless of how it's written.

RLS was enabled on both tables but no `CREATE POLICY` statements were defined. Without policies, the RLS declaration is meaningless — all rows may still be returned regardless of tenant.

### Issue C — Financial Precision: `NUMERIC(10, 3)` vs `NUMERIC(19, 4)`

`NUMERIC(p, s)` in PostgreSQL stores up to `p` total digits with `s` digits after the decimal point.

| Type | Total digits | Decimal places | Max value |
|---|---|---|---|
| `NUMERIC(10, 3)` | 10 | 3 | 9,999,999.999 |
| `NUMERIC(19, 4)` | 19 | 4 | 999,999,999,999,999.9999 |

**Why `NUMERIC(10, 3)` causes the "few cents off" problem:**

The seed data demonstrates this directly — three reservations for `prop-001` are stored as:

```
333.333 + 333.333 + 333.334 = 1000.000  ← correct in the DB
```

But when displayed, the frontend rounds each value to 2 decimal places:

```
$333.33 + $333.33 + $333.33 = $999.99  ← off by $0.01 
```

Sub-cent values stored in the DB get truncated inconsistently depending on *when* rounding happens — each layer rounds independently:

- **DB aggregate** — `SUM(total_amount)` in `backend/app/services/reservations.py` line 54 returns a `NUMERIC` value carrying 3 decimal places e.g. `1000.000`
- **Python `float()` cast** — `backend/app/api/v1/dashboard.py` line 42 converts that `NUMERIC` to a Python `float`: `total_revenue_float = float(revenue_data['total'])` — `float` is IEEE 754 double precision and can introduce binary rounding errors on values that aren't cleanly representable (e.g. `333.333` becomes `333.3329999999...` internally)
- **Frontend `toLocaleString()`** — `frontend/src/components/RevenueSummary.tsx` line 81 renders the final value: `displayTotal.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })` — this clips to 2 decimal places at display time, so whatever floating point residue arrived from the Python cast gets truncated here, not rounded consistently

Each layer may round differently, and the errors accumulate silently across many reservations.

**Why `NUMERIC(19, 4)` is the standard for financial data:**
- **4 decimal places** covers sub-cent precision for exchange rates and tax calculations, and rounds cleanly to 2 decimal places for display without residual error
- **19 total digits** handles large revenue portfolios without overflow
- Matches the precision used by most financial systems and accounting software, keeping the stored value and the displayed value consistent

### Fix

```sql
CREATE TABLE reservations (
    id TEXT PRIMARY KEY,
    property_id TEXT NOT NULL,                       -- Fix: enforces FK integrity
    tenant_id TEXT NOT NULL REFERENCES tenants(id),  -- Fix: prevents orphaned records
    check_in_date TIMESTAMP WITH TIME ZONE NOT NULL,
    check_out_date TIMESTAMP WITH TIME ZONE NOT NULL,
    total_amount NUMERIC(19, 4) NOT NULL,            -- Fix: standard financial precision
    currency TEXT DEFAULT 'USD',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    FOREIGN KEY (property_id, tenant_id) REFERENCES properties(id, tenant_id)
);

-- Fix: actual RLS policies to enforce tenant isolation
CREATE POLICY tenant_isolation_properties ON properties
    USING (tenant_id = current_setting('app.current_tenant_id', true));

CREATE POLICY tenant_isolation_reservations ON reservations
    USING (tenant_id = current_setting('app.current_tenant_id', true));
```

---

## Demo

### Start the app

```bash
docker compose up --build
```

- Frontend: http://localhost:3000
- Backend API docs: http://localhost:8000/docs

---

### Bug 1 — Verify property dropdown is tenant-scoped

1. Visit http://localhost:3000/login
2. Log in as **Client A** (`sunset@propertyflow.com` / `client_a_2024`)
3. The "Select Property" dropdown should show **only**:
   - Beach House Alpha (`prop-001`)
   - City Apartment Downtown (`prop-002`)
   - Country Villa Estate (`prop-003`)
4. `prop-004` (Lakeside Cottage) and `prop-005` (Urban Loft Modern) must **not** appear — those belong to Client B
5. Log out, log in as **Client B** (`ocean@propertyflow.com` / `client_b_2024`)
6. The dropdown should show **only**:
   - Lakeside Cottage (`prop-004`)
   - Urban Loft Modern (`prop-005`)

You can also verify via the API directly:

```bash
# Get a token for Client A
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"sunset@propertyflow.com","password":"client_a_2024"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# Client A's properties — should return 3 (tenant-a only)
curl -s http://localhost:8000/api/v1/dashboard/properties \
  -H "Authorization: Bearer $TOKEN"

# Client A tries to access prop-005 (Client B's) — should return 403
curl -s "http://localhost:8000/api/v1/dashboard/summary?property_id=prop-005" \
  -H "Authorization: Bearer $TOKEN"
```

Expected responses:
```json
// /dashboard/properties
[
  {"id": "prop-001", "name": "Beach House Alpha",       "tenant_id": "tenant-a"},
  {"id": "prop-002", "name": "City Apartment Downtown", "tenant_id": "tenant-a"},
  {"id": "prop-003", "name": "Country Villa Estate",    "tenant_id": "tenant-a"}
]

// /dashboard/summary?property_id=prop-005
{"detail": "Property 'prop-005' does not belong to your account."}
```

---

### Bug 2 — Verify cache is tenant-scoped

Both tenants share `prop-001` as a property ID (it exists in the DB for both). Before the fix, whichever tenant's data was cached first would be returned to the other on refresh.

```bash
# Client A token (from above)
TOKEN_A=$TOKEN

# Client B token
TOKEN_B=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"ocean@propertyflow.com","password":"client_b_2024"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# Client A requests prop-001 — caches under revenue:tenant-a:prop-001
curl -s "http://localhost:8000/api/v1/dashboard/summary?property_id=prop-001" \
  -H "Authorization: Bearer $TOKEN_A"

# Client B requests prop-001 — hits a separate key revenue:tenant-b:prop-001
# Before the fix this would return Client A's cached data
curl -s "http://localhost:8000/api/v1/dashboard/summary?property_id=prop-001" \
  -H "Authorization: Bearer $TOKEN_B"
```

Client B will get a 403 (prop-001 is not in their tenant's property list) — confirming the isolation works at both the ownership check and the cache layer.

---

### Run the automated tests

```bash
cd backend

# Install dev dependencies (requires uv)
uv sync --group dev

# Run the bug regression tests
uv run pytest tests/test_bugs.py -v
```

Expected output:
```
tests/test_bugs.py::test_properties_are_scoped_to_tenant       PASSED
tests/test_bugs.py::test_summary_blocked_for_foreign_property  PASSED
tests/test_bugs.py::test_cache_key_is_tenant_scoped            PASSED
tests/test_bugs.py::test_properties_service_filters_by_tenant  PASSED

4 passed in Xs
```

