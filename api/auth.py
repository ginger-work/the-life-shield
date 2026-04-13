"""
The Life Shield - Authentication Routes
POST /auth/signup
POST /auth/login
POST /auth/refresh
GET  /auth/me
POST /auth/logout
POST /auth/verify-email
POST /auth/password-reset
POST /auth/password-reset/confirm
"""

import uuid
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from config.security import settings, UserRole, TOKEN_TYPE_REFRESH
from database import get_db
from middleware.auth import (
    hash_password, verify_password,
    create_access_token, create_refresh_token,
    create_email_verify_token, create_password_reset_token,
    decode_token, get_current_verified_user,
    get_access_token_expiry, log_audit,
)
from models.user import User, UserSession, AuditLog
from schemas.auth import (
    SignupRequest, SignupResponse,
    LoginRequest, TokenResponse,
    RefreshRequest, MeResponse,
    LogoutRequest,
    EmailVerifyRequest,
    PasswordResetRequest, PasswordResetConfirmRequest,
)
from schemas.common import SuccessResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def _send_verification_email(user: User, token: str) -> None:
    """
    Background task: send email verification link.
    In production, swap this stub for your email provider (SendGrid, SES, etc.).
    """
    verify_url = f"{settings.FRONTEND_URL}/verify-email?token={token}"
    logger.info(
        f"[EMAIL] Verification link for {user.email}: {verify_url}"
    )
    # TODO: integrate email provider
    # await email_client.send(to=user.email, subject="Verify your email", ...)


async def _send_password_reset_email(user: User, token: str) -> None:
    """Background task: send password reset link."""
    reset_url = f"{settings.FRONTEND_URL}/password-reset?token={token}"
    logger.info(
        f"[EMAIL] Password reset link for {user.email}: {reset_url}"
    )
    # TODO: integrate email provider


def _build_token_response(user: User, access_token: str, refresh_token: str) -> TokenResponse:
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=int(get_access_token_expiry().total_seconds()),
        user_id=user.id,
        role=user.role,
    )


# ─────────────────────────────────────────────
# POST /auth/signup
# ─────────────────────────────────────────────

@router.post(
    "/signup",
    response_model=SignupResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Client registration",
    description=(
        "Register a new client account. Requires acceptance of terms, service disclosure, "
        "and CROA rights acknowledgment. Sends email verification."
    ),
)
async def signup(
    payload: SignupRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> SignupResponse:
    ip = _get_client_ip(request)

    # 1. Check email uniqueness
    existing = await db.execute(select(User).where(User.email == payload.email.lower()))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    # 2. Create user
    now = datetime.now(timezone.utc)
    user = User(
        email=payload.email.lower(),
        hashed_password=hash_password(payload.password),
        first_name=payload.first_name.strip(),
        last_name=payload.last_name.strip(),
        phone=payload.phone,
        role=UserRole.CLIENT,
        is_active=True,
        is_verified=False,
        # Consent — FCC compliance: only store if True
        sms_consent=payload.sms_consent,
        sms_consent_at=now if payload.sms_consent else None,
        email_consent=payload.email_consent,
        email_consent_at=now if payload.email_consent else None,
        voice_consent=payload.voice_consent,
        voice_consent_at=now if payload.voice_consent else None,
    )
    db.add(user)
    await db.flush()  # Get user.id without committing

    # 3. Create email verification token
    verify_token = create_email_verify_token(str(user.id))

    # 4. Audit log (CROA — record consent + disclosure acceptance)
    await log_audit(
        db=db,
        action="user.signup",
        resource_type="user",
        resource_id=str(user.id),
        user_id=user.id,
        details=(
            f'{{"terms_accepted": true, "service_disclosure_accepted": true, '
            f'"croa_disclosure_accepted": true, "sms_consent": {str(payload.sms_consent).lower()}, '
            f'"email_consent": {str(payload.email_consent).lower()}, '
            f'"voice_consent": {str(payload.voice_consent).lower()}}}'
        ),
        ip_address=ip,
        user_agent=request.headers.get("User-Agent"),
        success=True,
    )

    # 5. Send verification email (non-blocking)
    background_tasks.add_task(_send_verification_email, user, verify_token)

    logger.info(f"New client signup: {user.email} ({user.id})")

    return SignupResponse(
        user_id=user.id,
        email=user.email,
        requires_verification=True,
    )


# ─────────────────────────────────────────────
# POST /auth/login
# ─────────────────────────────────────────────

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="User login",
    description="Authenticate with email and password. Returns JWT access + refresh tokens.",
)
async def login(
    payload: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    ip = _get_client_ip(request)
    user_agent = request.headers.get("User-Agent", "")

    # 1. Look up user
    result = await db.execute(select(User).where(User.email == payload.email.lower()))
    user = result.scalar_one_or_none()

    # 2. Unified "invalid credentials" check (prevent user enumeration)
    if user is None or not verify_password(payload.password, user.hashed_password):
        if user is not None:
            # Track failed attempts
            user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
            if user.failed_login_attempts >= MAX_FAILED_ATTEMPTS:
                from datetime import timedelta
                user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=LOCKOUT_MINUTES)
                logger.warning(f"Account locked: {user.email} after {MAX_FAILED_ATTEMPTS} failed attempts")
            await log_audit(
                db=db, action="auth.login.failed", resource_type="user",
                resource_id=str(user.id), user_id=user.id,
                ip_address=ip, user_agent=user_agent, success=False,
                error_message="Invalid password",
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    # 3. Check account status
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled.")
    if user.is_locked:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Account is temporarily locked. Try again later.",
        )

    # 4. Reset failed attempts on success
    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = datetime.now(timezone.utc)
    user.last_login_ip = ip

    # 5. Create tokens
    access_token, _ = create_access_token(str(user.id), user.role.value)
    refresh_token, refresh_jti = create_refresh_token(str(user.id))

    # 6. Persist refresh session
    from datetime import timedelta
    session = UserSession(
        user_id=user.id,
        jti=refresh_jti,
        device_type=payload.device_type,
        device_name=payload.device_name,
        ip_address=ip,
        user_agent=user_agent,
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )
    db.add(session)

    # 7. Audit
    await log_audit(
        db=db, action="auth.login", resource_type="user",
        resource_id=str(user.id), user_id=user.id,
        ip_address=ip, user_agent=user_agent, success=True,
    )

    logger.info(f"Login: {user.email} ({user.id}) from {ip}")
    return _build_token_response(user, access_token, refresh_token)


# ─────────────────────────────────────────────
# POST /auth/refresh
# ─────────────────────────────────────────────

@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Refresh access token",
    description="Exchange a valid refresh token for a new access + refresh token pair.",
)
async def refresh_token(
    payload: RefreshRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    ip = _get_client_ip(request)

    # 1. Decode refresh token
    token_data = decode_token(payload.refresh_token, TOKEN_TYPE_REFRESH)
    user_id = token_data["sub"]
    jti = token_data["jti"]

    # 2. Look up the session in DB (ensures not revoked)
    result = await db.execute(
        select(UserSession).where(
            UserSession.jti == jti,
            UserSession.revoked_at.is_(None),
        )
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has been revoked or is invalid.",
        )

    # 3. Look up user
    user_result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = user_result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    # 4. Rotate tokens — revoke old session, issue new pair
    session.revoked_at = datetime.now(timezone.utc)

    new_access_token, _ = create_access_token(str(user.id), user.role.value)
    new_refresh_token, new_refresh_jti = create_refresh_token(str(user.id))

    from datetime import timedelta
    new_session = UserSession(
        user_id=user.id,
        jti=new_refresh_jti,
        device_type=session.device_type,
        device_name=session.device_name,
        ip_address=ip,
        user_agent=request.headers.get("User-Agent", ""),
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )
    db.add(new_session)

    await log_audit(
        db=db, action="auth.token.refreshed", resource_type="user",
        resource_id=str(user.id), user_id=user.id,
        ip_address=ip, success=True,
    )

    return _build_token_response(user, new_access_token, new_refresh_token)


# ─────────────────────────────────────────────
# GET /auth/me
# ─────────────────────────────────────────────

@router.get(
    "/me",
    response_model=MeResponse,
    summary="Current user profile",
    description="Returns the authenticated user's profile.",
)
async def get_me(
    current_user: User = Depends(get_current_verified_user),
) -> MeResponse:
    return MeResponse(
        id=current_user.id,
        email=current_user.email,
        first_name=current_user.first_name,
        last_name=current_user.last_name,
        full_name=current_user.full_name,
        role=current_user.role,
        phone=current_user.phone,
        is_verified=current_user.is_verified,
        is_active=current_user.is_active,
        sms_consent=current_user.sms_consent,
        email_consent=current_user.email_consent,
        voice_consent=current_user.voice_consent,
        last_login_at=current_user.last_login_at,
        created_at=current_user.created_at,
    )


# ─────────────────────────────────────────────
# POST /auth/logout
# ─────────────────────────────────────────────

@router.post(
    "/logout",
    response_model=SuccessResponse,
    summary="Logout / revoke tokens",
    description="Revoke the current session or all sessions. Pass all_devices=true to sign out everywhere.",
)
async def logout(
    payload: LogoutRequest,
    request: Request,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
) -> SuccessResponse:
    ip = _get_client_ip(request)

    if payload.all_devices:
        # Revoke all sessions for this user
        result = await db.execute(
            select(UserSession).where(
                UserSession.user_id == current_user.id,
                UserSession.revoked_at.is_(None),
            )
        )
        sessions = result.scalars().all()
        now = datetime.now(timezone.utc)
        for s in sessions:
            s.revoked_at = now

        await log_audit(
            db=db, action="auth.logout.all_devices", resource_type="user",
            resource_id=str(current_user.id), user_id=current_user.id,
            ip_address=ip, success=True,
        )
        return SuccessResponse(message=f"Signed out from all {len(sessions)} active sessions.")

    # Revoke a specific refresh token
    if payload.refresh_token:
        try:
            token_data = decode_token(payload.refresh_token, TOKEN_TYPE_REFRESH)
            jti = token_data["jti"]
            result = await db.execute(
                select(UserSession).where(
                    UserSession.jti == jti,
                    UserSession.user_id == current_user.id,
                )
            )
            session = result.scalar_one_or_none()
            if session:
                session.revoked_at = datetime.now(timezone.utc)
        except HTTPException:
            pass  # Token already invalid — still return success

    await log_audit(
        db=db, action="auth.logout", resource_type="user",
        resource_id=str(current_user.id), user_id=current_user.id,
        ip_address=ip, success=True,
    )
    return SuccessResponse(message="Logged out successfully.")


# ─────────────────────────────────────────────
# POST /auth/verify-email
# ─────────────────────────────────────────────

@router.post(
    "/verify-email",
    response_model=SuccessResponse,
    summary="Verify email address",
    description="Confirm email address using the token sent after signup.",
)
async def verify_email(
    payload: EmailVerifyRequest,
    db: AsyncSession = Depends(get_db),
) -> SuccessResponse:
    from config.security import TOKEN_TYPE_EMAIL_VERIFY
    token_data = decode_token(payload.token, TOKEN_TYPE_EMAIL_VERIFY)
    user_id = token_data["sub"]

    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    if user.is_verified:
        return SuccessResponse(message="Email already verified.")

    user.is_verified = True
    user.email_verified_at = datetime.now(timezone.utc)

    await log_audit(
        db=db, action="auth.email.verified", resource_type="user",
        resource_id=str(user.id), user_id=user.id, success=True,
    )
    return SuccessResponse(message="Email verified. You can now log in.")


# ─────────────────────────────────────────────
# POST /auth/password-reset
# ─────────────────────────────────────────────

@router.post(
    "/password-reset",
    response_model=SuccessResponse,
    summary="Initiate password reset",
    description=(
        "Send a password reset link to the provided email if an account exists. "
        "Always returns 200 to prevent user enumeration."
    ),
)
async def request_password_reset(
    payload: PasswordResetRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> SuccessResponse:
    result = await db.execute(select(User).where(User.email == payload.email.lower()))
    user = result.scalar_one_or_none()

    if user and user.is_active:
        reset_token = create_password_reset_token(str(user.id))
        background_tasks.add_task(_send_password_reset_email, user, reset_token)

        await log_audit(
            db=db, action="auth.password_reset.requested", resource_type="user",
            resource_id=str(user.id), user_id=user.id,
            ip_address=_get_client_ip(request), success=True,
        )

    # Always return same message (no enumeration)
    return SuccessResponse(
        message="If that email exists, you'll receive a password reset link shortly."
    )


# ─────────────────────────────────────────────
# POST /auth/password-reset/confirm
# ─────────────────────────────────────────────

@router.post(
    "/password-reset/confirm",
    response_model=SuccessResponse,
    summary="Confirm password reset",
    description="Set a new password using the token from the reset email.",
)
async def confirm_password_reset(
    payload: PasswordResetConfirmRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> SuccessResponse:
    from config.security import TOKEN_TYPE_PASSWORD_RESET
    token_data = decode_token(payload.token, TOKEN_TYPE_PASSWORD_RESET)
    user_id = token_data["sub"]

    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired reset token.")

    user.hashed_password = hash_password(payload.new_password)
    user.password_changed_at = datetime.now(timezone.utc)

    # Revoke all existing sessions (force re-login on all devices)
    sessions_result = await db.execute(
        select(UserSession).where(
            UserSession.user_id == user.id,
            UserSession.revoked_at.is_(None),
        )
    )
    now = datetime.now(timezone.utc)
    for s in sessions_result.scalars().all():
        s.revoked_at = now

    await log_audit(
        db=db, action="auth.password_reset.confirmed", resource_type="user",
        resource_id=str(user.id), user_id=user.id,
        ip_address=_get_client_ip(request), success=True,
    )

    return SuccessResponse(message="Password updated. Please log in with your new password.")
