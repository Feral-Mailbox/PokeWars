import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool
from app.db.database import configure_engine, get_engine, get_sessionmaker

def test_configure_custom_engine():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    configured = configure_engine(engine)
    assert configured == engine

def test_get_engine_defaults():
    engine = get_engine()
    assert str(engine.url).startswith("sqlite:///")

def test_sessionmaker_provides_session():
    Session = get_sessionmaker()
    with Session() as session:
        result = session.execute(text("SELECT 1")).scalar()
        assert result == 1
