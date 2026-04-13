#!/bin/bash
# ============================================================
# The Life Shield — Production Volume Init
# Run ONCE on the production server before first deploy
# ============================================================
set -e

echo "📦 Creating production Docker volumes..."

docker volume create lifeshield_postgres_data
docker volume create lifeshield_redis_data
docker volume create lifeshield_media_files
docker volume create lifeshield_nginx_certs

echo "✅ Volumes created:"
docker volume ls | grep lifeshield

echo ""
echo "Next steps:"
echo "  1. Copy SSL certs to lifeshield_nginx_certs volume"
echo "  2. Copy .env (production values) to server"
echo "  3. Run: make up-prod"
