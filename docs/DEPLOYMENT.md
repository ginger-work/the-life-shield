# The Life Shield — Deployment Guide

## Quick Start (Development)

```bash
# 1. Clone and setup
git clone <repo>
cd the-life-shield
cp .env.example .env

# 2. Fill in .env with local values
# DATABASE_URL=postgresql://lifeshield:password@localhost:5432/lifeshield_db
# TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER
# SENDGRID_API_KEY
# etc.

# 3. Start everything with Docker Compose
docker-compose up -d

# 4. Run migrations (auto on startup, but can be manual)
docker-compose exec api alembic upgrade head

# 5. Seed sample data (optional)
docker-compose exec api python scripts/seed_database.py

# 6. Open browser
# API: http://localhost:8000/api/docs
# Portal: http://localhost:3000
```

---

## Production Deployment

### System Requirements

- **Server:** Linux (Ubuntu 20.04+) or macOS
- **CPU:** 2+ cores minimum (4+ recommended)
- **RAM:** 4GB minimum (8GB+ recommended)
- **Disk:** 20GB minimum
- **Network:** Public IP with DNS configured

### Prerequisites

- Docker & Docker Compose 2.0+
- PostgreSQL 14+ (managed database recommended)
- Redis 7+ (optional but recommended for scaling)
- SSL certificate (Let's Encrypt via Certbot)
- Domain name (for DNS)

### Step 1: Prepare Server

```bash
# SSH into server
ssh ubuntu@your-server-ip

# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker & Docker Compose
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker ubuntu

# Verify
docker --version
docker-compose --version
```

### Step 2: Clone Repository

```bash
cd /opt
sudo git clone <repo> lifeshield
sudo chown -R ubuntu:ubuntu lifeshield
cd lifeshield
```

### Step 3: Configure Environment

```bash
cp .env.example .env
nano .env   # Edit all required values

# Critical for production:
APP_ENV=production
APP_SECRET_KEY=<generate: python -c "import secrets; print(secrets.token_hex(16))">
DATABASE_URL=postgresql://<user>:<pass>@<postgres-host>:5432/lifeshield_prod
TWILIO_ACCOUNT_SID=<your-sid>
TWILIO_AUTH_TOKEN=<your-token>
SENDGRID_API_KEY=<your-key>
TRGPAY_PUBLIC_KEY=<your-key>
TRGPAY_SECRET_KEY=<your-secret>
```

### Step 4: Setup SSL

```bash
# Install Certbot
sudo apt install certbot python3-certbot-nginx -y

# Generate certificate
sudo certbot certonly --standalone -d api.thelifeshield.com -d portal.thelifeshield.com

# Auto-renew
sudo systemctl enable certbot.timer
```

### Step 5: Configure Nginx

```bash
# Create /etc/nginx/sites-available/lifeshield
sudo tee /etc/nginx/sites-available/lifeshield > /dev/null <<EOF
upstream api {
    server localhost:8000;
}
upstream portal {
    server localhost:3000;
}

server {
    listen 80;
    server_name api.thelifeshield.com portal.thelifeshield.com;
    return 301 https://\$server_name\$request_uri;
}

server {
    listen 443 ssl http2;
    server_name api.thelifeshield.com;
    
    ssl_certificate /etc/letsencrypt/live/api.thelifeshield.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.thelifeshield.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    
    client_max_body_size 10M;
    
    location / {
        proxy_pass http://api;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}

server {
    listen 443 ssl http2;
    server_name portal.thelifeshield.com;
    
    ssl_certificate /etc/letsencrypt/live/portal.thelifeshield.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/portal.thelifeshield.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    
    location / {
        proxy_pass http://portal;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
    }
}
EOF

sudo ln -s /etc/nginx/sites-available/lifeshield /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

### Step 6: Build & Start Services

```bash
cd /opt/lifeshield

# Build Docker images (API)
docker-compose -f docker-compose.prod.yml build

# Start all services
docker-compose -f docker-compose.prod.yml up -d

# Wait for DB
docker-compose -f docker-compose.prod.yml logs api | grep "uvicorn"

# Run migrations
docker-compose -f docker-compose.prod.yml run --rm api alembic upgrade head

# Build portal (Next.js)
cd portal
npm install --production
npm run build
npm run start &   # Run in background or use PM2

# Verify
curl https://api.thelifeshield.com/health
curl https://portal.thelifeshield.com
```

### Step 7: Monitoring & Maintenance

```bash
# View logs
docker-compose logs -f api
docker-compose logs -f db
docker-compose logs -f redis

# Database backup
docker-compose exec db pg_dump -U lifeshield lifeshield_prod > backup_$(date +%Y%m%d).sql

# Update application
cd /opt/lifeshield
git pull origin main
docker-compose -f docker-compose.prod.yml up -d --build
docker-compose -f docker-compose.prod.yml run --rm api alembic upgrade head
```

---

## Health Checks

```bash
# API health
curl https://api.thelifeshield.com/health

# Database connectivity
curl https://api.thelifeshield.com/api/v1/auth/me -H "Authorization: Bearer <token>"

# Portal
curl https://portal.thelifeshield.com
```

---

## Scaling (Production)

### Horizontal Scaling
```yaml
# docker-compose.prod.yml
api:
  deploy:
    replicas: 3      # Run 3 instances
    
celery:
  deploy:
    replicas: 2      # Run 2 workers
```

### Database Pooling
```python
# app/core/database.py
DATABASE_POOL_SIZE=20      # Increase from 10
DATABASE_MAX_OVERFLOW=40   # Increase from 20
```

### Redis Caching
Enable Redis for session caching and rate limit tracking (already configured).

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Port 8000 already in use | `sudo lsof -i :8000` and kill process |
| Database connection refused | Verify DATABASE_URL, check PostgreSQL running |
| API returns 500 errors | `docker-compose logs api` to debug |
| Portal shows 404s | Verify NEXT_PUBLIC_API_URL in portal |
| Twilio SMS not working | Check TWILIO_* credentials and account status |
| SSL certificate error | Verify certbot renewal: `sudo certbot renew --dry-run` |

---

## Backup Strategy

```bash
# Daily automated backup
0 2 * * * /opt/lifeshield/scripts/backup.sh

# Script: /opt/lifeshield/scripts/backup.sh
#!/bin/bash
BACKUP_DIR="/backups/lifeshield"
mkdir -p $BACKUP_DIR
docker-compose exec -T db pg_dump -U lifeshield lifeshield_prod | gzip > $BACKUP_DIR/backup_$(date +\%Y\%m\%d_\%H\%M\%S).sql.gz
find $BACKUP_DIR -type f -mtime +30 -delete  # Delete backups older than 30 days
```

---

## Go-Live Checklist

- [ ] Environment variables configured (all keys present)
- [ ] SSL certificates installed and renewable
- [ ] Database migrated and tested
- [ ] Twilio/SendGrid/TRGpay credentials verified
- [ ] Backups scheduled and tested
- [ ] Monitoring alerts configured (email on 500 errors)
- [ ] Domain DNS pointing to server
- [ ] API and Portal endpoints responding with 200/301
- [ ] Tim Shaw AI agent responding in chat
- [ ] Admin dashboard accessible
- [ ] Payment processing (TRGpay) tested
- [ ] Load testing completed (k6 or similar)
