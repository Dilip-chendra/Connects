"""Phase 1 execution plans and attempts schema migration.

Revision ID: 002_phase1_execution_and_plans
Revises: 001_initial_core_schema
Create Date: 2026-10-19 20:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "002_phase1_execution_and_plans"
down_revision: str | None = "001_initial_core_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    # 1. Extend projects table
    op.add_column("projects", sa.Column("category", sa.String(50), nullable=True))
    op.add_column(
        "projects", sa.Column("target_launch_date", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "projects",
        sa.Column(
            "created_by",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    # 2. Create execution_plans table
    op.create_table(
        "execution_plans",
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
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(50), nullable=False, server_default="draft"),
        sa.Column("goal", sa.Text(), nullable=False),
        sa.Column("plan_source", sa.String(50), nullable=False, server_default="rule_based"),
        sa.Column("plan_data", sa.JSON(), nullable=False),
        sa.Column(
            "created_by",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "approved_by",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_execution_plans_tenant_id", "execution_plans", ["tenant_id"])
    op.create_index("ix_execution_plans_project_id", "execution_plans", ["project_id"])
    op.create_index("ix_execution_plans_status", "execution_plans", ["status"])

    # 3. Extend workflow_executions with plan_id
    op.add_column(
        "workflow_executions",
        sa.Column(
            "plan_id",
            sa.Uuid(),
            sa.ForeignKey("execution_plans.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    # 4. Create execution_attempts table
    op.create_table(
        "execution_attempts",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "task_id", sa.Uuid(), sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("output_payload", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_execution_attempts_tenant_id", "execution_attempts", ["tenant_id"])
    op.create_index("ix_execution_attempts_task_id", "execution_attempts", ["task_id"])

    # 5. Row-Level Security for execution_plans and execution_attempts
    if is_postgres:
        for table in ["execution_plans", "execution_attempts"]:
            op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
            op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")
            op.execute(
                f"""
                CREATE POLICY {table}_tenant_isolation ON {table}
                FOR ALL
                USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid)
                WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid);
                """
            )


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        op.execute("DROP POLICY IF EXISTS execution_attempts_tenant_isolation ON execution_attempts;")
        op.execute("DROP POLICY IF EXISTS execution_plans_tenant_isolation ON execution_plans;")

    op.drop_table("execution_attempts")
    op.drop_column("workflow_executions", "plan_id")
    op.drop_table("execution_plans")
    op.drop_column("projects", "created_by")
    op.drop_column("projects", "target_launch_date")
    op.drop_column("projects", "category")
