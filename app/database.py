"""Database session backward-compatibility module re-exporting from app.db.session."""
from app.db.session import engine, SessionLocal, Base, get_db

__all__ = ["engine", "SessionLocal", "Base", "get_db"]
