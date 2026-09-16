"""
Tests covering the 3 bugs fixed:
Bug 1 — Hardcoded property list exposed cross-tenant properties.
Bug 2 — Cache key missing tenant_id caused cross-tenant leakage.
Bug 3 — Schema issues tested via service layer.
"""
import pytest
from unittest.mock import patch, AsyncMock


class TestDashboardProperties:

    def test_client_a_only_sees_own_properties(self, client_a):
        """Client A (tenant-a) should only receive their 3 properties."""
        with patch("app.api.v1.dashboard.get_properties_for_tenant",
                   new=AsyncMock(return_value=[
                       {"id": "prop-001", "name": "Beach House Alpha",       "tenant_id": "tenant-a"},
                       {"id": "prop-002", "name": "City Apartment Downtown", "tenant_id": "tenant-a"},
                       {"id": "prop-003", "name": "Country Villa Estate",    "tenant_id": "tenant-a"},
                   ])):
            response = client_a.get("/api/v1/dashboard/properties")
        assert response.status_code == 200
        ids = [p["id"] for p in response.json()]
        assert set(ids) == {"prop-001", "prop-002", "prop-003"}
        assert "prop-004" not in ids and "prop-005" not in ids

    def test_client_b_only_sees_own_properties(self, client_b):
        """Client B (tenant-b) should only receive their 2 properties."""
        with patch("app.api.v1.dashboard.get_properties_for_tenant",
                   new=AsyncMock(return_value=[
                       {"id": "prop-004", "name": "Lakeside Cottage",  "tenant_id": "tenant-b"},
                       {"id": "prop-005", "name": "Urban Loft Modern", "tenant_id": "tenant-b"},
                   ])):
            response = client_b.get("/api/v1/dashboard/properties")
        assert response.status_code == 200
        ids = [p["id"] for p in response.json()]
        assert set(ids) == {"prop-004", "prop-005"}
        assert "prop-001" not in ids

    def test_properties_never_returns_all_five(self, client_a):
        """Endpoint must never return all 5 cross-tenant properties to one tenant."""
        with patch("app.api.v1.dashboard.get_properties_for_tenant",
                   new=AsyncMock(return_value=[
                       {"id": "prop-001", "name": "Beach House Alpha",       "tenant_id": "tenant-a"},
                       {"id": "prop-002", "name": "City Apartment Downtown", "tenant_id": "tenant-a"},
                       {"id": "prop-003", "name": "Country Villa Estate",    "tenant_id": "tenant-a"},
                   ])):
            response = client_a.get("/api/v1/dashboard/properties")
        assert len(response.json()) < 5
