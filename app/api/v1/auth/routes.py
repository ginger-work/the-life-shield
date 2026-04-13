"""
Auth API Router — JWT authentication for The Life Shield.

Endpoints:
  POST /api/v1/auth/register     - Register new user (client)
  POST /api/v1/auth/login        - Login, receive JWT
  POST /api/v1/auth/refresh      - Refresh access token
  POST /api/v1/auth/logout       - Revoke refresh token
  GET  /api/v1/auth/me           - Current user info
  POST /api/v1/auth/forgot-password  - Request password reset
  POST /api/v1/auth/reset-password   - Reset with token
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.user import User, UserRole, UserStatus

log = structlog.get_logger(__name__)
router = APIRouter()
bearer_scheme = HTTPBearer(auto_error=False)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    first_name: str
    last_name: str
    phone: Optional[str] = None
    sms_consent: bool = False
    email_consent: bool = False

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < settings.MIN_PASSWORD_LENGTH:
            raise ValueError(f"Password must be at least {settings.MIN_PASSWORD_LENGTH} characters")
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user_id: str
    role: str


class RefreshRequest(BaseModel):
    refresh_token: str


class UserResponse(BaseModel):
    id: str
    email: str
    first_name: str
    last_name: str
    role: str
    status: str
    sms_consent: bool
    email_consent: bool
    created_at: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < settings.MIN_PASSWORD_LENGTH:
            raise ValueError(f"Password must be at least {settings.MIN_PASSWORD_LENGTH} characters")
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


# ---------------------------------------------------------------------------
# Dependency: current user
# ---------------------------------------------------------------------------

async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Extract and validate JWT, return authenticated User."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = decode_token(credentials.credentials, expected_type="access")
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = db.query(User).filter(User.id == uuid.UUID(user_id)).first()
    if not user or user.status != UserStatus.ACTIVE:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")
    return user


async def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Require admin or staff role."""
    if current_user.role not in (UserRole.ADMIN, UserRole.STAFF):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current_user


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, db: Session = Depends(get_db)):
    """Register a new client account."""
    existing = db.query(User).filter(User.email == body.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    now = datetime.now(timezone.utc)
    user = User(
        id=uuid.uuid4(),
        email=body.email,
        hashed_password=hash_password(body.password),
        first_name=body.first_name,
        last_name=body.last_name,
        phone=body.phone,
        role=UserRole.CLIENT,
        status=UserStatus.ACTIVE,
        sms_consent=body.sms_consent,
        sms_consent_at=now if body.sms_consent else None,
        email_consent=body.email_consent,
        email_consent_at=now if body.email_consent else None,
    )
    db.add(user)
    db.flush()

    user_id_str = str(user.id)
    access_token = create_access_token(subject=user_id_str, extra_claims={"role": user.role})
    refresh_token, _ = create_refresh_token(subject=user_id_str)

    log.info("user_registered", user_id=user_id_str, email=body.email)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user_id=user_id_str,
        role=user.role,
    )


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, request: Request, db: Session = Depends(get_db)):
    """Authenticate and receive JWT tokens."""
    user = db.query(User).filter(User.email == body.email).first()

    if not user or not verify_password(body.password, user.hashed_password):
        log.warning("login_failed", email=body.email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if user.status != UserStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive or suspended",
        )

    # Update last login
    user.last_login_at = datetime.now(timezone.utc)
    user.last_login_ip = request.client.host if request.client else None

    user_id_str = str(user.id)
    access_token = create_access_token(subject=user_id_str, extra_claims={"role": user.role})
    refresh_token, _ = create_refresh_token(subject=user_id_str)

    log.info("user_login", user_id=user_id_str)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user_id=user_id_str,
        role=user.role,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(body: RefreshRequest, db: Session = Depends(get_db)):
    """Exchange a refresh token for a new access token."""
    try:
        payload = decode_token(body.refresh_token, expected_type="refresh")
        user_id = payload.get("sub")
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    user = db.query(User).filter(User.id == uuid.UUID(user_id)).first()
    if not user or user.status != UserStatus.ACTIVE:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    user_id_str = str(user.id)
    access_token = create_access_token(subject=user_id_str, extra_claims={"role": user.role})
    new_refresh, _ = create_refresh_token(subject=user_id_str)

    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh,
        expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user_id=user_id_str,
        role=user.role,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(current_user: User = Depends(get_current_user)):
    """Logout — token revocation handled client-side and via Redis in production."""
    log.info("user_logout", user_id=str(current_user.id))
    return None


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """Get current authenticated user profile."""
    return UserResponse(
        id=str(current_user.id),
        email=current_user.email,
        first_name=current_user.first_name,
        last_name=current_user.last_name,
        role=current_user.role,
        status=current_user.status,
        sms_consent=getattr(current_user, "sms_consent", False),
        email_consent=getattr(current_user, "email_consent", False),
        created_at=current_user.created_at.isoformat(),
    )


@router.post("/forgot-password", status_code=status.HTTP_200_OK)
async def forgot_password(body: ForgotPasswordRequest, db: Session = Depends(get_db)):
    """Send password reset email (always returns 200 to prevent enumeration)."""
    user = db.query(User).filter(User.email == body.email).first()
    if user:
        from app.core.security import create_password_reset_token
        token = create_password_reset_token(body.email)
        log.info("password_reset_requested", email=body.email, token_preview=token[:10])
        # TODO: Send email via SendGrid
    return {"message": "If that email exists, a reset link has been sent"}


@router.post("/reset-password", status_code=status.HTTP_200_OK)
async def reset_password(body: ResetPasswordRequest, db: Session = Depends(get_db)):
    """Reset password using a valid token."""
    try:
        from app.core.security import decode_token as _decode
        payload = _decode(body.token, expected_type="password_reset")
        email = payload.get("sub")
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired token")

    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user.hashed_password = hash_password(body.new_password)
    user.password_changed_at = datetime.now(timezone.utc)
    log.info("password_reset_complete", user_id=str(user.id))

    return {"message": "Password reset successfully"}
