"""Business Context Graph domain service and validation."""

import uuid
from enum import Enum
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import AuditLog, BusinessContextEdge, BusinessContextNode, Project


class ContextNodeType(str, Enum):
    GOAL = "goal"
    REQUIREMENT = "requirement"
    CONSTRAINT = "constraint"
    DECISION = "decision"
    TASK = "task"
    INTEGRATION_REQUIREMENT = "integration_requirement"
    VERIFICATION_REQUIREMENT = "verification_requirement"
    LAUNCH_CRITERION = "launch_criterion"


class ContextEdgeType(str, Enum):
    REQUIRES = "REQUIRES"
    DEPENDS_ON = "DEPENDS_ON"
    IMPLEMENTS = "IMPLEMENTS"
    VERIFIES = "VERIFIES"
    BLOCKED_BY = "BLOCKED_BY"
    SUPPORTS_GOAL = "SUPPORTS_GOAL"


class InvalidContextGraphError(Exception):
    """Raised when context nodes or edges violate domain constraints."""


class ContextGraphService:
    """Manages structured business context entities, relationships, and verification boundaries."""

    @staticmethod
    async def get_project_graph(
        session: AsyncSession,
        tenant_id: uuid.UUID,
        project_id: uuid.UUID,
    ) -> dict[str, list[Any]]:
        """Retrieves all context nodes and directed edges belonging to a project."""
        nodes_res = await session.execute(
            select(BusinessContextNode)
            .where(
                BusinessContextNode.tenant_id == tenant_id,
                BusinessContextNode.project_id == project_id,
            )
            .order_by(BusinessContextNode.created_at.asc())
        )
        nodes = nodes_res.scalars().all()

        edges_res = await session.execute(
            select(BusinessContextEdge)
            .where(
                BusinessContextEdge.tenant_id == tenant_id,
                BusinessContextEdge.project_id == project_id,
            )
            .order_by(BusinessContextEdge.created_at.asc())
        )
        edges = edges_res.scalars().all()

        return {
            "nodes": [
                {
                    "id": str(n.id),
                    "node_type": n.node_type,
                    "key": n.key,
                    "version": n.version,
                    "is_verified": n.is_verified,
                    "data": n.data,
                    "source_attribution": n.source_attribution,
                    "created_at": n.created_at.isoformat(),
                }
                for n in nodes
            ],
            "edges": [
                {
                    "id": str(e.id),
                    "source_node_id": str(e.source_node_id),
                    "target_node_id": str(e.target_node_id),
                    "relationship_type": e.relationship_type,
                    "created_at": e.created_at.isoformat(),
                }
                for e in edges
            ],
        }

    @staticmethod
    async def add_node(
        session: AsyncSession,
        tenant_id: uuid.UUID,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        node_type: str,
        key: str,
        data: dict[str, Any],
        source_attribution: str = "user_input",
    ) -> BusinessContextNode:
        """Validates and persists a typed context node scoped to tenant and project."""
        # Ensure project exists and belongs to this tenant
        proj = await session.execute(
            select(Project).where(Project.id == project_id, Project.tenant_id == tenant_id)
        )
        if not proj.scalar_one_or_none():
            raise InvalidContextGraphError("Project not found in this tenant context.")

        # Check existing version for this key/type
        existing_res = await session.execute(
            select(BusinessContextNode)
            .where(
                BusinessContextNode.project_id == project_id,
                BusinessContextNode.node_type == node_type,
                BusinessContextNode.key == key,
            )
            .order_by(BusinessContextNode.version.desc())
        )
        existing_node = existing_res.scalar_one_or_none()
        next_version = (existing_node.version + 1) if existing_node else 1

        node = BusinessContextNode(
            tenant_id=tenant_id,
            project_id=project_id,
            node_type=node_type,
            key=key,
            version=next_version,
            is_verified=False,
            data=data,
            source_attribution=source_attribution,
        )
        session.add(node)

        audit_entry = AuditLog(
            tenant_id=tenant_id,
            user_id=user_id,
            action="context_node.created",
            resource_type="business_context_node",
            resource_id=str(node.id),
            details={"node_type": node_type, "key": key, "version": next_version},
        )
        session.add(audit_entry)
        await session.flush()
        await session.refresh(node)
        return node

    @staticmethod
    async def add_edge(
        session: AsyncSession,
        tenant_id: uuid.UUID,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        source_node_id: uuid.UUID,
        target_node_id: uuid.UUID,
        relationship_type: str,
    ) -> BusinessContextEdge:
        """Connects two nodes after strictly verifying both belong to the authorized tenant and project."""
        if source_node_id == target_node_id:
            raise InvalidContextGraphError("A context node cannot have a relationship to itself.")

        # Validate source node ownership
        src_res = await session.execute(
            select(BusinessContextNode).where(
                BusinessContextNode.id == source_node_id,
                BusinessContextNode.tenant_id == tenant_id,
                BusinessContextNode.project_id == project_id,
            )
        )
        if not src_res.scalar_one_or_none():
            raise InvalidContextGraphError(
                "Source context node does not exist or does not belong to this project."
            )

        # Validate target node ownership
        tgt_res = await session.execute(
            select(BusinessContextNode).where(
                BusinessContextNode.id == target_node_id,
                BusinessContextNode.tenant_id == tenant_id,
                BusinessContextNode.project_id == project_id,
            )
        )
        if not tgt_res.scalar_one_or_none():
            raise InvalidContextGraphError(
                "Target context node does not exist or does not belong to this project."
            )

        edge = BusinessContextEdge(
            tenant_id=tenant_id,
            project_id=project_id,
            source_node_id=source_node_id,
            target_node_id=target_node_id,
            relationship_type=relationship_type,
        )
        session.add(edge)

        audit_entry = AuditLog(
            tenant_id=tenant_id,
            user_id=user_id,
            action="context_edge.created",
            resource_type="business_context_edge",
            resource_id=str(edge.id),
            details={
                "source": str(source_node_id),
                "target": str(target_node_id),
                "relationship": relationship_type,
            },
        )
        session.add(audit_entry)
        await session.flush()
        await session.refresh(edge)
        return edge
