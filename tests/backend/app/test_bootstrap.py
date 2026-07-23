import pytest

import app.db.models as models
from app.bootstrap import BootstrapError, ensure_bootstrap_admin
from app.db.models import UserRole


def test_bootstrap_admin_skips_creation_without_password(db, monkeypatch):
    monkeypatch.setattr(
        "app.bootstrap._bootstrap_settings",
        lambda: {"username": "anorgandroid", "email": "a@b.c", "password": ""},
    )
    with pytest.raises(BootstrapError):
        ensure_bootstrap_admin(db)
    assert db.query(models.User).count() == 0


def test_bootstrap_admin_skips_weak_password(db, monkeypatch):
    monkeypatch.setattr(
        "app.bootstrap._bootstrap_settings",
        lambda: {"username": "anorgandroid", "email": "a@b.c", "password": "1234"},
    )
    with pytest.raises(BootstrapError):
        ensure_bootstrap_admin(db)
    assert db.query(models.User).count() == 0


def test_bootstrap_admin_syncs_password_for_existing_user(db, monkeypatch):
    from app.routes.auth import hash_password, verify_password

    monkeypatch.setattr(
        "app.bootstrap._bootstrap_settings",
        lambda: {
            "username": "anorgandroid",
            "email": "anorgandroid@example.com",
            "password": "old-bootstrap-password-value",
        },
    )
    user = models.User(
        username="anorgandroid",
        email="anorgandroid@example.com",
        hashed_password=hash_password("previous-password-value"),
        avatar="default.png",
        elo=1000,
        currency=0,
        role=models.UserRole.admin,
    )
    db.add(user)
    db.commit()

    ensure_bootstrap_admin(db)

    db.refresh(user)
    assert verify_password("old-bootstrap-password-value", user.hashed_password)


def test_bootstrap_admin_creates_with_strong_password(db, monkeypatch):
    monkeypatch.setattr(
        "app.bootstrap._bootstrap_settings",
        lambda: {
            "username": "anorgandroid",
            "email": "anorgandroid@poketactics.local",
            "password": "very-strong-bootstrap-password",
        },
    )
    ensure_bootstrap_admin(db)
    user = db.query(models.User).filter_by(username="anorgandroid").first()
    assert user is not None
    assert user.role == UserRole.admin
