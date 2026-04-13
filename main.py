"""
The Life Shield - FastAPI Application Entry Point
Authentication, CORS, rate limiting, logging, error handling, API versioning.
"""

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

from api import auth_router, agents_router
from app.api.v1 import credit_router, disputes_router
from config.security import settings
from database import init_db

# ─────────────────────────────────────────────
# STRUCTURED LOGGING SETUP
# ─────────────────────────────────────────────

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer() if not settings.DEBUG
        else structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logging.basicConfig(
    format="%(message)s",
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
)

log = structlog.get_logger(__name__)


# ─────────────────────────────────────────────
# RATE LIMITER
# ─────────────────────────────────────────────

limiter = Limiter(key_func=get_remote_address, default_limits=[settings.RATE_LIMIT_DEFAULT])


# ─────────────────────────────────────────────
# APP LIFESPAN
# ─────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup + shutdown events."""
    log.info("Starting The Life Shield API", version="1.0.0", env="debug" if settings.DEBUG else "production")
    if settings.DEBUG:
        await init_db()  # Only auto-create tables in dev; use Alembic in prod
    yield
    log.info("Shutting down The Life Shield API")


# ─────────────────────────────────────────────
# FASTAPI APP
# ─────────────────────────────────────────────

app = FastAPI(
    title=settings.PROJECT_NAME,
    description=(
        "Premium AI credit repair platform — authentication, agent management, "
        "FCRA/CROA compliant dispute workflow, and multi-channel communication."
    ),
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    contact={
        "name": "The Life Shield Team",
        "email": "dev@thelifeshield.com",
    },
    license_info={"name": "Proprietary"},
    lifespan=lifespan,
)

# ─────────────────────────────────────────────
# MIDDLEWARE
# ─────────────────────────────────────────────

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=settings.ALLOW_CREDENTIALS,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-Correlation-ID", "X-Request-ID"],
)


# Request correlation ID + logging
@app.middleware("http")
async def logging_and_correlation_middleware(request: Request, call_next):
    correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
    request_id = str(uuid.uuid4())
    start_time = time.perf_counter()

    # Bind context for structured logging
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(
        correlation_id=correlation_id,
        request_id=request_id,
        method=request.method,
        path=request.url.path,
        client_ip=request.client.host if request.client else "unknown",
    )

    response = await call_next(request)

    elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
    log.info(
        "request_completed",
        status_code=response.status_code,
        elapsed_ms=elapsed_ms,
    )

    response.headers["X-Correlation-ID"] = correlation_id
    response.headers["X-Request-ID"] = request_id
    return response


# ─────────────────────────────────────────────
# EXCEPTION HANDLERS
# ─────────────────────────────────────────────

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Return structured 422 with field-level error details."""
    errors = []
    for error in exc.errors():
        errors.append({
            "field": ".".join(str(loc) for loc in error["loc"]),
            "message": error["msg"],
            "type": error["type"],
        })
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "VALIDATION_ERROR",
            "message": "Request validation failed",
            "details": errors,
        },
    )


@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    return JSONResponse(
        status_code=404,
        content={"error": "NOT_FOUND", "message": "The requested resource does not exist."},
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    log.error("unhandled_exception", exc_info=exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": "INTERNAL_ERROR", "message": "An unexpected error occurred."},
    )


# ─────────────────────────────────────────────
# API ROUTERS — versioned under /api/v1
# ─────────────────────────────────────────────

API_V1 = settings.API_V1_PREFIX  # /api/v1

app.include_router(auth_router, prefix=API_V1)
app.include_router(agents_router, prefix=API_V1)
app.include_router(credit_router, prefix=API_V1)
app.include_router(disputes_router, prefix=API_V1)


# ─────────────────────────────────────────────
# HEALTH CHECK
# ─────────────────────────────────────────────

@app.get("/health", tags=["Health"], include_in_schema=False)
async def health_check():
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "version": "1.0.0",
    }


# ─────────────────────────────────────────────
# ROOT
# ─────────────────────────────────────────────

@app.get("/", include_in_schema=False)
async def root():
    return {
        "service": settings.PROJECT_NAME,
        "docs": "/api/docs",
        "redoc": "/api/redoc",
        "openapi": "/api/openapi.json",
    }
