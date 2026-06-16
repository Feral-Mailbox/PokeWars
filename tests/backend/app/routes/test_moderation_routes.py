import json
import os
import tempfile

import pytest

import app.db.models as models
from app.db.models import UserRole
from app.dependencies import get_current_user
from app.main import app
from app.routes.auth import hash_password


def _make_user(db, username, role=UserRole.user):
    user = models.User(
        username=username,
        email=f"{username}@example.com",
        hashed_password=hash_password("password"),
        role=role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_moderation_queue_requires_staff(client, db):
    user = _make_user(db, "regular")
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        resp = client.get("/moderation/queue")
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_moderation_queue_accessible_to_admin(client, db):
    admin = _make_user(db, "adminuser", role=UserRole.admin)
    app.dependency_overrides[get_current_user] = lambda: admin
    try:
        resp = client.get("/moderation/queue")
        assert resp.status_code == 200
        assert resp.json() == []
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_bootstrap_admin_promotes_existing_user(db):
    from app.bootstrap import ensure_bootstrap_admin

    user = _make_user(db, "anorgandroid", role=UserRole.user)
    ensure_bootstrap_admin(db)
    db.refresh(user)
    assert user.role == UserRole.admin


def test_bootstrap_admin_skips_empty_username(db, monkeypatch):
    from app.bootstrap import BootstrapError, ensure_bootstrap_admin

    monkeypatch.delenv("BOOTSTRAP_ADMIN_USERNAME", raising=False)
    monkeypatch.setenv("BOOTSTRAP_ADMIN_USERNAME", "   ")
    with pytest.raises(BootstrapError):
        ensure_bootstrap_admin(db)
    assert db.query(models.User).count() == 0
