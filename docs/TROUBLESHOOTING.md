# The Life Shield — Troubleshooting Guide

---

## Quick Diagnostics

```bash
# See all container statuses + health
make status

# Tail all logs
make logs

# Check a specific service
docker compose -f docker/docker-compose.yml logs --tail=50 api
```

---

## Common Issues

### ❌ `make up` fails — "port already in use"

**Symptom:** Error like `bind: address already in use` for port 5432, 6379, or 80.

**Fix:**
```bash
# Find what's using the port
lsof -i :5432
lsof -i :6379
lsof -i :80

# Stop local Postgres/Redis if running
brew services stop postgresql
brew services stop redis

# Or change ports in .env
POSTGRES_PORT=5433
REDIS_PORT=6380
HTTP_PORT=8080
```

---

### ❌ API container exits immediately

**Symptom:** `lifeshield_api` shows `Exit 1` in `make status`.

**Fix:**
```bash
# Check startup logs
docker compose -f docker/docker-compose.yml logs api

# Common causes:
# 1. Missing .env file
cp .env.example .env

# 2. Database not ready (entrypoint will retry, but check db logs)
docker compose -f docker/docker-compose.yml logs db

# 3. Migration error
make shell
alembic upgrade head
```

---

### ❌ Database connection refused

**Symptom:** `psycopg2.OperationalError: could not connect to server`

**Fix:**
```bash
# Verify db container is healthy
docker compose -f docker/docker-compose.yml ps db

# Check DATABASE_URL in .env — inside Docker, use 'db' not 'localhost'
DATABASE_URL=postgresql://lifeshield:devpassword123@db:5432/lifeshield_dev
#                                                     ^^
#                                            Use service name, not localhost

# If running app OUTSIDE Docker (e.g., local python), use localhost
DATABASE_URL=postgresql://lifeshield:devpassword123@localhost:5432/lifeshield_dev
```

---

### ❌ Redis connection refused

**Symptom:** `redis.exceptions.ConnectionError`

**Fix:**
```bash
# Check Redis is running
docker compose -f docker/docker-compose.yml ps redis

# Verify password in .env matches
REDIS_PASSWORD=redisdevpass
REDIS_URL=redis://:redisdevpass@redis:6379/0
#                  ^^^^^^^^^^^
#             Must match REDIS_PASSWORD

# Test manually
make redis-cli
> PING
PONG
```

---

### ❌ Migration fails

**Symptom:** `alembic.exc.CommandError` or SQL errors during `make migrate`

**Fix:**
```bash
# Check current migration state
make migrate-status

# If database is out of sync, check what's pending
make shell
alembic history

# If a migration is half-applied (rare), you may need to roll back
make migrate-down

# Nuclear option — reset dev database entirely
make clean-all
make up
make migrate
make seed
```

---

### ❌ Hot reload not working

**Symptom:** Code changes in development not reflected.

**Fix:**
```bash
# Ensure the volume mount is correct in docker-compose.yml
# app service should have:
volumes:
  - ..:/app

# If still not working, force restart
make restart-api

# Or check that uvicorn is running with --reload
docker compose -f docker/docker-compose.yml exec api ps aux | grep uvicorn
```

---

### ❌ Nginx 502 Bad Gateway

**Symptom:** `502 Bad Gateway` from Nginx.

**Fix:**
```bash
# Check if API is healthy
make status
# Look for api container health status

# Check API logs for errors
make logs-api

# If API is starting up, wait 60 seconds (healthcheck start_period)
# Then retry

# Check Nginx logs
docker compose -f docker/docker-compose.yml logs nginx
```

---

### ❌ Celery workers not processing tasks

**Symptom:** Tasks stuck in queue, no Celery logs.

**Fix:**
```bash
# Check worker is running
make status
make logs-worker

# Verify broker URL
docker compose -f docker/docker-compose.yml exec worker env | grep CELERY

# Test Celery connectivity
make shell
python -c "from app.celery_app import celery_app; print(celery_app.control.ping())"

# Restart worker
docker compose -f docker/docker-compose.yml restart worker
```

---

### ❌ SSL certificate issues (production)

**Symptom:** Browser shows SSL warning or Nginx fails to start.

**Fix:**
```bash
# Check cert files exist in volume
docker run --rm -v lifeshield_nginx_certs:/certs ubuntu ls -la /certs

# Renew cert
sudo certbot renew --force-renewal

# Copy renewed certs to volume
docker run --rm -v lifeshield_nginx_certs:/certs ubuntu bash -c "
  cp /etc/letsencrypt/live/thelifeshield.com/fullchain.pem /certs/ &&
  cp /etc/letsencrypt/live/thelifeshield.com/privkey.pem /certs/ &&
  chmod 600 /certs/*.pem
"

# Reload Nginx
docker compose -f docker/docker-compose.prod.yml exec nginx nginx -s reload
```

---

### ❌ Out of disk space (production)

**Symptom:** Docker operations fail with "no space left on device".

**Fix:**
```bash
# Check disk usage
df -h
docker system df

# Clean up old images, stopped containers
docker system prune -f

# Clean specific things
docker image prune -af           # All unused images
docker volume prune              # Unused volumes (careful!)
docker container prune           # Stopped containers

# Check log sizes
du -sh /var/lib/docker/volumes/lifeshield_app_logs/
# Consider log rotation in production
```

---

### ❌ Performance issues

**Symptom:** API slow, high response times.

**Diagnostics:**
```bash
# Resource usage
docker stats

# Database slow queries
make db-shell
SELECT pid, now() - pg_stat_activity.query_start AS duration, query, state
FROM pg_stat_activity
WHERE (now() - pg_stat_activity.query_start) > interval '5 minutes';

# Redis memory
make redis-cli
> INFO memory
> INFO stats
```

**Fixes:**
- Increase `DATABASE_POOL_SIZE` in `.env`
- Scale Celery workers: edit `--concurrency=8` in compose
- Add database indexes for slow queries
- Check Sentry for N+1 query issues

---

## Getting More Help

1. Check application logs: `make logs-api`
2. Check Sentry dashboard for errors
3. Review the architecture: `docs/INFRASTRUCTURE.md`
4. Ping the DevOps channel with logs attached
