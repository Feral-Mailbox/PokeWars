import pytest
from app.utils.security import hash_password, verify_password
from argon2.exceptions import VerifyMismatchError

def test_hash_password_returns_different_string():
    plain = "securepassword"
    hashed = hash_password(plain)
    assert hashed != plain
    assert isinstance(hashed, str)
    assert hashed.startswith("$argon2")

def test_verify_password_success():
    plain = "correcthorsebatterystaple"
    hashed = hash_password(plain)
    assert verify_password(hashed, plain) is True

def test_verify_password_failure():
    hashed = hash_password("password123")
    result = verify_password(hashed, "wrongpassword")
    assert result is False
