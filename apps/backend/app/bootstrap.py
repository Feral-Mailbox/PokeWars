import logging
import os

from sqlalchemy.orm import Session

from app.db.database import get_sessionmaker
from app.db.models import User, UserRole

logger = logging.getLogger("bootstrap")

_INSECURE_PASSWORDS = frozenset(
    {
        "1234",
        "password",
        "admin",
        "change-me-on-first-run",
        "supersecure",
    }
)


def _bootstrap_settings() -> dict[str, str]:
    return {
        "username": os.getenv("BOOTSTRAP_ADMIN_USERNAME", "anorgandroid").strip(),
        "email": os.getenv("BOOTSTRAP_ADMIN_EMAIL", "anorgandroid@poketactics.local"),
        "password": os.getenv("BOOTSTRAP_ADMIN_PASSWORD", "").strip(),
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
    logger.info("Synced bootstrap admin password from BOOTSTRAP_ADMIN_PASSWORD")
    return True


def ensure_bootstrap_admin(db: Session) -> None:
    settings = _bootstrap_settings()
    username = settings["username"]
    if not username:
        logger.warning("BOOTSTRAP_ADMIN_USERNAME is empty; skipping bootstrap admin")
        return

    password = settings["password"]
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        if not _password_is_acceptable_for_create(password):
            if _password_is_acceptable_for_sync(password):
                logger.error(
                    "Bootstrap admin '%s' does not exist yet. "
                    "BOOTSTRAP_ADMIN_PASSWORD must be at least 12 characters to "
                    "auto-create the account, or register the user manually.",
                    username,
                )
            else:
                logger.error(
                    "BOOTSTRAP_ADMIN_PASSWORD must be set to a unique password of at least "
                    "12 characters before the bootstrap admin can be created."
                )
            return

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
        logger.info("Created bootstrap admin account for '%s'", username)
        return

    _sync_bootstrap_password(user, password, db)

    if user.role != UserRole.admin:
        user.role = UserRole.admin
        db.add(user)
        db.commit()
        logger.info("Promoted existing user '%s' to admin", username)
        return

    logger.info("Bootstrap admin '%s' already exists", username)


def run_bootstrap_admin() -> None:
    try:
        Session = get_sessionmaker()
        db = Session()
        try:
            ensure_bootstrap_admin(db)
        finally:
            db.close()
    except Exception:
        logger.exception("Bootstrap admin setup failed")
        raise
