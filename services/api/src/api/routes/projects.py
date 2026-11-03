"""Project management routes strictly scoped to authorized tenant."""

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security.auth import TenantContext, get_tenant_context
from src.database.models import AuditLog, Project
from src.database.session import get_db_session

router = APIRouter(tags=["projects"])


class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    description: str | None = None
    primary_goal: str = Field(min_length=5)
    category: str | None = Field(default="saas", max_length=50)
    target_launch_date: datetime | None = None


class ProjectUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    description: str | None = None
    primary_goal: str | None = Field(default=None, min_length=5)
    category: str | None = None
    target_launch_date: datetime | None = None
    status: str | None = None


class ProjectResponse(BaseModel):
    id: str
    tenant_id: str
    name: str
    description: str | None
    primary_goal: str
    category: str | None
    target_launch_date: str | None
    status: str
    created_by: str | None
    created_at: str
    updated_at: str


class ProjectListResponse(BaseModel):
    items: list[ProjectResponse]
    total: int
    limit: int
    offset: int


def _serialize_project(p: Project) -> ProjectResponse:
    return ProjectResponse(
        id=str(p.id),
        tenant_id=str(p.tenant_id),
        name=p.name,
        description=p.description,
        primary_goal=p.primary_goal,
        category=p.category,
        target_launch_date=p.target_launch_date.isoformat() if p.target_launch_date else None,
        status=p.status,
        created_by=str(p.created_by) if p.created_by else None,
        created_at=p.created_at.isoformat(),
        updated_at=p.updated_at.isoformat(),
    )


@router.get("", response_model=list[ProjectResponse])
async def list_projects(
    tenant_id: str,
    response: Response,
    q: str | None = Query(default=None, description="Search query across name and goal"),
    status_filter: str | None = Query(default=None, alias="status"),
    include_archived: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> list[ProjectResponse]:
    """Lists projects belonging to the active tenant with search, filtering, and pagination."""
    query = select(Project).where(Project.tenant_id == uuid.UUID(tenant_ctx.tenant_id))

    if not include_archived and status_filter != "archived":
        query = query.where(Project.status != "archived")

    if status_filter:
        query = query.where(Project.status == status_filter)

    if q:
        search_pattern = f"%{q}%"
        query = query.where(
            or_(
                Project.name.ilike(search_pattern),
                Project.primary_goal.ilike(search_pattern),
            )
        )

    # Fetch total count
    count_result = await session.execute(query)
    all_items = count_result.scalars().all()
    total = len(all_items)

    # Paginate
    paginated_items = all_items[offset : offset + limit]

    response.headers["X-Total-Count"] = str(total)
    response.headers["X-Limit"] = str(limit)
    response.headers["X-Offset"] = str(offset)

    return [_serialize_project(p) for p in paginated_items]


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    tenant_id: str,
    req: ProjectCreateRequest,
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> ProjectResponse:
    """Creates a project scoped to authorized tenant and records audit log."""
    if not tenant_ctx.can_mutate():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Role not permitted to create projects.",
        )

    project = Project(
        tenant_id=uuid.UUID(tenant_ctx.tenant_id),
        name=req.name,
        description=req.description,
        primary_goal=req.primary_goal,
        category=req.category or "saas",
        target_launch_date=req.target_launch_date,
        created_by=uuid.UUID(tenant_ctx.user_id),
        status="draft",
    )
    session.add(project)

    audit_entry = AuditLog(
        tenant_id=uuid.UUID(tenant_ctx.tenant_id),
        user_id=uuid.UUID(tenant_ctx.user_id),
        action="project.created",
        resource_type="project",
        resource_id=str(project.id),
        details={"name": req.name, "primary_goal": req.primary_goal},
    )
    session.add(audit_entry)

    await session.flush()
    await session.refresh(project)

    return _serialize_project(project)


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    tenant_id: str,
    project_id: str,
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> ProjectResponse:
    """Fetches a single project, verifying tenant ownership."""
    result = await session.execute(
        select(Project).where(
            Project.id == uuid.UUID(project_id),
            Project.tenant_id == uuid.UUID(tenant_ctx.tenant_id),
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found in this tenant.",
        )

    return _serialize_project(project)


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(
    tenant_id: str,
    project_id: str,
    req: ProjectUpdateRequest,
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> ProjectResponse:
    """Updates project information. Scoped strictly to authorized tenant."""
    if not tenant_ctx.can_mutate():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Role not permitted to update projects.",
        )

    result = await session.execute(
        select(Project).where(
            Project.id == uuid.UUID(project_id),
            Project.tenant_id == uuid.UUID(tenant_ctx.tenant_id),
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found in this tenant.",
        )

    updated_fields: dict[str, Any] = {}
    if req.name is not None:
        project.name = req.name
        updated_fields["name"] = req.name
    if req.description is not None:
        project.description = req.description
        updated_fields["description"] = req.description
    if req.primary_goal is not None:
        project.primary_goal = req.primary_goal
        updated_fields["primary_goal"] = req.primary_goal
    if req.category is not None:
        project.category = req.category
        updated_fields["category"] = req.category
    if req.target_launch_date is not None:
        project.target_launch_date = req.target_launch_date
        updated_fields["target_launch_date"] = req.target_launch_date.isoformat()
    if req.status is not None:
        project.status = req.status
        updated_fields["status"] = req.status

    audit_entry = AuditLog(
        tenant_id=uuid.UUID(tenant_ctx.tenant_id),
        user_id=uuid.UUID(tenant_ctx.user_id),
        action="project.updated",
        resource_type="project",
        resource_id=str(project.id),
        details=updated_fields,
    )
    session.add(audit_entry)
    await session.flush()
    await session.refresh(project)

    return _serialize_project(project)


@router.post("/{project_id}/archive", response_model=ProjectResponse)
async def archive_project(
    tenant_id: str,
    project_id: str,
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> ProjectResponse:
    """Soft-archives a project without deleting its historical workflow or context data."""
    if not tenant_ctx.can_mutate():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Role not permitted to archive projects.",
        )

    result = await session.execute(
        select(Project).where(
            Project.id == uuid.UUID(project_id),
            Project.tenant_id == uuid.UUID(tenant_ctx.tenant_id),
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found in this tenant.",
        )

    project.status = "archived"

    audit_entry = AuditLog(
        tenant_id=uuid.UUID(tenant_ctx.tenant_id),
        user_id=uuid.UUID(tenant_ctx.user_id),
        action="project.archived",
        resource_type="project",
        resource_id=str(project.id),
        details={"name": project.name},
    )
    session.add(audit_entry)
    await session.flush()
    await session.refresh(project)

    return _serialize_project(project)
