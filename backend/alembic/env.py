from logging.config import fileConfig

import os
import sys
from alembic import context
from sqlalchemy import engine_from_config, pool

"""
Ensure project root is on sys.path so `import app` works when running alembic.

This handles two layouts:
- when alembic lives at backend/alembic (one level up is backend which contains app)
- when project files are copied to /app and alembic is at /app/alembic (one level up is /app)

We prefer the nearest parent that contains an `app` package.
"""
cwd_dir = os.path.abspath(os.path.dirname(__file__))
candidate = os.path.abspath(os.path.join(cwd_dir, '..'))
if os.path.exists(os.path.join(candidate, 'app')):
    sys.path.insert(0, candidate)
else:
    # fallback to two levels up (older layout)
    sys.path.insert(0, os.path.abspath(os.path.join(cwd_dir, '..', '..')))

from app.core.config import DATABASE_URL
from app.db.base import Base
import app.models  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", DATABASE_URL)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
