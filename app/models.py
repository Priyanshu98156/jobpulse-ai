from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, Float, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from app.database import Base

class CandidateProfile(Base):
    __tablename__ = "candidate_profiles"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String(200), default="")
    email = Column(String(200), default="")
    phone = Column(String(50), default="")
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
    expected_salary = Column(String(100), default="Negotiable")
    
    summary = Column(Text, default="")
    master_resume_filename = Column(String(300), default="")
    master_resume_text = Column(Text, default="")
    
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, index=True)
    external_id = Column(String(200), index=True)
    platform = Column(String(100), index=True) # remotive, arbeitnow, themuse, greenhouse, lever, adzuna
    title = Column(String(300), nullable=False, index=True)
    company = Column(String(300), nullable=False, index=True)
    location = Column(String(200), default="Remote")
    job_type = Column(String(100), default="Full-time")
    salary_range = Column(String(200), default="")
    url = Column(Text, nullable=False)
    description = Column(Text, default="")
    date_posted = Column(DateTime, default=datetime.utcnow)
    
    # AI Matching & Analysis
    match_score = Column(Integer, nullable=True) # 0 to 100
    match_reason = Column(Text, default="")
    matching_skills = Column(JSON, default=list)
    missing_keywords = Column(JSON, default=list)
    
    # Lifecycle Status: discovered, review_pending, applied, skipped, interviewing, rejected, archived
    status = Column(String(50), default="discovered", index=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    application_package = relationship("ApplicationPackage", back_populates="job", uselist=False, cascade="all, delete-orphan")

class ApplicationPackage(Base):
    __tablename__ = "application_packages"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("jobs.id", ondelete="CASCADE"), unique=True)
    
    tailored_cover_letter = Column(Text, default="")
    screening_answers = Column(JSON, default=dict)
    resume_path = Column(String(500), default="")
    
    submission_method = Column(String(50), default="manual") # api, direct_link, manual
    submission_status = Column(String(50), default="draft") # draft, submitted, external_opened, failed
    submission_response = Column(Text, default="")
    submitted_at = Column(DateTime, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    job = relationship("Job", back_populates="application_package")

class ConnectorSetting(Base):
    __tablename__ = "connector_settings"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, index=True) # remotive, arbeitnow, themuse, greenhouse, lever, adzuna
    display_name = Column(String(150))
    enabled = Column(Boolean, default=True)
    config = Column(JSON, default=dict)
    last_synced_at = Column(DateTime, nullable=True)
    last_error = Column(Text, default="")

