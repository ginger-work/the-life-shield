#!/bin/bash
# ============================================================
# The Life Shield — Development Quick Start
# ============================================================
set -e

BLUE='\033[0;34m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${BLUE}"
echo "  ╔══════════════════════════════════════════╗"
echo "  ║      The Life Shield — Dev Setup          ║"
echo "  ╚══════════════════════════════════════════╝"
echo -e "${NC}"

# Check Docker
if ! command -v docker &>/dev/null; then
    echo "❌ Docker not found. Install Docker Desktop first."
    exit 1
fi

# Check .env
if [ ! -f .env ]; then
    echo -e "${YELLOW}📄 Creating .env from template...${NC}"
    cp .env.example .env
    echo "⚠️  .env created. Edit it with your API keys before continuing."
    echo "   At minimum, you can leave DB/Redis values as defaults for local dev."
    echo ""
fi

# Build and start
echo -e "${BLUE}🔨 Building containers...${NC}"
make build

echo -e "${BLUE}🚀 Starting services...${NC}"
make up

echo ""
echo -e "${GREEN}✅ Development environment ready!${NC}"
echo ""
echo "  API:      http://localhost:8000"
echo "  API Docs: http://localhost:8000/docs"
echo "  Nginx:    http://localhost:80"
echo ""
echo "  Commands:"
echo "    make logs      → View logs"
echo "    make shell     → App shell"
echo "    make migrate   → Run migrations"
echo "    make seed      → Load test data"
echo "    make down      → Stop everything"
echo ""
