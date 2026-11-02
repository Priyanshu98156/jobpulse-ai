from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
UPLOADS_DIR = DATA_DIR / "resumes"
UPLOADS_DIR.mkdir(exist_ok=True)

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        extra="ignore"
    )

    # Server binding (Mandatory localhost binding per standards)
    HOST: str = "127.0.0.1"
    PORT: int = 8000
    DEBUG: bool = True

    # Security
    CSRF_SECRET: str = "jobpulse_local_csrf_secret_key"
    ALLOWED_HOSTS: list[str] = ["127.0.0.1:8000", "localhost:8000", "127.0.0.1", "localhost", "testserver"]

    # AI Provider Defaults
    AI_PROVIDER: str = "gemini"
    AI_API_KEY: str = ""
    AI_MODEL: str = ""
    AI_BASE_URL: str = ""

    # Legacy alias
    GEMINI_API_KEY: str = ""

    # Adzuna API
    ADZUNA_APP_ID: str = ""
    ADZUNA_APP_KEY: str = ""

    # Automation
    SYNC_INTERVAL_MINUTES: int = 120
    AUTO_SYNC_ENABLED: bool = True
    NOTIFICATION_MIN_SCORE: int = 80

    DATABASE_URL: str = f"sqlite:///{DATA_DIR / 'jobs.db'}"

settings = Settings()

