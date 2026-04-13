"""
The Life Shield — Unit Tests: Authentication
Tests for password hashing, JWT token generation/validation,
and auth utility functions.
"""

import time
import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest

from app.core.auth import (
    AuthError,
    TokenExpiredError,
    TokenInvalidError,
    TokenTypeMismatchError,
    create_access_token,
    create_email_verification_token,
    create_password_reset_token,
    create_refresh_token,
    decode_token,
    extract_subject,
    generate_jti,
    hash_password,
    verify_password,
)
from config.security import (
    TOKEN_TYPE_ACCESS,
    TOKEN_TYPE_EMAIL_VERIFY,
    TOKEN_TYPE_PASSWORD_RESET,
    TOKEN_TYPE_REFRESH,
    settings,
)


# ═════════════════════════════════════════════════════════════════════════════
# PASSWORD HASHING
# ═════════════════════════════════════════════════════════════════════════════

class TestHashPassword:
    """Tests for hash_password()."""

    def test_returns_string(self, valid_password):
        result = hash_password(valid_password)
        assert isinstance(result, str)

    def test_hash_starts_with_bcrypt_prefix(self, valid_password):
        result = hash_password(valid_password)
        assert result.startswith("$2b$")

    def test_different_hashes_for_same_password(self, valid_password):
        """bcrypt uses random salts — two hashes of the same password differ."""
        hash1 = hash_password(valid_password)
        hash2 = hash_password(valid_password)
        assert hash1 != hash2

    def test_hashes_long_password(self):
        long_pw = "A" * 72 + "extra_ignored"  # bcrypt truncates at 72 bytes
        result = hash_password(long_pw)
        assert result.startswith("$2b$")

    def test_raises_on_empty_password(self):
        with pytest.raises(ValueError, match="Password cannot be empty"):
            hash_password("")

    def test_raises_on_none_password(self):
        with pytest.raises((ValueError, AttributeError)):
            hash_password(None)  # type: ignore[arg-type]

    def test_handles_unicode_password(self):
        unicode_pw = "Pässwörd!123#"
        result = hash_password(unicode_pw)
        assert result.startswith("$2b$")


class TestVerifyPassword:
    """Tests for verify_password()."""

    def test_correct_password_returns_true(self, valid_password):
        hashed = hash_password(valid_password)
        assert verify_password(valid_password, hashed) is True

    def test_wrong_password_returns_false(self, valid_password):
        hashed = hash_password(valid_password)
        assert verify_password("WrongPassword!99", hashed) is False

    def test_empty_password_returns_false(self, valid_password):
        hashed = hash_password(valid_password)
        assert verify_password("", hashed) is False

    def test_empty_hash_returns_false(self, valid_password):
        assert verify_password(valid_password, "") is False

    def test_both_empty_returns_false(self):
        assert verify_password("", "") is False

    def test_case_sensitive(self, valid_password):
        hashed = hash_password(valid_password)
        assert verify_password(valid_password.upper(), hashed) is False

    def test_unicode_round_trip(self):
        pw = "Pässwörd!123#"
        hashed = hash_password(pw)
        assert verify_password(pw, hashed) is True
        assert verify_password("Passwórd!123#", hashed) is False

    def test_sql_injection_attempt(self, valid_password):
        hashed = hash_password(valid_password)
        assert verify_password("' OR 1=1 --", hashed) is False


# ═════════════════════════════════════════════════════════════════════════════
# JTI GENERATION
# ═════════════════════════════════════════════════════════════════════════════

class TestGenerateJTI:
    def test_returns_string(self):
        assert isinstance(generate_jti(), str)

    def test_is_valid_uuid(self):
        jti = generate_jti()
        parsed = uuid.UUID(jti)
        assert str(parsed) == jti

    def test_unique_each_call(self):
        jtis = {generate_jti() for _ in range(100)}
        assert len(jtis) == 100


# ═════════════════════════════════════════════════════════════════════════════
# ACCESS TOKEN
# ═════════════════════════════════════════════════════════════════════════════

class TestCreateAccessToken:
    """Tests for create_access_token()."""

    def test_returns_string(self):
        token = create_access_token(subject="user-123")
        assert isinstance(token, str)

    def test_payload_contains_subject(self):
        user_id = str(uuid.uuid4())
        token = create_access_token(subject=user_id)
        payload = decode_token(token, expected_type=TOKEN_TYPE_ACCESS)
        assert payload["sub"] == user_id

    def test_payload_contains_correct_type(self):
        token = create_access_token(subject="user-123")
        payload = decode_token(token)
        assert payload["type"] == TOKEN_TYPE_ACCESS

    def test_payload_contains_jti(self):
        token = create_access_token(subject="user-123")
        payload = decode_token(token)
        assert "jti" in payload
        uuid.UUID(payload["jti"])  # validates it's a real UUID

    def test_extra_claims_embedded(self):
        token = create_access_token(
            subject="user-123",
            extra_claims={"role": "admin", "scope": "full"},
        )
        payload = decode_token(token)
        assert payload["role"] == "admin"
        assert payload["scope"] == "full"

    def test_custom_expiry(self):
        """Tokens with very short expiry expire quickly."""
        token = create_access_token(
            subject="user-123",
            expires_delta=timedelta(seconds=1),
        )
        payload = decode_token(token)
        assert "exp" in payload

    def test_expired_token_raises(self):
        token = create_access_token(
            subject="user-123",
            expires_delta=timedelta(seconds=-1),  # already expired
        )
        with pytest.raises(TokenExpiredError):
            decode_token(token)

    def test_multiple_tokens_have_different_jtis(self):
        t1 = create_access_token("user-1")
        t2 = create_access_token("user-1")
        p1 = decode_token(t1)
        p2 = decode_token(t2)
        assert p1["jti"] != p2["jti"]


# ═════════════════════════════════════════════════════════════════════════════
# REFRESH TOKEN
# ═════════════════════════════════════════════════════════════════════════════

class TestCreateRefreshToken:
    """Tests for create_refresh_token()."""

    def test_returns_tuple_of_token_and_jti(self):
        token, jti = create_refresh_token(subject="user-123")
        assert isinstance(token, str)
        assert isinstance(jti, str)

    def test_payload_type_is_refresh(self):
        token, _ = create_refresh_token(subject="user-123")
        payload = decode_token(token, expected_type=TOKEN_TYPE_REFRESH)
        assert payload["type"] == TOKEN_TYPE_REFRESH

    def test_jti_matches_payload(self):
        token, jti = create_refresh_token(subject="user-123")
        payload = decode_token(token)
        assert payload["jti"] == jti

    def test_accepts_pre_generated_jti(self):
        custom_jti = str(uuid.uuid4())
        token, returned_jti = create_refresh_token(subject="user-123", jti=custom_jti)
        assert returned_jti == custom_jti
        payload = decode_token(token)
        assert payload["jti"] == custom_jti

    def test_subject_preserved(self):
        user_id = str(uuid.uuid4())
        token, _ = create_refresh_token(subject=user_id)
        payload = decode_token(token)
        assert payload["sub"] == user_id

    def test_extra_claims_embedded(self):
        token, _ = create_refresh_token(
            subject="user-123",
            extra_claims={"device": "mobile"},
        )
        payload = decode_token(token)
        assert payload["device"] == "mobile"

    def test_custom_expiry(self):
        token, _ = create_refresh_token(
            subject="user-123",
            expires_delta=timedelta(days=7),
        )
        payload = decode_token(token)
        assert "exp" in payload


# ═════════════════════════════════════════════════════════════════════════════
# EMAIL VERIFICATION TOKEN
# ═════════════════════════════════════════════════════════════════════════════

class TestEmailVerificationToken:
    def test_returns_string(self):
        token = create_email_verification_token("user@example.com")
        assert isinstance(token, str)

    def test_payload_type_is_email_verify(self):
        token = create_email_verification_token("user@example.com")
        payload = decode_token(token, expected_type=TOKEN_TYPE_EMAIL_VERIFY)
        assert payload["type"] == TOKEN_TYPE_EMAIL_VERIFY

    def test_subject_is_email(self):
        email = "user@example.com"
        token = create_email_verification_token(email)
        payload = decode_token(token)
        assert payload["sub"] == email

    def test_wrong_type_check_raises(self):
        token = create_email_verification_token("user@example.com")
        with pytest.raises(TokenTypeMismatchError):
            decode_token(token, expected_type=TOKEN_TYPE_ACCESS)


# ═════════════════════════════════════════════════════════════════════════════
# PASSWORD RESET TOKEN
# ═════════════════════════════════════════════════════════════════════════════

class TestPasswordResetToken:
    def test_returns_string(self):
        token = create_password_reset_token("user@example.com")
        assert isinstance(token, str)

    def test_payload_type_is_password_reset(self):
        token = create_password_reset_token("user@example.com")
        payload = decode_token(token, expected_type=TOKEN_TYPE_PASSWORD_RESET)
        assert payload["type"] == TOKEN_TYPE_PASSWORD_RESET

    def test_subject_is_email(self):
        email = "reset@example.com"
        token = create_password_reset_token(email)
        payload = decode_token(token)
        assert payload["sub"] == email

    def test_different_from_email_verify_token(self):
        email = "test@example.com"
        reset_token = create_password_reset_token(email)
        verify_token = create_email_verification_token(email)
        # They should decode with the correct type check
        decode_token(reset_token, expected_type=TOKEN_TYPE_PASSWORD_RESET)
        decode_token(verify_token, expected_type=TOKEN_TYPE_EMAIL_VERIFY)
        # Cross-type check should fail
        with pytest.raises(TokenTypeMismatchError):
            decode_token(reset_token, expected_type=TOKEN_TYPE_EMAIL_VERIFY)


# ═════════════════════════════════════════════════════════════════════════════
# DECODE TOKEN
# ═════════════════════════════════════════════════════════════════════════════

class TestDecodeToken:
    """Tests for decode_token()."""

    def test_decodes_valid_token(self):
        token = create_access_token("user-123")
        payload = decode_token(token)
        assert payload["sub"] == "user-123"

    def test_raises_on_tampered_token(self):
        token = create_access_token("user-123")
        tampered = token[:-5] + "XXXXX"
        with pytest.raises(TokenInvalidError):
            decode_token(tampered)

    def test_raises_on_expired_token(self):
        token = create_access_token("user-123", expires_delta=timedelta(seconds=-10))
        with pytest.raises(TokenExpiredError):
            decode_token(token)

    def test_raises_on_garbage_string(self):
        with pytest.raises(TokenInvalidError):
            decode_token("this.is.not.a.jwt")

    def test_raises_on_wrong_secret(self):
        import jwt as pyjwt
        from datetime import datetime, timezone

        payload = {
            "sub": "user-123",
            "type": "access",
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        }
        bad_token = pyjwt.encode(payload, "wrong-secret", algorithm="HS256")
        with pytest.raises(TokenInvalidError):
            decode_token(bad_token)

    def test_type_mismatch_raises(self):
        token = create_access_token("user-123")
        with pytest.raises(TokenTypeMismatchError):
            decode_token(token, expected_type=TOKEN_TYPE_REFRESH)

    def test_no_type_check_accepts_any_valid_token(self):
        token = create_refresh_token("user-123")[0]
        payload = decode_token(token)  # No expected_type
        assert payload["type"] == TOKEN_TYPE_REFRESH

    def test_empty_string_raises(self):
        with pytest.raises(TokenInvalidError):
            decode_token("")


# ═════════════════════════════════════════════════════════════════════════════
# EXTRACT SUBJECT
# ═════════════════════════════════════════════════════════════════════════════

class TestExtractSubject:
    def test_extracts_subject_from_access_token(self):
        user_id = str(uuid.uuid4())
        token = create_access_token(user_id)
        assert extract_subject(token) == user_id

    def test_extracts_email_from_reset_token(self):
        email = "test@example.com"
        token = create_password_reset_token(email)
        assert extract_subject(token) == email

    def test_raises_on_expired_token(self):
        token = create_access_token("user-123", expires_delta=timedelta(seconds=-1))
        with pytest.raises(TokenExpiredError):
            extract_subject(token)

    def test_raises_on_invalid_token(self):
        with pytest.raises(TokenInvalidError):
            extract_subject("invalid.token.here")
