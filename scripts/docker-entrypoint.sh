#!/bin/bash
# ============================================================
# The Life Shield — Docker Entrypoint Script
# Handles startup, migrations, and app launch
# ============================================================
set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info()    { echo -e "${BLUE}[INFO]${NC}  $*"; }
log_success() { echo -e "${GREEN}[OK]${NC}    $*"; }
log_warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
log_error()   { echo -e "${RED}[ERROR]${NC} $*"; }

# ---- Wait for PostgreSQL ----
wait_for_postgres() {
    local host="${POSTGRES_HOST:-db}"
    local port="${POSTGRES_PORT:-5432}"
    local max_attempts=30
    local attempt=1

    log_info "Waiting for PostgreSQL at ${host}:${port}..."

    until pg_isready -h "$host" -p "$port" -U "${POSTGRES_USER:-lifeshield}" -q 2>/dev/null; do
        if [ $attempt -ge $max_attempts ]; then
            log_error "PostgreSQL did not become ready after ${max_attempts} attempts. Exiting."
            exit 1
        fi
        log_warn "PostgreSQL not ready (attempt ${attempt}/${max_attempts}) — retrying in 2s..."
        sleep 2
        attempt=$((attempt + 1))
    done

    log_success "PostgreSQL is ready."
}

# ---- Wait for Redis ----
wait_for_redis() {
    local host="${REDIS_HOST:-redis}"
    local port="${REDIS_PORT:-6379}"
    local max_attempts=20
    local attempt=1

    log_info "Waiting for Redis at ${host}:${port}..."

    until nc -z "$host" "$port" 2>/dev/null; do
        if [ $attempt -ge $max_attempts ]; then
            log_error "Redis did not become available after ${max_attempts} attempts."
            exit 1
        fi
        log_warn "Redis not ready (attempt ${attempt}/${max_attempts}) — retrying in 2s..."
        sleep 2
        attempt=$((attempt + 1))
    done

    log_success "Redis is ready."
}

# ---- Run Migrations ----
run_migrations() {
    if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
        log_info "Running database migrations..."
        if alembic upgrade head; then
            log_success "Migrations complete."
        else
            log_error "Migration failed! Check your migration files."
            exit 1
        fi
    else
        log_warn "Skipping migrations (RUN_MIGRATIONS=false)."
    fi
}

# ---- Create log directory ----
ensure_log_dir() {
    mkdir -p /app/logs
    log_success "Log directory ready."
}

# ============================================================
# Main
# ============================================================
log_info "Starting The Life Shield API (${ENVIRONMENT:-development})"
log_info "Container started at: $(date -u)"

# Wait for dependencies
wait_for_postgres
wait_for_redis

# Setup
ensure_log_dir

# Run migrations (skip for workers and scheduler)
if [ "${SKIP_MIGRATIONS:-false}" != "true" ]; then
    run_migrations
fi

log_success "Startup complete. Launching application..."
echo ""

# Hand off to CMD
exec "$@"
