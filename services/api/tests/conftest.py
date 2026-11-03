"""Pytest configuration and async test fixtures for Connects API."""

import asyncio
import os
import tempfile
import uuid
from collections.abc import AsyncGenerator, Generator

import pgserver
import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.core.security.auth import create_access_token
from src.database.models import Base, Membership, Tenant, User
from src.database.session import get_db_session
from src.main import app

# Use in-memory SQLite for instant, zero-dependency async unit tests unless Postgres URL provided
TEST_DATABASE_URL = os.getenv("CONNECTS_TEST_DATABASE_URL", "sqlite+aiosqlite:///:memory:")


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def test_engine() -> AsyncGenerator[AsyncEngine, None]:
    """Initializes schema on a shared async engine for the test session."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)

    @event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        if hasattr(dbapi_connection, "cursor"):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def db_session(test_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """Provides a fresh transactional session rolled back after every test."""
    session_factory = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest.fixture
async def setup_two_tenants(db_session: AsyncSession) -> dict[str, dict[str, str]]:
    """Seeds two isolated tenants with distinct users and memberships."""
    # Tenant A
    tenant_a = Tenant(name="Tenant Alpha", slug=f"tenant-alpha-{uuid.uuid4().hex[:6]}")
    user_a = User(email=f"user-a-{uuid.uuid4().hex[:6]}@example.com")
    db_session.add_all([tenant_a, user_a])
    await db_session.flush()

    mem_a = Membership(tenant_id=tenant_a.id, user_id=user_a.id, role="owner")
    db_session.add(mem_a)

    # Tenant B
    tenant_b = Tenant(name="Tenant Beta", slug=f"tenant-beta-{uuid.uuid4().hex[:6]}")
    user_b = User(email=f"user-b-{uuid.uuid4().hex[:6]}@example.com")
    db_session.add_all([tenant_b, user_b])
    await db_session.flush()

    mem_b = Membership(tenant_id=tenant_b.id, user_id=user_b.id, role="owner")
    db_session.add(mem_b)
    await db_session.commit()

    token_a = create_access_token(
        user_id=str(user_a.id),
        email=user_a.email,
        memberships=[{"tenant_id": str(tenant_a.id), "role": "owner"}],
    )
    token_b = create_access_token(
        user_id=str(user_b.id),
        email=user_b.email,
        memberships=[{"tenant_id": str(tenant_b.id), "role": "owner"}],
    )

    return {
        "tenant_a": {
            "tenant_id": str(tenant_a.id),
            "user_id": str(user_a.id),
            "email": user_a.email,
            "token": token_a,
        },
        "tenant_b": {
            "tenant_id": str(tenant_b.id),
            "user_id": str(user_b.id),
            "email": user_b.email,
            "token": token_b,
        },
    }


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """HTTP client with overridden database session."""

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db_session] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture(scope="session")
def postgres_service():
    """Starts an ephemeral real PostgreSQL 16 server with Alembic schema migrated to head."""
    tmp_pgdata = tempfile.mkdtemp()
    server = pgserver.get_server(tmp_pgdata)
    uri = server.get_uri()
    base_url = uri.rsplit("/", 1)[0]
    test_db_url = f"{base_url}/connects_pg_test"

    # Create dedicated test database and application role
    sync_engine = sa.create_engine(uri)
    with sync_engine.connect() as conn:
        conn.execution_options(isolation_level="AUTOCOMMIT")
        conn.execute(text("CREATE DATABASE connects_pg_test;"))
        conn.execute(text("""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'connects_app') THEN
                    CREATE ROLE connects_app WITH LOGIN PASSWORD 'connects_dev_password' NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
                END IF;
            END
            $$;
        """))
        conn.execute(text("GRANT ALL ON DATABASE connects_pg_test TO connects_app;"))
    sync_engine.dispose()

    # Apply Alembic upgrade head on connects_pg_test
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", test_db_url)
    command.upgrade(alembic_cfg, "head")

    # Grant schema permissions in connects_pg_test
    db_admin_engine = sa.create_engine(test_db_url)
    with db_admin_engine.connect() as conn:
        conn.execution_options(isolation_level="AUTOCOMMIT")
        conn.execute(text("GRANT ALL ON SCHEMA public TO connects_app;"))
        conn.execute(text("GRANT ALL ON ALL TABLES IN SCHEMA public TO connects_app;"))
        conn.execute(text("GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO connects_app;"))
        conn.execute(text("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO connects_app;"))
    db_admin_engine.dispose()

    app_user_url = test_db_url.replace("postgres:@", "connects_app:connects_dev_password@")
    app_async_url = app_user_url.replace("postgresql://", "postgresql+asyncpg://")

    yield {
        "admin_sync_url": test_db_url,
        "app_sync_url": app_user_url,
        "app_async_url": app_async_url,
    }

    server.cleanup()

