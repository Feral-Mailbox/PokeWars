import os

import pytest

from app.utils import session as session_utils
from app.utils.session import create_session_token, decode_session_token


def test_decode_session_token_rejects_empty():
    assert decode_session_token("") is None
    assert decode_session_token(None) is None  # type: ignore[arg-type]


def test_session_secret_rejects_insecure_outside_pytest(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "change-me")
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    with pytest.raises(RuntimeError, match="SESSION_SECRET"):
        session_utils._session_secret()


def test_session_secret_allows_pytest_placeholder(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-session-secret-for-pytest-only")
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "tests/backend/app/utils/test_session.py::x")
    assert session_utils._session_secret() == "test-session-secret-for-pytest-only"


def test_create_session_token_respects_expire_hours(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "ci-test-session-secret-value-32chars!!")
    monkeypatch.setenv("SESSION_EXPIRE_HOURS", "2")
    token = create_session_token(99)
    assert decode_session_token(token) == 99
