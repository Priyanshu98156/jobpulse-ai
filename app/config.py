import os
from pathlib import Path
from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
UPLOADS_DIR = DATA_DIR / "resumes"
UPLOADS_DIR.mkdir(exist_ok=True)

class Settings(BaseSettings):
    # Multi-Provider AI Settings
    AI_PROVIDER: str = os.getenv("AI_PROVIDER", "gemini") # gemini, groq, openrouter, mistral, cerebras, custom
    AI_API_KEY: str = os.getenv("AI_API_KEY", "") or os.getenv("GEMINI_API_KEY", "")
    AI_MODEL: str = os.getenv("AI_MODEL", "")
    AI_BASE_URL: str = os.getenv("AI_BASE_URL", "")

    # Legacy alias
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    
    # Adzuna API
    ADZUNA_APP_ID: str = os.getenv("ADZUNA_APP_ID", "")
    ADZUNA_APP_KEY: str = os.getenv("ADZUNA_APP_KEY", "")
    
    PORT: int = int(os.getenv("PORT", "8000"))
    HOST: str = os.getenv("HOST", "127.0.0.1")
    DEBUG: bool = os.getenv("DEBUG", "True").lower() in ("true", "1", "yes")
    
    SYNC_INTERVAL_MINUTES: int = int(os.getenv("SYNC_INTERVAL_MINUTES", "120"))
    AUTO_SYNC_ENABLED: bool = os.getenv("AUTO_SYNC_ENABLED", "True").lower() in ("true", "1", "yes")
    NOTIFICATION_MIN_SCORE: int = int(os.getenv("NOTIFICATION_MIN_SCORE", "80"))
    
    DATABASE_URL: str = f"sqlite:///{DATA_DIR / 'jobs.db'}"

    class Config:
        env_file = BASE_DIR / ".env"
        extra = "ignore"

settings = Settings()
