"""
Basic regression tests for the 3 bugs fixed.

Bug 1 — Hardcoded property list exposed cross-tenant properties in the dropdown.
Bug 2 — Cache key missing tenant_id caused cross-tenant revenue leakage on refresh.
Bug 3 — properties service correctly filters by tenant_id (no cross-tenant bleed).
"""
import pytest
from unittest.mock import patch, AsyncMock

TENANT_A_PROPS = [
    {"id": "prop-001", "name": "Beach House Alpha",       "tenant_id": "tenant-a"},
    {"id": "prop-002", "name": "City Apartment Downtown", "tenant_id": "tenant-a"},
    {"id": "prop-003", "name": "Country Villa Estate",    "tenant_id": "tenant-a"},
]
TENANT_B_PROPS = [
    {"id": "prop-004", "name": "Lakeside Cottage",  "tenant_id": "tenant-b"},
    {"id": "prop-005", "name": "Urban Loft Modern", "tenant_id": "tenant-b"},
]


# Bug 1a — /dashboard/properties must only return the logged-in tenant's properties
def test_properties_are_scoped_to_tenant(client_a):
    with patch("app.api.v1.dashboard.get_properties_for_tenant",
               new=AsyncMock(return_value=TENANT_A_PROPS)):
        r = client_a.get("/api/v1/dashboard/properties")
    assert r.status_code == 200
    ids = [p["id"] for p in r.json()]
    assert "prop-004" not in ids and "prop-005" not in ids  # tenant-b props must not appear


# Bug 1b — /dashboard/summary must return 403 when a foreign property_id is requested
def test_summary_blocked_for_foreign_property(client_a):
    with patch("app.api.v1.dashboard.get_properties_for_tenant",
               new=AsyncMock(return_value=TENANT_A_PROPS)):
        r = client_a.get("/api/v1/dashboard/summary?property_id=prop-005")
    assert r.status_code == 403
    assert "does not belong to your account" in r.json()["detail"]


# Bug 2 — cache key must include tenant_id to prevent cross-tenant cache leakage
@pytest.mark.asyncio
async def test_cache_key_is_tenant_scoped():
    from app.services.cache import get_revenue_summary

    captured = []

    async def mock_get(key):
        captured.append(key)
        return None

    async def mock_setex(key, ttl, value): pass

    async def mock_calculate(property_id, tenant_id):
        return {"property_id": property_id, "tenant_id": tenant_id,
                "total": "1000.00", "currency": "USD", "count": 3}

    with patch("app.services.cache.redis_client") as mock_redis, \
         patch("app.services.reservations.calculate_total_revenue", new=mock_calculate):
        mock_redis.get = mock_get
        mock_redis.setex = mock_setex
        await get_revenue_summary("prop-001", "tenant-a")

    assert captured[0] == "revenue:tenant-a:prop-001"  # must not be just "revenue:prop-001"


# Bug 3 — properties service must filter by tenant_id with no cross-tenant bleed
@pytest.mark.asyncio
async def test_properties_service_filters_by_tenant():
    from app.services.properties import get_properties_for_tenant

    with patch("app.services.properties.DatabasePool") as MockPool:
        MockPool.return_value.initialize = AsyncMock()
        MockPool.return_value.session_factory = None  # triggers seed fallback

        result_a = await get_properties_for_tenant("tenant-a")
        result_b = await get_properties_for_tenant("tenant-b")

    ids_a = {p["id"] for p in result_a}
    ids_b = {p["id"] for p in result_b}
    assert ids_a.isdisjoint(ids_b), f"Cross-tenant property overlap: {ids_a & ids_b}"
