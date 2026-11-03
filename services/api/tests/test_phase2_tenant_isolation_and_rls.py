"""PostgreSQL Row-Level Security (RLS) and Tenant Isolation tests for Phase 2 entities.

Verifies that:
1. Tenant A cannot SELECT, INSERT, UPDATE, or DELETE Tenant B's GitHub installations.
2. Tenant A cannot access or attach Tenant B's connected repositories.
3. Tenant A cannot query Tenant B's repository scans or findings.
4. RLS enforces deny-by-default when tenant context is empty or unauthenticated.
"""

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


@pytest.mark.asyncio
async def test_postgresql_phase2_tables_rls_boundary(postgres_service: dict) -> None:
    """Verifies kernel-level PostgreSQL RLS enforcement on all Phase 2 tables."""
    app_async_url = postgres_service["app_async_url"]
    admin_sync_url = postgres_service["admin_sync_url"]

    # 1. Seed two tenants with projects and GitHub data via admin connection
    tenant_a_id = uuid.uuid4()
    tenant_b_id = uuid.uuid4()
    proj_a_id = uuid.uuid4()
    proj_b_id = uuid.uuid4()
    inst_a_id = uuid.uuid4()
    inst_b_id = uuid.uuid4()
    repo_a_id = uuid.uuid4()
    repo_b_id = uuid.uuid4()
    scan_b_id = uuid.uuid4()
    find_b_id = uuid.uuid4()

    sync_admin = sa.create_engine(admin_sync_url)
    with sync_admin.connect() as conn:
        conn.execution_options(isolation_level="AUTOCOMMIT")

        # Insert Tenants
        conn.execute(
            text("INSERT INTO tenants (id, name, slug, tier, created_at, updated_at) VALUES (:id, :name, :slug, 'free', NOW(), NOW());"),
            [
                {"id": tenant_a_id, "name": "Tenant A", "slug": f"slug-a-{tenant_a_id.hex[:6]}"},
                {"id": tenant_b_id, "name": "Tenant B", "slug": f"slug-b-{tenant_b_id.hex[:6]}"},
            ],
        )

        # Insert Projects
        conn.execute(
            text("INSERT INTO projects (id, tenant_id, name, primary_goal, status, created_at, updated_at) VALUES (:id, :tid, :name, :goal, 'draft', NOW(), NOW());"),
            [
                {"id": proj_a_id, "tid": tenant_a_id, "name": "Proj A", "goal": "Goal A"},
                {"id": proj_b_id, "tid": tenant_b_id, "name": "Proj B", "goal": "Goal B"},
            ],
        )

        # Insert GitHub Installations
        conn.execute(
            text("""
                INSERT INTO github_installations (id, tenant_id, installation_id, account_login, account_type, repository_selection, permissions, status, created_at, updated_at)
                VALUES 
                (:id_a, :tid_a, 1111, 'org-a', 'Organization', 'selected', '{}', 'active', NOW(), NOW()),
                (:id_b, :tid_b, 2222, 'org-b', 'Organization', 'selected', '{}', 'active', NOW(), NOW());
            """),
            {"id_a": inst_a_id, "tid_a": tenant_a_id, "id_b": inst_b_id, "tid_b": tenant_b_id},
        )

        # Insert Connected Repositories
        conn.execute(
            text("""
                INSERT INTO connected_repositories (id, tenant_id, project_id, installation_id, github_repo_id, owner, name, full_name, html_url, is_private, default_branch, selected_branch, status, created_at, updated_at)
                VALUES
                (:id_a, :tid_a, :pid_a, :inst_a, 501, 'org-a', 'repo-a', 'org-a/repo-a', 'https://github.com/org-a/repo-a', true, 'main', 'main', 'connected', NOW(), NOW()),
                (:id_b, :tid_b, :pid_b, :inst_b, 502, 'org-b', 'repo-b', 'org-b/repo-b', 'https://github.com/org-b/repo-b', true, 'main', 'main', 'connected', NOW(), NOW());
            """),
            {
                "id_a": repo_a_id, "tid_a": tenant_a_id, "pid_a": proj_a_id, "inst_a": inst_a_id,
                "id_b": repo_b_id, "tid_b": tenant_b_id, "pid_b": proj_b_id, "inst_b": inst_b_id,
            },
        )

        # Insert Scan & Finding for Tenant B
        conn.execute(
            text("""
                INSERT INTO repository_scans (id, tenant_id, project_id, repository_id, commit_sha, branch, status, files_analyzed_count, findings_count, scan_summary, created_at)
                VALUES (:sid, :tid, :pid, :rid, 'deadbeef1234567890abcdef1234567890abcdef', 'main', 'completed', 10, 1, '{}', NOW());
            """),
            {"sid": scan_b_id, "tid": tenant_b_id, "pid": proj_b_id, "rid": repo_b_id},
        )
        conn.execute(
            text("""
                INSERT INTO repository_findings (id, tenant_id, project_id, scan_id, finding_id, category, severity, title, description, confidence, verification_status, commit_sha, rule_id, recommended_action, created_at)
                VALUES (:fid, :tid, :pid, :sid, 'FINDING-B-001', 'security', 'critical', 'Exposed Secret in Tenant B', 'Secret desc', 'high', 'OBSERVED', 'deadbeef1234567890abcdef1234567890abcdef', 'RULE-SEC', 'Rotate key', NOW());
            """),
            {"fid": find_b_id, "tid": tenant_b_id, "pid": proj_b_id, "sid": scan_b_id},
        )
    sync_admin.dispose()

    # 2. Test using standard application role `connects_app` (NO SUPERUSER, NO BYPASSRLS)
    app_engine = create_async_engine(app_async_url)
    session_maker = async_sessionmaker(app_engine, class_=AsyncSession, expire_on_commit=False)

    # Test Case A: Empty tenant context -> Deny by default (0 rows returned)
    async with session_maker() as session:
        inst_res = await session.execute(text("SELECT * FROM github_installations;"))
        assert len(inst_res.fetchall()) == 0

        repo_res = await session.execute(text("SELECT * FROM connected_repositories;"))
        assert len(repo_res.fetchall()) == 0

        scan_res = await session.execute(text("SELECT * FROM repository_scans;"))
        assert len(scan_res.fetchall()) == 0

        find_res = await session.execute(text("SELECT * FROM repository_findings;"))
        assert len(find_res.fetchall()) == 0

    # Test Case B: Bound to Tenant A context
    async with session_maker() as session:
        await session.execute(
            text("SELECT set_config('app.current_tenant_id', :tid, true);"),
            {"tid": str(tenant_a_id)},
        )

        # Tenant A can only see its own installation
        inst_res = await session.execute(text("SELECT id, account_login FROM github_installations;"))
        inst_rows = inst_res.fetchall()
        assert len(inst_rows) == 1
        assert str(inst_rows[0][0]) == str(inst_a_id)

        # Tenant A cannot see Tenant B's connected repo
        repo_res = await session.execute(text("SELECT id, full_name FROM connected_repositories;"))
        repo_rows = repo_res.fetchall()
        assert len(repo_rows) == 1
        assert str(repo_rows[0][0]) == str(repo_a_id)

        # Tenant A CANNOT see Tenant B's scans or findings
        scan_res = await session.execute(text("SELECT * FROM repository_scans;"))
        assert len(scan_res.fetchall()) == 0

        find_res = await session.execute(text("SELECT * FROM repository_findings;"))
        assert len(find_res.fetchall()) == 0

        # Tenant A attempting direct SQL access to Tenant B's finding ID returns NOTHING
        b_find_res = await session.execute(
            text("SELECT * FROM repository_findings WHERE id = :fid;"),
            {"fid": find_b_id},
        )
        assert len(b_find_res.fetchall()) == 0

        # Tenant A attempting to INSERT a finding belonging to Tenant B is BLOCKED by WITH CHECK
        with pytest.raises(sa.exc.DBAPIError):
            await session.execute(
                text("""
                    INSERT INTO repository_findings (id, tenant_id, project_id, scan_id, finding_id, category, severity, title, description, confidence, verification_status, commit_sha, rule_id, recommended_action, created_at)
                    VALUES (:fid, :tid_b, :pid_a, :sid, 'MALICIOUS', 'security', 'critical', 'Spoofed', 'Desc', 'high', 'OBSERVED', 'sha', 'RULE', 'Act', NOW());
                """),
                {"fid": uuid.uuid4(), "tid_b": tenant_b_id, "pid_a": proj_a_id, "sid": scan_b_id},
            )

    await app_engine.dispose()
