import hashlib
import logging
from datetime import datetime, timezone
from typing import Optional

from core.auth import AccessTokenError, decode_access_token
from core.database import get_db
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from models.auth import User
from models.user_profiles import User_profiles
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from schemas.auth import UserResponse

logger = logging.getLogger(__name__)

bearer_scheme = HTTPBearer(auto_error=False)


async def get_bearer_token(
    request: Request, credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme)
) -> str:
    """Extract bearer token from Authorization header."""
    if credentials and credentials.scheme.lower() == "bearer":
        return credentials.credentials

    logger.debug("Authentication required for request %s %s", request.method, request.url.path)
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication credentials were not provided")


async def get_current_user(
    token: str = Depends(get_bearer_token),
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """Dependency to get current authenticated user via JWT token."""
    try:
        payload = decode_access_token(token)
    except AccessTokenError as exc:
        # Log error type only, not the full exception which may contain sensitive token data
        logger.warning("Token validation failed: %s", type(exc).__name__)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=exc.message)

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication token")

    last_login_raw = payload.get("last_login")
    last_login = None
    if isinstance(last_login_raw, str):
        try:
            last_login = datetime.fromisoformat(last_login_raw)
        except ValueError:
            # Log user hash instead of actual user ID to avoid exposing sensitive information
            user_hash = hashlib.sha256(str(user_id).encode()).hexdigest()[:8] if user_id else "unknown"
            logger.debug("Failed to parse last_login for user hash: %s", user_hash)

    user = UserResponse(
        id=user_id,
        email=payload.get("email", ""),
        name=payload.get("name"),
        role=payload.get("role", "user"),
        last_login=last_login,
    )

    db_user_result = await db.execute(select(User).where(User.id == user_id))
    db_user = db_user_result.scalar_one_or_none()
    if db_user:
        user.auth_provider = db_user.auth_provider or "email"
        user.has_password = bool(db_user.password_hash)

    profile_result = await db.execute(select(User_profiles).where(User_profiles.user_id == user_id))
    profile = profile_result.scalar_one_or_none()
    if profile:
        profile_status = (profile.account_status or "active").lower()
        if profile_status == "banned":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This account has been banned")
        if profile_status == "suspended":
            suspended_until = profile.suspended_until
            if suspended_until is None or suspended_until > datetime.now(timezone.utc):
                reason = profile.suspension_reason or "This account is currently suspended"
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=reason)
        if profile.role:
            user.role = profile.role

    return user


async def get_optional_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> Optional[UserResponse]:
    """Return the authenticated user when present, otherwise allow public reads."""
    if not credentials or credentials.scheme.lower() != "bearer":
        return None
    try:
        payload = decode_access_token(credentials.credentials)
    except AccessTokenError:
        return None

    user_id = payload.get("sub")
    if not user_id:
        return None
    user = UserResponse(
        id=user_id,
        email=payload.get("email", ""),
        name=payload.get("name"),
        role=payload.get("role", "user"),
    )
    profile_result = await db.execute(select(User_profiles).where(User_profiles.user_id == user_id))
    profile = profile_result.scalar_one_or_none()
    if profile and profile.role:
        user.role = profile.role
    return user


async def get_admin_user(current_user: UserResponse = Depends(get_current_user)) -> UserResponse:
    """Dependency to ensure current user has admin role."""
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current_user


async def get_management_user(current_user: UserResponse = Depends(get_current_user)) -> UserResponse:
    """Dependency to ensure current user can access the management hub."""
    if current_user.role not in {"admin", "content_manager"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Management access required")
    return current_user
