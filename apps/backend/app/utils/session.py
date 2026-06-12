import os
from datetime import datetime, timedelta, timezone

import jwt
from jwt import InvalidTokenError

_INSECURE_SECRETS = frozenset(
    {
        "",
        "super-secret-key",
        "change-me",
        "test-session-secret-for-pytest-only",
    }
)


def _session_secret() -> str:
    secret = os.getenv("SESSION_SECRET", "").strip()
    if secret in _INSECURE_SECRETS:
        # Allow the pytest default when running under pytest.
        if os.getenv("PYTEST_CURRENT_TEST"):
            return "test-session-secret-for-pytest-only"
        raise RuntimeError(
            "SESSION_SECRET must be set to a long random value (not a default placeholder)."
        )
    return secret


def create_session_token(user_id: int) -> str:
    expire_hours = int(os.getenv("SESSION_EXPIRE_HOURS", "24"))
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(hours=expire_hours),
    }
    return jwt.encode(payload, _session_secret(), algorithm="HS256")


def decode_session_token(token: str) -> int | None:
    if not token:
        return None
    try:
        payload = jwt.decode(token, _session_secret(), algorithms=["HS256"])
        return int(payload["sub"])
    except (InvalidTokenError, ValueError, KeyError, TypeError):
        return None
