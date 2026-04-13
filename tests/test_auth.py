"""
The Life Shield - Authentication Test Suite
Tests for signup, login, refresh, me, logout, email verify, and password reset.
Uses pytest-asyncio + httpx AsyncClient.
"""

import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from main import app
from config.security import settings, UserRole
from database.connection import get_db
from models.base import Base
from models.user import User, UserSession
from middleware.auth import hash_password, create_refresh_token, create_email_verify_token


# ─────────────────────────────────────────────
# TEST DATABASE SETUP (in-memory SQLite)
# ─────────────────────────────────────────────

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(TEST_DB_URL, echo=False)
TestSessionLocal = async_sessionmaker(test_engine, expire_on_commit=False)


@pytest_asyncio.fixture(scope="function", autouse=True)
async def setup_test_db():
    """Create tables before each test, drop after."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def override_get_db():
    async with TestSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


app.dependency_overrides[get_db] = override_get_db


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def db_session():
    async with TestSessionLocal() as session:
        yield session


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

VALID_SIGNUP = {
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
}


async def create_verified_user(db: AsyncSession, email: str = "john@example.com", role: UserRole = UserRole.CLIENT) -> User:
    """Helper to insert a verified user directly into DB."""
    user = User(
        email=email,
        hashed_password=hash_password("SecureP@ss1!"),
        first_name="John",
        last_name="Smith",
        role=role,
        is_active=True,
        is_verified=True,
        email_verified_at=datetime.now(timezone.utc),
        email_consent=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def get_auth_tokens(client: AsyncClient, email: str = "john@example.com") -> dict:
    """Helper: login and return token dict."""
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "SecureP@ss1!", "device_type": "web"},
    )
    assert resp.status_code == 200
    return resp.json()


# ─────────────────────────────────────────────
# SIGNUP TESTS
# ─────────────────────────────────────────────

class TestSignup:
    @pytest.mark.asyncio
    async def test_signup_success(self, client, db_session):
        with patch("api.auth._send_verification_email", new_callable=AsyncMock):
            resp = await client.post("/api/v1/auth/signup", json=VALID_SIGNUP)
        assert resp.status_code == 201
        data = resp.json()
        assert data["email"] == VALID_SIGNUP["email"]
        assert data["requires_verification"] is True
        assert "user_id" in data

    @pytest.mark.asyncio
    async def test_signup_duplicate_email(self, client, db_session):
        with patch("api.auth._send_verification_email", new_callable=AsyncMock):
            await client.post("/api/v1/auth/signup", json=VALID_SIGNUP)
            resp = await client.post("/api/v1/auth/signup", json=VALID_SIGNUP)
        assert resp.status_code == 409
        assert "already exists" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_signup_weak_password(self, client):
        payload = {**VALID_SIGNUP, "password": "weak"}
        resp = await client.post("/api/v1/auth/signup", json=payload)
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_signup_requires_terms(self, client):
        payload = {**VALID_SIGNUP, "terms_accepted": False}
        resp = await client.post("/api/v1/auth/signup", json=payload)
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_signup_requires_croa_disclosure(self, client):
        payload = {**VALID_SIGNUP, "croa_disclosure_accepted": False}
        resp = await client.post("/api/v1/auth/signup", json=payload)
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_signup_requires_service_disclosure(self, client):
        payload = {**VALID_SIGNUP, "service_disclosure_accepted": False}
        resp = await client.post("/api/v1/auth/signup", json=payload)
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_signup_invalid_email(self, client):
        payload = {**VALID_SIGNUP, "email": "not-an-email"}
        resp = await client.post("/api/v1/auth/signup", json=payload)
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_signup_consent_stored(self, client, db_session):
        with patch("api.auth._send_verification_email", new_callable=AsyncMock):
            resp = await client.post("/api/v1/auth/signup", json=VALID_SIGNUP)
        assert resp.status_code == 201
        user_id = resp.json()["user_id"]

        from sqlalchemy import select as sa_select
        result = await db_session.execute(
            sa_select(User).where(User.id == uuid.UUID(user_id))
        )
        user = result.scalar_one()
        assert user.sms_consent is True
        assert user.email_consent is True
        assert user.voice_consent is False
        assert user.sms_consent_at is not None


# ─────────────────────────────────────────────
# LOGIN TESTS
# ─────────────────────────────────────────────

class TestLogin:
    @pytest.mark.asyncio
    async def test_login_success(self, client, db_session):
        await create_verified_user(db_session)
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "john@example.com", "password": "SecureP@ss1!"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"
        assert data["role"] == "client"

    @pytest.mark.asyncio
    async def test_login_wrong_password(self, client, db_session):
        await create_verified_user(db_session)
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "john@example.com", "password": "WrongPassword1!"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_login_unknown_email(self, client):
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "nobody@example.com", "password": "SecureP@ss1!"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_login_inactive_user(self, client, db_session):
        user = await create_verified_user(db_session)
        user.is_active = False
        await db_session.commit()

        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "john@example.com", "password": "SecureP@ss1!"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_login_creates_session(self, client, db_session):
        await create_verified_user(db_session)
        await client.post(
            "/api/v1/auth/login",
            json={"email": "john@example.com", "password": "SecureP@ss1!", "device_type": "web"},
        )
        from sqlalchemy import select as sa_select
        result = await db_session.execute(sa_select(UserSession))
        sessions = result.scalars().all()
        assert len(sessions) == 1
        assert sessions[0].device_type == "web"


# ─────────────────────────────────────────────
# REFRESH TOKEN TESTS
# ─────────────────────────────────────────────

class TestRefresh:
    @pytest.mark.asyncio
    async def test_refresh_success(self, client, db_session):
        await create_verified_user(db_session)
        tokens = await get_auth_tokens(client)

        resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": tokens["refresh_token"]},
        )
        assert resp.status_code == 200
        new_tokens = resp.json()
        assert "access_token" in new_tokens
        assert new_tokens["access_token"] != tokens["access_token"]
        assert new_tokens["refresh_token"] != tokens["refresh_token"]

    @pytest.mark.asyncio
    async def test_refresh_rotates_old_token(self, client, db_session):
        """Using an old refresh token after rotation should fail (single-use)."""
        await create_verified_user(db_session)
        tokens = await get_auth_tokens(client)

        # Use refresh token once
        await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})

        # Try to use same refresh token again
        resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_refresh_invalid_token(self, client):
        resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": "notavalidtoken"})
        assert resp.status_code == 401


# ─────────────────────────────────────────────
# ME ENDPOINT TESTS
# ─────────────────────────────────────────────

class TestMe:
    @pytest.mark.asyncio
    async def test_get_me_success(self, client, db_session):
        await create_verified_user(db_session)
        tokens = await get_auth_tokens(client)

        resp = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == "john@example.com"
        assert data["role"] == "client"
        assert data["is_verified"] is True

    @pytest.mark.asyncio
    async def test_get_me_no_token(self, client):
        resp = await client.get("/api/v1/auth/me")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_get_me_invalid_token(self, client):
        resp = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer thisisnotvalid"},
        )
        assert resp.status_code == 401


# ─────────────────────────────────────────────
# LOGOUT TESTS
# ─────────────────────────────────────────────

class TestLogout:
    @pytest.mark.asyncio
    async def test_logout_success(self, client, db_session):
        await create_verified_user(db_session)
        tokens = await get_auth_tokens(client)

        resp = await client.post(
            "/api/v1/auth/logout",
            json={"refresh_token": tokens["refresh_token"]},
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_logout_all_devices(self, client, db_session):
        """Login twice, then logout all devices."""
        await create_verified_user(db_session)
        tokens1 = await get_auth_tokens(client)
        tokens2 = await get_auth_tokens(client)

        resp = await client.post(
            "/api/v1/auth/logout",
            json={"all_devices": True},
            headers={"Authorization": f"Bearer {tokens1['access_token']}"},
        )
        assert resp.status_code == 200
        assert "2" in resp.json()["message"] or "session" in resp.json()["message"]

    @pytest.mark.asyncio
    async def test_logout_requires_auth(self, client):
        resp = await client.post("/api/v1/auth/logout", json={})
        assert resp.status_code == 401


# ─────────────────────────────────────────────
# EMAIL VERIFICATION TESTS
# ─────────────────────────────────────────────

class TestEmailVerification:
    @pytest.mark.asyncio
    async def test_verify_email_success(self, client, db_session):
        with patch("api.auth._send_verification_email", new_callable=AsyncMock):
            signup_resp = await client.post("/api/v1/auth/signup", json=VALID_SIGNUP)
        user_id = signup_resp.json()["user_id"]

        token = create_email_verify_token(user_id)
        resp = await client.post("/api/v1/auth/verify-email", json={"token": token})
        assert resp.status_code == 200
        assert "verified" in resp.json()["message"].lower()

    @pytest.mark.asyncio
    async def test_verify_email_invalid_token(self, client):
        resp = await client.post("/api/v1/auth/verify-email", json={"token": "badtoken"})
        assert resp.status_code == 401


# ─────────────────────────────────────────────
# PASSWORD RESET TESTS
# ─────────────────────────────────────────────

class TestPasswordReset:
    @pytest.mark.asyncio
    async def test_request_reset_known_email(self, client, db_session):
        await create_verified_user(db_session)
        with patch("api.auth._send_password_reset_email", new_callable=AsyncMock):
            resp = await client.post(
                "/api/v1/auth/password-reset",
                json={"email": "john@example.com"},
            )
        assert resp.status_code == 200
        assert "reset link" in resp.json()["message"].lower() or "receive" in resp.json()["message"].lower()

    @pytest.mark.asyncio
    async def test_request_reset_unknown_email(self, client):
        """Should return 200 regardless (no enumeration)."""
        resp = await client.post(
            "/api/v1/auth/password-reset",
            json={"email": "nobody@example.com"},
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_confirm_reset_success(self, client, db_session):
        user = await create_verified_user(db_session)
        token = create_password_reset_token_for_test(str(user.id))

        resp = await client.post(
            "/api/v1/auth/password-reset/confirm",
            json={"token": token, "new_password": "NewP@ssword1!", "confirm_password": "NewP@ssword1!"},
        )
        assert resp.status_code == 200

        # New password should work
        login_resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "john@example.com", "password": "NewP@ssword1!"},
        )
        assert login_resp.status_code == 200

    @pytest.mark.asyncio
    async def test_confirm_reset_passwords_mismatch(self, client, db_session):
        user = await create_verified_user(db_session)
        token = create_password_reset_token_for_test(str(user.id))
        resp = await client.post(
            "/api/v1/auth/password-reset/confirm",
            json={"token": token, "new_password": "NewP@ssword1!", "confirm_password": "Different1!"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_confirm_reset_invalid_token(self, client):
        resp = await client.post(
            "/api/v1/auth/password-reset/confirm",
            json={"token": "badtoken", "new_password": "NewP@ssword1!", "confirm_password": "NewP@ssword1!"},
        )
        assert resp.status_code == 401


# ─────────────────────────────────────────────
# RBAC TESTS
# ─────────────────────────────────────────────

class TestRBAC:
    @pytest.mark.asyncio
    async def test_client_cannot_access_admin_agents(self, client, db_session):
        """CLIENT role should get 403 on POST /agents."""
        user = await create_verified_user(db_session, role=UserRole.CLIENT)
        tokens = await get_auth_tokens(client)

        resp = await client.post(
            "/api/v1/agents",
            json={
                "agent_name": "test_agent",
                "display_name": "Test Agent",
            },
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_unverified_user_blocked(self, client, db_session):
        """Unverified users cannot access protected endpoints."""
        user = User(
            email="unverified@example.com",
            hashed_password=hash_password("SecureP@ss1!"),
            first_name="Un", last_name="Verified",
            role=UserRole.CLIENT,
            is_active=True,
            is_verified=False,
            email_consent=True,
        )
        db_session.add(user)
        await db_session.commit()

        # Login succeeds for unverified user
        login_resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "unverified@example.com", "password": "SecureP@ss1!"},
        )
        assert login_resp.status_code == 200
        access_token = login_resp.json()["access_token"]

        # But /me requires verified
        me_resp = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert me_resp.status_code == 403


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def create_password_reset_token_for_test(user_id: str) -> str:
    """Use internal function directly for test token generation."""
    from middleware.auth import create_password_reset_token
    return create_password_reset_token(user_id)
