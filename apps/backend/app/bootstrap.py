import logging
import os
from pathlib import Path

from sqlalchemy.orm import Session

from app.db.database import get_sessionmaker
from app.db.models import User, UserRole

logger = logging.getLogger("bootstrap")
BACKEND_ROOT = Path(__file__).resolve().parent.parent

_INSECURE_PASSWORDS = frozenset(
    {
        "1234",
        "password",
        "admin",
        "change-me-on-first-run",
        "supersecure",
    }
)


class BootstrapError(RuntimeError):
    """Raised when the bootstrap admin account could not be created or verified."""


def _bootstrap_settings() -> dict[str, str]:
    from dotenv import load_dotenv

    # Prefer the mounted .env over stale container env from an older compose start.
    load_dotenv(BACKEND_ROOT / ".env", override=True)
    return {
        "username": os.getenv("BOOTSTRAP_ADMIN_USERNAME", "anorgandroid").strip(),
        "email": os.getenv("BOOTSTRAP_ADMIN_EMAIL", "anorgandroid@poketactics.local"),
        "password": os.getenv("BOOTSTRAP_ADMIN_PASSWORD", "").strip().strip('"'),
    }


def _password_is_acceptable_for_create(password: str) -> bool:
    if len(password) < 12:
        return False
    return password.lower() not in _INSECURE_PASSWORDS


def _password_is_acceptable_for_sync(password: str) -> bool:
    if len(password) < 8:
        return False
    return password.lower() not in _INSECURE_PASSWORDS


def _hash_password(password: str) -> str:
    from app.routes.auth import hash_password

    return hash_password(password)


def _emit(message: str, *, level: int = logging.INFO) -> None:
    print(message, flush=True)
    logger.log(level, message)


def _sync_bootstrap_password(user: User, password: str, db: Session) -> bool:
    """Update the bootstrap admin hash when BOOTSTRAP_ADMIN_PASSWORD changes."""
    if not _password_is_acceptable_for_sync(password):
        return False

    from app.routes.auth import verify_password

    try:
        if verify_password(password, user.hashed_password):
            return False
    except Exception:
        logger.exception("Could not verify existing bootstrap admin password")

    user.hashed_password = _hash_password(password)
    db.add(user)
    db.commit()
    _emit("Synced bootstrap admin password from BOOTSTRAP_ADMIN_PASSWORD")
    return True


def ensure_bootstrap_admin(db: Session) -> User:
    settings = _bootstrap_settings()
    username = settings["username"]
    if not username:
        _emit("BOOTSTRAP_ADMIN_USERNAME is empty; skipping bootstrap admin", level=logging.WARNING)
        raise BootstrapError("BOOTSTRAP_ADMIN_USERNAME is empty")

    password = settings["password"]
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        if not _password_is_acceptable_for_create(password):
            if _password_is_acceptable_for_sync(password):
                message = (
                    f"Bootstrap admin '{username}' does not exist yet. "
                    "BOOTSTRAP_ADMIN_PASSWORD must be at least 12 characters to "
                    "auto-create the account, or register the user manually."
                )
            else:
                message = (
                    "BOOTSTRAP_ADMIN_PASSWORD must be set to a unique password of at least "
                    "12 characters before the bootstrap admin can be created."
                )
            _emit(f"ERROR: {message}", level=logging.ERROR)
            raise BootstrapError(message)

        user = User(
            username=username,
            email=settings["email"],
            hashed_password=_hash_password(password),
            avatar="default.png",
            elo=1000,
            currency=0,
            role=UserRole.admin,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        _emit(f"Created bootstrap admin account for '{username}'")
        return user

    if _sync_bootstrap_password(user, password, db):
        db.refresh(user)

    if user.role != UserRole.admin:
        user.role = UserRole.admin
        db.add(user)
        db.commit()
        db.refresh(user)
        _emit(f"Promoted existing user '{username}' to admin")
        return user

    _emit(f"Bootstrap admin '{username}' already exists")
    return user


def run_bootstrap_admin() -> User:
    try:
        Session = get_sessionmaker()
        db = Session()
        try:
            return ensure_bootstrap_admin(db)
        finally:
            db.close()
    except BootstrapError:
        raise
    except Exception as exc:
        logger.exception("Bootstrap admin setup failed")
        raise BootstrapError("Bootstrap admin setup failed") from exc
