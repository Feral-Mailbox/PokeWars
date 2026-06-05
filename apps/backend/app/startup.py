import logging
import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from dotenv import load_dotenv

logger = logging.getLogger("startup")

BACKEND_ROOT = Path(__file__).resolve().parent.parent


def load_environment() -> None:
    load_dotenv(BACKEND_ROOT / ".env")


def run_db_migrations() -> None:
    ini_path = BACKEND_ROOT / "alembic.ini"
    if not ini_path.exists():
        logger.warning("alembic.ini not found; skipping migrations")
        return

    config = Config(str(ini_path))
    db_url = os.getenv("DATABASE_URL")
    if db_url:
        config.set_main_option("sqlalchemy.url", db_url)

    command.upgrade(config, "head")
    logger.info("Database migrations applied")


def run_startup_tasks() -> None:
    load_environment()
    try:
        run_db_migrations()
    except Exception:
        logger.exception("Database migration failed during startup")
        raise
    from app.bootstrap import run_bootstrap_admin

    run_bootstrap_admin()
