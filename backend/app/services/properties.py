import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


async def get_properties_for_tenant(tenant_id: str) -> List[Dict[str, Any]]:
    """
    Queries the database for properties belonging to the given tenant.
    Falls back to seed data if the DB is unavailable (e.g. local dev without Supabase).
    """
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
        else:
            raise Exception("Database pool not available")

    except Exception as e:
        logger.warning(f"DB unavailable, using seed fallback for tenant {tenant_id}: {e}")

        # Fallback to seed data so the app still works without a live DB connection
        seed_properties = [
            {"id": "prop-001", "name": "Beach House Alpha",       "tenant_id": "tenant-a"},
            {"id": "prop-002", "name": "City Apartment Downtown", "tenant_id": "tenant-a"},
            {"id": "prop-003", "name": "Country Villa Estate",    "tenant_id": "tenant-a"},
            {"id": "prop-004", "name": "Lakeside Cottage",        "tenant_id": "tenant-b"},
            {"id": "prop-005", "name": "Urban Loft Modern",       "tenant_id": "tenant-b"},
        ]
        return [p for p in seed_properties if p["tenant_id"] == tenant_id]
