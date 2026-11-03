"""Automated tests for Phase 1 Goal Decomposition, Execution Plans, and Durable Execution Engine."""

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
async def test_goal_decomposition_plan_approval_and_execution_journey(
    client: AsyncClient, async_session: AsyncSession
):
    """Verifies end-to-end journey: Goal input -> Plan generation -> Review/Approve -> Execution -> Step -> Approvals -> Verification."""
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()

    tenant = Tenant(id=tenant_id, name="LaunchPad Inc", slug="launchpad-inc")
    user = User(id=user_id, email="ceo@launchpad.com")
    membership = Membership(tenant_id=tenant_id, user_id=user_id, role="owner")
    project = Project(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        name="Micro-SaaS Invoicing",
        primary_goal="Launch a recurring invoicing SaaS with Stripe payments and custom domains.",
        category="saas",
    )
    async_session.add_all([tenant, user, membership, project])
    await async_session.commit()

    token = create_access_token(
        user_id=str(user_id),
        email=user.email,
        memberships=[{"tenant_id": str(tenant_id), "role": "owner"}],
    )
    headers = {"Authorization": f"Bearer {token}", "X-Tenant-ID": str(tenant_id)}

    # 1. Generate plan from goal
    gen_res = await client.post(
        f"/workspaces/{tenant_id}/projects/{project.id}/plans/generate",
        json={},
        headers=headers,
    )
    assert gen_res.status_code == 201
    plan = gen_res.json()
    plan_id = plan["id"]
    assert plan["plan_source"] == "rule_based"
    assert plan["status"] == "draft"
    assert len(plan["plan_data"]["tasks"]) > 0
    assert len(plan["plan_data"]["milestones"]) > 0

    # 2. Reject execution of unapproved plan
    unapproved_exec = await client.post(
        f"/workspaces/{tenant_id}/projects/{project.id}/plans/{plan_id}/execute",
        headers=headers,
    )
    assert unapproved_exec.status_code == 400
    assert "must be explicitly approved first" in unapproved_exec.json()["error"]["message"]

    # 3. Explicitly approve plan
    approve_res = await client.post(
        f"/workspaces/{tenant_id}/projects/{project.id}/plans/{plan_id}/approve",
        headers=headers,
    )
    assert approve_res.status_code == 200
    approved_plan = approve_res.json()
    assert approved_plan["status"] == "approved"
    assert approved_plan["approved_by"] == str(user_id)
    assert approved_plan["approved_at"] is not None

    # 4. Initialize workflow execution from approved plan
    exec_res = await client.post(
        f"/workspaces/{tenant_id}/projects/{project.id}/plans/{plan_id}/execute",
        headers=headers,
    )
    assert exec_res.status_code == 201
    wf = exec_res.json()
    workflow_id = wf["id"]
    assert wf["status"] == "running"

    # 5. List initial workflow tasks: first task should be ready
    tasks_res = await client.get(
        f"/workspaces/{tenant_id}/workflows/{workflow_id}/tasks",
        headers=headers,
    )
    assert tasks_res.status_code == 200
    tasks = tasks_res.json()
    assert len(tasks) > 0
    first_task = tasks[0]
    assert first_task["status"] == "ready"

    # 6. Step 1: Execute ready foundation tasks
    step1_res = await client.post(
        f"/workspaces/{tenant_id}/workflows/{workflow_id}/step",
        headers=headers,
    )
    assert step1_res.status_code == 200
    step1_data = step1_res.json()
    assert step1_data["tasks_executed"] >= 1

    # Inspect first task: must be completed with attempt recorded
    tasks_after_step1 = await client.get(
        f"/workspaces/{tenant_id}/workflows/{workflow_id}/tasks",
        headers=headers,
    )
    t1 = tasks_after_step1.json()[0]
    assert t1["status"] == "completed"
    assert len(t1["attempts"]) >= 1
    assert t1["attempts"][0]["status"] == "completed"

    # 7. Step through workflow until reaching manual handoff / approval gate
    for _ in range(5):
        step_res = await client.post(
            f"/workspaces/{tenant_id}/workflows/{workflow_id}/step",
            headers=headers,
        )
        assert step_res.status_code == 200

    # 8. Check for pending approvals
    approvals_res = await client.get(
        f"/workspaces/{tenant_id}/approvals",
        headers=headers,
    )
    assert approvals_res.status_code == 200
    approvals = approvals_res.json()
    assert len(approvals) >= 1
    approval = approvals[0]
    assert approval["status"] == "pending"

    # 9. Founder approves launch gate
    decision_res = await client.post(
        f"/workspaces/{tenant_id}/approvals/{approval['id']}/decision",
        json={"decision": "approved", "notes": "Authorized for production readiness."},
        headers=headers,
    )
    assert decision_res.status_code == 200
    assert decision_res.json()["status"] == "approved"

    # 10. Step final verification tasks
    step_final = await client.post(
        f"/workspaces/{tenant_id}/workflows/{workflow_id}/step",
        headers=headers,
    )
    assert step_final.status_code == 200

    # Verify task verification records exist
    tasks_final = await client.get(
        f"/workspaces/{tenant_id}/workflows/{workflow_id}/tasks",
        headers=headers,
    )
    final_task_list = tasks_final.json()
    verif_tasks = [t for t in final_task_list if t["task_type"] == "verify_internal_record"]
    assert len(verif_tasks) >= 1
    assert verif_tasks[0]["status"] == "completed"
    assert len(verif_tasks[0]["verification_records"]) >= 1
    assert verif_tasks[0]["verification_records"][0]["status"] == "passed"
