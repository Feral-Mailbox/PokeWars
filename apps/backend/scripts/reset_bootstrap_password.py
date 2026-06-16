"""Generate a new bootstrap admin password and sync it to the database and .env."""

from __future__ import annotations

import os
import re
import secrets
from pathlib import Path

from dotenv import load_dotenv

BACKEND_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = BACKEND_ROOT / ".env"


def _generate_password(length: int = 16) -> str:
    alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    while True:
        password = "".join(secrets.choice(alphabet) for _ in range(length))
        if (
            any(c.islower() for c in password)
            and any(c.isupper() for c in password)
            and any(c.isdigit() for c in password)
        ):
            return password


def _update_env_password(password: str) -> None:
    text = ENV_PATH.read_text(encoding="utf-8")
    line = f'BOOTSTRAP_ADMIN_PASSWORD="{password}"'
    if re.search(r"^BOOTSTRAP_ADMIN_PASSWORD=", text, flags=re.MULTILINE):
        text = re.sub(r"^BOOTSTRAP_ADMIN_PASSWORD=.*$", line, text, count=1, flags=re.MULTILINE)
    else:
        text = text.rstrip() + f"\n{line}\n"
    ENV_PATH.write_text(text, encoding="utf-8")


def _upsert_admin(username: str, email: str, password: str) -> None:
    from app.db.database import get_sessionmaker
    from app.db.models import User, UserRole
    from app.routes.auth import hash_password

    Session = get_sessionmaker()
    db = Session()
    try:
        user = db.query(User).filter(User.username == username).first()
        hashed = hash_password(password)
        if user is None:
            user = User(
                username=username,
                email=email,
                hashed_password=hashed,
                avatar="default.png",
                elo=1000,
                currency=0,
                role=UserRole.admin,
            )
            db.add(user)
        else:
            user.hashed_password = hashed
            user.role = UserRole.admin
            db.add(user)
        db.commit()
    finally:
        db.close()


def main() -> None:
    load_dotenv(ENV_PATH, override=True)
    username = os.getenv("BOOTSTRAP_ADMIN_USERNAME", "anorgandroid").strip()
    email = os.getenv("BOOTSTRAP_ADMIN_EMAIL", f"{username}@poketactics.local")

    password = _generate_password()
    _update_env_password(password)
    _upsert_admin(username, email, password)

    print("\n=== Bootstrap admin password reset ===")
    print(f"Username: {username}")
    print(f"Password: {password}")
    print(f"({len(password)} characters — copy exactly, no spaces)")
    print(f"Updated {ENV_PATH.name} and database hash.")


if __name__ == "__main__":
    main()
