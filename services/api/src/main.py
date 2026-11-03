"""FastAPI application entrypoint for Connects Platform API."""

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.api.routes import (
    auth,
    context,
    github,
    health,
    plans,
    projects,
    tenants,
    workflows,
    workspaces,
)
from src.core.config import settings
from src.core.logging import logger

app = FastAPI(
    title=settings.APP_NAME,
    description="Connects — AI-Powered Startup Operating System & Orchestration Platform",
    version="0.1.0",
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Uniform error handlers
@app.exception_handler(HTTPException)
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(
    request: Request, exc: HTTPException | StarletteHTTPException
) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": f"HTTP_{exc.status_code}",
                "message": exc.detail,
            }
        },
        headers=getattr(exc, "headers", None) or {},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error(f"Unhandled exception during request {request.method} {request.url.path}: {exc!s}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "An internal error occurred. Please contact support.",
            }
        },
    )


# Mount routers
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(workspaces.router)
app.include_router(tenants.router)

# Mount projects under both /workspaces/{tenant_id}/projects and /tenants/{tenant_id}/projects
app.include_router(projects.router, prefix="/workspaces/{tenant_id}/projects")
app.include_router(projects.router, prefix="/tenants/{tenant_id}/projects")

# Mount context under both /workspaces and /tenants
app.include_router(context.router, prefix="/workspaces/{tenant_id}/projects/{project_id}/context")
app.include_router(context.router, prefix="/tenants/{tenant_id}/projects/{project_id}/context")

# Mount plans under both /workspaces and /tenants
app.include_router(plans.router, prefix="/workspaces/{tenant_id}/projects/{project_id}/plans")
app.include_router(plans.router, prefix="/tenants/{tenant_id}/projects/{project_id}/plans")

# Mount workflows under both /workspaces and /tenants
app.include_router(workflows.router, prefix="/workspaces/{tenant_id}")
app.include_router(workflows.router, prefix="/tenants/{tenant_id}")

# Mount github under both /workspaces and /tenants
app.include_router(github.router, prefix="/workspaces/{tenant_id}/github")
app.include_router(github.router, prefix="/tenants/{tenant_id}/github")


@app.get("/")
async def root_status() -> dict:
    return {
        "app": settings.APP_NAME,
        "version": "0.1.0",
        "tagline": "One Goal. Connected Tools. Real Outcomes.",
    }
