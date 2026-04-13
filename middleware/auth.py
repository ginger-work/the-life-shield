"""
The Life Shield - Auth Middleware & JWT Services
JWT creation, validation, password hashing, and FastAPI dependencies.
"""

import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

import bcrypt
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from config.security import (
    settings,
    UserRole,
    has_permission,
    TOKEN_TYPE_ACCESS,
    TOKEN_TYPE_REFRESH,
    TOKEN_TYPE_EMAIL_VERIFY,
    TOKEN_TYPE_PASSWORD_RESET,
    get_access_token_expiry,
    get_refresh_token_expiry,
    get_email_verify_expiry,
    get_password_reset_expiry,
)
from database import get_db
from models.user import User, UserSession, AuditLog

logger = logging.getLogger(__name__)

# FastAPI Bearer scheme
bearer_scheme = HTTPBearer(auto_error=False)


# ─────────────────────────────────────────────
# PASSWORD HASHING
# ─────────────────────────────────────────────

def hash_password(plain_password: str) -> str:
    """Hash a password using bcrypt."""
    salt = bcrypt.gensalt(rounds=settings.BCRYPT_ROUNDS)
    hashed = bcrypt.hashpw(plain_password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its bcrypt hash."""
    return bcrypt.checkpw(
        plain_password.encode("utf-8"),
        hashed_password.encode("utf-8")
    )


# ─────────────────────────────────────────────
# JWT CREATION
# ─────────────────────────────────────────────

def _create_token(
    subject: str,
    token_type: str,
    expires_delta: timedelta,
    extra_claims: Optional[dict] = None,
) -> tuple[str, str]:
    """
    Create a signed JWT.
    Returns (encoded_token, jti).
    """
    now = datetime.now(timezone.utc)
    jti = str(uuid.uuid4())
    payload = {
        "sub": subject,
        "type": token_type,
        "jti": jti,
        "iat": now,
        "exp": now + expires_delta,
    }
    if extra_claims:
        payload.update(extra_claims)

    token = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return token, jti


def create_access_token(user_id: str, role: str) -> tuple[str, str]:
    """Create short-lived access token. Returns (token, jti)."""
    return _create_token(
        subject=user_id,
        token_type=TOKEN_TYPE_ACCESS,
        expires_delta=get_access_token_expiry(),
        extra_claims={"role": role},
    )


def create_refresh_token(user_id: str) -> tuple[str, str]:
    """Create long-lived refresh token. Returns (token, jti)."""
    return _create_token(
        subject=user_id,
        token_type=TOKEN_TYPE_REFRESH,
        expires_delta=get_refresh_token_expiry(),
    )


def create_email_verify_token(user_id: str) -> str:
    """Create one-time email verification token."""
    token, _ = _create_token(
        subject=user_id,
        token_type=TOKEN_TYPE_EMAIL_VERIFY,
        expires_delta=get_email_verify_expiry(),
    )
    return token


def create_password_reset_token(user_id: str) -> str:
    """Create one-time password reset token."""
    token, _ = _create_token(
        subject=user_id,
        token_type=TOKEN_TYPE_PASSWORD_RESET,
        expires_delta=get_password_reset_expiry(),
    )
    return token


# ─────────────────────────────────────────────
# JWT DECODING
# ─────────────────────────────────────────────

def decode_token(token: str, expected_type: str) -> dict:
    """
    Decode and validate a JWT.
    Raises HTTPException on failure.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
    except JWTError as exc:
        logger.warning(f"JWT decode error: {exc}")
        raise credentials_exception

    if payload.get("type") != expected_type:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token type. Expected {expected_type}.",
        )

    if "sub" not in payload:
        raise credentials_exception

    return payload


# ─────────────────────────────────────────────
# FASTAPI DEPENDENCIES
# ─────────────────────────────────────────────

async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    FastAPI dependency: extract + validate access token, return current User.
    Raises 401 if missing/invalid/expired.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_token(credentials.credentials, TOKEN_TYPE_ACCESS)
    user_id = payload.get("sub")

    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled")
    if user.is_locked:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is temporarily locked")

    return user


async def get_current_verified_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Require email-verified account."""
    if not current_user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email address not verified. Check your inbox.",
        )
    return current_user


def require_role(*roles: UserRole):
    """
    Dependency factory: require that the current user has one of the given roles.
    Usage: Depends(require_role(UserRole.ADMIN, UserRole.AGENT))
    """
    async def _check(current_user: User = Depends(get_current_verified_user)) -> User:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required roles: {[r.value for r in roles]}",
            )
        return current_user
    return _check


def require_permission(permission: str):
    """
    Dependency factory: require that the current user's role has a specific permission.
    Usage: Depends(require_permission("agents:write"))
    """
    async def _check(current_user: User = Depends(get_current_verified_user)) -> User:
        if not has_permission(current_user.role, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required: {permission}",
            )
        return current_user
    return _check


# ─────────────────────────────────────────────
# AUDIT LOGGING HELPER
# ─────────────────────────────────────────────

async def log_audit(
    db: AsyncSession,
    action: str,
    resource_type: str,
    resource_id: Optional[str] = None,
    user_id: Optional[uuid.UUID] = None,
    details: Optional[str] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    correlation_id: Optional[str] = None,
    success: bool = True,
    error_message: Optional[str] = None,
) -> None:
    """Write an immutable audit log entry."""
    entry = AuditLog(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details,
        ip_address=ip_address,
        user_agent=user_agent,
        correlation_id=correlation_id,
        success=success,
        error_message=error_message,
    )
    db.add(entry)
    # Note: session commit happens in get_db() dependency on request completion
