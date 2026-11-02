from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, Float, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from app.db.session import Base
from app.core.security import EncryptedText

def utc_now():
    """Timezone-aware UTC timestamp helper conforming to standards."""
    return datetime.now(timezone.utc)

class CandidateProfile(Base):
    __tablename__ = "candidate_profiles"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String(200), default="")
    # Sensitive PII encrypted at rest using Fernet with master key in OS Keyring
    email = Column(EncryptedText, default="")
    phone = Column(EncryptedText, default="")
    location = Column(String(200), default="")
    linkedin_url = Column(String(300), default="")
    github_url = Column(String(300), default="")
    portfolio_url = Column(String(300), default="")
    
    # Target preferences
    target_titles = Column(Text, default="Data Scientist, Machine Learning Engineer, Python Developer")
    target_locations = Column(Text, default="Remote, Worldwide, India, US")
    skills = Column(Text, default="Python, Machine Learning, Deep Learning, SQL, FastAPI, Docker")
    years_of_experience = Column(Float, default=3.0)
    work_authorization = Column(String(200), default="Authorized to work in India / US Remote")
    notice_period = Column(String(100), default="Immediate / 30 Days")
    expected_salary = Column(EncryptedText, default="Negotiable")
    
    summary = Column(Text, default="")
    master_resume_filename = Column(String(300), default="")
    master_resume_text = Column(Text, default="")
    
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, index=True)
    external_id = Column(String(200), index=True)
    platform = Column(String(100), index=True) # remotive, himalayas, jobicy, ashby, greenhouse, lever
    title = Column(String(300), nullable=False, index=True)
    company = Column(String(300), nullable=False, index=True)
    location = Column(String(200), default="Remote")
    job_type = Column(String(100), default="Full-time")
    salary_range = Column(String(200), default="")
    url = Column(Text, nullable=False)
    description = Column(Text, default="")
    date_posted = Column(DateTime, default=utc_now)
    
    # Remote Eligibility Gate fields
    remote_type = Column(String(50), default="unknown") # fully_remote, hybrid, onsite, unknown
    eligibility_status = Column(String(50), default="eligible", index=True) # eligible, likely_eligible, unclear, ineligible
    eligibility_evidence = Column(Text, default="")
    regions_allowed = Column(JSON, default=list)

    # AI Matching & Analysis
    match_score = Column(Integer, nullable=True) # 0 to 100
    match_reason = Column(Text, default="")
    matching_skills = Column(JSON, default=list)
    missing_keywords = Column(JSON, default=list)
    
    # Lifecycle Status: discovered, eligible_checked, scored, drafted, review_pending, filled, submitted, skipped, interviewing, rejected
    status = Column(String(50), default="discovered", index=True)
    
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)
    
    application_package = relationship("ApplicationPackage", back_populates="job", uselist=False, cascade="all, delete-orphan")

class ApplicationPackage(Base):
    __tablename__ = "application_packages"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("jobs.id", ondelete="CASCADE"), unique=True)
    
    tailored_cover_letter = Column(Text, default="")
    screening_answers = Column(JSON, default=dict)
    resume_path = Column(String(500), default="")
    
    submission_method = Column(String(50), default="assisted_browser") # assisted_browser, manual
    submission_status = Column(String(50), default="draft") # draft, review_pending, filled, submitted
    submission_response = Column(Text, default="")
    submitted_at = Column(DateTime, nullable=True)
    
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)
    
    job = relationship("Job", back_populates="application_package")

class ConnectorSetting(Base):
    __tablename__ = "connector_settings"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, index=True)
    display_name = Column(String(150))
    enabled = Column(Boolean, default=True)
    config = Column(JSON, default=dict)
    last_synced_at = Column(DateTime, nullable=True)
    last_error = Column(Text, default="")

class AIKey(Base):
    __tablename__ = "ai_keys"

    id = Column(Integer, primary_key=True, index=True)
    label = Column(String(150), default="Primary Key")
    provider = Column(String(50), nullable=False) # groq, openrouter, gemini, mistral, cerebras, custom
    
    # Zero secrets in SQLite: the secret key lives strictly in OS Keyring.
    # keyring_id is the reference handle, and api_key_masked is for safe UI display.
    keyring_id = Column(String(150), unique=True, nullable=False)
    api_key_masked = Column(String(50), default="")
    
    model = Column(String(150), default="")
    base_url = Column(String(300), default="")
    
    enabled = Column(Boolean, default=True)
    is_in_cooldown = Column(Boolean, default=False)
    cooldown_until = Column(DateTime, nullable=True)
    
    total_requests = Column(Integer, default=0)
    successful_requests = Column(Integer, default=0)
    rate_limit_hits = Column(Integer, default=0)
    last_error_message = Column(Text, default="")
    last_used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utc_now)

    @property
    def api_key(self) -> str:
        from app.core.security import get_keyring_secret, KEYRING_SERVICE_VAULT
        if not self.keyring_id:
            return ""
        return get_keyring_secret(KEYRING_SERVICE_VAULT, self.keyring_id) or ""

    def set_secret(self, secret: str) -> None:
        from app.core.security import set_keyring_secret, mask_secret, KEYRING_SERVICE_VAULT
        import uuid
        if not self.keyring_id:
            self.keyring_id = f"ai_key_{uuid.uuid4().hex[:12]}"
        set_keyring_secret(KEYRING_SERVICE_VAULT, self.keyring_id, secret)
        self.api_key_masked = mask_secret(secret)


