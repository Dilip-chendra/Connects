"""SQLAlchemy 2.0 Database Models for Connects.

Defines all 13 core entities with strict typing, foreign keys, unique constraints,
check constraints, tenant ownership, and indexing.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Tenant(Base):
    """Tenants represent organization/workspace isolation boundaries."""

    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    tier: Mapped[str] = mapped_column(String(50), default="free", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    memberships: Mapped[list["Membership"]] = relationship(
        "Membership", back_populates="tenant", cascade="all, delete-orphan"
    )
    projects: Mapped[list["Project"]] = relationship(
        "Project", back_populates="tenant", cascade="all, delete-orphan"
    )
    connector_configs: Mapped[list["ConnectorConfig"]] = relationship(
        "ConnectorConfig", back_populates="tenant", cascade="all, delete-orphan"
    )
    github_installations: Mapped[list["GitHubInstallation"]] = relationship(
        "GitHubInstallation", back_populates="tenant", cascade="all, delete-orphan"
    )


class User(Base):
    """Individual human users."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    memberships: Mapped[list["Membership"]] = relationship(
        "Membership", back_populates="user", cascade="all, delete-orphan"
    )


class Membership(Base):
    """Associates a User with a Tenant under a defined Role."""

    __tablename__ = "memberships"
    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", name="uq_memberships_tenant_user"),
        Index("ix_memberships_tenant_id", "tenant_id"),
        Index("ix_memberships_user_id", "user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(
        String(50), default="member", nullable=False
    )  # owner, admin, member, viewer
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="memberships")
    user: Mapped["User"] = relationship("User", back_populates="memberships")


class Project(Base):
    """High-level startup/application project owned by a Tenant."""

    __tablename__ = "projects"
    __table_args__ = (
        Index("ix_projects_tenant_id", "tenant_id"),
        Index("ix_projects_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    primary_goal: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), default="draft", nullable=False
    )  # draft, active, launched, paused
    category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    target_launch_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="projects")
    context_nodes: Mapped[list["BusinessContextNode"]] = relationship(
        "BusinessContextNode", back_populates="project", cascade="all, delete-orphan"
    )
    workflow_executions: Mapped[list["WorkflowExecution"]] = relationship(
        "WorkflowExecution", back_populates="project", cascade="all, delete-orphan"
    )
    execution_plans: Mapped[list["ExecutionPlan"]] = relationship(
        "ExecutionPlan", back_populates="project", cascade="all, delete-orphan"
    )
    connected_repositories: Mapped[list["ConnectedRepository"]] = relationship(
        "ConnectedRepository", back_populates="project", cascade="all, delete-orphan"
    )
    repository_scans: Mapped[list["RepositoryScan"]] = relationship(
        "RepositoryScan", back_populates="project", cascade="all, delete-orphan"
    )
    repository_findings: Mapped[list["RepositoryFinding"]] = relationship(
        "RepositoryFinding", back_populates="project", cascade="all, delete-orphan"
    )


class BusinessContextNode(Base):
    """Persistent entities in the Project Business Context Graph."""

    __tablename__ = "business_context_nodes"
    __table_args__ = (
        UniqueConstraint(
            "project_id", "node_type", "key", "version", name="uq_context_node_version"
        ),
        Index("ix_context_nodes_tenant_project", "tenant_id", "project_id"),
        Index("ix_context_nodes_type_key", "node_type", "key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    node_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # goal, requirement, repository, env_var, pricing_plan, entitlement, endpoint
    key: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    source_attribution: Mapped[str] = mapped_column(
        String(100), nullable=False
    )  # user_prompt, repo_scan, provider_sync, verification_engine
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    project: Mapped["Project"] = relationship("Project", back_populates="context_nodes")


class BusinessContextEdge(Base):
    """Directed edges connecting entities in the Business Context Graph."""

    __tablename__ = "business_context_edges"
    __table_args__ = (
        Index("ix_context_edges_tenant_project", "tenant_id", "project_id"),
        Index("ix_context_edges_source_target", "source_node_id", "target_node_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    source_node_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("business_context_nodes.id", ondelete="CASCADE"), nullable=False
    )
    target_node_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("business_context_nodes.id", ondelete="CASCADE"), nullable=False
    )
    relationship_type: Mapped[str] = mapped_column(
        String(100), nullable=False
    )  # implements, requires, configures, deploys, verifies, monetizes
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class WorkflowExecution(Base):
    """An execution run of an orchestration workflow."""

    __tablename__ = "workflow_executions"
    __table_args__ = (
        Index("ix_workflow_executions_tenant_id", "tenant_id"),
        Index("ix_workflow_executions_project_id", "project_id"),
        Index("ix_workflow_executions_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    template_name: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), default="planned", nullable=False
    )  # planned, running, paused, awaiting_approval, completed, failed, cancelled
    trigger_type: Mapped[str] = mapped_column(String(50), default="user_intent", nullable=False)
    metadata_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    plan_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("execution_plans.id", ondelete="SET NULL"), nullable=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    project: Mapped["Project"] = relationship("Project", back_populates="workflow_executions")
    execution_plan: Mapped["ExecutionPlan | None"] = relationship(
        "ExecutionPlan", back_populates="workflow_executions"
    )
    tasks: Mapped[list["Task"]] = relationship(
        "Task", back_populates="workflow_execution", cascade="all, delete-orphan"
    )


class Task(Base):
    """Individual atomic execution unit within a WorkflowExecution."""

    __tablename__ = "tasks"
    __table_args__ = (
        UniqueConstraint(
            "workflow_execution_id", "idempotency_key", name="uq_tasks_workflow_idempotency"
        ),
        Index("ix_tasks_tenant_id", "tenant_id"),
        Index("ix_tasks_status", "status"),
        Index("ix_tasks_connector_id", "connector_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    workflow_execution_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("workflow_executions.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    task_type: Mapped[str] = mapped_column(String(100), nullable=False)
    connector_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(
        String(50), default="planned", nullable=False
    )  # planned, ready, running, awaiting_approval, verifying, completed, failed, blocked, cancelled, manual_handoff
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    input_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    output_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    error_details: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_retries: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    workflow_execution: Mapped["WorkflowExecution"] = relationship(
        "WorkflowExecution", back_populates="tasks"
    )
    dependencies: Mapped[list["TaskDependency"]] = relationship(
        "TaskDependency", foreign_keys="TaskDependency.task_id", cascade="all, delete-orphan"
    )
    verification_records: Mapped[list["VerificationRecord"]] = relationship(
        "VerificationRecord", back_populates="task", cascade="all, delete-orphan"
    )
    approval_requests: Mapped[list["ApprovalRequest"]] = relationship(
        "ApprovalRequest", back_populates="task", cascade="all, delete-orphan"
    )
    execution_attempts: Mapped[list["ExecutionAttempt"]] = relationship(
        "ExecutionAttempt", back_populates="task", cascade="all, delete-orphan"
    )


class TaskDependency(Base):
    """Represents a DAG dependency edge: task_id requires depends_on_task_id to succeed first."""

    __tablename__ = "task_dependencies"
    __table_args__ = (
        UniqueConstraint("task_id", "depends_on_task_id", name="uq_task_dependencies_pair"),
        Index("ix_task_dependencies_task_id", "task_id"),
        Index("ix_task_dependencies_depends_on", "depends_on_task_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
    )
    depends_on_task_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
    )


class VerificationRecord(Base):
    """Cryptographic, HTTP, or process proof validating task outcome."""

    __tablename__ = "verification_records"
    __table_args__ = (
        Index("ix_verification_records_tenant_id", "tenant_id"),
        Index("ix_verification_records_task_id", "task_id"),
        Index("ix_verification_records_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
    )
    verification_type: Mapped[str] = mapped_column(
        String(100), nullable=False
    )  # http_probe, ssl_check, webhook_ack, test_suite, db_assertion
    status: Mapped[str] = mapped_column(String(50), nullable=False)  # passed, failed, warning
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    task: Mapped["Task"] = relationship("Task", back_populates="verification_records")


class ApprovalRequest(Base):
    """Human-in-the-Loop approval gate for sensitive operations."""

    __tablename__ = "approval_requests"
    __table_args__ = (
        Index("ix_approval_requests_tenant_id", "tenant_id"),
        Index("ix_approval_requests_task_id", "task_id"),
        Index("ix_approval_requests_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
    )
    requested_action: Mapped[str] = mapped_column(String(255), nullable=False)
    impact_assessment: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), default="pending", nullable=False
    )  # pending, approved, rejected
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    task: Mapped["Task"] = relationship("Task", back_populates="approval_requests")


class ConnectorConfig(Base):
    """Encrypted third-party integration credential store."""

    __tablename__ = "connector_configs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "provider", name="uq_connector_configs_tenant_provider"),
        Index("ix_connector_configs_tenant_id", "tenant_id"),
        Index("ix_connector_configs_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # github, vercel, render, stripe, razorpay
    status: Mapped[str] = mapped_column(
        String(50), default="active", nullable=False
    )  # active, revoked, error, expired
    auth_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # oauth2, api_key, personal_access_token
    scopes: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    encrypted_credentials: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    credential_nonce: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    key_version: Mapped[str] = mapped_column(String(50), default="v1", nullable=False)
    metadata_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    last_health_check: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="connector_configs")


class AuditLog(Base):
    """Immutable audit trail of sensitive and authorization events."""

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_tenant_id", "tenant_id"),
        Index("ix_audit_logs_created_at", "created_at"),
        Index("ix_audit_logs_action", "action"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("tenants.id", ondelete="SET NULL"), nullable=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class ExecutionPlan(Base):
    """Structured, versioned execution plan generated from business goals."""

    __tablename__ = "execution_plans"
    __table_args__ = (
        Index("ix_execution_plans_tenant_id", "tenant_id"),
        Index("ix_execution_plans_project_id", "project_id"),
        Index("ix_execution_plans_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), default="draft", nullable=False
    )  # draft, reviewed, approved, rejected, executing, completed
    goal: Mapped[str] = mapped_column(Text, nullable=False)
    plan_source: Mapped[str] = mapped_column(
        String(50), default="rule_based", nullable=False
    )  # rule_based, ai_provider
    plan_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    project: Mapped["Project"] = relationship("Project", back_populates="execution_plans")
    workflow_executions: Mapped[list["WorkflowExecution"]] = relationship(
        "WorkflowExecution", back_populates="execution_plan"
    )


class ExecutionAttempt(Base):
    """Record of an individual execution attempt of a task."""

    __tablename__ = "execution_attempts"
    __table_args__ = (
        Index("ix_execution_attempts_tenant_id", "tenant_id"),
        Index("ix_execution_attempts_task_id", "task_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # running, completed, failed, blocked
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    task: Mapped["Task"] = relationship("Task", back_populates="execution_attempts")


class GitHubInstallation(Base):
    """Authorized GitHub App installation for a workspace/tenant."""

    __tablename__ = "github_installations"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "installation_id", name="uq_github_installations_tenant_installation"
        ),
        Index("ix_github_installations_tenant_id", "tenant_id"),
        Index("ix_github_installations_installation_id", "installation_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    installation_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    account_login: Mapped[str] = mapped_column(String(255), nullable=False)
    account_type: Mapped[str] = mapped_column(String(50), nullable=False)  # User, Organization
    account_avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    repository_selection: Mapped[str] = mapped_column(
        String(50), default="selected", nullable=False
    )  # all, selected
    permissions: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), default="active", nullable=False
    )  # active, suspended, deleted
    installed_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="github_installations")
    connected_repositories: Mapped[list["ConnectedRepository"]] = relationship(
        "ConnectedRepository", back_populates="installation", cascade="all, delete-orphan"
    )


class ConnectedRepository(Base):
    """GitHub repository connected to a Connects project."""

    __tablename__ = "connected_repositories"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "project_id", "github_repo_id", name="uq_connected_repos_project_github"
        ),
        Index("ix_connected_repositories_tenant_id", "tenant_id"),
        Index("ix_connected_repositories_project_id", "project_id"),
        Index("ix_connected_repositories_github_repo_id", "github_repo_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    installation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("github_installations.id", ondelete="CASCADE"), nullable=False
    )
    github_repo_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    owner: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(512), nullable=False)
    html_url: Mapped[str] = mapped_column(String(512), nullable=False)
    is_private: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    default_branch: Mapped[str] = mapped_column(String(100), default="main", nullable=False)
    selected_branch: Mapped[str] = mapped_column(String(100), default="main", nullable=False)
    latest_commit_sha: Mapped[str | None] = mapped_column(String(40), nullable=True)
    status: Mapped[str] = mapped_column(
        String(50), default="connected", nullable=False
    )  # connected, disconnected, access_revoked, error
    last_error_category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_scanned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    project: Mapped["Project"] = relationship("Project", back_populates="connected_repositories")
    installation: Mapped["GitHubInstallation"] = relationship(
        "GitHubInstallation", back_populates="connected_repositories"
    )
    scans: Mapped[list["RepositoryScan"]] = relationship(
        "RepositoryScan", back_populates="repository", cascade="all, delete-orphan"
    )


class RepositoryScan(Base):
    """Execution run of RepositoryInspector against a specific commit SHA."""

    __tablename__ = "repository_scans"
    __table_args__ = (
        Index("ix_repository_scans_tenant_id", "tenant_id"),
        Index("ix_repository_scans_project_id", "project_id"),
        Index("ix_repository_scans_repository_id", "repository_id"),
        Index("ix_repository_scans_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    repository_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("connected_repositories.id", ondelete="CASCADE"), nullable=False
    )
    commit_sha: Mapped[str] = mapped_column(String(40), nullable=False)
    branch: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), default="queued", nullable=False
    )  # queued, running, completed, failed, cancelled
    files_analyzed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    findings_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    scan_summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    initiated_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped["Project"] = relationship("Project", back_populates="repository_scans")
    repository: Mapped["ConnectedRepository"] = relationship(
        "ConnectedRepository", back_populates="scans"
    )
    findings: Mapped[list["RepositoryFinding"]] = relationship(
        "RepositoryFinding", back_populates="scan", cascade="all, delete-orphan"
    )


class RepositoryFinding(Base):
    """Specific verifiable finding, observation, or launch-readiness gap."""

    __tablename__ = "repository_findings"
    __table_args__ = (
        Index("ix_repository_findings_tenant_id", "tenant_id"),
        Index("ix_repository_findings_scan_id", "scan_id"),
        Index("ix_repository_findings_project_id", "project_id"),
        Index("ix_repository_findings_category", "category"),
        Index("ix_repository_findings_severity", "severity"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    scan_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("repository_scans.id", ondelete="CASCADE"), nullable=False
    )
    finding_id: Mapped[str] = mapped_column(String(100), nullable=False)  # stable ID
    category: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # application_structure, testing, database, deployment, security
    severity: Mapped[str] = mapped_column(
        String(50), default="info", nullable=False
    )  # info, low, medium, high, critical
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[str] = mapped_column(
        String(50), default="high", nullable=False
    )  # high, medium, low
    verification_status: Mapped[str] = mapped_column(
        String(50), default="OBSERVED", nullable=False
    )  # OBSERVED, NEEDS_REVIEW, NOT_FOUND_IN_SCANNED_SCOPE, UNVERIFIED
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    line_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    line_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    evidence_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    commit_sha: Mapped[str] = mapped_column(String(40), nullable=False)
    rule_id: Mapped[str] = mapped_column(String(100), nullable=False)
    recommended_action: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    scan: Mapped["RepositoryScan"] = relationship("RepositoryScan", back_populates="findings")
    project: Mapped["Project"] = relationship("Project", back_populates="repository_findings")


