"""API routes for managing Project Business Context Graph nodes and relationships."""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security.auth import TenantContext, get_tenant_context
from src.database.session import get_db_session
from src.domain.context.graph import (
    ContextGraphService,
    InvalidContextGraphError,
)

router = APIRouter(tags=["context-graph"])


class CreateNodeRequest(BaseModel):
    node_type: str = Field(description="Typed category: goal, requirement, constraint, decision, task, launch_criterion, etc.")
    key: str = Field(min_length=1, max_length=255)
    data: dict[str, Any] = Field(default_factory=dict)
    source_attribution: str = Field(default="user_input")


class CreateEdgeRequest(BaseModel):
    source_node_id: str
    target_node_id: str
    relationship_type: str = Field(description="REQUIRES, DEPENDS_ON, IMPLEMENTS, VERIFIES, BLOCKED_BY, SUPPORTS_GOAL")


class ContextNodeResponse(BaseModel):
    id: str
    node_type: str
    key: str
    version: int
    is_verified: bool
    data: dict[str, Any]
    source_attribution: str
    created_at: str


class ContextEdgeResponse(BaseModel):
    id: str
    source_node_id: str
    target_node_id: str
    relationship_type: str
    created_at: str


class ContextGraphResponse(BaseModel):
    nodes: list[ContextNodeResponse]
    edges: list[ContextEdgeResponse]


@router.get("", response_model=ContextGraphResponse)
async def get_project_context(
    tenant_id: str,
    project_id: str,
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> ContextGraphResponse:
    """Returns the full business context graph for the authorized project."""
    graph = await ContextGraphService.get_project_graph(
        session=session,
        tenant_id=uuid.UUID(tenant_ctx.tenant_id),
        project_id=uuid.UUID(project_id),
    )
    return ContextGraphResponse(
        nodes=[ContextNodeResponse(**n) for n in graph["nodes"]],
        edges=[ContextEdgeResponse(**e) for e in graph["edges"]],
    )


@router.post("/nodes", response_model=ContextNodeResponse, status_code=status.HTTP_201_CREATED)
async def create_context_node(
    tenant_id: str,
    project_id: str,
    req: CreateNodeRequest,
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> ContextNodeResponse:
    """Creates a new typed business context node."""
    if not tenant_ctx.can_mutate():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Role not permitted to create context nodes.",
        )

    try:
        node = await ContextGraphService.add_node(
            session=session,
            tenant_id=uuid.UUID(tenant_ctx.tenant_id),
            project_id=uuid.UUID(project_id),
            user_id=uuid.UUID(tenant_ctx.user_id),
            node_type=req.node_type,
            key=req.key,
            data=req.data,
            source_attribution=req.source_attribution,
        )
        return ContextNodeResponse(
            id=str(node.id),
            node_type=node.node_type,
            key=node.key,
            version=node.version,
            is_verified=node.is_verified,
            data=node.data,
            source_attribution=node.source_attribution,
            created_at=node.created_at.isoformat(),
        )
    except InvalidContextGraphError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/edges", response_model=ContextEdgeResponse, status_code=status.HTTP_201_CREATED)
async def create_context_edge(
    tenant_id: str,
    project_id: str,
    req: CreateEdgeRequest,
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> ContextEdgeResponse:
    """Creates a directed relationship edge between two verified context nodes in the project."""
    if not tenant_ctx.can_mutate():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Role not permitted to create context edges.",
        )

    try:
        edge = await ContextGraphService.add_edge(
            session=session,
            tenant_id=uuid.UUID(tenant_ctx.tenant_id),
            project_id=uuid.UUID(project_id),
            user_id=uuid.UUID(tenant_ctx.user_id),
            source_node_id=uuid.UUID(req.source_node_id),
            target_node_id=uuid.UUID(req.target_node_id),
            relationship_type=req.relationship_type,
        )
        return ContextEdgeResponse(
            id=str(edge.id),
            source_node_id=str(edge.source_node_id),
            target_node_id=str(edge.target_node_id),
            relationship_type=edge.relationship_type,
            created_at=edge.created_at.isoformat(),
        )
    except (InvalidContextGraphError, ValueError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
