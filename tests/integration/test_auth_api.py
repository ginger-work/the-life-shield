"""
Integration tests for Auth API endpoints.
Tests: register, login, refresh, logout, me, forgot-password, reset-password.
"""
import pytest
from fastapi.testclient import TestClient


def test_register_creates_new_user(test_client):
    """POST /api/v1/auth/register should create user and return tokens."""
    response = test_client.post("/api/v1/auth/register", json={
        "email": "newuser@test.com",
        "password": "SecurePass1!",
        "first_name": "Test",
        "last_name": "User",
    })
    assert response.status_code == 201
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"
    assert data["role"] == "client"


def test_register_duplicate_email_returns_409(test_client):
    """Registering the same email twice should return 409."""
    payload = {
        "email": "dup@test.com",
        "password": "SecurePass1!",
        "first_name": "Dup",
        "last_name": "User",
    }
    test_client.post("/api/v1/auth/register", json=payload)
    response = test_client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 409


def test_register_weak_password_returns_422(test_client):
    """Weak password should fail validation."""
    response = test_client.post("/api/v1/auth/register", json={
        "email": "weakpass@test.com",
        "password": "short",
        "first_name": "Test",
        "last_name": "User",
    })
    assert response.status_code == 422


def test_login_returns_tokens(test_client, registered_user):
    """POST /api/v1/auth/login should return JWT tokens."""
    email, password = registered_user
    response = test_client.post("/api/v1/auth/login", json={
        "email": email,
        "password": password,
    })
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data


def test_login_wrong_password_returns_401(test_client, registered_user):
    """Wrong password should return 401."""
    email, _ = registered_user
    response = test_client.post("/api/v1/auth/login", json={
        "email": email,
        "password": "WrongPassword1!",
    })
    assert response.status_code == 401


def test_login_unknown_email_returns_401(test_client):
    """Unknown email should return 401."""
    response = test_client.post("/api/v1/auth/login", json={
        "email": "nobody@nowhere.com",
        "password": "AnyPass1!",
    })
    assert response.status_code == 401


def test_get_me_with_valid_token(test_client, auth_headers):
    """GET /api/v1/auth/me should return current user profile."""
    response = test_client.get("/api/v1/auth/me", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "email" in data
    assert "role" in data
    assert data["role"] == "client"


def test_get_me_without_token_returns_401(test_client):
    """GET /api/v1/auth/me without auth should return 401."""
    response = test_client.get("/api/v1/auth/me")
    assert response.status_code == 401


def test_refresh_token_returns_new_access_token(test_client, registered_user):
    """POST /api/v1/auth/refresh should return a new access token."""
    email, password = registered_user
    login_resp = test_client.post("/api/v1/auth/login", json={
        "email": email, "password": password
    })
    refresh_token = login_resp.json()["refresh_token"]

    response = test_client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data


def test_refresh_with_invalid_token_returns_401(test_client):
    """Invalid refresh token should return 401."""
    response = test_client.post("/api/v1/auth/refresh", json={"refresh_token": "invalid.token.here"})
    assert response.status_code == 401


def test_logout_returns_204(test_client, auth_headers):
    """POST /api/v1/auth/logout should return 204."""
    response = test_client.post("/api/v1/auth/logout", headers=auth_headers)
    assert response.status_code == 204


def test_forgot_password_always_returns_200(test_client):
    """POST /api/v1/auth/forgot-password should return 200 regardless of email existence."""
    # Known email
    response1 = test_client.post("/api/v1/auth/forgot-password", json={"email": "anyone@test.com"})
    assert response1.status_code == 200

    # Unknown email — should still return 200 (prevent enumeration)
    response2 = test_client.post("/api/v1/auth/forgot-password", json={"email": "nobody@fake.com"})
    assert response2.status_code == 200
