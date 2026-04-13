"""
Application configuration using pydantic-settings.
All values read from environment variables with sensible defaults.
"""
from functools import lru_cache
from typing import List, Optional

from pydantic import AnyHttpUrl, EmailStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Central configuration class.
    Reads from environment variables (and .env file in development).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Application ---
    APP_ENV: str = "development"
    APP_SECRET_KEY: str = "change-this-in-production"
    APP_DEBUG: bool = False
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    APP_NAME: str = "The Life Shield API"
    APP_VERSION: str = "1.0.0"
    APP_DESCRIPTION: str = "AI-powered Credit Repair Platform - Phase 1 Foundation"

    # --- Database ---
    DATABASE_URL: str = "postgresql://lifeshield:lifeshield_dev_password@localhost:5432/lifeshield_db"
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20
    DATABASE_POOL_TIMEOUT: int = 30
    DATABASE_ECHO: bool = False  # Set True to log all SQL (debug only)

    # --- Redis ---
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # --- JWT ---
    JWT_SECRET_KEY: str = "change-this-jwt-secret-in-production"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    JWT_ALGORITHM: str = "HS256"

    # --- Password Policy ---
    BCRYPT_ROUNDS: int = 12
    MIN_PASSWORD_LENGTH: int = 12

    # --- CORS ---
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173"

    @property
    def cors_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]

    # --- Rate Limiting ---
    RATE_LIMIT_PER_MINUTE: int = 60
    RATE_LIMIT_PER_HOUR: int = 500
    FAILED_LOGIN_LOCKOUT_THRESHOLD: int = 5
    FAILED_LOGIN_LOCKOUT_DURATION_MINUTES: int = 15

    # --- External APIs (optional in Phase 1 - populated as APIs are integrated) ---
    STRIPE_SECRET_KEY: Optional[str] = None
    STRIPE_PUBLISHABLE_KEY: Optional[str] = None
    STRIPE_WEBHOOK_SECRET: Optional[str] = None

    TWILIO_ACCOUNT_SID: Optional[str] = None
    TWILIO_AUTH_TOKEN: Optional[str] = None
    TWILIO_PHONE_NUMBER: Optional[str] = None

    SENDGRID_API_KEY: Optional[str] = None
    SENDGRID_FROM_EMAIL: str = "noreply@thelifeshield.com"
    SENDGRID_FROM_NAME: str = "The Life Shield"

    OPENAI_API_KEY: Optional[str] = None
    OPENAI_MODEL: str = "gpt-4-turbo"

    ANTHROPIC_API_KEY: Optional[str] = None
    ANTHROPIC_MODEL: str = "claude-3-5-sonnet-20241022"

    ELEVENLABS_API_KEY: Optional[str] = None

    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    AWS_REGION: str = "us-east-1"
    AWS_S3_BUCKET: str = "lifeshield-documents-vault"

    SENTRY_DSN: Optional[str] = None

    # --- Credit Bureau APIs ---
    BUREAU_SANDBOX_MODE: bool = True  # Set False in production with real API keys

    # Equifax
    EQUIFAX_CLIENT_ID: Optional[str] = None
    EQUIFAX_CLIENT_SECRET: Optional[str] = None

    # Experian
    EXPERIAN_CLIENT_ID: Optional[str] = None
    EXPERIAN_CLIENT_SECRET: Optional[str] = None
    EXPERIAN_SUBCODE: Optional[str] = None

    # TransUnion
    TRANSUNION_API_KEY: Optional[str] = None
    TRANSUNION_API_SECRET: Optional[str] = None
    TRANSUNION_MEMBER_CODE: Optional[str] = None
    TRANSUNION_SECURITY_CODE: Optional[str] = None

    # iSoftPull
    ISOFTPULL_API_KEY: Optional[str] = None

    # --- Logging ---
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @property
    def is_development(self) -> bool:
        return self.APP_ENV == "development"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Return cached settings singleton.
    Use dependency injection in FastAPI: Depends(get_settings)
    """
    return Settings()


# Convenience alias
settings = get_settings()
