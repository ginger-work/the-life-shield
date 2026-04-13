# The Life Shield — Infrastructure Architecture

---

## Architecture Overview

```
                          ┌─────────────────────────────────────────────┐
                          │              CLIENT (Browser / App)          │
                          └─────────────────────────────────────────────┘
                                           │ HTTPS (443)
                                           ▼
                          ┌─────────────────────────────────────────────┐
                          │              NGINX (Reverse Proxy)           │
                          │  • SSL termination                           │
                          │  • Rate limiting                             │
                          │  • Static file serving                       │
                          │  • WebSocket proxying                        │
                          └─────────────────────────────────────────────┘
                                           │ HTTP (internal)
                          ┌────────────────┼────────────────────────────┐
                          │                ▼                            │
                          │   ┌─────────────────────────────┐           │
                          │   │     FastAPI Application      │           │
                          │   │  • REST API endpoints        │           │
                          │   │  • WebSocket (real-time)     │           │
                          │   │  • AI Agent coordination     │           │
                          │   │  • Business logic            │           │
                          │   └─────────────────────────────┘           │
                          │            │          │                      │
                          │  ┌─────────┘          └──────────┐           │
                          │  ▼                               ▼           │
                          │  ┌──────────────┐   ┌─────────────────────┐ │
                          │  │  PostgreSQL  │   │        Redis        │ │
                          │  │  (Primary DB)│   │  • Cache (DB 0)     │ │
                          │  │  • Clients   │   │  • Celery tasks (1) │ │
                          │  │  • Disputes  │   │  • Results (DB 2)   │ │
                          │  │  • Payments  │   │  • Sessions         │ │
                          │  │  • Consents  │   └─────────────────────┘ │
                          │  └──────────────┘             │             │
                          │                               ▼             │
                          │                   ┌─────────────────────┐   │
                          │                   │    Celery Worker     │   │
                          │                   │  • Credit pulls      │   │
                          │                   │  • Dispute filings   │   │
                          │                   │  • Email/SMS sends   │   │
                          │                   │  • AI agent tasks    │   │
                          │                   └─────────────────────┘   │
                          │                                              │
                          │                   ┌─────────────────────┐   │
                          │                   │   Celery Beat        │   │
                          │                   │  • Credit monitoring │   │
                          │                   │  • Scheduled reports │   │
                          │                   │  • Reminder tasks    │   │
                          │                   └─────────────────────┘   │
                          │                                              │
                          │          backend Docker network              │
                          └──────────────────────────────────────────────┘

                          ┌────────────────────────────────────────────┐
                          │          External APIs & Services           │
                          │                                             │
                          │  Credit:  Equifax │ Experian │ TransUnion  │
                          │           iSoftPull (soft pull)            │
                          │  Comms:   Twilio (SMS/Voice)               │
                          │           SendGrid (Email)                 │
                          │           Zoom (Video)                     │
                          │  AI:      OpenAI GPT-4o │ Claude 3.5      │
                          │           ElevenLabs (Tim Shaw voice)      │
                          │  Payment: Stripe │ PayPal                  │
                          │  Storage: AWS S3 (encrypted vault)         │
                          │  Auth:    ID.me (identity verification)    │
                          │  Monitor: Sentry │ Mixpanel                │
                          └────────────────────────────────────────────┘
```

---

## Docker Networks

| Network | Purpose | Services |
|---------|---------|----------|
| `lifeshield_frontend` | Public-facing | Nginx, API |
| `lifeshield_backend` | Internal only | API, DB, Redis, Worker, Scheduler |

- PostgreSQL and Redis are **not exposed** to the frontend network
- In production, DB has **no external port binding**

---

## Docker Volumes

| Volume | Purpose | Backed Up? |
|--------|---------|-----------|
| `lifeshield_postgres_data` | Database files | Yes (nightly) |
| `lifeshield_redis_data` | Redis persistence (AOF) | Optional |
| `lifeshield_media_files` | Client documents, media | Yes |
| `lifeshield_app_logs` | Application + Nginx logs | Optional |
| `lifeshield_nginx_certs` | SSL certificates | Cert auto-renewal |

---

## Service Health Checks

All services have health checks configured:

| Service | Check | Interval |
|---------|-------|---------|
| PostgreSQL | `pg_isready` | 10s |
| Redis | `redis-cli ping` | 10s |
| FastAPI | `GET /health` | 30s |
| Nginx | `GET /health` | 30s |

---

## Environment Tiers

| Tier | Compose File | Purpose |
|------|-------------|---------|
| Development | `docker/docker-compose.yml` | Local dev, hot-reload |
| Production | `docker/docker-compose.prod.yml` | Live server |

**Key differences in production:**
- Multi-worker Uvicorn (4+ workers)
- No port exposed for DB (internal only)
- Production Docker image (slim, no dev tools)
- Resource limits on all containers
- SSL/TLS via Nginx

---

## Data Flow: Credit Dispute

```
Client (browser)
    │ POST /api/v1/disputes/create
    ▼
Nginx → FastAPI
    │ Validate request
    │ Store dispute record (PostgreSQL)
    │ Enqueue task → Redis (Celery broker)
    │ Return 202 Accepted
    ▼
Celery Worker (async)
    │ Pull task from Redis
    │ Pull credit report (Equifax/Experian/TransUnion API)
    │ Generate dispute letter (Claude/OpenAI)
    │ File dispute via bureau API
    │ Send confirmation email (SendGrid)
    │ Update dispute status (PostgreSQL)
    │ Notify client via WebSocket
    ▼
Client sees real-time status update
```

---

## Data Flow: Tim Shaw AI Agent

```
Client texts Tim Shaw (Twilio SMS)
    │
    ▼
Twilio webhook → FastAPI /webhook/sms
    │ Load client context (PostgreSQL + Redis cache)
    │ Build agent prompt with client's credit profile
    │
    ▼
AI Agent (Claude 3.5 / GPT-4o)
    │ Generate response
    │ Identify actions needed (dispute? pull report? schedule call?)
    │ Log conversation (PostgreSQL)
    │
    ▼
Twilio SMS reply → Client
    │
Optional: ElevenLabs TTS → Voice call
```

---

## Security Architecture

- **HIPAA considerations**: All PII encrypted at rest (AES-256-GCM)
- **FCRA compliance**: Consent captured and stored before any credit pull
- **API keys**: Stored in `.env`, never in code or Docker images
- **Network isolation**: DB/Redis unreachable from internet
- **Non-root containers**: App runs as `appuser` (non-root)
- **Security headers**: HSTS, X-Frame-Options, CSP via Nginx
- **Rate limiting**: Auth endpoints throttled (5 req/min)

---

## Scaling Path

**Phase 1 (now):** Single server, Docker Compose
**Phase 2:** Docker Swarm or Kubernetes (ECS/EKS on AWS)
**Phase 3:** Managed services (AWS RDS, ElastiCache, ECS Fargate)

The current Docker Compose architecture is designed to be **drop-in compatible** with Kubernetes — just convert `docker-compose.prod.yml` to Kubernetes manifests when ready.
