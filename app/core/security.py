"""
Security utilities: password hashing, JWT token management, and
access control helpers.

Design principles:
- Passwords hashed with bcrypt (never stored plaintext)
- JWTs signed with HS256 (upgrade to RS256 for distributed systems)
- Access tokens: short-lived (30 min default)
- Refresh tokens: long-lived (7 days default)
- All token operations are explicit - no magic
"""
import secrets
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Optional
from uuid import UUID

import bcrypt as _bcrypt
from jose import JWTError, jwt

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Password Hashing (native bcrypt - passlib removed for Python 3.14 compat)
# ---------------------------------------------------------------------------

def hash_password(plain_password: str) -> str:
    """
    Hash a plain-text password with bcrypt.
    Returns bcrypt hash string (includes salt and cost factor).
    """
    rounds = getattr(settings, 'BCRYPT_ROUNDS', 12)
    salt = _bcrypt.gensalt(rounds=rounds)
    return _bcrypt.hashpw(plain_password.encode('utf-8'), salt).decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plain-text password against its bcrypt hash.
    Returns True if password matches, False otherwise.
    """
    try:
        return _bcrypt.checkpw(
            plain_password.encode('utf-8'),
            hashed_password.encode('utf-8')
        )
    except Exception:
        return False


def validate_password_strength(password: str) -> list[str]:
    """
    Validate password meets security policy.

    Returns:
        List of violation messages (empty list = password is valid)
    """
    violations = []

    if len(password) < settings.MIN_PASSWORD_LENGTH:
        violations.append(
            f"Password must be at least {settings.MIN_PASSWORD_LENGTH} characters"
        )

    if not any(c.isupper() for c in password):
        violations.append("Password must contain at least one uppercase letter")

    if not any(c.islower() for c in password):
        violations.append("Password must contain at least one lowercase letter")

    if not any(c.isdigit() for c in password):
        violations.append("Password must contain at least one number")

    if not any(c in "!@#$%^&*()_+-=[]{}|;':\",./<>?" for c in password):
        violations.append("Password must contain at least one special character")

    return violations


# ---------------------------------------------------------------------------
# JWT Token Management
# ---------------------------------------------------------------------------

class TokenType(str, Enum):
    ACCESS = "access"
    REFRESH = "refresh"


def create_access_token(
    subject: str,
    additional_claims: Optional[dict[str, Any]] = None,
) -> str:
    """
    Create a short-lived JWT access token.

    Args:
        subject: Unique identifier (user_id as string)
        additional_claims: Extra claims to embed (role, email, etc.)

    Returns:
        Signed JWT string
    """
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
    )

    payload = {
        "sub": str(subject),
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": TokenType.ACCESS,
        "jti": secrets.token_urlsafe(16),  # Unique token ID (for revocation)
    }

    if additional_claims:
        payload.update(additional_claims)

    return jwt.encode(
        payload,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def create_refresh_token(subject: str) -> str:
    """
    Create a long-lived JWT refresh token.

    Args:
        subject: Unique identifier (user_id as string)

    Returns:
        Signed JWT string
    """
    expire = datetime.now(timezone.utc) + timedelta(
        days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS
    )

    payload = {
        "sub": str(subject),
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": TokenType.REFRESH,
        "jti": secrets.token_urlsafe(16),
    }

    return jwt.encode(
        payload,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def decode_token(token: str, expected_type: Optional[str] = None) -> dict[str, Any]:
    """
    Decode and validate a JWT token.

    Args:
        token: JWT string to decode
        expected_type: Optional token type to validate (access, refresh, email_verify, password_reset)

    Returns:
        Decoded payload dictionary

    Raises:
        JWTError: If token is invalid, expired, or tampered with
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        if expected_type and payload.get("type") != expected_type:
            raise ValueError(f"Invalid token type: expected {expected_type}, got {payload.get('type')}")
        return payload
    except JWTError as e:
        logger.warning("JWT decode failed", error=str(e))
        raise


def extract_token_subject(payload: dict[str, Any]) -> str:
    """
    Extract the subject (user_id) from a decoded token payload.

    Raises:
        ValueError: If subject is missing
    """
    subject = payload.get("sub")
    if not subject:
        raise ValueError("Token missing subject claim")
    return subject


# ---------------------------------------------------------------------------
# Secure Random Utilities
# ---------------------------------------------------------------------------

def generate_secure_token(length: int = 32) -> str:
    """Generate a cryptographically secure random token."""
    return secrets.token_urlsafe(length)


def generate_otp(digits: int = 6) -> str:
    """Generate a numeric OTP code (e.g., for email verification)."""
    return str(secrets.randbelow(10 ** digits)).zfill(digits)


def create_email_verify_token(user_id: str) -> str:
    """Create short-lived email verification token."""
    expire = datetime.now(timezone.utc) + timedelta(hours=24)
    payload = {
        "sub": str(user_id),
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "email_verify",
        "jti": secrets.token_urlsafe(16),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_password_reset_token(email: str) -> str:
    """Create short-lived password reset token."""
    expire = datetime.now(timezone.utc) + timedelta(hours=1)
    payload = {
        "sub": email,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "password_reset",
        "jti": secrets.token_urlsafe(16),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
