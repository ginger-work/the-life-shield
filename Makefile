# ============================================================
# The Life Shield — Makefile
# Common Docker & dev commands
# Usage: make <target>
# ============================================================

.PHONY: help build up down restart logs shell \
        migrate seed test lint format \
        up-prod down-prod build-prod \
        db-shell redis-cli \
        clean clean-all status

# Default compose file
COMPOSE_FILE := docker/docker-compose.yml
COMPOSE_PROD  := docker/docker-compose.prod.yml
APP_SERVICE   := api
PROJECT_NAME  := lifeshield

# Detect docker compose v2 vs v1
DOCKER_COMPOSE := $(shell docker compose version >/dev/null 2>&1 && echo "docker compose" || echo "docker-compose")

# ============================================================
# HELP
# ============================================================
help: ## Show this help message
	@echo ""
	@echo "  ╔══════════════════════════════════════════╗"
	@echo "  ║       The Life Shield — Make Tasks        ║"
	@echo "  ╚══════════════════════════════════════════╝"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
	@echo ""

# ============================================================
# DEVELOPMENT
# ============================================================

build: ## Build all Docker images (development)
	@echo "🔨 Building containers..."
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) build --no-cache

build-fast: ## Build containers (use cache)
	@echo "🔨 Building containers (cached)..."
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) build

up: ## Start all services (development)
	@echo "🚀 Starting The Life Shield (dev)..."
	@cp -n .env.example .env 2>/dev/null && echo "📄 Created .env from .env.example — fill in your values!" || true
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) up -d
	@echo ""
	@echo "  ✅ Services running:"
	@echo "     API:      http://localhost:8000"
	@echo "     API Docs: http://localhost:8000/docs"
	@echo "     Nginx:    http://localhost:80"
	@echo ""

up-fg: ## Start all services in foreground (shows logs)
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) up

down: ## Stop all services
	@echo "🛑 Stopping services..."
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) down

restart: ## Restart all services
	@echo "🔄 Restarting services..."
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) restart

restart-api: ## Restart only the API container
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) restart $(APP_SERVICE)

status: ## Show container status
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) ps

logs: ## Tail logs from all services
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) logs -f

logs-api: ## Tail API logs only
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) logs -f $(APP_SERVICE)

logs-db: ## Tail database logs only
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) logs -f db

logs-worker: ## Tail Celery worker logs
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) logs -f worker

# ============================================================
# DATABASE
# ============================================================

migrate: ## Run database migrations (Alembic)
	@echo "📦 Running migrations..."
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) exec $(APP_SERVICE) alembic upgrade head

migrate-create: ## Create a new migration (ARGS="message")
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) exec $(APP_SERVICE) alembic revision --autogenerate -m "$(ARGS)"

migrate-down: ## Roll back last migration
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) exec $(APP_SERVICE) alembic downgrade -1

migrate-status: ## Show migration status
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) exec $(APP_SERVICE) alembic current

seed: ## Load test/seed data
	@echo "🌱 Seeding database..."
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) exec $(APP_SERVICE) python scripts/seed.py

db-shell: ## Open PostgreSQL interactive shell
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) exec db \
		psql -U $${POSTGRES_USER:-lifeshield} -d $${POSTGRES_DB:-lifeshield_dev}

db-backup: ## Backup the database (OUTPUT=./backup.sql)
	@echo "💾 Backing up database..."
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) exec db \
		pg_dump -U $${POSTGRES_USER:-lifeshield} $${POSTGRES_DB:-lifeshield_dev} \
		> backup-$$(date +%Y%m%d-%H%M%S).sql
	@echo "✅ Backup saved."

db-restore: ## Restore database (FILE=backup.sql)
	@[ -n "$(FILE)" ] || (echo "❌ Specify FILE=your_backup.sql" && exit 1)
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) exec -T db \
		psql -U $${POSTGRES_USER:-lifeshield} $${POSTGRES_DB:-lifeshield_dev} < $(FILE)

redis-cli: ## Open Redis CLI
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) exec redis \
		redis-cli -a $${REDIS_PASSWORD:-redisdevpass}

# ============================================================
# APPLICATION SHELL
# ============================================================

shell: ## Open bash shell in API container
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) exec $(APP_SERVICE) /bin/bash

python: ## Open Python shell in API container
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) exec $(APP_SERVICE) python -c "import IPython; IPython.start_ipython()"

# ============================================================
# TESTING & CODE QUALITY
# ============================================================

test: ## Run test suite
	@echo "🧪 Running tests..."
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) exec $(APP_SERVICE) \
		pytest tests/ -v --tb=short

test-cov: ## Run tests with coverage report
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) exec $(APP_SERVICE) \
		pytest tests/ -v --cov=app --cov-report=html --cov-report=term-missing

lint: ## Run linters (ruff)
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) exec $(APP_SERVICE) ruff check .

format: ## Format code (ruff + black)
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) exec $(APP_SERVICE) ruff format .

typecheck: ## Run type checking (mypy)
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) exec $(APP_SERVICE) mypy app/

# ============================================================
# PRODUCTION
# ============================================================

build-prod: ## Build production Docker image
	@echo "🔨 Building production image..."
	$(DOCKER_COMPOSE) -f $(COMPOSE_PROD) build --no-cache

up-prod: ## Start all services (production)
	@echo "🚀 Starting The Life Shield (production)..."
	$(DOCKER_COMPOSE) -f $(COMPOSE_PROD) up -d

down-prod: ## Stop production services
	$(DOCKER_COMPOSE) -f $(COMPOSE_PROD) down

logs-prod: ## Tail production logs
	$(DOCKER_COMPOSE) -f $(COMPOSE_PROD) logs -f

migrate-prod: ## Run migrations in production
	$(DOCKER_COMPOSE) -f $(COMPOSE_PROD) exec $(APP_SERVICE) alembic upgrade head

# ============================================================
# CLEANUP
# ============================================================

clean: ## Remove stopped containers and dangling images
	@echo "🧹 Cleaning up..."
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) down --remove-orphans
	docker image prune -f
	@echo "✅ Done."

clean-all: ## Remove ALL containers, volumes, and images (DESTRUCTIVE)
	@echo "⚠️  WARNING: This will destroy all data volumes!"
	@read -p "Are you sure? [y/N] " ans; \
	if [ "$$ans" = "y" ]; then \
		$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) down -v --remove-orphans; \
		docker image prune -af; \
		echo "✅ Full clean complete."; \
	else \
		echo "Aborted."; \
	fi

# Default target
.DEFAULT_GOAL := help
