"""Health and readiness probes."""

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.session import get_db_session

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live", status_code=status.HTTP_200_OK)
async def liveness_probe() -> dict:
    """Basic liveness check indicating API process is running."""
    return {"status": "alive"}


@router.get("/ready", status_code=status.HTTP_200_OK)
async def readiness_probe(session: AsyncSession = Depends(get_db_session)) -> JSONResponse:
    """Readiness probe verifying database connectivity without exposing connection secrets."""
    db_healthy = False
    try:
        result = await session.execute(text("SELECT 1"))
        db_healthy = result.scalar() == 1
    except (SQLAlchemyError, OSError):
        db_healthy = False

    if db_healthy:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"status": "ready", "database": "connected"},
        )
    else:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "degraded", "database": "unavailable"},
        )
