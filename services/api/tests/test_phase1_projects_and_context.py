"""Automated tests for Phase 1 Project Management and Business Context Graph."""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.core.security.auth import create_access_token
from src.database.models import Base, Membership, Project, Tenant, User
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
async def test_project_crud_and_archival(client: AsyncClient, async_session: AsyncSession):
    """Verifies project creation with category/launch date, search filtering, and soft archival."""
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()

    tenant = Tenant(id=tenant_id, name="Test Tenant", slug="test-tenant")
    user = User(id=user_id, email="owner@test.com")
    membership = Membership(tenant_id=tenant_id, user_id=user_id, role="owner")
    async_session.add_all([tenant, user, membership])
    await async_session.commit()

    token = create_access_token(
        user_id=str(user_id),
        email=user.email,
        memberships=[{"tenant_id": str(tenant_id), "role": "owner"}],
    )
    headers = {"Authorization": f"Bearer {token}", "X-Tenant-ID": str(tenant_id)}

    # 1. Create project
    proj_payload = {
        "name": "AI Resume Optimizer",
        "description": "SaaS platform for resume optimization",
        "primary_goal": "Launch an AI resume optimization SaaS with Stripe payments.",
        "category": "saas",
    }
    create_res = await client.post(
        f"/workspaces/{tenant_id}/projects",
        json=proj_payload,
        headers=headers,
    )
    assert create_res.status_code == 201
    proj = create_res.json()
    assert proj["name"] == "AI Resume Optimizer"
    assert proj["category"] == "saas"
    assert proj["status"] == "draft"
    project_id = proj["id"]

    # 2. List projects with search query
    search_res = await client.get(
        f"/workspaces/{tenant_id}/projects?q=Resume",
        headers=headers,
    )
    assert search_res.status_code == 200
    search_data = search_res.json()
    assert len(search_data) == 1
    assert search_data[0]["id"] == project_id
    assert search_res.headers["X-Total-Count"] == "1"

    # 3. Update project details
    patch_res = await client.patch(
        f"/workspaces/{tenant_id}/projects/{project_id}",
        json={"description": "Updated description with ATS integration."},
        headers=headers,
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["description"] == "Updated description with ATS integration."

    # 4. Soft-archive project
    archive_res = await client.post(
        f"/workspaces/{tenant_id}/projects/{project_id}/archive",
        headers=headers,
    )
    assert archive_res.status_code == 200
    assert archive_res.json()["status"] == "archived"

    # Default list excludes archived
    list_active = await client.get(f"/workspaces/{tenant_id}/projects", headers=headers)
    assert len(list_active.json()) == 0

    # Including archived returns the project
    list_all = await client.get(
        f"/workspaces/{tenant_id}/projects?include_archived=true",
        headers=headers,
    )
    assert len(list_all.json()) == 1


@pytest.mark.asyncio
async def test_business_context_graph_nodes_and_edges(client: AsyncClient, async_session: AsyncSession):
    """Verifies adding typed context nodes, relationships, and edge validation rules."""
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()

    tenant = Tenant(id=tenant_id, name="Graph Tenant", slug="graph-tenant")
    user = User(id=user_id, email="founder@graph.com")
    membership = Membership(tenant_id=tenant_id, user_id=user_id, role="owner")
    project = Project(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        name="Platform Core",
        primary_goal="Build operating system for micro-startups.",
    )
    async_session.add_all([tenant, user, membership, project])
    await async_session.commit()

    token = create_access_token(
        user_id=str(user_id),
        email=user.email,
        memberships=[{"tenant_id": str(tenant_id), "role": "owner"}],
    )
    headers = {"Authorization": f"Bearer {token}", "X-Tenant-ID": str(tenant_id)}

    # 1. Create Node A (Goal)
    node_a_res = await client.post(
        f"/workspaces/{tenant_id}/projects/{project.id}/context/nodes",
        json={"node_type": "goal", "key": "core_mission", "data": {"priority": 1}},
        headers=headers,
    )
    assert node_a_res.status_code == 201
    node_a_id = node_a_res.json()["id"]

    # 2. Create Node B (Requirement)
    node_b_res = await client.post(
        f"/workspaces/{tenant_id}/projects/{project.id}/context/nodes",
        json={"node_type": "requirement", "key": "stripe_billing", "data": {"currency": "USD"}},
        headers=headers,
    )
    assert node_b_res.status_code == 201
    node_b_id = node_b_res.json()["id"]

    # 3. Create Edge connecting Node B -> Node A (SUPPORTS_GOAL)
    edge_res = await client.post(
        f"/workspaces/{tenant_id}/projects/{project.id}/context/edges",
        json={
            "source_node_id": node_b_id,
            "target_node_id": node_a_id,
            "relationship_type": "SUPPORTS_GOAL",
        },
        headers=headers,
    )
    assert edge_res.status_code == 201
    assert edge_res.json()["relationship_type"] == "SUPPORTS_GOAL"

    # 4. Reject self-referential edge (Node A -> Node A)
    self_edge = await client.post(
        f"/workspaces/{tenant_id}/projects/{project.id}/context/edges",
        json={
            "source_node_id": node_a_id,
            "target_node_id": node_a_id,
            "relationship_type": "REQUIRES",
        },
        headers=headers,
    )
    assert self_edge.status_code == 400
    assert "cannot have a relationship to itself" in self_edge.json()["error"]["message"]

    # 5. Query full context graph
    graph_res = await client.get(
        f"/workspaces/{tenant_id}/projects/{project.id}/context",
        headers=headers,
    )
    assert graph_res.status_code == 200
    graph_data = graph_res.json()
    assert len(graph_data["nodes"]) == 2
    assert len(graph_data["edges"]) == 1
