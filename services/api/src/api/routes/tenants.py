"""Tenant-scoped API routes."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security.auth import TenantContext, get_tenant_context
from src.database.models import AuditLog, Tenant
from src.database.session import get_db_session

router = APIRouter(prefix="/tenants/{tenant_id}", tags=["tenants"])


class TenantResponse(BaseModel):
    id: str
    name: str
    slug: str
    tier: str


class AuditLogResponse(BaseModel):
    id: str
    action: str
    resource_type: str
    resource_id: str | None
    details: dict
    created_at: str


@router.get("", response_model=TenantResponse)
async def get_tenant_details(
    tenant_id: str,
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> TenantResponse:
    """Returns details for authorized tenant."""
    result = await session.execute(
        select(Tenant).where(Tenant.id == uuid.UUID(tenant_ctx.tenant_id))
    )
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found.")

    return TenantResponse(
        id=str(tenant.id),
        name=tenant.name,
        slug=tenant.slug,
        tier=tenant.tier,
    )


@router.get("/audit-logs", response_model=list[AuditLogResponse])
async def list_tenant_audit_logs(
    tenant_id: str,
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> list[AuditLogResponse]:
    """Returns tenant-scoped audit logs (never leaks cross-tenant logs)."""
    result = await session.execute(
        select(AuditLog)
        .where(AuditLog.tenant_id == uuid.UUID(tenant_ctx.tenant_id))
        .order_by(AuditLog.created_at.desc())
        .limit(50)
    )
    logs = result.scalars().all()
    return [
        AuditLogResponse(
            id=str(log.id),
            action=log.action,
            resource_type=log.resource_type,
            resource_id=log.resource_id,
            details=log.details,
            created_at=log.created_at.isoformat(),
        )
        for log in logs
    ]
