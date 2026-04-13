"""
The Life Shield — Core Authentication Utilities
JWT token creation/validation, password hashing, and session management.
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import bcrypt
import jwt
from jwt.exceptions import DecodeError, ExpiredSignatureError, InvalidTokenError

from config.security import (
    TOKEN_TYPE_ACCESS,
    TOKEN_TYPE_EMAIL_VERIFY,
    TOKEN_TYPE_PASSWORD_RESET,
    TOKEN_TYPE_REFRESH,
    settings,
)


# ─────────────────────────────────────────────────────────────────────────────
# EXCEPTIONS
# ─────────────────────────────────────────────────────────────────────────────

class AuthError(Exception):
    """Base authentication error."""


class TokenExpiredError(AuthError):
    """JWT token has expired."""


class TokenInvalidError(AuthError):
    """JWT token is malformed or has an invalid signature."""


class TokenTypeMismatchError(AuthError):
    """JWT token type does not match expected type."""


# ─────────────────────────────────────────────────────────────────────────────
# PASSWORD UTILITIES
# ─────────────────────────────────────────────────────────────────────────────

def hash_password(plain_password: str) -> str:
    """
    Hash a plaintext password using bcrypt.

    Args:
        plain_password: The raw password string from the user.

    Returns:
        A bcrypt-hashed password string.

    Raises:
        ValueError: If plain_password is empty or None.
    """
    if not plain_password:
        raise ValueError("Password cannot be empty")
    salt = bcrypt.gensalt(rounds=settings.BCRYPT_ROUNDS)
    return bcrypt.hashpw(plain_password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plaintext password against a bcrypt hash.

    Args:
        plain_password: The raw password string to verify.
        hashed_password: The stored bcrypt hash.

    Returns:
        True if the password matches, False otherwise.
    """
    if not plain_password or not hashed_password:
        return False
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except Exception:
        return False


# ─────────────────────────────────────────────────────────────────────────────
# JWT UTILITIES
# ─────────────────────────────────────────────────────────────────────────────

def generate_jti() -> str:
    """Generate a unique JWT ID (JTI) for token identity tracking."""
    return str(uuid.uuid4())


def _create_token(
    data: dict[str, Any],
    token_type: str,
    expires_delta: timedelta,
) -> str:
    """
    Internal helper to create a signed JWT.

    Args:
        data: Claims to include in the payload.
        token_type: One of TOKEN_TYPE_* constants.
        expires_delta: How long until the token expires.

    Returns:
        Encoded JWT string.
    """
    now = datetime.now(timezone.utc)
    expire = now + expires_delta
    payload = {
        **data,
        "type": token_type,
        "iat": now,
        "exp": expire,
        "jti": generate_jti(),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_access_token(
    subject: str,
    extra_claims: Optional[dict[str, Any]] = None,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Create a short-lived access token.

    Args:
        subject: The user ID (UUID string) as the JWT subject.
        extra_claims: Additional claims to embed (e.g., role).
        expires_delta: Override the default expiry.

    Returns:
        Signed JWT access token string.
    """
    if expires_delta is None:
        expires_delta = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    data = {"sub": subject, **(extra_claims or {})}
    return _create_token(data, TOKEN_TYPE_ACCESS, expires_delta)


def create_refresh_token(
    subject: str,
    jti: Optional[str] = None,
    extra_claims: Optional[dict[str, Any]] = None,
    expires_delta: Optional[timedelta] = None,
) -> tuple[str, str]:
    """
    Create a long-lived refresh token.

    Args:
        subject: The user ID (UUID string) as the JWT subject.
        jti: Optional pre-generated JTI (for DB tracking).
        extra_claims: Additional claims to embed.
        expires_delta: Override the default expiry.

    Returns:
        Tuple of (encoded_token, jti) — the JTI is used to store
        the session in the database for revocation.
    """
    if expires_delta is None:
        expires_delta = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    token_jti = jti or generate_jti()
    data = {"sub": subject, "jti": token_jti, **(extra_claims or {})}
    now = datetime.now(timezone.utc)
    expire = now + expires_delta
    payload = {
        **data,
        "type": TOKEN_TYPE_REFRESH,
        "iat": now,
        "exp": expire,
    }
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return token, token_jti


def create_email_verification_token(email: str) -> str:
    """
    Create a short-lived email verification token.

    Args:
        email: The email address to verify.

    Returns:
        Signed JWT verification token string.
    """
    expires = timedelta(hours=settings.EMAIL_VERIFY_TOKEN_EXPIRE_HOURS)
    return _create_token({"sub": email}, TOKEN_TYPE_EMAIL_VERIFY, expires)


def create_password_reset_token(email: str) -> str:
    """
    Create a short-lived password reset token.

    Args:
        email: The email address requesting reset.

    Returns:
        Signed JWT password reset token string.
    """
    expires = timedelta(hours=settings.PASSWORD_RESET_TOKEN_EXPIRE_HOURS)
    return _create_token({"sub": email}, TOKEN_TYPE_PASSWORD_RESET, expires)


def decode_token(
    token: str,
    expected_type: Optional[str] = None,
) -> dict[str, Any]:
    """
    Decode and validate a JWT token.

    Args:
        token: The raw JWT string.
        expected_type: If provided, raises TokenTypeMismatchError if the
                       token's "type" claim doesn't match.

    Returns:
        The decoded payload dict.

    Raises:
        TokenExpiredError: If the token has expired.
        TokenInvalidError: If the token is malformed or signature is wrong.
        TokenTypeMismatchError: If expected_type is given and doesn't match.
    """
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )
    except ExpiredSignatureError as exc:
        raise TokenExpiredError("Token has expired") from exc
    except (DecodeError, InvalidTokenError) as exc:
        raise TokenInvalidError(f"Token is invalid: {exc}") from exc

    if expected_type and payload.get("type") != expected_type:
        raise TokenTypeMismatchError(
            f"Expected token type '{expected_type}', got '{payload.get('type')}'"
        )

    return payload


def extract_subject(token: str) -> str:
    """
    Decode a token and return the 'sub' claim without type validation.
    Useful for public-facing helpers.

    Raises:
        TokenExpiredError, TokenInvalidError
    """
    payload = decode_token(token)
    sub = payload.get("sub")
    if not sub:
        raise TokenInvalidError("Token missing 'sub' claim")
    return sub
