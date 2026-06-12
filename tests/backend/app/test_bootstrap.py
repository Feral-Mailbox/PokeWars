import app.db.models as models
from app.bootstrap import ensure_bootstrap_admin
from app.db.models import UserRole


def test_bootstrap_admin_skips_creation_without_password(db, monkeypatch):
    monkeypatch.delenv("BOOTSTRAP_ADMIN_PASSWORD", raising=False)
    ensure_bootstrap_admin(db)
    assert db.query(models.User).count() == 0


def test_bootstrap_admin_skips_weak_password(db, monkeypatch):
    monkeypatch.setenv("BOOTSTRAP_ADMIN_PASSWORD", "1234")
    ensure_bootstrap_admin(db)
    assert db.query(models.User).count() == 0


def test_bootstrap_admin_creates_with_strong_password(db, monkeypatch):
    monkeypatch.setenv("BOOTSTRAP_ADMIN_PASSWORD", "very-strong-bootstrap-password")
    ensure_bootstrap_admin(db)
    user = db.query(models.User).filter_by(username="anorgandroid").first()
    assert user is not None
    assert user.role == UserRole.admin
