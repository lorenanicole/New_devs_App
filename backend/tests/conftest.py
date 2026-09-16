import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock
from app.main import app

# --- Shared mock JWT payloads matching the login endpoint's token structure ---

TENANT_A_USER = {
    "id": "user-sunset",
    "email": "sunset@propertyflow.com",
    "tenant_id": "tenant-a",
    "permissions": [],
    "cities": [],
    "is_admin": False,
}

TENANT_B_USER = {
    "id": "user-ocean",
    "email": "ocean@propertyflow.com",
    "tenant_id": "tenant-b",
    "permissions": [],
    "cities": [],
    "is_admin": False,
}


def make_authenticated_client(user: dict) -> TestClient:
    """
    Returns a TestClient with the auth dependency overridden to return
    the given user — no real JWT or Supabase needed.
    """
    from app.core.auth import authenticate_request
    from app.models.auth import AuthenticatedUser

    auth_user = AuthenticatedUser(
        id=user["id"],
        email=user["email"],
        tenant_id=user["tenant_id"],
        permissions=user["permissions"],
        cities=user["cities"],
        is_admin=user["is_admin"],
    )

    app.dependency_overrides[authenticate_request] = lambda: auth_user
    client = TestClient(app, raise_server_exceptions=True)
    return client


@pytest.fixture
def client_a():
    client = make_authenticated_client(TENANT_A_USER)
    yield client
    app.dependency_overrides.clear()


@pytest.fixture
def client_b():
    client = make_authenticated_client(TENANT_B_USER)
    yield client
    app.dependency_overrides.clear()
