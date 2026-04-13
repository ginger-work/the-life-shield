"""
The Life Shield — FastAPI Application Entry Point (app package)
Structured using FastAPI best practices: api_router pattern.
"""
from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from app.core.config import settings
from app.core.database import Base, engine
from app.api.v1 import api_router

# ─── Structured Logging ───────────────────────────────────────────────────────

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer() if not settings.APP_DEBUG
        else structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logging.basicConfig(
    format="%(message)s",
    level=logging.DEBUG if settings.APP_DEBUG else logging.INFO,
)

log = structlog.get_logger(__name__)

# ─── Rate Limiter ─────────────────────────────────────────────────────────────

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[f"{settings.RATE_LIMIT_PER_MINUTE}/minute"],
)

# ─── Lifespan ─────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("starting_life_shield", version=settings.APP_VERSION, env=settings.APP_ENV)
    if settings.APP_ENV in ("development", "test"):
        Base.metadata.create_all(bind=engine)
        log.info("database_tables_created")
    yield
    log.info("shutting_down_life_shield")

# ─── FastAPI App ──────────────────────────────────────────────────────────────

app = FastAPI(
    title=settings.APP_NAME,
    description="AI-powered credit repair platform. FCRA & CROA compliant. Multi-agent system.",
    version=settings.APP_VERSION,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    contact={"name": "The Life Shield", "email": "support@thelifeshield.com"},
    license_info={"name": "Proprietary"},
    lifespan=lifespan,
)

# ─── Middleware ────────────────────────────────────────────────────────────────

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-Correlation-ID", "X-Request-ID"],
)


@app.middleware("http")
async def correlation_and_logging_middleware(request: Request, call_next):
    """Attach correlation IDs and log every request."""
    correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
    request_id = str(uuid.uuid4())
    start = time.perf_counter()

    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(
        correlation_id=correlation_id,
        request_id=request_id,
        method=request.method,
        path=request.url.path,
        client_ip=request.client.host if request.client else "unknown",
    )

    response = await call_next(request)
    elapsed_ms = round((time.perf_counter() - start) * 1000, 2)

    log.info("request_completed", status_code=response.status_code, elapsed_ms=elapsed_ms)
    response.headers["X-Correlation-ID"] = correlation_id
    response.headers["X-Request-ID"] = request_id
    return response

# ─── Exception Handlers ───────────────────────────────────────────────────────

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = [
        {"field": ".".join(str(loc) for loc in e["loc"]), "message": e["msg"], "type": e["type"]}
        for e in exc.errors()
    ]
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"error": "VALIDATION_ERROR", "details": errors},
    )


@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    return JSONResponse(
        status_code=404,
        content={"error": "NOT_FOUND", "message": "Resource not found."},
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    log.error("unhandled_exception", exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={"error": "INTERNAL_ERROR", "message": "An unexpected error occurred."},
    )

# ─── Routers ──────────────────────────────────────────────────────────────────

app.include_router(api_router, prefix="/api/v1")

# ─── Health ───────────────────────────────────────────────────────────────────

@app.get("/health", include_in_schema=False)
async def health_check():
    from app.core.database import check_database_health
    db_status = check_database_health()
    return {
        "status": "healthy" if db_status.get("healthy") else "degraded",
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "database": db_status,
    }


@app.get("/", include_in_schema=False)
async def root():
    return {
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/api/docs",
        "health": "/health",
    }
