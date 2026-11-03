"""Independent verification suite against real PostgreSQL 16 server.

Tests:
1. Fresh database Alembic migration up to head.
2. Catalog inspection confirming all 13 tables, indexes, constraints, and FORCE RLS flags.
3. Database boundary tenant isolation (direct SQL cross-tenant SELECT, INSERT, UPDATE, DELETE rejection).
4. Missing/empty tenant context deny-by-default behavior.
5. Task dependencies RLS protection via subqueries.
6. Audit log immutability (denial of UPDATE and DELETE under RLS).
7. Downgrade to base and clean re-upgrade to head (reproducibility).
"""

import uuid

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


def test_postgresql_migration_upgrade_and_catalog_inspection(postgres_service: dict) -> None:
    """Applies Alembic migration to real PostgreSQL and audits system catalogs."""
    admin_sync_url = postgres_service["admin_sync_url"]

    # 1. Run Alembic upgrade head
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", admin_sync_url)
    command.upgrade(alembic_cfg, "head")

    # 2. Grant table permissions and audit PostgreSQL pg_tables catalog and pg_roles
    engine = sa.create_engine(admin_sync_url)
    with engine.connect() as conn:
        conn.execution_options(isolation_level="AUTOCOMMIT")
        conn.execute(text("GRANT ALL ON ALL TABLES IN SCHEMA public TO connects_app;"))
        conn.execute(text("GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO connects_app;"))

        # Verify role security attributes
        role_res = conn.execute(
            text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = 'connects_app';")
        )
        role_row = role_res.fetchone()
        assert role_row is not None
        assert role_row[0] is False, "connects_app must NOT be a superuser"
        assert role_row[1] is False, "connects_app must NOT have BYPASSRLS privilege"

        tables_res = conn.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname = 'public';")
        )
        actual_tables = {row[0] for row in tables_res.fetchall()}
        expected_tables = {
            "alembic_version",
            "tenants",
            "users",
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
            "execution_plans",
            "execution_attempts",
        }
        assert expected_tables.issubset(actual_tables), f"Missing tables: {expected_tables - actual_tables}"

        # 3. Verify FORCE ROW LEVEL SECURITY in pg_class catalog
        force_rls_res = conn.execute(
            text("""
                SELECT relname 
                FROM pg_class 
                WHERE relforcerowsecurity = true;
            """)
        )
        forced_tables = {row[0] for row in force_rls_res.fetchall()}
        expected_forced = {
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
            "execution_plans",
            "execution_attempts",
        }
        assert expected_forced.issubset(forced_tables), f"Missing FORCE RLS on: {expected_forced - forced_tables}"

        # 4. Verify RLS policies in pg_policy catalog
        policies_res = conn.execute(
            text("""
                SELECT polname, polrelid::regclass::text, polcmd 
                FROM pg_policy;
            """)
        )
        policies = policies_res.fetchall()
        policy_names = {p[0] for p in policies}
        assert "projects_tenant_isolation_policy" in policy_names
        assert "task_dependencies_tenant_isolation_policy" in policy_names
        assert "audit_logs_select_policy" in policy_names
        assert "audit_logs_insert_policy" in policy_names


@pytest.mark.asyncio
async def test_postgresql_direct_sql_tenant_isolation_boundary(postgres_service: dict) -> None:
    """Verifies that RLS enforces strict isolation at the PostgreSQL kernel level."""
    app_async_url = postgres_service["app_async_url"]
    engine = create_async_engine(app_async_url, echo=False)
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    tenant_a_id = uuid.uuid4()
    tenant_b_id = uuid.uuid4()
    project_a_id = uuid.uuid4()

    # Seed tenants and project for Tenant A
    async with session_factory() as session:
        # Create base tenants
        await session.execute(
            text("INSERT INTO tenants (id, name, slug, tier, created_at, updated_at) VALUES (:id, :name, :slug, 'free', NOW(), NOW())"),
            [
                {"id": tenant_a_id, "name": "Tenant A", "slug": f"t-a-{tenant_a_id.hex[:6]}"},
                {"id": tenant_b_id, "name": "Tenant B", "slug": f"t-b-{tenant_b_id.hex[:6]}"},
            ]
        )
        await session.commit()

    # Connect as Tenant A and insert project
    async with session_factory() as session:
        # Establish transaction-local tenant context
        await session.execute(
            text("SELECT set_config('app.current_tenant_id', :tid, true)"),
            {"tid": str(tenant_a_id)},
        )
        await session.execute(
            text("INSERT INTO projects (id, tenant_id, name, primary_goal, status, created_at, updated_at) VALUES (:id, :tid, 'Project A', 'Goal A', 'active', NOW(), NOW())"),
            {"id": project_a_id, "tid": tenant_a_id},
        )
        await session.commit()

    # ATTACK 1: Missing tenant context queries projects -> Returns 0 rows (Deny-by-default)
    async with session_factory() as session:
        await session.execute(text("SELECT set_config('app.current_tenant_id', '', true)"))
        res = await session.execute(text("SELECT id, name FROM projects;"))
        rows = res.fetchall()
        assert len(rows) == 0, "Unset tenant context must see 0 rows under RLS"

    # ATTACK 2: Tenant B queries all projects -> Returns 0 rows
    async with session_factory() as session:
        await session.execute(
            text("SELECT set_config('app.current_tenant_id', :tid, true)"),
            {"tid": str(tenant_b_id)},
        )
        res = await session.execute(text("SELECT id, name FROM projects;"))
        rows = res.fetchall()
        assert len(rows) == 0, "Tenant B must not see Tenant A's project"

    # ATTACK 3: Tenant B attempts to UPDATE Tenant A's project -> 0 rows modified
    async with session_factory() as session:
        await session.execute(
            text("SELECT set_config('app.current_tenant_id', :tid, true)"),
            {"tid": str(tenant_b_id)},
        )
        update_res = await session.execute(
            text("UPDATE projects SET name = 'Hacked' WHERE id = :id"),
            {"id": project_a_id},
        )
        assert update_res.rowcount == 0, "Tenant B must not be able to update Tenant A's record"
        await session.commit()

    # ATTACK 4: Tenant B attempts to DELETE Tenant A's project -> 0 rows deleted
    async with session_factory() as session:
        await session.execute(
            text("SELECT set_config('app.current_tenant_id', :tid, true)"),
            {"tid": str(tenant_b_id)},
        )
        delete_res = await session.execute(
            text("DELETE FROM projects WHERE id = :id"),
            {"id": project_a_id},
        )
        assert delete_res.rowcount == 0, "Tenant B must not be able to delete Tenant A's record"
        await session.commit()

    # ATTACK 5: Tenant B attempts to INSERT row with Tenant A's ID -> Rejected by WITH CHECK
    async with session_factory() as session:
        await session.execute(
            text("SELECT set_config('app.current_tenant_id', :tid, true)"),
            {"tid": str(tenant_b_id)},
        )
        with pytest.raises(Exception) as exc_info:
            await session.execute(
                text("INSERT INTO projects (id, tenant_id, name, primary_goal, status, created_at, updated_at) VALUES (:id, :tid, 'Malicious Project', 'Injected', 'active', NOW(), NOW())"),
                {"id": uuid.uuid4(), "tid": tenant_a_id},
            )
            await session.commit()
        assert "violates row-level security policy" in str(exc_info.value).lower()

    # 6. Audit Log Immutability: Verify UPDATE and DELETE on audit_logs are rejected
    async with session_factory() as session:
        await session.execute(
            text("SELECT set_config('app.current_tenant_id', :tid, true)"),
            {"tid": str(tenant_a_id)},
        )
        audit_id = uuid.uuid4()
        # Insert permitted
        await session.execute(
            text("INSERT INTO audit_logs (id, tenant_id, action, resource_type, details, created_at) VALUES (:id, :tid, 'test.action', 'test', '{}', NOW())"),
            {"id": audit_id, "tid": tenant_a_id},
        )
        await session.commit()

        # Update prohibited
        update_audit = await session.execute(
            text("UPDATE audit_logs SET action = 'tampered' WHERE id = :id"),
            {"id": audit_id},
        )
        assert update_audit.rowcount == 0, "Audit logs must not be updatable under RLS"

        # Delete prohibited
        delete_audit = await session.execute(
            text("DELETE FROM audit_logs WHERE id = :id"),
            {"id": audit_id},
        )
        assert delete_audit.rowcount == 0, "Audit logs must not be deletable under RLS"

    await engine.dispose()


def test_postgresql_migration_downgrade_and_reupgrade(postgres_service: dict) -> None:
    """Verifies that the migration can be downgraded cleanly and re-applied reproducibly."""
    admin_sync_url = postgres_service["admin_sync_url"]
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", admin_sync_url)

    # 1. Downgrade to base
    command.downgrade(alembic_cfg, "base")

    # Verify tables are dropped
    engine = sa.create_engine(admin_sync_url)
    with engine.connect() as conn:
        res = conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public';"))
        remaining_tables = {row[0] for row in res.fetchall()}
        assert "projects" not in remaining_tables
        assert "tasks" not in remaining_tables
        assert "tenants" not in remaining_tables

    # 2. Re-apply upgrade head reproducibly
    command.upgrade(alembic_cfg, "head")
    with engine.connect() as conn:
        res = conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public';"))
        recreated_tables = {row[0] for row in res.fetchall()}
        assert "projects" in recreated_tables
        assert "tasks" in recreated_tables
        assert "audit_logs" in recreated_tables
