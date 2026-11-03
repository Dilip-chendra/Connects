"""Authentication, JWT token lifecycle, and Tenant Context extraction."""

from contextvars import ContextVar
from datetime import UTC, datetime, timedelta
from typing import Any, Optional

import jwt
from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from src.core.config import settings

# Global async-local context variable for tenant context
current_tenant_context: ContextVar[Optional["TenantContext"]] = ContextVar(
    "current_tenant_context", default=None
)

security_scheme = HTTPBearer(auto_error=False)


class AuthenticatedUser(BaseModel):
    id: str
    email: str
    is_active: bool = True
    memberships: list[dict[str, str]] = []  # List of {"tenant_id": ..., "role": ...}


class TenantContext(BaseModel):
    tenant_id: str
    user_id: str
    role: str

    def can_mutate(self) -> bool:
        return self.role in ("owner", "admin", "member")

    def can_admin(self) -> bool:
        return self.role in ("owner", "admin")


JWT_ISSUER = "connects-auth"
JWT_AUDIENCE = "connects-api"


def create_access_token(
    user_id: str,
    email: str,
    memberships: list[dict[str, str]],
    expires_delta: timedelta | None = None,
) -> str:
    """Creates a signed JWT access token containing user identity and tenant memberships."""
    expire = datetime.now(UTC) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode: dict[str, Any] = {
        "sub": user_id,
        "email": email,
        "memberships": memberships,
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
        "exp": expire,
        "iat": datetime.now(UTC),
    }
    encoded = jwt.encode(
        to_encode,
        settings.JWT_SECRET_KEY.get_secret_value(),
        algorithm=settings.JWT_ALGORITHM,
    )
    return encoded


def decode_access_token(token: str) -> dict[str, Any]:
    """Decodes and validates JWT signature, algorithm, issuer, audience, and expiration."""
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY.get_secret_value(),
            algorithms=[settings.JWT_ALGORITHM],
            issuer=JWT_ISSUER,
            audience=JWT_AUDIENCE,
        )
        return payload
    except jwt.ExpiredSignatureError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token has expired.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e
    except jwt.PyJWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e


async def get_authenticated_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security_scheme),
) -> AuthenticatedUser:
    """FastAPI dependency to extract and validate the authenticated user from Bearer header or HttpOnly cookie."""
    token: str | None = None
    if credentials and credentials.credentials:
        token = credentials.credentials
    elif "access_token" in request.cookies:
        token = request.cookies.get("access_token")

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_access_token(token)
    user_id = payload.get("sub")
    email = payload.get("email")
    if not user_id or not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed token claims.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return AuthenticatedUser(
        id=user_id,
        email=email,
        is_active=True,
        memberships=payload.get("memberships", []),
    )


async def get_tenant_context(
    request: Request,
    user: AuthenticatedUser = Depends(get_authenticated_user),
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-ID"),
) -> TenantContext:
    """FastAPI dependency deriving active TenantContext with strict membership verification.

    Target tenant is resolved from path or header, but ACCESS IS ONLY GRANTED
    if the authenticated user's token contains a verified membership in that tenant.
    Never relies on the request header alone.
    """
    target_tenant_id = request.path_params.get("tenant_id") or x_tenant_id
    if not target_tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant ID must be specified in path or X-Tenant-ID header.",
        )

    # Deny-by-default: Verify user is a confirmed member of the target tenant
    matched_role: str | None = None
    for membership in user.memberships:
        if membership.get("tenant_id") == target_tenant_id:
            matched_role = membership.get("role", "viewer")
            break

    if not matched_role:
        # Do not disclose tenant existence: return uniform 403 Forbidden
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access to the specified tenant is denied.",
        )

    ctx = TenantContext(
        tenant_id=target_tenant_id,
        user_id=user.id,
        role=matched_role,
    )
    current_tenant_context.set(ctx)
    return ctx
