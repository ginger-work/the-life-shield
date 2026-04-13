# The Life Shield — Local Development Guide

> **Time to first run:** ~5 minutes (after Docker is installed)

---

## Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Docker Desktop | 24+ | [docker.com](https://www.docker.com/products/docker-desktop/) |
| Make | any | macOS: `brew install make` |
| Git | any | pre-installed on most systems |

---

## Quick Start

```bash
# 1. Clone the repo
git clone https://github.com/your-org/the-life-shield.git
cd the-life-shield

# 2. Run the dev setup script
bash scripts/start-dev.sh

# 3. That's it. API is live at:
#    http://localhost:8000
#    http://localhost:8000/docs  (Swagger UI)
```

Or manually step by step:

```bash
# Copy environment template
cp .env.example .env
# (Edit .env with your API keys if needed)

# Build and start all services
make build
make up

# Run database migrations
make migrate

# (Optional) Load test data
make seed
```

---

## Services & Ports

| Service | Port | URL |
|---------|------|-----|
| Nginx (reverse proxy) | 80 | http://localhost |
| FastAPI (direct) | 8000 | http://localhost:8000 |
| Swagger Docs | 8000 | http://localhost:8000/docs |
| ReDoc | 8000 | http://localhost:8000/redoc |
| PostgreSQL | 5432 | localhost:5432 |
| Redis | 6379 | localhost:6379 |

---

## Common Commands

```bash
# Start / Stop
make up          # Start all services (detached)
make up-fg       # Start in foreground (shows logs)
make down        # Stop all services

# Logs
make logs        # Tail all logs
make logs-api    # API logs only
make logs-db     # Database logs only
make logs-worker # Celery worker logs

# Database
make migrate                    # Run pending migrations
make migrate-create ARGS="add users table"  # New migration
make migrate-down               # Roll back one
make seed                       # Load test data
make db-shell                   # psql interactive shell

# Code Quality
make test        # Run test suite
make test-cov    # Tests + coverage report
make lint        # Run linter (ruff)
make format      # Auto-format code

# Shells
make shell       # bash in API container
make db-shell    # psql shell
make redis-cli   # Redis CLI
```

---

## Project Structure

```
the-life-shield/
├── app/                    # FastAPI application
│   ├── main.py             # App entry point
│   ├── api/                # API routes
│   │   └── v1/             # Versioned endpoints
│   ├── models/             # SQLAlchemy models
│   ├── schemas/            # Pydantic schemas
│   ├── services/           # Business logic
│   ├── agents/             # AI agent logic (Tim Shaw)
│   ├── tasks/              # Celery async tasks
│   └── core/               # Config, DB, security
├── docker/
│   ├── Dockerfile          # Multi-stage Docker image
│   ├── docker-compose.yml  # Dev compose
│   └── docker-compose.prod.yml  # Production compose
├── nginx/
│   ├── nginx.dev.conf      # Dev Nginx config
│   └── nginx.prod.conf     # Prod Nginx config (SSL)
├── migrations/             # Alembic migration files
├── scripts/
│   ├── docker-entrypoint.sh  # Container startup script
│   ├── init-db.sql           # DB initialization
│   ├── seed.py               # Test data seeder
│   └── start-dev.sh          # Quick start script
├── tests/                  # Test suite
├── docs/                   # Documentation
├── .env.example            # Environment template
├── .env                    # Your local env (NOT in git)
├── Makefile                # Common commands
└── requirements.txt        # Python dependencies
```

---

## Environment Variables

See `.env.example` for a full list. For local dev, the defaults work out of the box for DB and Redis. You'll need real API keys to use:

- Credit bureau APIs (Equifax, Experian, TransUnion)
- Twilio (SMS/voice)
- SendGrid (email)
- Stripe (payments)
- OpenAI / Anthropic (AI features)
- ElevenLabs (Tim Shaw voice)

**Feature flags** let you disable integrations you don't have keys for:

```env
ENABLE_CREDIT_PULL=false
ENABLE_PAYMENTS=false
ENABLE_VIDEO_CALLS=false
```

---

## Working with the Database

### Create a migration

After changing a SQLAlchemy model:

```bash
make migrate-create ARGS="describe your change"
# Then review the generated file in migrations/versions/
make migrate
```

### Inspect the database

```bash
make db-shell
# Inside psql:
\dt          # list tables
\d clients   # describe clients table
SELECT * FROM subscription_tiers;
```

### Fresh start

```bash
make clean-all   # WARNING: destroys all data
make up
make migrate
make seed
```

---

## AI Agent (Tim Shaw)

Tim Shaw is the AI credit agent clients interact with. In development:

- Set `ENABLE_AI_AGENT=true` in `.env`
- Set `ANTHROPIC_API_KEY` and/or `OPENAI_API_KEY`
- Voice features require `ELEVENLABS_API_KEY` and `ELEVENLABS_VOICE_ID`

Without these keys, the agent will fall back to mock responses.

---

## Hot Reload

The dev container mounts the `app/` directory and runs Uvicorn with `--reload`. Code changes are reflected immediately without restarting containers.

---

## Troubleshooting

See `docs/TROUBLESHOOTING.md` for common issues and solutions.
