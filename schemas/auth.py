"""
The Life Shield - Auth Schemas
Pydantic request/response models for authentication endpoints.
"""

import re
import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from config.security import UserRole


# ─────────────────────────────────────────────
# PASSWORD VALIDATION HELPER
# ─────────────────────────────────────────────

def validate_password_strength(password: str) -> str:
    """
    Enforce password policy:
    - 8+ characters
    - At least one uppercase
    - At least one lowercase
    - At least one digit
    - At least one special character
    """
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters long")
    if not re.search(r"[A-Z]", password):
        raise ValueError("Password must contain at least one uppercase letter")
    if not re.search(r"[a-z]", password):
        raise ValueError("Password must contain at least one lowercase letter")
    if not re.search(r"\d", password):
        raise ValueError("Password must contain at least one digit")
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
        raise ValueError("Password must contain at least one special character")
    return password


# ─────────────────────────────────────────────
# SIGNUP
# ─────────────────────────────────────────────

class SignupRequest(BaseModel):
    """Client registration — creates a CLIENT-role user."""
    first_name: str = Field(..., min_length=1, max_length=100, examples=["John"])
    last_name: str = Field(..., min_length=1, max_length=100, examples=["Smith"])
    email: EmailStr = Field(..., examples=["john.smith@example.com"])
    password: str = Field(..., min_length=8, max_length=128)
    phone: Optional[str] = Field(None, pattern=r"^\+?[1-9]\d{9,14}$", examples=["+19195551234"])

    # Consent (required per FCC rules)
    sms_consent: bool = Field(False, description="Client consents to SMS communication")
    email_consent: bool = Field(True, description="Client consents to email communication")
    voice_consent: bool = Field(False, description="Client consents to voice calls")

    # CROA-required: terms + service disclosure must be accepted
    terms_accepted: bool = Field(..., description="Must be true to register")
    service_disclosure_accepted: bool = Field(
        ..., description="Client acknowledges AI service disclosure"
    )
    croa_disclosure_accepted: bool = Field(
        ..., description="Client acknowledges CROA rights and 3-day cancellation"
    )

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        return validate_password_strength(v)

    @model_validator(mode="after")
    def require_disclosures(self) -> "SignupRequest":
        if not self.terms_accepted:
            raise ValueError("You must accept the terms of service to register")
        if not self.service_disclosure_accepted:
            raise ValueError("You must acknowledge the service disclosure to register")
        if not self.croa_disclosure_accepted:
            raise ValueError("You must acknowledge CROA rights to register")
        return self

    model_config = {"json_schema_extra": {"example": {
        "first_name": "John",
        "last_name": "Smith",
        "email": "john.smith@example.com",
        "password": "SecureP@ss1!",
        "phone": "+19195551234",
        "sms_consent": True,
        "email_consent": True,
        "voice_consent": False,
        "terms_accepted": True,
        "service_disclosure_accepted": True,
        "croa_disclosure_accepted": True,
    }}}


class SignupResponse(BaseModel):
    """Response after successful registration."""
    message: str = "Registration successful. Please check your email to verify your account."
    user_id: uuid.UUID
    email: EmailStr
    requires_verification: bool = True


# ─────────────────────────────────────────────
# LOGIN
# ─────────────────────────────────────────────

class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., max_length=128)
    device_type: Optional[str] = Field(None, examples=["web", "mobile", "desktop"])
    device_name: Optional[str] = Field(None, max_length=255, examples=["Chrome on Mac"])

    model_config = {"json_schema_extra": {"example": {
        "email": "john.smith@example.com",
        "password": "SecureP@ss1!",
        "device_type": "web",
        "device_name": "Chrome on Mac",
    }}}


class TokenResponse(BaseModel):
    """Returned on successful login or token refresh."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(..., description="Access token TTL in seconds")
    user_id: uuid.UUID
    role: UserRole

    model_config = {"json_schema_extra": {"example": {
        "access_token": "eyJhbGci...",
        "refresh_token": "eyJhbGci...",
        "token_type": "bearer",
        "expires_in": 1800,
        "user_id": "550e8400-e29b-41d4-a716-446655440000",
        "role": "client",
    }}}


# ─────────────────────────────────────────────
# REFRESH
# ─────────────────────────────────────────────

class RefreshRequest(BaseModel):
    refresh_token: str = Field(..., description="Valid refresh token from prior login")


# ─────────────────────────────────────────────
# ME (current user)
# ─────────────────────────────────────────────

class MeResponse(BaseModel):
    """Current authenticated user profile."""
    id: uuid.UUID
    email: EmailStr
    first_name: str
    last_name: str
    full_name: str
    role: UserRole
    phone: Optional[str]
    is_verified: bool
    is_active: bool
    sms_consent: bool
    email_consent: bool
    voice_consent: bool
    last_login_at: Optional[datetime]
    created_at: datetime

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────
# LOGOUT
# ─────────────────────────────────────────────

class LogoutRequest(BaseModel):
    """Optionally pass refresh_token to revoke; omit to revoke current access session only."""
    refresh_token: Optional[str] = None
    all_devices: bool = Field(False, description="Revoke all sessions for this user")


# ─────────────────────────────────────────────
# EMAIL VERIFICATION
# ─────────────────────────────────────────────

class EmailVerifyRequest(BaseModel):
    token: str = Field(..., description="Token from verification email")


# ─────────────────────────────────────────────
# PASSWORD RESET
# ─────────────────────────────────────────────

class PasswordResetRequest(BaseModel):
    """Step 1: Initiate password reset by email."""
    email: EmailStr

    model_config = {"json_schema_extra": {"example": {"email": "john.smith@example.com"}}}


class PasswordResetConfirmRequest(BaseModel):
    """Step 2: Set new password using reset token."""
    token: str = Field(..., description="Token from reset email")
    new_password: str = Field(..., min_length=8, max_length=128)
    confirm_password: str = Field(..., min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        return validate_password_strength(v)

    @model_validator(mode="after")
    def passwords_match(self) -> "PasswordResetConfirmRequest":
        if self.new_password != self.confirm_password:
            raise ValueError("Passwords do not match")
        return self
