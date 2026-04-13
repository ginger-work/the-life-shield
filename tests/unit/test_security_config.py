"""
The Life Shield — Unit Tests: Security Configuration
Tests for RBAC permissions, token expiry helpers, and security constants.
"""

import pytest

from config.security import (
    ROLE_PERMISSIONS,
    TOKEN_TYPE_ACCESS,
    TOKEN_TYPE_EMAIL_VERIFY,
    TOKEN_TYPE_PASSWORD_RESET,
    TOKEN_TYPE_REFRESH,
    UserRole,
    get_access_token_expiry,
    get_email_verify_expiry,
    get_password_reset_expiry,
    get_refresh_token_expiry,
    has_permission,
    settings,
)


# ═════════════════════════════════════════════════════════════════════════════
# ROLE PERMISSIONS (RBAC)
# ═════════════════════════════════════════════════════════════════════════════

class TestRolePermissions:
    """Tests for ROLE_PERMISSIONS and has_permission()."""

    # ADMIN permissions
    def test_admin_has_full_agent_permissions(self):
        for perm in ["agents:read", "agents:write", "agents:delete"]:
            assert has_permission(UserRole.ADMIN, perm), f"Admin missing: {perm}"

    def test_admin_has_compliance_override(self):
        assert has_permission(UserRole.ADMIN, "compliance:override")

    def test_admin_has_audit_read(self):
        assert has_permission(UserRole.ADMIN, "audit:read")

    def test_admin_has_admin_dashboard(self):
        assert has_permission(UserRole.ADMIN, "admin:dashboard")

    def test_admin_has_billing_write(self):
        assert has_permission(UserRole.ADMIN, "billing:write")

    # AGENT permissions
    def test_agent_can_read_clients(self):
        assert has_permission(UserRole.AGENT, "clients:read")

    def test_agent_can_read_disputes(self):
        assert has_permission(UserRole.AGENT, "disputes:read")

    def test_agent_cannot_delete_clients(self):
        assert not has_permission(UserRole.AGENT, "clients:delete")

    def test_agent_cannot_access_billing_write(self):
        assert not has_permission(UserRole.AGENT, "billing:write")

    def test_agent_cannot_override_compliance(self):
        assert not has_permission(UserRole.AGENT, "compliance:override")

    # CLIENT permissions
    def test_client_can_read_profile(self):
        assert has_permission(UserRole.CLIENT, "profile:read")

    def test_client_can_write_vault(self):
        assert has_permission(UserRole.CLIENT, "vault:write")

    def test_client_can_enroll_sessions(self):
        assert has_permission(UserRole.CLIENT, "sessions:enroll")

    def test_client_cannot_access_admin_dashboard(self):
        assert not has_permission(UserRole.CLIENT, "admin:dashboard")

    def test_client_cannot_write_agents(self):
        assert not has_permission(UserRole.CLIENT, "agents:write")

    def test_client_cannot_approve_disputes(self):
        assert not has_permission(UserRole.CLIENT, "disputes:approve")

    def test_client_cannot_delete_clients(self):
        assert not has_permission(UserRole.CLIENT, "clients:delete")

    # Edge cases
    def test_unknown_permission_returns_false(self):
        assert not has_permission(UserRole.ADMIN, "nonexistent:permission")

    def test_all_roles_have_permission_list(self):
        for role in UserRole:
            assert role in ROLE_PERMISSIONS
            assert isinstance(ROLE_PERMISSIONS[role], list)


# ═════════════════════════════════════════════════════════════════════════════
# TOKEN EXPIRY HELPERS
# ═════════════════════════════════════════════════════════════════════════════

class TestTokenExpiry:
    def test_access_token_expiry_matches_settings(self):
        from datetime import timedelta
        expected = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        assert get_access_token_expiry() == expected

    def test_refresh_token_expiry_matches_settings(self):
        from datetime import timedelta
        expected = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        assert get_refresh_token_expiry() == expected

    def test_email_verify_expiry_matches_settings(self):
        from datetime import timedelta
        expected = timedelta(hours=settings.EMAIL_VERIFY_TOKEN_EXPIRE_HOURS)
        assert get_email_verify_expiry() == expected

    def test_password_reset_expiry_matches_settings(self):
        from datetime import timedelta
        expected = timedelta(hours=settings.PASSWORD_RESET_TOKEN_EXPIRE_HOURS)
        assert get_password_reset_expiry() == expected

    def test_access_token_shorter_than_refresh(self):
        assert get_access_token_expiry() < get_refresh_token_expiry()

    def test_password_reset_shorter_than_email_verify(self):
        # Reset tokens should be short-lived
        assert get_password_reset_expiry() <= get_email_verify_expiry()


# ═════════════════════════════════════════════════════════════════════════════
# TOKEN TYPE CONSTANTS
# ═════════════════════════════════════════════════════════════════════════════

class TestTokenTypeConstants:
    def test_access_token_type(self):
        assert TOKEN_TYPE_ACCESS == "access"

    def test_refresh_token_type(self):
        assert TOKEN_TYPE_REFRESH == "refresh"

    def test_email_verify_type(self):
        assert TOKEN_TYPE_EMAIL_VERIFY == "email_verify"

    def test_password_reset_type(self):
        assert TOKEN_TYPE_PASSWORD_RESET == "password_reset"

    def test_all_types_are_distinct(self):
        types = {TOKEN_TYPE_ACCESS, TOKEN_TYPE_REFRESH, TOKEN_TYPE_EMAIL_VERIFY, TOKEN_TYPE_PASSWORD_RESET}
        assert len(types) == 4


# ═════════════════════════════════════════════════════════════════════════════
# SECURITY SETTINGS
# ═════════════════════════════════════════════════════════════════════════════

class TestSecuritySettings:
    def test_algorithm_is_hs256(self):
        assert settings.ALGORITHM == "HS256"

    def test_bcrypt_rounds_positive(self):
        assert settings.BCRYPT_ROUNDS > 0

    def test_secret_key_present(self):
        assert settings.SECRET_KEY
        assert len(settings.SECRET_KEY) >= 16

    def test_api_prefix(self):
        assert settings.API_V1_PREFIX == "/api/v1"

    def test_allowed_origins_list(self):
        assert isinstance(settings.ALLOWED_ORIGINS, list)
        assert len(settings.ALLOWED_ORIGINS) > 0
