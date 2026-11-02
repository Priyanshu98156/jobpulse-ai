from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, HttpUrl

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class RemoteType(str, Enum):
    FULLY_REMOTE = "fully_remote"
    HYBRID = "hybrid"
    ONSITE = "onsite"
    UNKNOWN = "unknown"

class EligibilityStatus(str, Enum):
    ELIGIBLE = "eligible"
    LIKELY_ELIGIBLE = "likely_eligible"
    UNCLEAR = "unclear"
    INELIGIBLE = "ineligible"

class ApplicationStatus(str, Enum):
    DISCOVERED = "discovered"
    ELIGIBLE_CHECKED = "eligible_checked"
    SCORED = "scored"
    DRAFTED = "drafted"
    REVIEW_PENDING = "review_pending"
    FILLED = "filled"
    SUBMITTED = "submitted"
    SKIPPED = "skipped"
    INTERVIEWING = "interviewing"
    REJECTED = "rejected"

class SubmissionMethod(str, Enum):
    ASSISTED_BROWSER = "assisted_browser"
    CLIPBOARD_ASSIST = "clipboard_assist"
    MANUAL = "manual"

class JobPosting(BaseModel):
    id: Optional[int] = None
    external_id: str
    platform: str
    title: str
    company: str
    location: str = "Remote"
    job_type: str = "Full-time"
    salary_range: Optional[str] = ""
    url: str
    description: str = ""
    date_posted: datetime = Field(default_factory=utc_now)
    remote_type: RemoteType = RemoteType.UNKNOWN
    eligibility_status: EligibilityStatus = EligibilityStatus.ELIGIBLE
    eligibility_evidence: str = ""
    regions_allowed: List[str] = Field(default_factory=list)
    match_score: Optional[int] = None
    match_reason: str = ""
    matching_skills: List[str] = Field(default_factory=list)
    missing_keywords: List[str] = Field(default_factory=list)
    status: ApplicationStatus = ApplicationStatus.DISCOVERED
