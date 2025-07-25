import sys
import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# Add the app directory to sys.path so Alembic can import your modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Import your Base from the correct path
from app.db.models import Base  # Updated path
from app.db.models import *

# Load Alembic Config
config = context.config

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# This will be used by Alembic for 'autogenerate'
target_metadata = Base.metadata

# Get database URL from .env
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "../../.env"))  # adjust to root .env

db_url = os.getenv("DATABASE_URL")
if not db_url:
    raise ValueError("DATABASE_URL is not set in .env")

config.set_main_option("sqlalchemy.url", db_url)

def run_migrations_offline():
    context.configure(
        url=db_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
