from unittest.mock import MagicMock

import pytest

import app.bootstrap as bootstrap
import app.db.models as models
from app.bootstrap import BootstrapError, ensure_bootstrap_admin, run_bootstrap_admin
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


def test_bootstrap_settings_reads_env(monkeypatch):
    monkeypatch.setattr("dotenv.load_dotenv", MagicMock())
    monkeypatch.setenv("BOOTSTRAP_ADMIN_USERNAME", "boss")
    monkeypatch.setenv("BOOTSTRAP_ADMIN_EMAIL", "boss@example.com")
    monkeypatch.setenv("BOOTSTRAP_ADMIN_PASSWORD", '"secret-bootstrap-pass"')
    settings = bootstrap._bootstrap_settings()
    assert settings == {
        "username": "boss",
        "email": "boss@example.com",
        "password": "secret-bootstrap-pass",
    }


def test_sync_skips_unacceptable_password(db, monkeypatch):
    from app.routes.auth import hash_password

    user = models.User(
        username="anorgandroid",
        email="a@b.c",
        hashed_password=hash_password("previous-password-value"),
        avatar="default.png",
        elo=1000,
        currency=0,
        role=UserRole.admin,
    )
    db.add(user)
    db.commit()

    assert bootstrap._sync_bootstrap_password(user, "short", db) is False
    assert bootstrap._sync_bootstrap_password(user, "password", db) is False


def test_sync_rehashes_when_verify_raises(db, monkeypatch):
    from app.routes.auth import hash_password, verify_password

    user = models.User(
        username="anorgandroid",
        email="a@b.c",
        hashed_password=hash_password("previous-password-value"),
        avatar="default.png",
        elo=1000,
        currency=0,
        role=UserRole.admin,
    )
    db.add(user)
    db.commit()

    monkeypatch.setattr(
        "app.routes.auth.verify_password",
        MagicMock(side_effect=ValueError("bad hash")),
    )
    assert bootstrap._sync_bootstrap_password(user, "new-bootstrap-password", db) is True
    db.refresh(user)
    assert verify_password("new-bootstrap-password", user.hashed_password)


def test_create_rejects_medium_length_password_with_specific_message(db, monkeypatch):
    monkeypatch.setattr(
        "app.bootstrap._bootstrap_settings",
        lambda: {
            "username": "anorgandroid",
            "email": "a@b.c",
            "password": "ten-chars!",  # 10 chars: sync-ok, create-not-ok
        },
    )
    with pytest.raises(BootstrapError, match="at least 12 characters to"):
        ensure_bootstrap_admin(db)


def test_ensure_existing_admin_already_exists(db, monkeypatch):
    from app.routes.auth import hash_password

    password = "already-matching-password"
    user = models.User(
        username="anorgandroid",
        email="a@b.c",
        hashed_password=hash_password(password),
        avatar="default.png",
        elo=1000,
        currency=0,
        role=UserRole.admin,
    )
    db.add(user)
    db.commit()
    monkeypatch.setattr(
        "app.bootstrap._bootstrap_settings",
        lambda: {"username": "anorgandroid", "email": "a@b.c", "password": password},
    )
    result = ensure_bootstrap_admin(db)
    assert result.id == user.id


def test_run_bootstrap_admin_success(monkeypatch):
    fake_user = MagicMock()
    session = MagicMock()
    sessionmaker = MagicMock(return_value=session)
    monkeypatch.setattr(bootstrap, "get_sessionmaker", lambda: sessionmaker)
    monkeypatch.setattr(bootstrap, "ensure_bootstrap_admin", MagicMock(return_value=fake_user))
    assert run_bootstrap_admin() is fake_user
    session.close.assert_called_once()


def test_run_bootstrap_admin_reraises_bootstrap_error(monkeypatch):
    session = MagicMock()
    sessionmaker = MagicMock(return_value=session)
    monkeypatch.setattr(bootstrap, "get_sessionmaker", lambda: sessionmaker)
    monkeypatch.setattr(
        bootstrap,
        "ensure_bootstrap_admin",
        MagicMock(side_effect=BootstrapError("nope")),
    )
    with pytest.raises(BootstrapError, match="nope"):
        run_bootstrap_admin()
    session.close.assert_called_once()


def test_run_bootstrap_admin_wraps_unexpected_errors(monkeypatch):
    monkeypatch.setattr(
        bootstrap,
        "get_sessionmaker",
        MagicMock(side_effect=RuntimeError("engine down")),
    )
    with pytest.raises(BootstrapError, match="Bootstrap admin setup failed"):
        run_bootstrap_admin()
