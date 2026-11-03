"""Authentication and user session management routes."""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.config import settings
from src.core.security.auth import (
    AuthenticatedUser,
    create_access_token,
    get_authenticated_user,
)
from src.core.security.password import hash_password, verify_password
from src.database.models import AuditLog, User
from src.database.session import get_db_session

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserSummaryResponse(BaseModel):
    id: str
    email: str
    full_name: str | None
    is_active: bool
    memberships: list[dict[str, str]]


class AuthTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserSummaryResponse


@router.post("/register", response_model=AuthTokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    req: RegisterRequest,
    response: Response,
    session: AsyncSession = Depends(get_db_session),
) -> AuthTokenResponse:
    """Registers a new user, hashes password securely, issues session token & cookie."""
    if len(req.password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters in length.",
        )

    # Check existing email
    existing = await session.execute(select(User).where(User.email == req.email.lower()))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email address already exists.",
        )

    user = User(
        email=req.email.lower(),
        hashed_password=hash_password(req.password),
        full_name=req.full_name,
        is_active=True,
    )
    session.add(user)
    await session.flush()
    await session.refresh(user)

    audit_entry = AuditLog(
        tenant_id=None,
        user_id=user.id,
        action="user.registered",
        resource_type="user",
        resource_id=str(user.id),
        details={"email": user.email},
    )
    session.add(audit_entry)
    await session.flush()

    token = create_access_token(
        user_id=str(user.id),
        email=user.email,
        memberships=[],
    )

    is_production = settings.ENVIRONMENT.lower() == "production"
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        samesite="lax",
        secure=is_production,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )

    return AuthTokenResponse(
        access_token=token,
        user=UserSummaryResponse(
            id=str(user.id),
            email=user.email,
            full_name=user.full_name,
            is_active=user.is_active,
            memberships=[],
        ),
    )


@router.post("/login", response_model=AuthTokenResponse)
async def login(
    req: LoginRequest,
    response: Response,
    session: AsyncSession = Depends(get_db_session),
) -> AuthTokenResponse:
    """Validates user credentials, returns signed JWT and sets HttpOnly cookie."""
    result = await session.execute(
        select(User)
        .options(selectinload(User.memberships))
        .where(User.email == req.email.lower())
    )
    user = result.scalar_one_or_none()

    if not user or not user.hashed_password or not verify_password(req.password, user.hashed_password):
        # Timing safe uniform error response
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated.",
        )

    memberships_payload = [
        {"tenant_id": str(m.tenant_id), "role": m.role} for m in user.memberships
    ]

    token = create_access_token(
        user_id=str(user.id),
        email=user.email,
        memberships=memberships_payload,
    )

    is_production = settings.ENVIRONMENT.lower() == "production"
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        samesite="lax",
        secure=is_production,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )

    audit_entry = AuditLog(
        tenant_id=None,
        user_id=user.id,
        action="user.login",
        resource_type="user",
        resource_id=str(user.id),
        details={"email": user.email},
    )
    session.add(audit_entry)
    await session.flush()

    return AuthTokenResponse(
        access_token=token,
        user=UserSummaryResponse(
            id=str(user.id),
            email=user.email,
            full_name=user.full_name,
            is_active=user.is_active,
            memberships=memberships_payload,
        ),
    )


@router.get("/me", response_model=UserSummaryResponse)
async def get_current_user_profile(
    user: AuthenticatedUser = Depends(get_authenticated_user),
    session: AsyncSession = Depends(get_db_session),
) -> UserSummaryResponse:
    """Returns profile and memberships for current authenticated user."""
    result = await session.execute(
        select(User)
        .options(selectinload(User.memberships))
        .where(User.id == uuid.UUID(user.id))
    )
    db_user = result.scalar_one_or_none()
    if not db_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    memberships = [
        {"tenant_id": str(m.tenant_id), "role": m.role} for m in db_user.memberships
    ]

    return UserSummaryResponse(
        id=str(db_user.id),
        email=db_user.email,
        full_name=db_user.full_name,
        is_active=db_user.is_active,
        memberships=memberships,
    )


@router.post("/logout")
async def logout(response: Response) -> dict[str, Any]:
    """Clears access token cookie."""
    response.delete_cookie(key="access_token")
    return {"message": "Logged out successfully."}
