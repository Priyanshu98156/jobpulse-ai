from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class CandidateIdentityDomain(BaseModel):
    id: Optional[int] = None
    full_name: str
    email: str
    phone: str
    location: str
    citizenship: str = "India"
    work_authorization: str = "Authorized to work in India / US Remote B2B"
    notice_period: str = "Immediate / 30 Days"
    expected_salary: str = "Competitive"
    linkedin_url: Optional[str] = ""
    github_url: Optional[str] = ""
    portfolio_url: Optional[str] = ""
    summary: str = ""

class WorkExperienceDomain(BaseModel):
    id: Optional[int] = None
    candidate_id: Optional[int] = None
    company: str
    title: str
    location: str = "Remote"
    is_remote: bool = True
    start_date: str # e.g. "2022-01"
    end_date: Optional[str] = None # e.g. "Present" or "2024-05"
    is_current: bool = False
    description: str = ""
    bullet_points: List[str] = Field(default_factory=list)

class EducationDomain(BaseModel):
    id: Optional[int] = None
    candidate_id: Optional[int] = None
    institution: str
    degree: str
    field_of_study: str
    start_year: Optional[int] = None
    end_year: Optional[int] = None
    gpa: Optional[str] = ""

class ProjectDomain(BaseModel):
    id: Optional[int] = None
    candidate_id: Optional[int] = None
    name: str
    role: str = "Lead Developer"
    technologies: List[str] = Field(default_factory=list)
    url: Optional[str] = ""
    description: str = ""
    highlights: List[str] = Field(default_factory=list)

class SkillDomain(BaseModel):
    id: Optional[int] = None
    candidate_id: Optional[int] = None
    name: str
    category: str = "languages" # languages, frameworks, databases, tools, soft_skills
    years_experience: float = 1.0
    claimable: bool = True # Crucial guardrail: only claimable skills can be cited in tailored materials

class ResumeVersionDomain(BaseModel):
    id: Optional[int] = None
    candidate_id: Optional[int] = None
    version_name: str
    file_path: str
    content_text: str = ""
    content_hash: str = ""
    is_master: bool = False
    created_at: datetime = Field(default_factory=utc_now)

class SearchProfileDomain(BaseModel):
    id: Optional[int] = None
    candidate_id: Optional[int] = None
    target_titles: List[str] = Field(default_factory=list)
    target_locations: List[str] = Field(default_factory=list)
    contractor_acceptable: bool = True
    min_hours_overlap: int = 4
    min_base_salary: Optional[int] = None

class AnswerBankDomain(BaseModel):
    id: Optional[int] = None
    candidate_id: Optional[int] = None
    question_pattern: str # e.g., "years of experience in Python", "sponsorship required"
    answer_text: str
    category: str = "general" # legal, compensation, technical, personal
    is_factual: bool = True # If True, NEVER modified or hallucinated by LLMs
    source: str = "user_verified" # user_verified, resume_extracted


class CandidateOnboardingDomain(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=200)
    base_city: str = Field(default="", max_length=100)
    base_country: str = Field(default="India", max_length=100)
    target_titles: List[str] = Field(..., min_length=1)
    target_cities: List[str] = Field(default_factory=list)
    work_modes: List[str] = Field(default_factory=lambda: ["remote_worldwide", "remote_domestic"])
    skills: str = Field(default="")
    years_of_experience: float = Field(default=0.0, ge=0.0, le=50.0)
    visa_sponsorship_needed: bool = False
    open_to_relocation: bool = False
    expected_salary: str = Field(default="Competitive", max_length=100)
    notice_period: str = Field(default="Immediate / 30 Days", max_length=100)
    summary: Optional[str] = ""

    @field_validator("target_titles")
    @classmethod
    def validate_target_titles(cls, v: List[str]) -> List[str]:
        cleaned = [t.strip() for t in v if t and t.strip()]
        if not cleaned:
            raise ValueError("At least one target job title is required.")
        if len(cleaned) > 3:
            raise ValueError("Maximum 3 target job titles allowed.")
        return cleaned[:3]

