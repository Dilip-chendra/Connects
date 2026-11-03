"""Database session management with transaction-local tenant isolation."""

from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.core.config import settings
from src.core.security.auth import current_tenant_context

engine: AsyncEngine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    future=True,
    pool_pre_ping=True,
)

async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provides a scoped async database session.

    If an active tenant context exists and the dialect is PostgreSQL,
    sets transaction-local setting 'app.current_tenant_id' to enforce RLS.
    """
    async with async_session_factory() as session:
        try:
            tenant_ctx = current_tenant_context.get()
            if tenant_ctx and session.bind and session.bind.dialect.name == "postgresql":
                # set_config with is_local=true ensures setting is strictly scoped to active transaction
                # and automatically cleared when connection returns to the pool.
                await session.execute(
                    text("SELECT set_config('app.current_tenant_id', :tenant_id, true)"),
                    {"tenant_id": str(tenant_ctx.tenant_id)},
                )
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
