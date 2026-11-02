from typing import List, Optional
from pydantic import BaseModel, Field
from app.domain.models import EligibilityStatus

class EligibilityVerdict(BaseModel):
    status: EligibilityStatus
    reason: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_quote: str = ""
    requires_human_look: bool = False

class ScoringVerdict(BaseModel):
    match_score: int = Field(ge=0, le=100)
    match_reason: str
    matching_skills: List[str] = Field(default_factory=list)
    missing_keywords: List[str] = Field(default_factory=list)
    recommended_action: str = "review_needed" # apply, review_needed, skip
