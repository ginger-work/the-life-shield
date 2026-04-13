# The Life Shield — API Documentation

**Version:** 1.0.0  
**Base URL:** `https://api.thelifeshield.com/api/v1`  
**Swagger UI:** `/api/docs`  
**ReDoc:** `/api/redoc`  
**OpenAPI JSON:** `/api/openapi.json`

---

## Table of Contents

1. [Setup & Installation](#setup--installation)
2. [Authentication Flow](#authentication-flow)
3. [RBAC — Roles & Permissions](#rbac--roles--permissions)
4. [Auth Endpoints](#auth-endpoints)
5. [Agent Endpoints](#agent-endpoints)
6. [Error Reference](#error-reference)
7. [Rate Limits](#rate-limits)
8. [Compliance Notes](#compliance-notes)

---

## Setup & Installation

### Prerequisites
- Python 3.11+
- PostgreSQL 15+ (production) or SQLite (dev/test)
- Redis 7+ (token revocation + rate limiting)

### Local Dev Setup

```bash
# 1. Clone and enter project
cd the-life-shield

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env — at minimum set SECRET_KEY and DATABASE_URL

# 5. Run database migrations (Alembic)
alembic upgrade head
# OR for dev with auto-create:
# Set DEBUG=true — tables auto-created on startup

# 6. Start the server
uvicorn main:app --reload --port 8000

# API available at:
# http://localhost:8000/api/docs  (Swagger)
# http://localhost:8000/api/redoc (ReDoc)
```

### Running Tests

```bash
pytest
# With coverage report:
pytest --cov=. --cov-report=html
```

### Docker (Quick Start)

```dockerfile
# Dockerfile (minimal example)
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## Authentication Flow

```
SIGNUP FLOW
───────────────────────────────────────────────────────
1. POST /auth/signup
   ├── Validate: email, password strength, required disclosures
   ├── Create user (CLIENT role)
   ├── Log consent + CROA disclosure acceptance (CROA compliance)
   ├── Send verification email (background task)
   └── Return: {user_id, email, requires_verification: true}

2. POST /auth/verify-email  (token from email)
   └── Mark account as verified

3. POST /auth/login
   ├── Validate credentials
   ├── Issue access_token (30 min TTL) + refresh_token (30 day TTL)
   ├── Store refresh session (JTI) in DB
   └── Return: {access_token, refresh_token, role, expires_in}

ACCESS TOKEN FLOW
───────────────────────────────────────────────────────
4. Include token in all requests:
   Authorization: Bearer <access_token>

5. Token expires → POST /auth/refresh
   ├── Exchange refresh_token for new access + refresh pair
   ├── Old refresh token is REVOKED (single-use rotation)
   └── Return: new {access_token, refresh_token}

LOGOUT
───────────────────────────────────────────────────────
6. POST /auth/logout
   ├── Revoke current refresh token
   └── Optional: all_devices=true → revoke all sessions

PASSWORD RESET
───────────────────────────────────────────────────────
7. POST /auth/password-reset   (enter email)
8. POST /auth/password-reset/confirm  (token + new password)
   └── Revokes ALL existing sessions (forces re-login)
```

### ASCII Flow Diagram

```
Client                   API                      DB               Email
  |                       |                        |                  |
  |--POST /signup-------->|                        |                  |
  |                       |--INSERT user---------->|                  |
  |                       |--INSERT audit_log----->|                  |
  |                       |                        |--send verify---->|
  |<--201 {user_id}-------|                        |                  |
  |                                                                   |
  |<--verification email---------------------------------------------|
  |                                                                   |
  |--POST /verify-email-->|                        |                  |
  |                       |--UPDATE user verified->|                  |
  |<--200 OK--------------|                        |                  |
  |                                                |                  |
  |--POST /login--------->|                        |                  |
  |                       |--SELECT user---------->|                  |
  |                       |--INSERT user_session-->|                  |
  |<--200 {tokens}--------|                        |                  |
  |                                                |                  |
  |--GET /auth/me-------->|                        |                  |
  |   (Bearer token)      |--SELECT user---------->|                  |
  |<--200 {profile}-------|                        |                  |
```

---

## RBAC — Roles & Permissions

| Permission              | ADMIN | AGENT | CLIENT |
|-------------------------|:-----:|:-----:|:------:|
| agents:read             | ✅    | ✅    | ❌     |
| agents:write            | ✅    | ❌    | ❌     |
| agents:delete           | ✅    | ❌    | ❌     |
| clients:read            | ✅    | ✅    | ❌     |
| clients:write           | ✅    | ❌    | ❌     |
| disputes:read           | ✅    | ✅    | ✅     |
| disputes:write          | ✅    | ✅    | ❌     |
| disputes:approve        | ✅    | ❌    | ❌     |
| communications:read     | ✅    | ✅    | ✅     |
| billing:write           | ✅    | ❌    | ❌     |
| compliance:override     | ✅    | ❌    | ❌     |
| admin:dashboard         | ✅    | ❌    | ❌     |
| profile:read            | ✅    | ✅    | ✅     |
| vault:read              | ✅    | ✅    | ✅     |
| vault:write             | ✅    | ❌    | ✅     |

---

## Auth Endpoints

---

### `POST /auth/signup`

Register a new client account.

**Request Body:**
```json
{
  "first_name": "John",
  "last_name": "Smith",
  "email": "john.smith@example.com",
  "password": "SecureP@ss1!",
  "phone": "+19195551234",
  "sms_consent": true,
  "email_consent": true,
  "voice_consent": false,
  "terms_accepted": true,
  "service_disclosure_accepted": true,
  "croa_disclosure_accepted": true
}
```

**Password Requirements:**  
- 8+ characters  
- At least 1 uppercase, 1 lowercase, 1 digit, 1 special character

**Consent Fields (FCC Compliance):**  
- `sms_consent` — consent to receive SMS messages  
- `email_consent` — consent to receive email  
- `voice_consent` — consent to receive voice calls  
- All consent timestamps are stored in the audit trail

**Required Disclosures (CROA Compliance):**  
- `terms_accepted` — must be `true`  
- `service_disclosure_accepted` — AI service disclosure accepted  
- `croa_disclosure_accepted` — client acknowledges 3-day cancellation right

**Response `201`:**
```json
{
  "message": "Registration successful. Please check your email to verify your account.",
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "email": "john.smith@example.com",
  "requires_verification": true
}
```

**Errors:**
- `409` — Email already registered
- `422` — Validation error (password weak, missing disclosure, etc.)

---

### `POST /auth/login`

Authenticate and receive tokens.

**Request Body:**
```json
{
  "email": "john.smith@example.com",
  "password": "SecureP@ss1!",
  "device_type": "web",
  "device_name": "Chrome on Mac"
}
```

**Response `200`:**
```json
{
  "access_token": "eyJhbGci...",
  "refresh_token": "eyJhbGci...",
  "token_type": "bearer",
  "expires_in": 1800,
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "role": "client"
}
```

**Account Lockout:**  
5 consecutive failed attempts → account locked for 15 minutes.

**Errors:**
- `401` — Invalid email or password
- `403` — Account disabled or locked

---

### `POST /auth/refresh`

Exchange refresh token for a new token pair (rotation — old token revoked).

**Request Body:**
```json
{
  "refresh_token": "eyJhbGci..."
}
```

**Response `200`:** Same as login response.

**Errors:**
- `401` — Token revoked, expired, or invalid

---

### `GET /auth/me`

Get current user profile. Requires verified account.

**Headers:** `Authorization: Bearer <access_token>`

**Response `200`:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "email": "john.smith@example.com",
  "first_name": "John",
  "last_name": "Smith",
  "full_name": "John Smith",
  "role": "client",
  "phone": "+19195551234",
  "is_verified": true,
  "is_active": true,
  "sms_consent": true,
  "email_consent": true,
  "voice_consent": false,
  "last_login_at": "2026-04-13T18:00:00Z",
  "created_at": "2026-04-01T12:00:00Z"
}
```

---

### `POST /auth/logout`

Revoke current session or all sessions.

**Headers:** `Authorization: Bearer <access_token>`

**Request Body:**
```json
{
  "refresh_token": "eyJhbGci...",
  "all_devices": false
}
```

Pass `"all_devices": true` to revoke every session (sign out everywhere).

**Response `200`:**
```json
{"message": "Logged out successfully."}
```

---

### `POST /auth/verify-email`

Confirm email using token from verification email.

**Request Body:**
```json
{
  "token": "eyJhbGci..."
}
```

**Response `200`:**
```json
{"message": "Email verified. You can now log in."}
```

---

### `POST /auth/password-reset`

Request a password reset link (always returns 200 — no enumeration).

**Request Body:**
```json
{"email": "john.smith@example.com"}
```

**Response `200`:**
```json
{"message": "If that email exists, you'll receive a password reset link shortly."}
```

---

### `POST /auth/password-reset/confirm`

Set new password using the token from the reset email.

**Request Body:**
```json
{
  "token": "eyJhbGci...",
  "new_password": "NewP@ssword1!",
  "confirm_password": "NewP@ssword1!"
}
```

**Response `200`:**
```json
{"message": "Password updated. Please log in with your new password."}
```

Note: All existing sessions are revoked on successful reset.

---

## Agent Endpoints

All agent endpoints require **ADMIN** role unless noted.  
`GET /agents` and `GET /agents/{id}` accept **ADMIN or AGENT** role.

---

### `GET /agents`

List all agent profiles (paginated).

**Headers:** `Authorization: Bearer <admin_access_token>`

**Query Params:**
- `page` (default: 1)
- `per_page` (default: 25, max: 100)
- `is_active` (bool, optional)
- `role` (string, optional)

**Response `200`:**
```json
{
  "items": [
    {
      "id": "...",
      "agent_name": "tim_shaw",
      "display_name": "Tim Shaw",
      "role": "client_success_agent",
      "tone": "calm, professional, confident",
      "disclosure_text": "AI Client Agent for The Life Shield",
      "voice_provider": "elevenlabs",
      "max_clients": 2000,
      "assigned_client_count": 247,
      "performance_rating": 4.8,
      "is_active": true,
      "created_at": "2026-01-15T00:00:00Z"
    }
  ],
  "total": 1,
  "page": 1,
  "per_page": 25,
  "pages": 1
}
```

---

### `POST /agents`

Create a new AI agent profile.

**Request Body:**
```json
{
  "agent_name": "tim_shaw",
  "display_name": "Tim Shaw",
  "role": "client_success_agent",
  "tone": "calm, professional, confident",
  "communication_style": "clear, actionable, empathetic",
  "greeting_template": "Hi, I'm Tim Shaw, your client success agent.",
  "disclosure_text": "AI Client Agent for The Life Shield",
  "voice_provider": "elevenlabs",
  "voice_id": "tim_shaw_voice_001",
  "speech_rate": 1.0,
  "pitch": 1.0,
  "avatar_type": "tavus",
  "avatar_id": "avatar_tim_shaw_001",
  "specialties": ["credit_disputes", "financial_education", "scheduling"],
  "knows_fcra": true,
  "knows_croa": true,
  "knows_fcc_rules": true,
  "knows_nc_regulations": true,
  "can_answer_faq": true,
  "can_explain_status": true,
  "can_schedule_meetings": true,
  "can_recommend_products": false,
  "can_file_disputes": false,
  "max_clients": 2000
}
```

**Important:** `can_make_promises` and `can_override_decisions` are **always `false`** and cannot be changed via API (compliance hardcoded).

**Response `201`:** Full `AgentResponse` object.

---

### `GET /agents/{agent_id}`

Get a single agent profile by UUID.

**Response `200`:** Full `AgentResponse` object.  
**Response `404`:** Agent not found.

---

### `PUT /agents/{agent_id}`

Update agent profile. All fields optional.

**Request Body:** Any subset of `AgentUpdateRequest` fields.

**Response `200`:** Updated `AgentResponse`.

---

### `DELETE /agents/{agent_id}`

Soft-deactivate an agent (never hard-deleted — preserves audit trail).  
Deactivated agents stop accepting new client assignments.

**Response `200`:**
```json
{"message": "Agent 'Tim Shaw' has been deactivated."}
```

---

### `POST /agents/{agent_id}/assign`

Assign an agent to a client. Replaces any existing active assignment.

**Request Body:**
```json
{
  "client_user_id": "550e8400-e29b-41d4-a716-446655440000",
  "agent_id": "661e9511-e29b-41d4-a716-446655440111",
  "notes": "VIP client, high priority"
}
```

**Response `201`:**
```json
{"message": "Agent 'Tim Shaw' assigned to client 'John Smith'."}
```

---

## Error Reference

All errors follow this envelope:

```json
{
  "error": "ERROR_CODE",
  "message": "Human-readable description",
  "details": { ... },
  "correlation_id": "uuid"
}
```

| HTTP Code | Error Code          | Meaning                                    |
|-----------|---------------------|--------------------------------------------|
| 400       | BAD_REQUEST         | Invalid request structure                  |
| 401       | UNAUTHORIZED        | Missing or invalid credentials             |
| 403       | FORBIDDEN           | Insufficient role/permissions              |
| 404       | NOT_FOUND           | Resource does not exist                    |
| 409       | CONFLICT            | Duplicate resource (e.g., email)           |
| 422       | VALIDATION_ERROR    | Pydantic validation failure (field errors) |
| 429       | RATE_LIMITED        | Too many requests                          |
| 500       | INTERNAL_ERROR      | Unexpected server error                    |

---

## Rate Limits

| Endpoint                     | Limit        |
|------------------------------|--------------|
| `POST /auth/signup`          | 5/minute     |
| `POST /auth/login`           | 10/minute    |
| `POST /auth/password-reset`  | 3/hour       |
| `POST /auth/refresh`         | 20/minute    |
| All other endpoints          | 100/minute   |

Rate limit headers returned on all responses:
- `X-RateLimit-Limit`
- `X-RateLimit-Remaining`
- `X-RateLimit-Reset`

---

## Compliance Notes

### CROA (Credit Repair Organizations Act)
- All disclosures accepted at signup are logged with timestamp in `audit_trail`
- `croa_disclosure_accepted` field required at signup — enforced in validation
- 3-day cancellation right acknowledged at signup
- No payment before disclosure + contract (enforce in billing module)

### FCC (Communication Consent)
- `sms_consent`, `email_consent`, `voice_consent` stored with timestamps
- Consent checked before every outbound communication
- Opt-out requests honored immediately (update consent, escalate to supervisor)

### FCRA (Fair Credit Reporting Act)
- Dispute filing requires Analyst + Compliance + Human Supervisor approval
- Investigation timelines enforced (30-day rule)
- All dispute actions logged in `audit_trail`

### General Security
- Passwords hashed with bcrypt (12 rounds)
- JWT access tokens: 30-minute TTL (HS256)
- Refresh tokens: 30-day TTL, single-use rotation
- Account lockout: 5 failed attempts → 15-minute lock
- All sensitive actions recorded in `audit_trail` (immutable)
- Soft-delete pattern — data never permanently deleted
- Correlation IDs on every request (`X-Correlation-ID` header)

---

*The Life Shield API v1.0.0 — Built for compliance, designed for scale.*
