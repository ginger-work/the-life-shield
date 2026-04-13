"""
Alembic Migration Environment — The Life Shield

Discovers all SQLAlchemy models by importing app.models.
Uses DATABASE_URL from environment variable if set (overrides alembic.ini).
"""
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Load application config
config = context.config

# Override sqlalchemy.url from environment if available
db_url = os.environ.get("DATABASE_URL")
if db_url:
    config.set_main_option("sqlalchemy.url", db_url)

# Logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import all models so Alembic autogenerate can discover them
# This MUST import Base and all model modules
from app.core.database import Base

# Import all model modules to register their metadata
import app.models.user          # noqa: F401
import app.models.agent         # noqa: F401
import app.models.client        # noqa: F401
import app.models.dispute       # noqa: F401
import app.models.communication  # noqa: F401
import app.models.billing        # noqa: F401
import app.models.audit          # noqa: F401
import app.models.compliance     # noqa: F401
import app.models.document       # noqa: F401
import app.models.appointment    # noqa: F401

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode.
    Emits SQL to stdout without a live DB connection.
    Useful for generating migration scripts to review.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    Run migrations in 'online' mode with a live DB connection.
    Used for `alembic upgrade head` in CI and production.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
