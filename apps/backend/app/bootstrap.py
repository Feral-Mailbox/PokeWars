import logging
import os

from sqlalchemy.orm import Session

from app.db.database import get_sessionmaker
from app.db.models import User, UserRole

logger = logging.getLogger("bootstrap")


def _bootstrap_settings() -> dict[str, str]:
    return {
        "username": os.getenv("BOOTSTRAP_ADMIN_USERNAME", "anorgandroid").strip(),
        "email": os.getenv("BOOTSTRAP_ADMIN_EMAIL", "anorgandroid@poketactics.local"),
        "password": os.getenv("BOOTSTRAP_ADMIN_PASSWORD", "1234"),
    }


def _hash_password(password: str) -> str:
    from app.routes.auth import hash_password

    return hash_password(password)


def ensure_bootstrap_admin(db: Session) -> None:
    settings = _bootstrap_settings()
    username = settings["username"]
    if not username:
        logger.warning("BOOTSTRAP_ADMIN_USERNAME is empty; skipping bootstrap admin")
        return

    user = db.query(User).filter(User.username == username).first()
    if user is None:
        user = User(
            username=username,
            email=settings["email"],
            hashed_password=_hash_password(settings["password"]),
            avatar="default.png",
            elo=1000,
            currency=0,
            role=UserRole.admin,
        )
        db.add(user)
        db.commit()
        logger.info("Created bootstrap admin account for '%s'", username)
        return

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
