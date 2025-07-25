# app/db/database.py
import os
from typing import Optional
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, Session

_engine: Optional[Engine] = None
_SessionLocal: Optional[sessionmaker] = None

def configure_engine(url_or_engine=None, **kwargs) -> Engine:
    """
    Configure (or reconfigure) the global engine + SessionLocal.
    In tests, call this with your own engine (e.g. StaticPool memory).
    """
    global _engine, _SessionLocal

    if url_or_engine is None:
        url_or_engine = os.getenv("DATABASE_URL", "sqlite:///./dev.db")

    if hasattr(url_or_engine, "connect"):  # looks like an Engine
        _engine = url_or_engine
    else:
        _engine = create_engine(url_or_engine, **kwargs)

    _SessionLocal = sessionmaker(bind=_engine, autocommit=False, autoflush=False)
    return _engine

def get_engine() -> Engine:
    global _engine
    if _engine is None:
        configure_engine()  # default initialize
    return _engine

def get_sessionmaker() -> sessionmaker:
    global _SessionLocal
    if _SessionLocal is None:
        configure_engine()
    return _SessionLocal

def get_db() -> Session:
    """FastAPI dependency – import and use this in app.dependencies."""
    SessionLocal = get_sessionmaker()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
