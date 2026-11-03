"""Automated tests for Phase 1 Authentication and Workspace Onboarding."""


import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.database.models import Base
from src.database.session import get_db_session
from src.main import app

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture
async def async_session():
    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_maker() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def client(async_session: AsyncSession):
    async def override_get_db():
        yield async_session

    app.dependency_overrides[get_db_session] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_user_registration_and_login_flow(client: AsyncClient):
    """Verifies complete registration, password hashing, and login flow with JWT token and cookie."""
    # 1. Register new user
    reg_payload = {
        "email": "founder@example.com",
        "password": "StrongPassword123!",
        "full_name": "Startup Founder",
    }
    reg_res = await client.post("/auth/register", json=reg_payload)
    assert reg_res.status_code == 201
    reg_data = reg_res.json()
    assert "access_token" in reg_data
    assert reg_data["user"]["email"] == "founder@example.com"
    assert "set-cookie" in reg_res.headers
    assert "access_token=" in reg_res.headers["set-cookie"]

    # 2. Reject duplicate email registration
    dup_res = await client.post("/auth/register", json=reg_payload)
    assert dup_res.status_code == 409
    assert "already exists" in dup_res.json()["error"]["message"]

    # 3. Reject password shorter than 8 characters
    short_res = await client.post(
        "/auth/register",
        json={"email": "short@example.com", "password": "short"},
    )
    assert short_res.status_code == 400

    # 4. Login with correct password
    login_res = await client.post(
        "/auth/login",
        json={"email": "founder@example.com", "password": "StrongPassword123!"},
    )
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]
    assert token is not None

    # 5. Login with invalid password fails with uniform 401
    bad_login = await client.post(
        "/auth/login",
        json={"email": "founder@example.com", "password": "WrongPassword!"},
    )
    assert bad_login.status_code == 401
    assert bad_login.json()["error"]["message"] == "Invalid email or password."

    # 6. Current user profile endpoint
    headers = {"Authorization": f"Bearer {token}"}
    me_res = await client.get("/auth/me", headers=headers)
    assert me_res.status_code == 200
    assert me_res.json()["email"] == "founder@example.com"


@pytest.mark.asyncio
async def test_atomic_workspace_creation_and_membership_lifecycle(client: AsyncClient):
    """Verifies atomic creation of workspace (tenant) + owner membership and role authorization."""
    # 1. Register a user
    reg_res = await client.post(
        "/auth/register",
        json={"email": "owner@example.com", "password": "Password123!"},
    )
    token = reg_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Create workspace
    ws_payload = {"name": "Acme Ventures", "tier": "pro"}
    ws_res = await client.post("/workspaces", json=ws_payload, headers=headers)
    assert ws_res.status_code == 201
    ws = ws_res.json()
    assert ws["name"] == "Acme Ventures"
    assert ws["slug"] == "acme-ventures"
    assert ws["tier"] == "pro"
    assert ws["role"] == "owner"
    tenant_id = ws["id"]

    # 3. List workspaces for current user
    list_res = await client.get("/workspaces", headers=headers)
    assert list_res.status_code == 200
    workspaces = list_res.json()
    assert len(workspaces) == 1
    assert workspaces[0]["id"] == tenant_id

    # 4. Update workspace requires updated token containing membership
    # Log in again to get token with updated memberships
    login_res = await client.post(
        "/auth/login",
        json={"email": "owner@example.com", "password": "Password123!"},
    )
    owner_token = login_res.json()["access_token"]
    owner_headers = {
        "Authorization": f"Bearer {owner_token}",
        "X-Tenant-ID": tenant_id,
    }

    patch_res = await client.patch(
        f"/workspaces/{tenant_id}",
        json={"name": "Acme Holdings"},
        headers=owner_headers,
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["name"] == "Acme Holdings"

    # 5. List workspace members
    members_res = await client.get(f"/workspaces/{tenant_id}/members", headers=owner_headers)
    assert members_res.status_code == 200
    members = members_res.json()
    assert len(members) == 1
    assert members[0]["role"] == "owner"
    assert members[0]["email"] == "owner@example.com"
