"""Tests for cache key tenant isolation — Bug 2 fix."""
import pytest
from unittest.mock import patch, AsyncMock


class TestCacheKey:

    @pytest.mark.asyncio
    async def test_cache_key_includes_tenant_id(self):
        """Cache key must be revenue:{tenant_id}:{property_id} not revenue:{property_id}."""
        from app.services.cache import get_revenue_summary

        captured_keys = []

        async def mock_get(key):
            captured_keys.append(key)
            return None  # cache miss

        async def mock_setex(key, ttl, value):
            pass

        async def mock_calculate(property_id, tenant_id):
            return {"property_id": property_id, "tenant_id": tenant_id,
                    "total": "1000.00", "currency": "USD", "count": 3}

        with patch("app.services.cache.redis_client") as mock_redis, \
             patch("app.services.reservations.calculate_total_revenue", new=mock_calculate):
            mock_redis.get = mock_get
            mock_redis.setex = mock_setex
            await get_revenue_summary("prop-001", "tenant-a")

        assert len(captured_keys) == 1
        key = captured_keys[0]
        assert key == "revenue:tenant-a:prop-001", f"Wrong cache key: {key}"
        assert key != "revenue:prop-001", "Cache key missing tenant_id — Bug 2 not fixed!"

    @pytest.mark.asyncio
    async def test_two_tenants_get_separate_cache_keys(self):
        """tenant-a and tenant-b must produce different cache keys for the same property_id."""
        from app.services.cache import get_revenue_summary

        keys = []

        async def mock_get(key):
            keys.append(key)
            return None

        async def mock_setex(key, ttl, value):
            pass

        async def mock_calculate(property_id, tenant_id):
            return {"property_id": property_id, "tenant_id": tenant_id,
                    "total": "500.00", "currency": "USD", "count": 1}

        with patch("app.services.cache.redis_client") as mock_redis, \
             patch("app.services.reservations.calculate_total_revenue", new=mock_calculate):
            mock_redis.get = mock_get
            mock_redis.setex = mock_setex
            await get_revenue_summary("prop-001", "tenant-a")
            await get_revenue_summary("prop-001", "tenant-b")

        assert len(keys) == 2
        assert keys[0] != keys[1], "Both tenants share the same cache key — Bug 2 still present!"
        assert keys[0] == "revenue:tenant-a:prop-001"
        assert keys[1] == "revenue:tenant-b:prop-001"
