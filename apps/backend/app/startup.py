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


def should_skip_startup_tasks() -> bool:
    return os.getenv("SKIP_STARTUP_TASKS") == "1" or bool(os.getenv("PYTEST_CURRENT_TEST"))


def run_db_migrations() -> None:
    ini_path = BACKEND_ROOT / "alembic.ini"
    if not ini_path.exists():
        logger.warning("alembic.ini not found; skipping migrations")
        return

    config = Config(str(ini_path))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    db_url = os.getenv("DATABASE_URL")
    if db_url:
        config.set_main_option("sqlalchemy.url", db_url)

    command.upgrade(config, "head")
    logger.info("Database migrations applied")


def validate_security_settings() -> None:
    secret = os.getenv("SESSION_SECRET", "").strip()
    insecure_secrets = {"", "super-secret-key", "change-me"}
    if secret in insecure_secrets:
        raise RuntimeError(
            "SESSION_SECRET must be set to a long random value before starting the server."
        )


def run_startup_tasks() -> None:
    if should_skip_startup_tasks():
        logger.info("Skipping startup tasks (test mode)")
        return

    load_environment()
    validate_security_settings()
    try:
        run_db_migrations()
    except Exception:
        logger.exception("Database migration failed during startup")
        raise
    from app.bootstrap import run_bootstrap_admin

    run_bootstrap_admin()
