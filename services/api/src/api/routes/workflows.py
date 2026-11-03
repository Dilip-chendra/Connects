"""Workflow execution, task dispatch, internal capability stepping, and approval routes."""

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.security.auth import TenantContext, get_tenant_context
from src.database.models import (
    ApprovalRequest,
    AuditLog,
    Task,
    WorkflowExecution,
)
from src.database.session import get_db_session
from src.domain.execution.engine import ExecutionEngine, ExecutionEngineError
from src.domain.workflows.state_machine import TaskStatus, WorkflowStatus

router = APIRouter(tags=["workflows"])


class LegacyWorkflowCreateRequest(BaseModel):
    project_id: str
    template_name: str


class WorkflowCreateFromPlanRequest(BaseModel):
    plan_id: str


class WorkflowResponse(BaseModel):
    id: str
    tenant_id: str
    project_id: str
    plan_id: str | None
    template_name: str
    status: str
    started_at: str | None
    completed_at: str | None
    created_at: str


class TaskAttemptResponse(BaseModel):
    id: str
    attempt_number: int
    status: str
    error_message: str | None
    output_payload: dict[str, Any]
    started_at: str
    completed_at: str | None


class TaskDetailResponse(BaseModel):
    id: str
    name: str
    description: str | None
    task_type: str
    connector_id: str | None
    status: str
    idempotency_key: str
    retry_count: int
    max_retries: int
    requires_approval: bool
    input_payload: dict[str, Any]
    output_payload: dict[str, Any]
    error_details: dict[str, Any] | None
    prerequisites: list[str]
    attempts: list[TaskAttemptResponse]
    verification_records: list[dict[str, Any]]
    created_at: str
    updated_at: str


class ApprovalDecisionRequest(BaseModel):
    decision: str  # approved, rejected
    notes: str | None = None


class ApprovalResponse(BaseModel):
    id: str
    task_id: str
    task_name: str
    requested_action: str
    impact_assessment: str
    status: str
    reviewed_by: str | None
    reviewed_at: str | None
    decision_notes: str | None
    created_at: str


@router.post("/workflows", response_model=WorkflowResponse, status_code=status.HTTP_201_CREATED)
async def create_workflow_direct(
    tenant_id: str,
    req: LegacyWorkflowCreateRequest,
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> WorkflowResponse:
    """Directly creates a workflow execution within authorized tenant project."""
    from src.database.models import Project

    proj_result = await session.execute(
        select(Project).where(
            Project.id == uuid.UUID(req.project_id),
            Project.tenant_id == uuid.UUID(tenant_ctx.tenant_id),
        )
    )
    if not proj_result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")

    wf = WorkflowExecution(
        tenant_id=uuid.UUID(tenant_ctx.tenant_id),
        project_id=uuid.UUID(req.project_id),
        template_name=req.template_name,
        status="planned",
        trigger_type="user_intent",
    )
    session.add(wf)
    await session.flush()
    await session.refresh(wf)

    return WorkflowResponse(
        id=str(wf.id),
        tenant_id=str(wf.tenant_id),
        project_id=str(wf.project_id),
        plan_id=None,
        template_name=wf.template_name,
        status=wf.status,
        started_at=None,
        completed_at=None,
        created_at=wf.created_at.isoformat(),
    )


@router.post(
    "/projects/{project_id}/plans/{plan_id}/execute",
    response_model=WorkflowResponse,
    status_code=status.HTTP_201_CREATED,
)
async def execute_approved_plan(
    tenant_id: str,
    project_id: str,
    plan_id: str,
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> WorkflowResponse:
    """Initializes a durable workflow execution from an approved plan."""
    if not tenant_ctx.can_mutate():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Role not permitted to trigger workflow executions.",
        )

    try:
        wf = await ExecutionEngine.initialize_execution(
            session=session,
            tenant_id=uuid.UUID(tenant_ctx.tenant_id),
            project_id=uuid.UUID(project_id),
            plan_id=uuid.UUID(plan_id),
            user_id=uuid.UUID(tenant_ctx.user_id),
        )
        return WorkflowResponse(
            id=str(wf.id),
            tenant_id=str(wf.tenant_id),
            project_id=str(wf.project_id),
            plan_id=str(wf.plan_id) if wf.plan_id else None,
            template_name=wf.template_name,
            status=wf.status,
            started_at=wf.started_at.isoformat() if wf.started_at else None,
            completed_at=wf.completed_at.isoformat() if wf.completed_at else None,
            created_at=wf.created_at.isoformat(),
        )
    except ExecutionEngineError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.get("/workflows/{workflow_id}", response_model=WorkflowResponse)
async def get_workflow(
    tenant_id: str,
    workflow_id: str,
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> WorkflowResponse:
    """Returns workflow execution details scoped to authorized tenant."""
    res = await session.execute(
        select(WorkflowExecution).where(
            WorkflowExecution.id == uuid.UUID(workflow_id),
            WorkflowExecution.tenant_id == uuid.UUID(tenant_ctx.tenant_id),
        )
    )
    wf = res.scalar_one_or_none()
    if not wf:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found.")

    return WorkflowResponse(
        id=str(wf.id),
        tenant_id=str(wf.tenant_id),
        project_id=str(wf.project_id),
        plan_id=str(wf.plan_id) if wf.plan_id else None,
        template_name=wf.template_name,
        status=wf.status,
        started_at=wf.started_at.isoformat() if wf.started_at else None,
        completed_at=wf.completed_at.isoformat() if wf.completed_at else None,
        created_at=wf.created_at.isoformat(),
    )


@router.post("/workflows/{workflow_id}/step")
async def step_workflow_execution(
    tenant_id: str,
    workflow_id: str,
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Steps the workflow engine: dispatches ready tasks, executes internal capabilities, pauses for approvals."""
    if not tenant_ctx.can_mutate():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Role not permitted to step workflows.",
        )

    try:
        step_result = await ExecutionEngine.step_workflow(
            session=session,
            tenant_id=uuid.UUID(tenant_ctx.tenant_id),
            workflow_id=uuid.UUID(workflow_id),
            user_id=uuid.UUID(tenant_ctx.user_id),
        )
        return step_result
    except ExecutionEngineError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.get("/workflows/{workflow_id}/tasks", response_model=list[TaskDetailResponse])
async def list_workflow_tasks(
    tenant_id: str,
    workflow_id: str,
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> list[TaskDetailResponse]:
    """Lists all tasks for a workflow execution with dependencies and execution attempts."""
    tasks_res = await session.execute(
        select(Task)
        .options(
            selectinload(Task.dependencies),
            selectinload(Task.execution_attempts),
            selectinload(Task.verification_records),
        )
        .where(
            Task.workflow_execution_id == uuid.UUID(workflow_id),
            Task.tenant_id == uuid.UUID(tenant_ctx.tenant_id),
        )
        .order_by(Task.created_at.asc())
    )
    tasks = tasks_res.scalars().all()

    # Load all tasks to map depends_on UUIDs to their task names / ids
    return [
        TaskDetailResponse(
            id=str(t.id),
            name=t.name,
            description=t.description,
            task_type=t.task_type,
            connector_id=t.connector_id,
            status=t.status,
            idempotency_key=t.idempotency_key,
            retry_count=t.retry_count,
            max_retries=t.max_retries,
            requires_approval=t.requires_approval,
            input_payload=t.input_payload or {},
            output_payload=t.output_payload or {},
            error_details=t.error_details,
            prerequisites=[str(d.depends_on_task_id) for d in t.dependencies],
            attempts=[
                TaskAttemptResponse(
                    id=str(a.id),
                    attempt_number=a.attempt_number,
                    status=a.status,
                    error_message=a.error_message,
                    output_payload=a.output_payload or {},
                    started_at=a.started_at.isoformat(),
                    completed_at=a.completed_at.isoformat() if a.completed_at else None,
                )
                for a in t.execution_attempts
            ],
            verification_records=[
                {
                    "id": str(v.id),
                    "type": v.verification_type,
                    "status": v.status,
                    "evidence": v.evidence,
                    "timestamp": v.timestamp.isoformat(),
                }
                for v in t.verification_records
            ],
            created_at=t.created_at.isoformat(),
            updated_at=t.updated_at.isoformat(),
        )
        for t in tasks
    ]


@router.post("/workflows/{workflow_id}/tasks/{task_id}/complete-handoff", response_model=TaskDetailResponse)
async def complete_task_handoff(
    tenant_id: str,
    workflow_id: str,
    task_id: str,
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> TaskDetailResponse:
    """Allows a founder to complete a manual handoff task, marking it verified and completed."""
    if not tenant_ctx.can_mutate():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Role not permitted to complete manual handoffs.",
        )

    tasks_res = await session.execute(
        select(Task)
        .options(
            selectinload(Task.dependencies),
            selectinload(Task.execution_attempts),
            selectinload(Task.verification_records),
        )
        .where(
            Task.id == uuid.UUID(task_id),
            Task.workflow_execution_id == uuid.UUID(workflow_id),
            Task.tenant_id == uuid.UUID(tenant_ctx.tenant_id),
        )
    )
    task = tasks_res.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found.")

    task.status = TaskStatus.COMPLETED.value
    task.output_payload = {
        "status": "handoff_completed_by_user",
        "completed_by": tenant_ctx.user_id,
        "completed_at": datetime.now(UTC).isoformat(),
    }

    audit_entry = AuditLog(
        tenant_id=uuid.UUID(tenant_ctx.tenant_id),
        user_id=uuid.UUID(tenant_ctx.user_id),
        action="task.handoff_completed",
        resource_type="task",
        resource_id=str(task.id),
        details={"task_name": task.name},
    )
    session.add(audit_entry)
    await session.flush()
    await session.refresh(task)

    return TaskDetailResponse(
        id=str(task.id),
        name=task.name,
        description=task.description,
        task_type=task.task_type,
        connector_id=task.connector_id,
        status=task.status,
        idempotency_key=task.idempotency_key,
        retry_count=task.retry_count,
        max_retries=task.max_retries,
        requires_approval=task.requires_approval,
        input_payload=task.input_payload or {},
        output_payload=task.output_payload or {},
        error_details=task.error_details,
        prerequisites=[str(d.depends_on_task_id) for d in task.dependencies],
        attempts=[],
        verification_records=[],
        created_at=task.created_at.isoformat(),
        updated_at=task.updated_at.isoformat(),
    )


@router.post("/workflows/{workflow_id}/cancel", response_model=WorkflowResponse)
async def cancel_workflow(
    tenant_id: str,
    workflow_id: str,
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> WorkflowResponse:
    """Cancels an active or paused workflow and transitions unstarted tasks to cancelled."""
    if not tenant_ctx.can_admin():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin or Owner role is required to cancel workflows.",
        )

    res = await session.execute(
        select(WorkflowExecution).where(
            WorkflowExecution.id == uuid.UUID(workflow_id),
            WorkflowExecution.tenant_id == uuid.UUID(tenant_ctx.tenant_id),
        )
    )
    wf = res.scalar_one_or_none()
    if not wf:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found.")

    wf.status = WorkflowStatus.CANCELLED.value
    wf.completed_at = datetime.now(UTC)

    # Cancel unstarted tasks
    tasks_res = await session.execute(
        select(Task).where(
            Task.workflow_execution_id == wf.id,
            Task.tenant_id == uuid.UUID(tenant_ctx.tenant_id),
            Task.status.in_([TaskStatus.PLANNED.value, TaskStatus.READY.value, TaskStatus.AWAITING_APPROVAL.value]),
        )
    )
    for task in tasks_res.scalars().all():
        task.status = TaskStatus.CANCELLED.value

    audit_entry = AuditLog(
        tenant_id=uuid.UUID(tenant_ctx.tenant_id),
        user_id=uuid.UUID(tenant_ctx.user_id),
        action="workflow.cancelled",
        resource_type="workflow_execution",
        resource_id=str(wf.id),
        details={"cancelled_by": tenant_ctx.user_id},
    )
    session.add(audit_entry)
    await session.flush()
    await session.refresh(wf)

    return WorkflowResponse(
        id=str(wf.id),
        tenant_id=str(wf.tenant_id),
        project_id=str(wf.project_id),
        plan_id=str(wf.plan_id) if wf.plan_id else None,
        template_name=wf.template_name,
        status=wf.status,
        started_at=wf.started_at.isoformat() if wf.started_at else None,
        completed_at=wf.completed_at.isoformat() if wf.completed_at else None,
        created_at=wf.created_at.isoformat(),
    )


@router.get("/approvals", response_model=list[ApprovalResponse])
async def list_pending_approvals(
    tenant_id: str,
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> list[ApprovalResponse]:
    """Lists pending human approval requests for the workspace."""
    res = await session.execute(
        select(ApprovalRequest)
        .options(selectinload(ApprovalRequest.task))
        .where(
            ApprovalRequest.tenant_id == uuid.UUID(tenant_ctx.tenant_id),
            ApprovalRequest.status == "pending",
        )
        .order_by(ApprovalRequest.created_at.desc())
    )
    approvals = res.scalars().all()
    return [
        ApprovalResponse(
            id=str(a.id),
            task_id=str(a.task_id),
            task_name=a.task.name if a.task else "Task Action",
            requested_action=a.requested_action,
            impact_assessment=a.impact_assessment,
            status=a.status,
            reviewed_by=str(a.reviewed_by) if a.reviewed_by else None,
            reviewed_at=a.reviewed_at.isoformat() if a.reviewed_at else None,
            decision_notes=a.decision_notes,
            created_at=a.created_at.isoformat(),
        )
        for a in approvals
    ]


@router.post("/approvals/{approval_id}/decision", response_model=ApprovalResponse)
async def process_approval_decision(
    tenant_id: str,
    approval_id: str,
    req: ApprovalDecisionRequest,
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> ApprovalResponse:
    """Records human founder approval or rejection decision."""
    if not tenant_ctx.can_admin():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin or Owner role is required to make approval decisions.",
        )

    try:
        appr = await ExecutionEngine.process_approval_decision(
            session=session,
            tenant_id=uuid.UUID(tenant_ctx.tenant_id),
            approval_id=uuid.UUID(approval_id),
            user_id=uuid.UUID(tenant_ctx.user_id),
            decision=req.decision,
            notes=req.notes,
        )
        return ApprovalResponse(
            id=str(appr.id),
            task_id=str(appr.task_id),
            task_name=appr.task.name if appr.task else "Task Action",
            requested_action=appr.requested_action,
            impact_assessment=appr.impact_assessment,
            status=appr.status,
            reviewed_by=str(appr.reviewed_by) if appr.reviewed_by else None,
            reviewed_at=appr.reviewed_at.isoformat() if appr.reviewed_at else None,
            decision_notes=appr.decision_notes,
            created_at=appr.created_at.isoformat(),
        )
    except ExecutionEngineError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
