"""Initial core schema migration.

Revision ID: 001_initial_core_schema
Revises:
Create Date: 2026-10-19 19:15:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "001_initial_core_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Tenants
    op.create_table(
        "tenants",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(255), nullable=False),
        sa.Column("tier", sa.String(50), nullable=False, server_default="free"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("slug", name="uq_tenants_slug"),
    )
    op.create_index("ix_tenants_slug", "tenants", ["slug"])

    # 2. Users
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=True),
        sa.Column("full_name", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("ix_users_email", "users", ["email"])

    # 3. Memberships
    op.create_table(
        "memberships",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("role", sa.String(50), nullable=False, server_default="member"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "user_id", name="uq_memberships_tenant_user"),
    )
    op.create_index("ix_memberships_tenant_id", "memberships", ["tenant_id"])
    op.create_index("ix_memberships_user_id", "memberships", ["user_id"])

    # 4. Projects
    op.create_table(
        "projects",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("primary_goal", sa.Text(), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="draft"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_projects_tenant_id", "projects", ["tenant_id"])
    op.create_index("ix_projects_status", "projects", ["status"])

    # 5. Business Context Nodes
    op.create_table(
        "business_context_nodes",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "project_id",
            sa.Uuid(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("node_type", sa.String(50), nullable=False),
        sa.Column("key", sa.String(255), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("source_attribution", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "project_id", "node_type", "key", "version", name="uq_context_node_version"
        ),
    )
    op.create_index(
        "ix_context_nodes_tenant_project", "business_context_nodes", ["tenant_id", "project_id"]
    )
    op.create_index("ix_context_nodes_type_key", "business_context_nodes", ["node_type", "key"])

    # 6. Business Context Edges
    op.create_table(
        "business_context_edges",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "project_id",
            sa.Uuid(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_node_id",
            sa.Uuid(),
            sa.ForeignKey("business_context_nodes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "target_node_id",
            sa.Uuid(),
            sa.ForeignKey("business_context_nodes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("relationship_type", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_context_edges_tenant_project", "business_context_edges", ["tenant_id", "project_id"]
    )
    op.create_index(
        "ix_context_edges_source_target",
        "business_context_edges",
        ["source_node_id", "target_node_id"],
    )

    # 7. Workflow Executions
    op.create_table(
        "workflow_executions",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "project_id",
            sa.Uuid(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("template_name", sa.String(100), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="planned"),
        sa.Column("trigger_type", sa.String(50), nullable=False, server_default="user_intent"),
        sa.Column("metadata_payload", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_workflow_executions_tenant_id", "workflow_executions", ["tenant_id"])
    op.create_index("ix_workflow_executions_project_id", "workflow_executions", ["project_id"])
    op.create_index("ix_workflow_executions_status", "workflow_executions", ["status"])

    # 8. Tasks
    op.create_table(
        "tasks",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "workflow_execution_id",
            sa.Uuid(),
            sa.ForeignKey("workflow_executions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("task_type", sa.String(100), nullable=False),
        sa.Column("connector_id", sa.String(100), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="planned"),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("input_payload", sa.JSON(), nullable=False),
        sa.Column("output_payload", sa.JSON(), nullable=False),
        sa.Column("error_details", sa.JSON(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_retries", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("requires_approval", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "workflow_execution_id", "idempotency_key", name="uq_tasks_workflow_idempotency"
        ),
    )
    op.create_index("ix_tasks_tenant_id", "tasks", ["tenant_id"])
    op.create_index("ix_tasks_status", "tasks", ["status"])
    op.create_index("ix_tasks_connector_id", "tasks", ["connector_id"])

    # 9. Task Dependencies
    op.create_table(
        "task_dependencies",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "task_id", sa.Uuid(), sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "depends_on_task_id",
            sa.Uuid(),
            sa.ForeignKey("tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.UniqueConstraint("task_id", "depends_on_task_id", name="uq_task_dependencies_pair"),
    )
    op.create_index("ix_task_dependencies_task_id", "task_dependencies", ["task_id"])
    op.create_index("ix_task_dependencies_depends_on", "task_dependencies", ["depends_on_task_id"])

    # 10. Verification Records
    op.create_table(
        "verification_records",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "task_id", sa.Uuid(), sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("verification_type", sa.String(100), nullable=False),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_verification_records_tenant_id", "verification_records", ["tenant_id"])
    op.create_index("ix_verification_records_task_id", "verification_records", ["task_id"])
    op.create_index("ix_verification_records_status", "verification_records", ["status"])

    # 11. Approval Requests
    op.create_table(
        "approval_requests",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "task_id", sa.Uuid(), sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("requested_action", sa.String(255), nullable=False),
        sa.Column("impact_assessment", sa.Text(), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column(
            "reviewed_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_approval_requests_tenant_id", "approval_requests", ["tenant_id"])
    op.create_index("ix_approval_requests_task_id", "approval_requests", ["task_id"])
    op.create_index("ix_approval_requests_status", "approval_requests", ["status"])

    # 12. Connector Configs
    op.create_table(
        "connector_configs",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="active"),
        sa.Column("auth_type", sa.String(50), nullable=False),
        sa.Column("scopes", sa.JSON(), nullable=False),
        sa.Column("encrypted_credentials", sa.LargeBinary(), nullable=False),
        sa.Column("credential_nonce", sa.LargeBinary(), nullable=False),
        sa.Column("key_version", sa.String(50), nullable=False, server_default="v1"),
        sa.Column("metadata_payload", sa.JSON(), nullable=False),
        sa.Column("last_health_check", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "provider", name="uq_connector_configs_tenant_provider"),
    )
    op.create_index("ix_connector_configs_tenant_id", "connector_configs", ["tenant_id"])
    op.create_index("ix_connector_configs_status", "connector_configs", ["status"])

    # 13. Audit Logs
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("resource_type", sa.String(100), nullable=False),
        sa.Column("resource_id", sa.String(255), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("ip_address", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_logs_tenant_id", "audit_logs", ["tenant_id"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])

    # Apply PostgreSQL Row Level Security (RLS) if running on PostgreSQL engine
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # 1. Direct tenant-owned tables
        direct_tenant_tables = [
            "memberships",
            "projects",
            "business_context_nodes",
            "business_context_edges",
            "workflow_executions",
            "tasks",
            "verification_records",
            "approval_requests",
            "connector_configs",
        ]
        for tbl in direct_tenant_tables:
            op.execute(f"ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY;")
            op.execute(f"ALTER TABLE {tbl} FORCE ROW LEVEL SECURITY;")
            op.execute(f"""
                CREATE POLICY {tbl}_tenant_isolation_policy ON {tbl}
                FOR ALL
                USING (
                    tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid
                )
                WITH CHECK (
                    tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid
                );
            """)

        # 2. Indirectly scoped tables (task_dependencies via tasks)
        op.execute("ALTER TABLE task_dependencies ENABLE ROW LEVEL SECURITY;")
        op.execute("ALTER TABLE task_dependencies FORCE ROW LEVEL SECURITY;")
        op.execute("""
            CREATE POLICY task_dependencies_tenant_isolation_policy ON task_dependencies
            FOR ALL
            USING (
                EXISTS (
                    SELECT 1 FROM tasks
                    WHERE tasks.id = task_dependencies.task_id
                      AND tasks.tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid
                )
            )
            WITH CHECK (
                EXISTS (
                    SELECT 1 FROM tasks
                    WHERE tasks.id = task_dependencies.task_id
                      AND tasks.tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid
                )
            );
        """)

        # 3. Append-only Audit Logs (denies UPDATE and DELETE unconditionally under RLS)
        op.execute("ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;")
        op.execute("ALTER TABLE audit_logs FORCE ROW LEVEL SECURITY;")
        op.execute("""
            CREATE POLICY audit_logs_select_policy ON audit_logs
            FOR SELECT
            USING (
                tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid
            );
        """)
        op.execute("""
            CREATE POLICY audit_logs_insert_policy ON audit_logs
            FOR INSERT
            WITH CHECK (
                tenant_id IS NULL OR
                tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid
            );
        """)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        all_rls_tables = [
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
        ]
        for tbl in all_rls_tables:
            op.execute(f"DROP POLICY IF EXISTS {tbl}_tenant_isolation_policy ON {tbl};")
            op.execute(f"DROP POLICY IF EXISTS {tbl}_select_policy ON {tbl};")
            op.execute(f"DROP POLICY IF EXISTS {tbl}_insert_policy ON {tbl};")
            op.execute(f"ALTER TABLE {tbl} NO FORCE ROW LEVEL SECURITY;")
            op.execute(f"ALTER TABLE {tbl} DISABLE ROW LEVEL SECURITY;")

    op.drop_table("audit_logs")
    op.drop_table("connector_configs")
    op.drop_table("approval_requests")
    op.drop_table("verification_records")
    op.drop_table("task_dependencies")
    op.drop_table("tasks")
    op.drop_table("workflow_executions")
    op.drop_table("business_context_edges")
    op.drop_table("business_context_nodes")
    op.drop_table("projects")
    op.drop_table("memberships")
    op.drop_table("users")
    op.drop_table("tenants")
