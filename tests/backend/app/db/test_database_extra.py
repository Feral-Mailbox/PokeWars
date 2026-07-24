import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from app.db import database


def test_configure_engine_from_url_string(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    engine = database.configure_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    assert engine is database.get_engine()
    with engine.connect() as conn:
        assert conn.execute(text("SELECT 1")).scalar() == 1


def test_configure_engine_uses_database_url_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite+pysqlite:///:memory:")
    engine = database.configure_engine()
    assert "sqlite" in str(engine.url)


def test_get_sessionmaker_initializes_when_only_engine_missing_session(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite+pysqlite:///:memory:")
    database._engine = None
    database._SessionLocal = None
    # Force engine first, then clear only SessionLocal to hit the lazy branch.
    database.get_engine()
    database._SessionLocal = None
    Session = database.get_sessionmaker()
    assert Session is not None


def test_get_db_yields_and_closes_session(monkeypatch):
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    database.configure_engine(engine)
    gen = database.get_db()
    session = next(gen)
    assert session.execute(text("SELECT 1")).scalar() == 1
    with pytest.raises(StopIteration):
        next(gen)
