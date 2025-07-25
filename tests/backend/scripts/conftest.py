import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

import app.db.models as models
from app.db import database

@pytest.fixture(scope="session")
def test_engine():
    # one shared in-memory SQLite connection
    return create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )

@pytest.fixture(scope="function")
def db(test_engine):
    # make the app (and the seeding scripts) use this engine
    database.configure_engine(test_engine)

    # clean schema for every test
    models.Base.metadata.drop_all(bind=test_engine)
    models.Base.metadata.create_all(bind=test_engine)

    SessionTesting = database.get_sessionmaker()
    session = SessionTesting()
    try:
        yield session
    finally:
        session.close()
        models.Base.metadata.drop_all(bind=test_engine)
