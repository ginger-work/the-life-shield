# The Life Shield — Production Deployment Guide

> Platform: AWS EC2 (Ubuntu 22.04 LTS recommended) + Docker Compose

---

## Prerequisites on Production Server

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker

# Install Docker Compose plugin
sudo apt install docker-compose-plugin -y

# Install Make
sudo apt install make -y

# Verify
docker --version
docker compose version
```

---

## First-Time Setup

### 1. Clone the repo

```bash
cd /opt
sudo mkdir lifeshield && sudo chown $USER:$USER lifeshield
cd lifeshield
git clone https://github.com/your-org/the-life-shield.git .
```

### 2. Create `.env` with production values

```bash
cp .env.example .env
nano .env
```

Critical values to update:
- `ENVIRONMENT=production`
- `DEBUG=false`
- `SECRET_KEY=` (generate: `openssl rand -hex 50`)
- `JWT_SECRET_KEY=` (generate: `openssl rand -hex 50`)
- All API keys (Stripe, Twilio, SendGrid, OpenAI, etc.)
- `POSTGRES_PASSWORD=` (strong password)
- `REDIS_PASSWORD=` (strong password)
- `DATABASE_URL=` (update with above password)
- `REDIS_URL=` (update with above password)

### 3. Create production volumes

```bash
bash scripts/create-prod-volumes.sh
```

### 4. Set up SSL certificates

Using Let's Encrypt (Certbot):

```bash
sudo apt install certbot -y

# Obtain cert (point DNS to server first)
sudo certbot certonly --standalone -d thelifeshield.com -d www.thelifeshield.com

# Copy to Docker volume
docker run --rm -v lifeshield_nginx_certs:/certs ubuntu bash -c "
  cp /etc/letsencrypt/live/thelifeshield.com/fullchain.pem /certs/ &&
  cp /etc/letsencrypt/live/thelifeshield.com/privkey.pem /certs/ &&
  chmod 600 /certs/*.pem
"
```

### 5. Build and launch

```bash
make build-prod
make up-prod

# Run migrations
make migrate-prod

# Verify all containers running
docker compose -f docker/docker-compose.prod.yml ps
```

---

## Deploying Updates

```bash
# Pull latest code
git pull origin main

# Build new image
make build-prod

# Restart services (zero-downtime rolling restart)
make up-prod

# Run any new migrations
make migrate-prod

# Clean old images
docker image prune -f
```

---

## Automated Deployment (GitHub Actions)

The CI/CD pipeline (`.github/workflows/ci.yml`) handles automated deploys on push to `main`.

### Required GitHub Secrets

Set these in: **Settings → Secrets → Actions**

| Secret | Value |
|--------|-------|
| `PROD_HOST` | Your server IP or domain |
| `PROD_USER` | SSH username (e.g., `ubuntu`) |
| `PROD_SSH_KEY` | Private SSH key (the key allowed on server) |

Workflow on every `main` push:
1. Lint → Test → Build Docker image
2. Push image to GitHub Container Registry
3. SSH into server → pull image → restart containers

---

## Monitoring

### View logs

```bash
make logs-prod
# Or specific service:
docker compose -f docker/docker-compose.prod.yml logs -f api
```

### Container health

```bash
docker compose -f docker/docker-compose.prod.yml ps
```

### Sentry (Error Tracking)

Set `SENTRY_DSN` in `.env` and errors will be reported automatically.

### Resource usage

```bash
docker stats
```

---

## SSL Certificate Renewal

Certbot auto-renewal should be configured:

```bash
# Test renewal
sudo certbot renew --dry-run

# Cron job (add to crontab)
0 3 * * * certbot renew --quiet && docker exec lifeshield_nginx nginx -s reload
```

---

## Backup Strategy

### Database backup

```bash
make db-backup
# Saves: backup-YYYYMMDD-HHMMSS.sql
```

Automate with cron:

```bash
0 2 * * * cd /opt/lifeshield && make db-backup && \
  aws s3 cp backup-*.sql s3://lifeshield-backups/db/ && \
  find . -name "backup-*.sql" -mtime +7 -delete
```

### Redis backup

Redis is configured with `appendonly yes` — data persists in the `lifeshield_redis_data` volume automatically.

---

## Security Hardening Checklist

- [ ] `.env` has `DEBUG=false`
- [ ] All passwords are strong and unique
- [ ] `SECRET_KEY` is 50+ random chars
- [ ] PostgreSQL not exposed externally (no port in prod compose)
- [ ] Nginx configured with SSL and security headers
- [ ] UFW firewall: only 22, 80, 443 open
- [ ] SSH key-only authentication (no password SSH)
- [ ] Regular backups tested and working
- [ ] Sentry configured for error alerting
- [ ] Let's Encrypt auto-renewal tested

```bash
# Quick firewall setup
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

---

## Rollback

```bash
# Find previous image tag
docker images | grep lifeshield

# Roll back to specific tag
IMAGE_TAG=main-abc123 make up-prod

# Or quickly restart current prod
make down-prod && make up-prod
```
