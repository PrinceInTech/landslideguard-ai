"""Database engine, session and base setup using SQLAlchemy.

The prototype uses SQLite for zero-config operation. The repository layer
(see app/services) abstracts all database access so a MongoDB backend could be
swapped in later without changing the API layer.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import settings

connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(settings.DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    # Import models so tables are registered on Base.metadata
    from app import models  # noqa: F401
    Base.metadata.create_all(bind=engine)
