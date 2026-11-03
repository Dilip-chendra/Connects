"""Workspace (Tenant) lifecycle and membership routes."""

import re
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.security.auth import (
    AuthenticatedUser,
    TenantContext,
    get_authenticated_user,
    get_tenant_context,
)
from src.database.models import AuditLog, Membership, Tenant
from src.database.session import get_db_session

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


class WorkspaceCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    slug: str | None = Field(default=None, max_length=100)
    tier: str = Field(default="free")


class WorkspaceUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=100)
    tier: str | None = None


class WorkspaceResponse(BaseModel):
    id: str
    name: str
    slug: str
    tier: str
    role: str | None = None
    created_at: str


class WorkspaceMemberResponse(BaseModel):
    id: str
    user_id: str
    email: str
    full_name: str | None
    role: str
    created_at: str


class WorkspaceActivityResponse(BaseModel):
    id: str
    action: str
    resource_type: str
    resource_id: str | None
    details: dict[str, Any]
    created_at: str


def slugify(text: str) -> str:
    slug = re.sub(r"[^\w\s-]", "", text.lower())
    slug = re.sub(r"[\s_-]+", "-", slug).strip("-")
    return slug or "workspace"


@router.post("", response_model=WorkspaceResponse, status_code=status.HTTP_201_CREATED)
async def create_workspace(
    req: WorkspaceCreateRequest,
    user: AuthenticatedUser = Depends(get_authenticated_user),
    session: AsyncSession = Depends(get_db_session),
) -> WorkspaceResponse:
    """Atomically creates a workspace (tenant) and establishes the creator as 'owner'."""
    base_slug = req.slug or slugify(req.name)
    slug = base_slug

    # Ensure unique slug
    suffix = 1
    while True:
        existing = await session.execute(select(Tenant).where(Tenant.slug == slug))
        if not existing.scalar_one_or_none():
            break
        slug = f"{base_slug}-{suffix}"
        suffix += 1

    tenant = Tenant(
        name=req.name,
        slug=slug,
        tier=req.tier,
    )
    session.add(tenant)
    await session.flush()
    await session.refresh(tenant)

    # Establish atomic owner membership
    membership = Membership(
        tenant_id=tenant.id,
        user_id=uuid.UUID(user.id),
        role="owner",
    )
    session.add(membership)

    audit_entry = AuditLog(
        tenant_id=tenant.id,
        user_id=uuid.UUID(user.id),
        action="workspace.created",
        resource_type="tenant",
        resource_id=str(tenant.id),
        details={"name": tenant.name, "slug": tenant.slug, "tier": tenant.tier},
    )
    session.add(audit_entry)
    await session.flush()

    return WorkspaceResponse(
        id=str(tenant.id),
        name=tenant.name,
        slug=tenant.slug,
        tier=tenant.tier,
        role="owner",
        created_at=tenant.created_at.isoformat(),
    )


@router.get("", response_model=list[WorkspaceResponse])
async def list_user_workspaces(
    user: AuthenticatedUser = Depends(get_authenticated_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[WorkspaceResponse]:
    """Lists all workspaces that the current authenticated user belongs to."""
    result = await session.execute(
        select(Membership)
        .options(selectinload(Membership.tenant))
        .where(Membership.user_id == uuid.UUID(user.id))
        .order_by(Membership.created_at.desc())
    )
    memberships = result.scalars().all()
    return [
        WorkspaceResponse(
            id=str(m.tenant.id),
            name=m.tenant.name,
            slug=m.tenant.slug,
            tier=m.tenant.tier,
            role=m.role,
            created_at=m.tenant.created_at.isoformat(),
        )
        for m in memberships
        if m.tenant
    ]


@router.get("/{tenant_id}", response_model=WorkspaceResponse)
async def get_workspace(
    tenant_id: str,
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> WorkspaceResponse:
    """Returns workspace details for authorized tenant member."""
    result = await session.execute(
        select(Tenant).where(Tenant.id == uuid.UUID(tenant_ctx.tenant_id))
    )
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found.")

    return WorkspaceResponse(
        id=str(tenant.id),
        name=tenant.name,
        slug=tenant.slug,
        tier=tenant.tier,
        role=tenant_ctx.role,
        created_at=tenant.created_at.isoformat(),
    )


@router.patch("/{tenant_id}", response_model=WorkspaceResponse)
async def update_workspace(
    tenant_id: str,
    req: WorkspaceUpdateRequest,
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> WorkspaceResponse:
    """Updates workspace settings. Requires admin or owner role."""
    if not tenant_ctx.can_admin():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin or Owner role is required to modify workspace settings.",
        )

    result = await session.execute(
        select(Tenant).where(Tenant.id == uuid.UUID(tenant_ctx.tenant_id))
    )
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found.")

    updated_fields: dict[str, Any] = {}
    if req.name is not None:
        tenant.name = req.name
        updated_fields["name"] = req.name
    if req.tier is not None:
        tenant.tier = req.tier
        updated_fields["tier"] = req.tier

    audit_entry = AuditLog(
        tenant_id=tenant.id,
        user_id=uuid.UUID(tenant_ctx.user_id),
        action="workspace.updated",
        resource_type="tenant",
        resource_id=str(tenant.id),
        details=updated_fields,
    )
    session.add(audit_entry)
    await session.flush()
    await session.refresh(tenant)

    return WorkspaceResponse(
        id=str(tenant.id),
        name=tenant.name,
        slug=tenant.slug,
        tier=tenant.tier,
        role=tenant_ctx.role,
        created_at=tenant.created_at.isoformat(),
    )


@router.get("/{tenant_id}/members", response_model=list[WorkspaceMemberResponse])
async def list_workspace_members(
    tenant_id: str,
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> list[WorkspaceMemberResponse]:
    """Lists members and roles for the active workspace."""
    result = await session.execute(
        select(Membership)
        .options(selectinload(Membership.user))
        .where(Membership.tenant_id == uuid.UUID(tenant_ctx.tenant_id))
        .order_by(Membership.created_at.asc())
    )
    memberships = result.scalars().all()
    return [
        WorkspaceMemberResponse(
            id=str(m.id),
            user_id=str(m.user_id),
            email=m.user.email if m.user else "",
            full_name=m.user.full_name if m.user else None,
            role=m.role,
            created_at=m.created_at.isoformat(),
        )
        for m in memberships
    ]


@router.get("/{tenant_id}/activity", response_model=list[WorkspaceActivityResponse])
async def list_workspace_activity(
    tenant_id: str,
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> list[WorkspaceActivityResponse]:
    """Returns audit trail and activity log for the active workspace."""
    result = await session.execute(
        select(AuditLog)
        .where(AuditLog.tenant_id == uuid.UUID(tenant_ctx.tenant_id))
        .order_by(AuditLog.created_at.desc())
        .limit(100)
    )
    logs = result.scalars().all()
    return [
        WorkspaceActivityResponse(
            id=str(log.id),
            action=log.action,
            resource_type=log.resource_type,
            resource_id=log.resource_id,
            details=log.details,
            created_at=log.created_at.isoformat(),
        )
        for log in logs
    ]
