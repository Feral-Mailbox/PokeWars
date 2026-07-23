import os
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

import app.db.models as models
from app.db import database
from app.dependencies import get_db
from app.main import app


@pytest.fixture(scope="session", autouse=True)
def _configure_test_environment():
    os.environ["SESSION_SECRET"] = "test-session-secret-for-pytest-only"
    os.environ["SKIP_STARTUP_TASKS"] = "1"


@pytest.fixture(autouse=True)
def _mock_redis(monkeypatch):
    """Avoid connecting to Docker hostname `redis` during unit tests."""
    fake = MagicMock()
    fake.publish.return_value = 1
    fake.get.return_value = None
    fake.set.return_value = True
    fake.delete.return_value = 1
    monkeypatch.setattr("app.routes.games.redis_client", fake)
    yield fake


@pytest.fixture(scope="session")
def test_engine():
    """Shared in-memory database for backend tests."""
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
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def make_test_map(
    db,
    *,
    name="Test Map",
    width=5,
    height=5,
    creator_id=None,
    allowed_modes=None,
):
    """Create and flush a Map row for tests that need Game.map_id."""
    map_obj = models.Map(
        name=name,
        creator_id=creator_id,
        is_official=True,
        width=width,
        height=height,
        tileset_names=["grass"],
        tile_data={"movement_cost": [[1] * width for _ in range(height)]},
        allowed_modes=allowed_modes or ["Conquest"],
        allowed_player_counts=[2],
    )
    db.add(map_obj)
    db.flush()
    return map_obj
