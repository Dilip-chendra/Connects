"""Tests verifying schema integrity, unique constraints, and cascade/preservation deletion rules."""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import (
    AuditLog,
    Base,
    Membership,
    Project,
    Task,
    Tenant,
    User,
    WorkflowExecution,
)


def test_all_thirteen_core_tables_defined() -> None:
    expected_tables = {
        "tenants",
        "users",
        "memberships",
        "projects",
        "business_context_nodes",
        "business_context_edges",
        "workflow_executions",
        "tasks",
        "task_dependencies",
        "verification_records",
        "approval_requests",
        "connector_configs",
        "audit_logs",
    }
    actual_tables = set(Base.metadata.tables.keys())
    assert expected_tables.issubset(actual_tables), (
        f"Missing tables: {expected_tables - actual_tables}"
    )


async def test_duplicate_tenant_slug_rejected(db_session: AsyncSession) -> None:
    slug = f"unique-slug-{uuid.uuid4().hex[:6]}"
    t1 = Tenant(name="Tenant 1", slug=slug)
    db_session.add(t1)
    await db_session.flush()

    t2 = Tenant(name="Tenant 2", slug=slug)
    db_session.add(t2)
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


async def test_duplicate_membership_rejected(db_session: AsyncSession) -> None:
    tenant = Tenant(name="T", slug=f"t-{uuid.uuid4().hex[:6]}")
    user = User(email=f"u-{uuid.uuid4().hex[:6]}@example.com")
    db_session.add_all([tenant, user])
    await db_session.flush()

    m1 = Membership(tenant_id=tenant.id, user_id=user.id, role="owner")
    db_session.add(m1)
    await db_session.flush()

    m2 = Membership(tenant_id=tenant.id, user_id=user.id, role="member")
    db_session.add(m2)
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


async def test_duplicate_task_idempotency_key_rejected(db_session: AsyncSession) -> None:
    tenant = Tenant(name="T", slug=f"t-{uuid.uuid4().hex[:6]}")
    db_session.add(tenant)
    await db_session.flush()

    project = Project(tenant_id=tenant.id, name="P", primary_goal="G")
    db_session.add(project)
    await db_session.flush()

    wf = WorkflowExecution(tenant_id=tenant.id, project_id=project.id, template_name="test")
    db_session.add(wf)
    await db_session.flush()

    task1 = Task(
        tenant_id=tenant.id,
        workflow_execution_id=wf.id,
        name="Task 1",
        task_type="repo_scan",
        idempotency_key="unique-idempotency-key-1",
    )
    db_session.add(task1)
    await db_session.flush()

    # Second task with same idempotency key under same workflow must fail
    task2 = Task(
        tenant_id=tenant.id,
        workflow_execution_id=wf.id,
        name="Task 2",
        task_type="repo_scan",
        idempotency_key="unique-idempotency-key-1",
    )
    db_session.add(task2)
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


async def test_audit_log_preserved_when_user_deleted(db_session: AsyncSession) -> None:
    """Verifies that user deletion sets user_id=NULL on audit records instead of cascading deletion."""
    tenant = Tenant(name="T", slug=f"t-{uuid.uuid4().hex[:6]}")
    user = User(email=f"audit-user-{uuid.uuid4().hex[:6]}@example.com")
    db_session.add_all([tenant, user])
    await db_session.flush()

    audit = AuditLog(
        tenant_id=tenant.id,
        user_id=user.id,
        action="user.login",
        resource_type="auth",
        details={"ip": "127.0.0.1"},
    )
    db_session.add(audit)
    await db_session.commit()

    audit_id = audit.id

    # Delete the user
    await db_session.delete(user)
    await db_session.commit()
    db_session.expire_all()

    # Verify audit record still exists and user_id is now NULL
    res = await db_session.execute(select(AuditLog).where(AuditLog.id == audit_id))
    persisted_audit = res.scalar_one_or_none()
    assert persisted_audit is not None
    assert persisted_audit.user_id is None
    assert persisted_audit.action == "user.login"
