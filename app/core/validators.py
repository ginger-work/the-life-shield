"""
The Life Shield — Input Validation Utilities
Password policy, email normalization, and common field validators.
"""

import re
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────

MIN_PASSWORD_LENGTH = 12
EMAIL_REGEX = re.compile(
    r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$"
)
PHONE_REGEX = re.compile(
    r"^\+?1?\s*[\-.]?\s*\(?(\d{3})\)?[\s.\-]?(\d{3})[\s.\-]?(\d{4})$"
)


# ─────────────────────────────────────────────────────────────────────────────
# EXCEPTIONS
# ─────────────────────────────────────────────────────────────────────────────

class ValidationError(Exception):
    """Raised when a validation check fails."""

    def __init__(self, field: str, message: str):
        self.field = field
        self.message = message
        super().__init__(f"{field}: {message}")


# ─────────────────────────────────────────────────────────────────────────────
# EMAIL
# ─────────────────────────────────────────────────────────────────────────────

def normalize_email(email: str) -> str:
    """
    Normalize an email address: strip whitespace, lowercase.

    Args:
        email: Raw email string.

    Returns:
        Normalized email string.

    Raises:
        ValidationError: If the email format is invalid.
    """
    if not email:
        raise ValidationError("email", "Email cannot be empty")
    normalized = email.strip().lower()
    if not EMAIL_REGEX.match(normalized):
        raise ValidationError("email", f"Invalid email format: {email!r}")
    return normalized


def validate_email(email: str) -> bool:
    """Return True if the email is valid, False otherwise."""
    try:
        normalize_email(email)
        return True
    except ValidationError:
        return False


# ─────────────────────────────────────────────────────────────────────────────
# PASSWORD
# ─────────────────────────────────────────────────────────────────────────────

def validate_password_strength(password: str) -> list[str]:
    """
    Check password against The Life Shield's security policy.

    Rules:
    - Minimum 12 characters
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one digit
    - At least one special character

    Args:
        password: The raw password string.

    Returns:
        A list of violation messages. Empty list means the password is valid.
    """
    violations: list[str] = []

    if not password:
        violations.append("Password cannot be empty")
        return violations

    if len(password) < MIN_PASSWORD_LENGTH:
        violations.append(
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters long"
        )
    if not re.search(r"[A-Z]", password):
        violations.append("Password must contain at least one uppercase letter")
    if not re.search(r"[a-z]", password):
        violations.append("Password must contain at least one lowercase letter")
    if not re.search(r"\d", password):
        violations.append("Password must contain at least one digit")
    if not re.search(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?`~]", password):
        violations.append(
            "Password must contain at least one special character"
        )

    return violations


def is_password_valid(password: str) -> bool:
    """Return True if password meets all policy requirements."""
    return len(validate_password_strength(password)) == 0


# ─────────────────────────────────────────────────────────────────────────────
# PHONE
# ─────────────────────────────────────────────────────────────────────────────

def validate_phone(phone: str) -> bool:
    """Return True if the phone number matches a valid US format."""
    if not phone:
        return False
    return bool(PHONE_REGEX.match(phone.strip()))


def normalize_phone(phone: str) -> str:
    """
    Normalize a US phone number to E.164 format (+1XXXXXXXXXX).

    Args:
        phone: Raw phone string.

    Returns:
        E.164 formatted string.

    Raises:
        ValidationError: If the phone number is invalid.
    """
    if not phone:
        raise ValidationError("phone", "Phone number cannot be empty")
    cleaned = re.sub(r"[\s.\-\(\)]", "", phone.strip())
    if cleaned.startswith("+1"):
        digits = cleaned[2:]
    elif cleaned.startswith("1") and len(cleaned) == 11:
        digits = cleaned[1:]
    else:
        digits = cleaned

    if not re.match(r"^\d{10}$", digits):
        raise ValidationError("phone", f"Invalid US phone number: {phone!r}")

    return f"+1{digits}"


# ─────────────────────────────────────────────────────────────────────────────
# NAME
# ─────────────────────────────────────────────────────────────────────────────

def validate_name(value: str, field: str = "name") -> str:
    """
    Validate and clean a name field (first/last name).

    Args:
        value: Raw name string.
        field: Field name for error messages.

    Returns:
        Stripped name string.

    Raises:
        ValidationError: If empty or too long.
    """
    if not value or not value.strip():
        raise ValidationError(field, f"{field.replace('_', ' ').title()} cannot be empty")
    stripped = value.strip()
    if len(stripped) > 100:
        raise ValidationError(field, f"{field.replace('_', ' ').title()} cannot exceed 100 characters")
    return stripped
