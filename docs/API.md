# The Life Shield — API Documentation

**Base URL:** `https://api.thelifeshield.com/api/v1`  
**Dev URL:** `http://localhost:8000/api/v1`  
**API Docs (Swagger):** `/api/docs`  
**API Docs (ReDoc):** `/api/redoc`

---

## Authentication

All protected endpoints require a Bearer JWT token in the `Authorization` header:

```
Authorization: Bearer <access_token>
```

### Endpoints

#### POST /auth/register
Register a new client account.

**Request:**
```json
{
  "email": "client@example.com",
  "password": "SecurePass1!",
  "first_name": "John",
  "last_name": "Smith",
  "sms_consent": true,
  "email_consent": true
}
```

**Response:** `201 Created`
```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer",
  "expires_in": 1800,
  "user_id": "uuid",
  "role": "client"
}
```

#### POST /auth/login
**Request:** `{ "email": "...", "password": "..." }`  
**Response:** Same as register.

#### POST /auth/refresh
**Request:** `{ "refresh_token": "eyJ..." }`  
**Response:** New access + refresh tokens.

#### POST /auth/logout
**Headers:** Bearer token required.  
**Response:** `204 No Content`

#### GET /auth/me
**Response:**
```json
{
  "id": "uuid",
  "email": "client@example.com",
  "first_name": "John",
  "last_name": "Smith",
  "role": "client",
  "status": "active",
  "sms_consent": true,
  "email_consent": true,
  "created_at": "2026-04-13T00:00:00Z"
}
```

---

## Credit Reports

#### POST /credit/soft-pull
Pull soft credit report (no score impact). Background task.

**Request:** `{}`  
**Response:** `{ "success": true, "message": "Credit report pull started" }`

#### GET /credit/reports
Get latest credit reports for authenticated client.

**Response:**
```json
{
  "success": true,
  "reports": [
    { "bureau": "equifax", "score": 652, "pulled_at": "2026-04-13T..." }
  ]
}
```

#### GET /credit/score-history?days=90
Score history for chart visualization.

#### GET /credit/tradelines
All tradelines, inquiries, and negative items.

---

## Disputes

### Approval Flow (MANDATORY per CROA)
1. `POST /disputes` — Creates dispute case + generates letter  
2. `POST /disputes/{id}/approve-letter` — Client approves (REQUIRED)  
3. `POST /disputes/{id}/file` — Files to bureau (after approval only)  
4. `GET /disputes/{id}` — Monitor status  
5. `POST /disputes/{id}/bureau-response` — Record bureau response  

#### POST /disputes
Create new dispute case.

**Request:**
```json
{
  "tradeline_id": "uuid",
  "bureau": "equifax",
  "dispute_reason": "inaccurate",
  "client_statement": "Optional client explanation"
}
```

**Dispute Reasons:** `inaccurate`, `incomplete`, `unverifiable`, `obsolete`, `fraudulent`, `not_mine`, `wrong_balance`, `wrong_status`, `duplicate`

#### GET /disputes
List all disputes for current client.

#### GET /disputes/{id}
Full dispute detail including bureau responses.

#### POST /disputes/{id}/approve-letter
**Request:** `{ "approved": true, "notes": "optional" }`

---

## Agents (Tim Shaw)

#### POST /agents/chat
Send message to Tim Shaw.

**Request:** `{ "message": "What's the status of my dispute?", "channel": "portal_chat" }`

**Channels:** `portal_chat`, `sms`, `email`

**Response:**
```json
{
  "success": true,
  "agent": "Tim Shaw",
  "response": "I reviewed your account...",
  "channel": "portal_chat",
  "requires_human": false,
  "timestamp": "2026-04-13T19:00:00Z"
}
```

#### GET /agents/status
Tim Shaw availability and channel info.

#### POST /agents/escalate
**Request:** `{ "reason": "legal_threat", "message": "optional context" }`

**Escalation Reasons:** `legal_threat`, `billing_dispute`, `complaint`, `complex_dispute`, `identity_theft`, `emergency`

---

## Communications

#### POST /communications/sms/send *(admin)*
Send SMS to client. Checks consent first.

#### POST /communications/sms/webhook
Twilio inbound SMS webhook. Returns TwiML.

#### POST /communications/voice/webhook
TwiML response for voice calls. Returns Tim Shaw greeting.

#### POST /communications/email/send *(admin)*
Send email via SendGrid.

#### POST /communications/chat/message
Send portal chat message.

#### POST /communications/video/schedule
Schedule Zoom meeting.

#### GET /communications/consent/status/{client_id}
Check consent per channel.

#### POST /communications/consent/grant / /revoke
Manage channel consent.

---

## Products & Billing

#### GET /products
List all available products and guides.

#### GET /products/subscriptions/plans
Available subscription plans.

**Plans:**
| Plan | Price | Key Feature |
|------|-------|-------------|
| basic | $29.99/mo | 3 disputes, email support |
| premium | $79.99/mo | Unlimited disputes, Tim Shaw 24/7 |
| vip | $199.99/mo | Daily monitoring, video sessions |

#### POST /products/subscriptions
Subscribe to a plan (charges via TRGpay).

**Request:** `{ "plan_id": "premium", "payment_token": "tok_..." }`

#### GET /products/billing/history
Payment history for current client.

---

## Admin (Back Office)

> All admin endpoints require `role: admin` or `role: staff`.

#### GET /admin/clients
List all clients with pagination and filters.

**Query params:** `status`, `agent_id`, `search`, `limit`, `offset`

#### GET /admin/analytics/overview
KPIs: total/active clients, disputes, revenue.

#### POST /admin/override/takeover/{client_id}
Human supervisor takes over client conversation.

#### POST /admin/override/release/{client_id}
Release back to Tim Shaw.

#### POST /admin/override/broadcast
Send message to all (or selected) clients.

---

## Error Codes

| Code | Meaning |
|------|---------|
| 400 | Bad request / validation error |
| 401 | Not authenticated (missing/invalid token) |
| 403 | Forbidden (insufficient role) |
| 404 | Resource not found |
| 409 | Conflict (e.g., duplicate email) |
| 422 | Unprocessable entity (schema validation) |
| 429 | Rate limit exceeded |
| 500 | Internal server error |

---

## Rate Limits

- Default: 60 requests/minute per IP
- Auth endpoints: 10 requests/minute
- SMS/email send: 10 requests/minute per client

---

## Compliance Notes

- All dispute letters require **human client approval** before filing (CROA § 404)
- AI disclosure required in all Tim Shaw communications
- SMS requires explicit written consent (TCPA)
- Audit trail is append-only — no records are ever deleted
- SSN never logged or stored in plain text
