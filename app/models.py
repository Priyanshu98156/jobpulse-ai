"""Models backward-compatibility module re-exporting from app.db.models."""
from app.db.models import (
    CandidateProfile,
    Job,
    ApplicationPackage,
    ConnectorSetting,
    AIKey,
    utc_now,
)

__all__ = [
    "CandidateProfile",
    "Job",
    "ApplicationPackage",
    "ConnectorSetting",
    "AIKey",
    "utc_now",
]
