"""
The Life Shield - Security Configuration
JWT settings, password hashing, RBAC roles, and security constants.
"""

import os
import secrets
from datetime import timedelta
from enum import Enum
from typing import Optional

from pydantic_settings import BaseSettings


# ─────────────────────────────────────────────
# ROLES & PERMISSIONS
# ─────────────────────────────────────────────

class UserRole(str, Enum):
    ADMIN = "admin"
    CLIENT = "client"
    AGENT = "agent"


ROLE_PERMISSIONS: dict[str, list[str]] = {
    UserRole.ADMIN: [
        # Full access
        "agents:read", "agents:write", "agents:delete",
        "clients:read", "clients:write", "clients:delete",
        "disputes:read", "disputes:write", "disputes:approve",
        "communications:read", "communications:write",
        "billing:read", "billing:write",
        "compliance:read", "compliance:override",
        "admin:dashboard", "admin:override",
        "audit:read",
        "sessions:read", "sessions:write",
        "products:read", "products:write",
    ],
    UserRole.AGENT: [
        # Agent-level access
        "clients:read",
        "disputes:read", "disputes:write",
        "communications:read", "communications:write",
        "sessions:read",
        "products:read",
        "audit:read",
    ],
    UserRole.CLIENT: [
        # Client self-service access
        "profile:read", "profile:write",
        "disputes:read",
        "communications:read",
        "sessions:read", "sessions:enroll",
        "products:read", "products:purchase",
        "vault:read", "vault:write",
        "budget:read", "budget:write",
    ],
}


def has_permission(role: UserRole, permission: str) -> bool:
    """Check if a role has a specific permission."""
    return permission in ROLE_PERMISSIONS.get(role, [])


# ─────────────────────────────────────────────
# SETTINGS
# ─────────────────────────────────────────────

class SecuritySettings(BaseSettings):
    # JWT
    SECRET_KEY: str = os.getenv("SECRET_KEY", secrets.token_urlsafe(64))
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    EMAIL_VERIFY_TOKEN_EXPIRE_HOURS: int = 24
    PASSWORD_RESET_TOKEN_EXPIRE_HOURS: int = 2

    # Bcrypt
    BCRYPT_ROUNDS: int = 12

    # Rate limiting
    RATE_LIMIT_SIGNUP: str = "5/minute"
    RATE_LIMIT_LOGIN: str = "10/minute"
    RATE_LIMIT_PASSWORD_RESET: str = "3/hour"
    RATE_LIMIT_REFRESH: str = "20/minute"
    RATE_LIMIT_DEFAULT: str = "100/minute"

    # CORS
    ALLOWED_ORIGINS: list[str] = [
        "https://thelifeshield.com",
        "https://app.thelifeshield.com",
        "https://admin.thelifeshield.com",
    ]
    ALLOW_CREDENTIALS: bool = True

    # App
    API_V1_PREFIX: str = "/api/v1"
    PROJECT_NAME: str = "The Life Shield"
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

    # Email (SMTP)
    SMTP_HOST: str = os.getenv("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER: str = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    FROM_EMAIL: str = os.getenv("FROM_EMAIL", "noreply@thelifeshield.com")
    FROM_NAME: str = "The Life Shield"

    # Database
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/lifeshield"
    )

    # Redis (for token revocation & rate limiting)
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # Frontend base URL (for email links)
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "https://thelifeshield.com")

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = SecuritySettings()


# ─────────────────────────────────────────────
# TOKEN HELPERS
# ─────────────────────────────────────────────

def get_access_token_expiry() -> timedelta:
    return timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)


def get_refresh_token_expiry() -> timedelta:
    return timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)


def get_email_verify_expiry() -> timedelta:
    return timedelta(hours=settings.EMAIL_VERIFY_TOKEN_EXPIRE_HOURS)


def get_password_reset_expiry() -> timedelta:
    return timedelta(hours=settings.PASSWORD_RESET_TOKEN_EXPIRE_HOURS)


# ─────────────────────────────────────────────
# SECURITY CONSTANTS
# ─────────────────────────────────────────────

# Token types stored in JWT "type" claim
TOKEN_TYPE_ACCESS = "access"
TOKEN_TYPE_REFRESH = "refresh"
TOKEN_TYPE_EMAIL_VERIFY = "email_verify"
TOKEN_TYPE_PASSWORD_RESET = "password_reset"

# HTTP Auth scheme
AUTH_SCHEME = "Bearer"

# Headers
CORRELATION_ID_HEADER = "X-Correlation-ID"
REQUEST_ID_HEADER = "X-Request-ID"
