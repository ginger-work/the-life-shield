# ============================================================
# The Life Shield — Python Application Image
# Multi-stage build: builder → production (slim)
# ============================================================

# ------------------------------------
# Stage 1: Builder
# ------------------------------------
FROM python:3.11-slim AS builder

LABEL maintainer="TRG TechLink <ginger@trgtechlink.com>"
LABEL project="the-life-shield"

# System dependencies for building Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    libffi-dev \
    libssl-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Upgrade pip
RUN pip install --upgrade pip wheel setuptools

# Copy requirements and install dependencies
WORKDIR /build
COPY requirements*.txt ./
RUN pip install --no-cache-dir -r requirements.txt


# ------------------------------------
# Stage 2: Production (slim)
# ------------------------------------
FROM python:3.11-slim AS production

LABEL maintainer="TRG TechLink <ginger@trgtechlink.com>"
LABEL project="the-life-shield"
LABEL stage="production"

# Runtime-only system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    netcat-traditional \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser -s /sbin/nologin appuser

# App working directory
WORKDIR /app

# Copy application code
COPY --chown=appuser:appuser . .

# Copy startup scripts
COPY --chown=appuser:appuser scripts/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Switch to non-root user
USER appuser

# Expose API port
EXPOSE 8000

# Health check — hits /health endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]


# ------------------------------------
# Stage 3: Development (hot-reload)
# ------------------------------------
FROM production AS development

LABEL stage="development"

USER root

# Install dev tools
RUN pip install --no-cache-dir \
    watchfiles \
    pytest \
    pytest-asyncio \
    pytest-cov \
    httpx \
    faker \
    ipython

USER appuser

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload", "--reload-dir", "/app"]
