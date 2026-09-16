from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any, List
from app.services.cache import get_revenue_summary
from app.services.properties import get_properties_for_tenant
from app.core.auth import authenticate_request as get_current_user

router = APIRouter()


@router.get("/dashboard/properties")
async def get_tenant_properties(
    current_user: dict = Depends(get_current_user)
) -> List[Dict[str, Any]]:
    """
    Returns only the properties that belong to the currently authenticated tenant.
    DB query is handled in app.services.properties.
    """
    tenant_id = getattr(current_user, "tenant_id", None) or "default_tenant"
    return await get_properties_for_tenant(tenant_id)


@router.get("/dashboard/summary")
async def get_dashboard_summary(
    property_id: str,
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:

    tenant_id = getattr(current_user, "tenant_id", "default_tenant") or "default_tenant"

    # Validate the requested property belongs to this tenant before returning
    # any revenue data — blocks direct API calls that bypass the frontend dropdown
    tenant_properties = [p["id"] for p in await get_properties_for_tenant(tenant_id)]
    if property_id not in tenant_properties:
        raise HTTPException(
            status_code=403,
            detail=f"Property '{property_id}' does not belong to your account."
        )

    revenue_data = await get_revenue_summary(property_id, tenant_id)

    total_revenue_float = float(revenue_data['total'])

    return {
        "property_id": revenue_data['property_id'],
        "total_revenue": total_revenue_float,
        "currency": revenue_data['currency'],
        "reservations_count": revenue_data['count']
    }
