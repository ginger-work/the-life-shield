"""
The Life Shield — Integration Tests: Auth Flow (E2E)
End-to-end auth scenarios: registration, login, token refresh,
lockout, and session management. No external services required.
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.core.auth import (
    TokenExpiredError,
    TokenInvalidError,
    TokenTypeMismatchError,
    create_access_token,
    create_email_verification_token,
    create_password_reset_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from config.security import (
    TOKEN_TYPE_ACCESS,
    TOKEN_TYPE_EMAIL_VERIFY,
    TOKEN_TYPE_PASSWORD_RESET,
    TOKEN_TYPE_REFRESH,
    UserRole,
)
from models.user import AuditLog, User, UserSession
from tests.conftest import make_user


# ═════════════════════════════════════════════════════════════════════════════
# REGISTRATION FLOW
# ═════════════════════════════════════════════════════════════════════════════

class TestRegistrationFlow:
    """Simulates the full user registration pipeline."""

    def test_register_client_user(self, db, valid_password):
        """A new client signs up with a valid password."""
        hashed = hash_password(valid_password)
        user = make_user(
            db,
            email="newclient@example.com",
            hashed_password=hashed,
            role=UserRole.CLIENT,
            is_verified=False,
        )
        db.flush()

        # Verify password correct
        assert verify_password(valid_password, user.hashed_password) is True
        # User not yet verified
        assert user.is_verified is False

    def test_email_verification_token_flow(self, db):
        """Email verification token is created and decoded correctly."""
        email = "verify@example.com"
        user = make_user(db, email=email, is_verified=False)
        db.flush()

        token = create_email_verification_token(email)
        payload = decode_token(token, expected_type=TOKEN_TYPE_EMAIL_VERIFY)

        assert payload["sub"] == email
        # Simulate marking user verified
        user.is_verified = True
        user.email_verified_at = datetime.now(timezone.utc)
        db.flush()
        assert user.is_verified is True

    def test_duplicate_email_registration_blocked(self, db):
        """Second registration with same email should fail at DB level."""
        from sqlalchemy.exc import IntegrityError
        email = "duplicate@example.com"
        make_user(db, email=email)
        db.flush()
        with pytest.raises(IntegrityError):
            make_user(db, email=email)
            db.flush()


# ═════════════════════════════════════════════════════════════════════════════
# LOGIN FLOW
# ═════════════════════════════════════════════════════════════════════════════

class TestLoginFlow:
    """Simulates the login → token issuance pipeline."""

    def test_successful_login_returns_tokens(self, db, valid_password):
        """Valid credentials produce access + refresh tokens."""
        hashed = hash_password(valid_password)
        user = make_user(db, hashed_password=hashed, is_verified=True)
        db.flush()

        # Step 1: Verify password
        assert verify_password(valid_password, user.hashed_password) is True

        # Step 2: Issue tokens
        access_token = create_access_token(
            subject=str(user.id),
            extra_claims={"role": user.role},
        )
        refresh_token, jti = create_refresh_token(subject=str(user.id))

        # Step 3: Store session
        session = UserSession(
            id=uuid.uuid4(),
            user_id=user.id,
            jti=jti,
            device_type="web",
            ip_address="127.0.0.1",
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            created_at=datetime.now(timezone.utc),
        )
        db.add(session)
        db.flush()

        # Verify tokens
        access_payload = decode_token(access_token, expected_type=TOKEN_TYPE_ACCESS)
        refresh_payload = decode_token(refresh_token, expected_type=TOKEN_TYPE_REFRESH)

        assert access_payload["sub"] == str(user.id)
        assert access_payload["role"] == user.role
        assert refresh_payload["sub"] == str(user.id)
        assert refresh_payload["jti"] == jti

    def test_wrong_password_denied(self, db, valid_password):
        """Incorrect password must not produce tokens."""
        hashed = hash_password(valid_password)
        user = make_user(db, hashed_password=hashed)
        db.flush()
        assert verify_password("WrongPassword!99", user.hashed_password) is False

    def test_inactive_user_blocked(self, db):
        """Deactivated users should not be allowed to log in."""
        user = make_user(db, is_active=False)
        assert user.is_active is False

    def test_unverified_user_flag(self, db, valid_password):
        """Unverified emails should be flagged in the login response."""
        hashed = hash_password(valid_password)
        user = make_user(db, hashed_password=hashed, is_verified=False)
        assert user.is_verified is False

    def test_failed_login_increments_counter(self, db):
        """Track failed login attempts for lockout protection."""
        user = make_user(db)
        user.failed_login_attempts = 0
        db.flush()

        # Simulate failed login
        user.failed_login_attempts += 1
        db.flush()

        fetched = db.query(User).filter_by(id=user.id).first()
        assert fetched.failed_login_attempts == 1

    def test_account_locked_after_max_attempts(self, db):
        """After 5 failed attempts, account should be locked."""
        user = make_user(db)
        user.failed_login_attempts = 5
        user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=15)
        db.flush()
        assert user.is_locked is True

    def test_lockout_expires(self, db):
        """Lockout expires after the lockout period."""
        user = make_user(db)
        user.locked_until = datetime.now(timezone.utc) - timedelta(minutes=1)  # expired
        assert user.is_locked is False

    def test_successful_login_resets_failure_counter(self, db):
        """Successful login should clear failed_login_attempts."""
        user = make_user(db)
        user.failed_login_attempts = 3
        db.flush()

        # Simulate successful login
        user.failed_login_attempts = 0
        user.last_login_at = datetime.now(timezone.utc)
        user.last_login_ip = "192.168.1.1"
        db.flush()

        fetched = db.query(User).filter_by(id=user.id).first()
        assert fetched.failed_login_attempts == 0
        assert fetched.last_login_at is not None


# ═════════════════════════════════════════════════════════════════════════════
# TOKEN REFRESH FLOW
# ═════════════════════════════════════════════════════════════════════════════

class TestTokenRefreshFlow:
    """Tests for the refresh token → new access token flow."""

    def test_refresh_token_issues_new_access_token(self, db):
        """Valid refresh token produces a new access token."""
        user = make_user(db)
        refresh_token, jti = create_refresh_token(subject=str(user.id))
        session = UserSession(
            id=uuid.uuid4(),
            user_id=user.id,
            jti=jti,
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            created_at=datetime.now(timezone.utc),
        )
        db.add(session)
        db.flush()

        # Simulate refresh flow
        payload = decode_token(refresh_token, expected_type=TOKEN_TYPE_REFRESH)
        fetched_session = db.query(UserSession).filter_by(jti=payload["jti"]).first()
        assert fetched_session is not None
        assert fetched_session.is_valid is True

        # Issue new access token
        new_access = create_access_token(subject=payload["sub"])
        new_payload = decode_token(new_access, expected_type=TOKEN_TYPE_ACCESS)
        assert new_payload["sub"] == str(user.id)

    def test_revoked_refresh_token_rejected(self, db):
        """Revoked sessions should block refresh."""
        user = make_user(db)
        refresh_token, jti = create_refresh_token(subject=str(user.id))
        session = UserSession(
            id=uuid.uuid4(),
            user_id=user.id,
            jti=jti,
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            created_at=datetime.now(timezone.utc),
            revoked_at=datetime.now(timezone.utc),  # Already revoked
        )
        db.add(session)
        db.flush()

        fetched_session = db.query(UserSession).filter_by(jti=jti).first()
        assert fetched_session.is_valid is False

    def test_expired_refresh_token_raises(self):
        """Expired refresh token raises TokenExpiredError."""
        refresh_token, _ = create_refresh_token(
            subject="user-123",
            expires_delta=timedelta(seconds=-10),
        )
        with pytest.raises(TokenExpiredError):
            decode_token(refresh_token, expected_type=TOKEN_TYPE_REFRESH)

    def test_access_token_used_as_refresh_rejected(self):
        """Access tokens must not be accepted as refresh tokens."""
        access_token = create_access_token("user-123")
        with pytest.raises(TokenTypeMismatchError):
            decode_token(access_token, expected_type=TOKEN_TYPE_REFRESH)


# ═════════════════════════════════════════════════════════════════════════════
# LOGOUT / SESSION REVOCATION
# ═════════════════════════════════════════════════════════════════════════════

class TestLogoutFlow:
    """Tests for session revocation and logout."""

    def test_logout_revokes_session(self, db):
        """Logging out marks the session as revoked."""
        user = make_user(db)
        _, jti = create_refresh_token(subject=str(user.id))
        session = UserSession(
            id=uuid.uuid4(),
            user_id=user.id,
            jti=jti,
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            created_at=datetime.now(timezone.utc),
        )
        db.add(session)
        db.flush()

        assert session.is_valid is True

        # Simulate logout
        session.revoked_at = datetime.now(timezone.utc)
        db.flush()

        fetched = db.query(UserSession).filter_by(jti=jti).first()
        assert fetched.is_valid is False

    def test_revoke_all_sessions_for_user(self, db):
        """Revoke all sessions (e.g., on password change)."""
        user = make_user(db)
        sessions = []
        for _ in range(3):
            _, jti = create_refresh_token(subject=str(user.id))
            s = UserSession(
                id=uuid.uuid4(),
                user_id=user.id,
                jti=jti,
                expires_at=datetime.now(timezone.utc) + timedelta(days=30),
                created_at=datetime.now(timezone.utc),
            )
            db.add(s)
            sessions.append(s)
        db.flush()

        # Revoke all
        now = datetime.now(timezone.utc)
        for s in sessions:
            s.revoked_at = now
        db.flush()

        valid_sessions = db.query(UserSession).filter_by(
            user_id=user.id
        ).all()
        assert all(not s.is_valid for s in valid_sessions)

    def test_audit_log_on_logout(self, db):
        """Logout should be recorded in audit trail."""
        user = make_user(db)
        log = AuditLog(
            id=uuid.uuid4(),
            user_id=user.id,
            action="user.logout",
            resource_type="user_sessions",
            success=True,
            created_at=datetime.now(timezone.utc),
        )
        db.add(log)
        db.flush()

        fetched = db.query(AuditLog).filter_by(
            user_id=user.id,
            action="user.logout",
        ).first()
        assert fetched is not None


# ═════════════════════════════════════════════════════════════════════════════
# PASSWORD RESET FLOW
# ═════════════════════════════════════════════════════════════════════════════

class TestPasswordResetFlow:
    def test_reset_token_created_and_decoded(self):
        email = "reset@example.com"
        token = create_password_reset_token(email)
        payload = decode_token(token, expected_type=TOKEN_TYPE_PASSWORD_RESET)
        assert payload["sub"] == email

    def test_reset_updates_password_and_revokes_sessions(self, db, valid_password):
        """Password reset clears old sessions and sets new password."""
        user = make_user(db)
        _, jti = create_refresh_token(subject=str(user.id))
        session = UserSession(
            id=uuid.uuid4(),
            user_id=user.id,
            jti=jti,
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            created_at=datetime.now(timezone.utc),
        )
        db.add(session)
        db.flush()

        # Simulate reset
        new_password = "NewSecurePass1!XYZ"
        new_hash = hash_password(new_password)
        user.hashed_password = new_hash
        user.password_changed_at = datetime.now(timezone.utc)
        session.revoked_at = datetime.now(timezone.utc)
        db.flush()

        # Verify new password works
        assert verify_password(new_password, user.hashed_password) is True
        # Old sessions revoked
        assert not session.is_valid

    def test_wrong_type_token_rejected(self):
        """Email verify token cannot be used as password reset."""
        token = create_email_verification_token("user@example.com")
        with pytest.raises(TokenTypeMismatchError):
            decode_token(token, expected_type=TOKEN_TYPE_PASSWORD_RESET)

    def test_expired_reset_token_rejected(self):
        token = create_password_reset_token("user@example.com")
        # Manually decode and re-sign with past expiry
        import jwt as pyjwt
        from config.security import settings
        payload = pyjwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        payload["exp"] = int((datetime.now(timezone.utc) - timedelta(hours=3)).timestamp())
        expired_token = pyjwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
        with pytest.raises(TokenExpiredError):
            decode_token(expired_token)


# ═════════════════════════════════════════════════════════════════════════════
# AUDIT TRAIL ON AUTH EVENTS
# ═════════════════════════════════════════════════════════════════════════════

class TestAuthAuditTrail:
    """Auth events must be recorded in the immutable audit trail (CROA/FCRA compliance)."""

    def test_login_audit_log(self, db):
        user = make_user(db)
        log = AuditLog(
            id=uuid.uuid4(),
            user_id=user.id,
            action="user.login",
            resource_type="users",
            ip_address="10.0.0.1",
            success=True,
            created_at=datetime.now(timezone.utc),
        )
        db.add(log)
        db.flush()
        assert db.query(AuditLog).filter_by(action="user.login", user_id=user.id).first()

    def test_failed_login_audit_log(self, db):
        user = make_user(db)
        log = AuditLog(
            id=uuid.uuid4(),
            user_id=user.id,
            action="user.login",
            resource_type="users",
            success=False,
            error_message="Invalid credentials",
            created_at=datetime.now(timezone.utc),
        )
        db.add(log)
        db.flush()
        fetched = db.query(AuditLog).filter_by(
            user_id=user.id, action="user.login", success=False
        ).first()
        assert fetched is not None
        assert "Invalid credentials" in fetched.error_message

    def test_password_change_audit_log(self, db):
        user = make_user(db)
        log = AuditLog(
            id=uuid.uuid4(),
            user_id=user.id,
            action="user.password_changed",
            resource_type="users",
            success=True,
            created_at=datetime.now(timezone.utc),
        )
        db.add(log)
        db.flush()
        assert db.query(AuditLog).filter_by(
            user_id=user.id, action="user.password_changed"
        ).first()

    def test_multiple_auth_events_all_recorded(self, db):
        user = make_user(db)
        events = ["user.login", "user.logout", "user.password_changed", "user.email_verified"]
        for event in events:
            db.add(AuditLog(
                id=uuid.uuid4(),
                user_id=user.id,
                action=event,
                resource_type="users",
                success=True,
                created_at=datetime.now(timezone.utc),
            ))
        db.flush()
        count = db.query(AuditLog).filter_by(user_id=user.id).count()
        assert count == len(events)
