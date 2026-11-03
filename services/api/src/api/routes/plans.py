"""API routes for goal decomposition, plan review, editing, approval, and rejection."""

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security.auth import TenantContext, get_tenant_context
from src.database.models import AuditLog, ExecutionPlan, Project
from src.database.session import get_db_session
from src.domain.planning.generator import RuleBasedPlanGenerator
from src.domain.planning.schemas import PlanTaskSchema
from src.domain.workflows.state_machine import DependencyCycleError, DependencyGraphValidator

router = APIRouter(tags=["plans"])


class GeneratePlanRequest(BaseModel):
    goal_override: str | None = None


class UpdatePlanRequest(BaseModel):
    tasks: list[PlanTaskSchema] | None = None
    assumptions: list[str] | None = None


class ExecutionPlanSummaryResponse(BaseModel):
    id: str
    tenant_id: str
    project_id: str
    version: int
    status: str
    goal: str
    plan_source: str
    task_count: int
    created_at: str
    approved_at: str | None


class ExecutionPlanDetailResponse(BaseModel):
    id: str
    tenant_id: str
    project_id: str
    version: int
    status: str
    goal: str
    plan_source: str
    plan_data: dict[str, Any]
    created_by: str | None
    approved_by: str | None
    approved_at: str | None
    created_at: str
    updated_at: str


def _serialize_plan_detail(p: ExecutionPlan) -> ExecutionPlanDetailResponse:
    return ExecutionPlanDetailResponse(
        id=str(p.id),
        tenant_id=str(p.tenant_id),
        project_id=str(p.project_id),
        version=p.version,
        status=p.status,
        goal=p.goal,
        plan_source=p.plan_source,
        plan_data=p.plan_data,
        created_by=str(p.created_by) if p.created_by else None,
        approved_by=str(p.approved_by) if p.approved_by else None,
        approved_at=p.approved_at.isoformat() if p.approved_at else None,
        created_at=p.created_at.isoformat(),
        updated_at=p.updated_at.isoformat(),
    )


@router.post("/generate", response_model=ExecutionPlanDetailResponse, status_code=status.HTTP_201_CREATED)
async def generate_plan(
    tenant_id: str,
    project_id: str,
    req: GeneratePlanRequest,
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> ExecutionPlanDetailResponse:
    """Decomposes project goal into a structured draft plan using the rule-based planner."""
    if not tenant_ctx.can_mutate():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Role not permitted to generate plans.",
        )

    # Verify project exists in active tenant
    proj_res = await session.execute(
        select(Project).where(
            Project.id == uuid.UUID(project_id),
            Project.tenant_id == uuid.UUID(tenant_ctx.tenant_id),
        )
    )
    project = proj_res.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")

    goal_text = req.goal_override or project.primary_goal
    planner = RuleBasedPlanGenerator()
    generated_plan = await planner.generate_plan(goal=goal_text)

    # Determine next version
    existing_plans = await session.execute(
        select(ExecutionPlan)
        .where(
            ExecutionPlan.project_id == uuid.UUID(project_id),
            ExecutionPlan.tenant_id == uuid.UUID(tenant_ctx.tenant_id),
        )
        .order_by(ExecutionPlan.version.desc())
    )
    latest = existing_plans.scalar_one_or_none()
    next_version = (latest.version + 1) if latest else 1

    plan = ExecutionPlan(
        tenant_id=uuid.UUID(tenant_ctx.tenant_id),
        project_id=uuid.UUID(project_id),
        version=next_version,
        status="draft",
        goal=goal_text,
        plan_source=generated_plan.planning_source,
        plan_data=generated_plan.model_dump(),
        created_by=uuid.UUID(tenant_ctx.user_id),
    )
    session.add(plan)

    audit_entry = AuditLog(
        tenant_id=uuid.UUID(tenant_ctx.tenant_id),
        user_id=uuid.UUID(tenant_ctx.user_id),
        action="plan.generated",
        resource_type="execution_plan",
        resource_id=str(plan.id),
        details={"version": next_version, "plan_source": plan.plan_source},
    )
    session.add(audit_entry)
    await session.flush()
    await session.refresh(plan)

    return _serialize_plan_detail(plan)


@router.get("", response_model=list[ExecutionPlanSummaryResponse])
async def list_project_plans(
    tenant_id: str,
    project_id: str,
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> list[ExecutionPlanSummaryResponse]:
    """Lists all execution plans associated with the project."""
    res = await session.execute(
        select(ExecutionPlan)
        .where(
            ExecutionPlan.project_id == uuid.UUID(project_id),
            ExecutionPlan.tenant_id == uuid.UUID(tenant_ctx.tenant_id),
        )
        .order_by(ExecutionPlan.version.desc())
    )
    plans = res.scalars().all()
    return [
        ExecutionPlanSummaryResponse(
            id=str(p.id),
            tenant_id=str(p.tenant_id),
            project_id=str(p.project_id),
            version=p.version,
            status=p.status,
            goal=p.goal,
            plan_source=p.plan_source,
            task_count=len(p.plan_data.get("tasks", [])),
            created_at=p.created_at.isoformat(),
            approved_at=p.approved_at.isoformat() if p.approved_at else None,
        )
        for p in plans
    ]


@router.get("/{plan_id}", response_model=ExecutionPlanDetailResponse)
async def get_plan(
    tenant_id: str,
    project_id: str,
    plan_id: str,
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> ExecutionPlanDetailResponse:
    """Retrieves full plan details with tasks and dependencies."""
    res = await session.execute(
        select(ExecutionPlan).where(
            ExecutionPlan.id == uuid.UUID(plan_id),
            ExecutionPlan.project_id == uuid.UUID(project_id),
            ExecutionPlan.tenant_id == uuid.UUID(tenant_ctx.tenant_id),
        )
    )
    plan = res.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found.")

    return _serialize_plan_detail(plan)


@router.patch("/{plan_id}", response_model=ExecutionPlanDetailResponse)
async def update_plan(
    tenant_id: str,
    project_id: str,
    plan_id: str,
    req: UpdatePlanRequest,
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> ExecutionPlanDetailResponse:
    """Updates proposed tasks or assumptions while in draft or reviewed status."""
    if not tenant_ctx.can_mutate():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Role not permitted to edit plans.",
        )

    res = await session.execute(
        select(ExecutionPlan).where(
            ExecutionPlan.id == uuid.UUID(plan_id),
            ExecutionPlan.project_id == uuid.UUID(project_id),
            ExecutionPlan.tenant_id == uuid.UUID(tenant_ctx.tenant_id),
        )
    )
    plan = res.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found.")

    if plan.status not in ("draft", "reviewed"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot edit plan in '{plan.status}' status. Create a new revision instead.",
        )

    updated_data = dict(plan.plan_data)

    if req.tasks is not None:
        # Validate DAG acyclicity
        adjacency: dict[str, list[str]] = {t.id: t.prerequisites for t in req.tasks}
        try:
            DependencyGraphValidator.detect_cycles(adjacency)
        except DependencyCycleError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

        updated_data["tasks"] = [t.model_dump() for t in req.tasks]

    if req.assumptions is not None:
        updated_data["assumptions"] = req.assumptions

    plan.plan_data = updated_data
    plan.status = "reviewed"

    audit_entry = AuditLog(
        tenant_id=uuid.UUID(tenant_ctx.tenant_id),
        user_id=uuid.UUID(tenant_ctx.user_id),
        action="plan.updated",
        resource_type="execution_plan",
        resource_id=str(plan.id),
        details={"status": plan.status},
    )
    session.add(audit_entry)
    await session.flush()
    await session.refresh(plan)

    return _serialize_plan_detail(plan)


@router.post("/{plan_id}/approve", response_model=ExecutionPlanDetailResponse)
async def approve_plan(
    tenant_id: str,
    project_id: str,
    plan_id: str,
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> ExecutionPlanDetailResponse:
    """Approves a plan, creating an immutable snapshot for workflow execution."""
    if not tenant_ctx.can_admin():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin or Owner role is required to approve execution plans.",
        )

    res = await session.execute(
        select(ExecutionPlan).where(
            ExecutionPlan.id == uuid.UUID(plan_id),
            ExecutionPlan.project_id == uuid.UUID(project_id),
            ExecutionPlan.tenant_id == uuid.UUID(tenant_ctx.tenant_id),
        )
    )
    plan = res.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found.")

    if plan.status not in ("draft", "reviewed"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Plan is already in '{plan.status}' status.",
        )

    plan.status = "approved"
    plan.approved_by = uuid.UUID(tenant_ctx.user_id)
    plan.approved_at = datetime.now(UTC)

    audit_entry = AuditLog(
        tenant_id=uuid.UUID(tenant_ctx.tenant_id),
        user_id=uuid.UUID(tenant_ctx.user_id),
        action="plan.approved",
        resource_type="execution_plan",
        resource_id=str(plan.id),
        details={"approved_by": tenant_ctx.user_id, "version": plan.version},
    )
    session.add(audit_entry)
    await session.flush()
    await session.refresh(plan)

    return _serialize_plan_detail(plan)


@router.post("/{plan_id}/reject", response_model=ExecutionPlanDetailResponse)
async def reject_plan(
    tenant_id: str,
    project_id: str,
    plan_id: str,
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> ExecutionPlanDetailResponse:
    """Rejects a plan."""
    if not tenant_ctx.can_admin():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin or Owner role is required to reject execution plans.",
        )

    res = await session.execute(
        select(ExecutionPlan).where(
            ExecutionPlan.id == uuid.UUID(plan_id),
            ExecutionPlan.project_id == uuid.UUID(project_id),
            ExecutionPlan.tenant_id == uuid.UUID(tenant_ctx.tenant_id),
        )
    )
    plan = res.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found.")

    plan.status = "rejected"

    audit_entry = AuditLog(
        tenant_id=uuid.UUID(tenant_ctx.tenant_id),
        user_id=uuid.UUID(tenant_ctx.user_id),
        action="plan.rejected",
        resource_type="execution_plan",
        resource_id=str(plan.id),
        details={"rejected_by": tenant_ctx.user_id, "version": plan.version},
    )
    session.add(audit_entry)
    await session.flush()
    await session.refresh(plan)

    return _serialize_plan_detail(plan)
