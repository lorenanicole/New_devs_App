"""Tests for /dashboard/summary — Bug 1 fix (403 on foreign property_id)."""
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


class TestDashboardSummary:

    def test_client_a_gets_own_revenue(self, client_a):
        with patch("app.api.v1.dashboard.get_properties_for_tenant",
                   new=AsyncMock(return_value=TENANT_A_PROPS)), \
             patch("app.api.v1.dashboard.get_revenue_summary",
                   new=AsyncMock(return_value={
                       "property_id": "prop-001", "total": "1000.00",
                       "currency": "USD", "count": 3,
                   })):
            r = client_a.get("/api/v1/dashboard/summary?property_id=prop-001")
        assert r.status_code == 200
        assert r.json()["total_revenue"] == 1000.0
        assert r.json()["reservations_count"] == 3

    def test_client_a_blocked_from_prop_005(self, client_a):
        """Core Bug 1 regression — was returning Client B's $3,256 to Client A."""
        with patch("app.api.v1.dashboard.get_properties_for_tenant",
                   new=AsyncMock(return_value=TENANT_A_PROPS)):
            r = client_a.get("/api/v1/dashboard/summary?property_id=prop-005")
        assert r.status_code == 403
        assert "does not belong to your account" in r.json()["detail"]

    def test_client_b_blocked_from_prop_001(self, client_b):
        with patch("app.api.v1.dashboard.get_properties_for_tenant",
                   new=AsyncMock(return_value=TENANT_B_PROPS)):
            r = client_b.get("/api/v1/dashboard/summary?property_id=prop-001")
        assert r.status_code == 403
        assert "does not belong to your account" in r.json()["detail"]

    def test_client_b_gets_own_revenue(self, client_b):
        with patch("app.api.v1.dashboard.get_properties_for_tenant",
                   new=AsyncMock(return_value=TENANT_B_PROPS)), \
             patch("app.api.v1.dashboard.get_revenue_summary",
                   new=AsyncMock(return_value={
                       "property_id": "prop-005", "total": "3256.00",
                       "currency": "USD", "count": 3,
                   })):
            r = client_b.get("/api/v1/dashboard/summary?property_id=prop-005")
        assert r.status_code == 200
        assert r.json()["total_revenue"] == 3256.0
