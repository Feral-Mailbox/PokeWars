# tests/apps/backend/app/routes/conftest.py
import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

import app.db.models as models
from app.db import database
from app.main import app
from app.dependencies import get_db
from fastapi.testclient import TestClient


@pytest.fixture(scope="session")
def test_engine():
    """Shared in-memory database for all route tests."""
    return create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )


@pytest.fixture(scope="function")
def db(test_engine):
    """Session fixture that rebuilds the schema per test."""
    database.configure_engine(test_engine)
    models.Base.metadata.drop_all(bind=test_engine)
    models.Base.metadata.create_all(bind=test_engine)

    SessionTesting = database.get_sessionmaker()
    session = SessionTesting()
    try:
        yield session
    finally:
        session.close()
        models.Base.metadata.drop_all(bind=test_engine)


@pytest.fixture(scope="function")
def client(db):
    """Test client that overrides get_db dependency."""
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
