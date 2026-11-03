"""Phase 2 GitHub integration and repository intelligence schema migration.

Revision ID: 003_phase2_github_repo
Revises: 002_phase1_execution_and_plans
Create Date: 2026-10-20 14:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "003_phase2_github_repo"
down_revision: str | None = "002_phase1_execution_and_plans"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    # 1. github_installations
    op.create_table(
        "github_installations",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("installation_id", sa.BigInteger(), nullable=False),
        sa.Column("account_login", sa.String(255), nullable=False),
        sa.Column("account_type", sa.String(50), nullable=False),
        sa.Column("account_avatar_url", sa.String(500), nullable=True),
        sa.Column("repository_selection", sa.String(50), default="selected", nullable=False),
        sa.Column("permissions", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(50), default="active", nullable=False),
        sa.Column(
            "installed_by",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "tenant_id", "installation_id", name="uq_github_installations_tenant_installation"
        ),
    )
    op.create_index("ix_github_installations_tenant_id", "github_installations", ["tenant_id"])
    op.create_index(
        "ix_github_installations_installation_id", "github_installations", ["installation_id"]
    )

    # 2. connected_repositories
    op.create_table(
        "connected_repositories",
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
            "installation_id",
            sa.Uuid(),
            sa.ForeignKey("github_installations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("github_repo_id", sa.BigInteger(), nullable=False),
        sa.Column("owner", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(512), nullable=False),
        sa.Column("html_url", sa.String(512), nullable=False),
        sa.Column("is_private", sa.Boolean(), default=True, nullable=False),
        sa.Column("default_branch", sa.String(100), default="main", nullable=False),
        sa.Column("selected_branch", sa.String(100), default="main", nullable=False),
        sa.Column("latest_commit_sha", sa.String(40), nullable=True),
        sa.Column("status", sa.String(50), default="connected", nullable=False),
        sa.Column("last_error_category", sa.String(100), nullable=True),
        sa.Column("last_scanned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "tenant_id", "project_id", "github_repo_id", name="uq_connected_repos_project_github"
        ),
    )
    op.create_index(
        "ix_connected_repositories_tenant_id", "connected_repositories", ["tenant_id"]
    )
    op.create_index(
        "ix_connected_repositories_project_id", "connected_repositories", ["project_id"]
    )
    op.create_index(
        "ix_connected_repositories_github_repo_id", "connected_repositories", ["github_repo_id"]
    )

    # 3. repository_scans
    op.create_table(
        "repository_scans",
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
            "repository_id",
            sa.Uuid(),
            sa.ForeignKey("connected_repositories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("commit_sha", sa.String(40), nullable=False),
        sa.Column("branch", sa.String(100), nullable=False),
        sa.Column("status", sa.String(50), default="queued", nullable=False),
        sa.Column("files_analyzed_count", sa.Integer(), default=0, nullable=False),
        sa.Column("findings_count", sa.Integer(), default=0, nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("error_category", sa.String(100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("scan_summary", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column(
            "initiated_by",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_repository_scans_tenant_id", "repository_scans", ["tenant_id"])
    op.create_index("ix_repository_scans_project_id", "repository_scans", ["project_id"])
    op.create_index("ix_repository_scans_repository_id", "repository_scans", ["repository_id"])
    op.create_index("ix_repository_scans_status", "repository_scans", ["status"])

    # 4. repository_findings
    op.create_table(
        "repository_findings",
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
            "scan_id",
            sa.Uuid(),
            sa.ForeignKey("repository_scans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("finding_id", sa.String(100), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("severity", sa.String(50), default="info", nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("confidence", sa.String(50), default="high", nullable=False),
        sa.Column("verification_status", sa.String(50), default="OBSERVED", nullable=False),
        sa.Column("file_path", sa.String(500), nullable=True),
        sa.Column("line_start", sa.Integer(), nullable=True),
        sa.Column("line_end", sa.Integer(), nullable=True),
        sa.Column("evidence_excerpt", sa.Text(), nullable=True),
        sa.Column("commit_sha", sa.String(40), nullable=False),
        sa.Column("rule_id", sa.String(100), nullable=False),
        sa.Column("recommended_action", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_repository_findings_tenant_id", "repository_findings", ["tenant_id"])
    op.create_index("ix_repository_findings_scan_id", "repository_findings", ["scan_id"])
    op.create_index("ix_repository_findings_project_id", "repository_findings", ["project_id"])
    op.create_index("ix_repository_findings_category", "repository_findings", ["category"])
    op.create_index("ix_repository_findings_severity", "repository_findings", ["severity"])

    # 5. Row-Level Security for all 4 Phase 2 tables
    if is_postgres:
        phase2_tables = [
            "github_installations",
            "connected_repositories",
            "repository_scans",
            "repository_findings",
        ]
        for table in phase2_tables:
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
        for table in [
            "repository_findings",
            "repository_scans",
            "connected_repositories",
            "github_installations",
        ]:
            op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table};")

    op.drop_table("repository_findings")
    op.drop_table("repository_scans")
    op.drop_table("connected_repositories")
    op.drop_table("github_installations")
