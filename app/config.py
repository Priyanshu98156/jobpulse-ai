"""Configuration backward-compatibility module re-exporting from app.core.config."""
from app.core.config import settings, Settings, BASE_DIR, DATA_DIR, UPLOADS_DIR

__all__ = ["settings", "Settings", "BASE_DIR", "DATA_DIR", "UPLOADS_DIR"]
