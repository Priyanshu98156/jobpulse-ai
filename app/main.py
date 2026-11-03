import shutil
import logging
from datetime import datetime
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Optional, Dict, Any

from fastapi import FastAPI, Request, Depends, HTTPException, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.config import settings, BASE_DIR, UPLOADS_DIR
from app.database import engine, get_db, Base
from app.models import Job, CandidateProfile, ApplicationPackage, ConnectorSetting, AIKey, AnswerBank, utc_now
from app.connectors.manager import connector_manager
from app.services.scheduler import start_scheduler, stop_scheduler
from app.services.resume_service import resume_service
from app.services.ai_service import ai_service
from app.services.key_pool_service import key_pool_service, PROVIDER_PRESETS
from app.core.logging import setup_logging
from app.core.middleware import SecurityHeadersAndCSRFMiddleware

# Setup enterprise structured logging with PII/secret auto-redaction
setup_logging(level=logging.DEBUG if settings.DEBUG else logging.INFO)
logger = logging.getLogger(__name__)

def seed_initial_data():
    """Initializes default profile and connector rows if they don't exist."""
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        # Candidate Profile
        profile = db.query(CandidateProfile).first()
        if not profile:
            profile = CandidateProfile(
                full_name="Mahadev",
                email="mahadev@example.com",
                phone="+91 98765 43210",
                location="Bengaluru, India (Open to Remote Worldwide)",
                target_titles="Data Scientist, Machine Learning Engineer, Python Backend Developer",
                target_locations="Remote, Worldwide, India, US",
                skills="Python, Machine Learning, Deep Learning, SQL, FastAPI, Docker, PyTorch, Scikit-learn, Git, REST APIs",
                years_of_experience=3.5,
                work_authorization="Authorized to work in India / US Remote",
                notice_period="Immediate / 30 Days",
                expected_salary="Competitive / Open to negotiation",
                summary="Results-driven Data Scientist & Python Software Engineer with strong experience in building production ML pipelines, predictive analytics, and scalable backend microservices."
            )
            db.add(profile)

        # Connector Settings
        default_connectors = [
            ("remotive", "Remotive (Remote Tech & Data)", True),
            ("arbeitnow", "Arbeitnow (Global & Remote Tech)", True),
            ("themuse", "The Muse (Top Tech & Enterprise Companies)", True),
            ("himalayas", "Himalayas (Global Remote Tech Jobs)", True),
            ("greenhouse", "Greenhouse ATS (Direct Boards & API Apply)", True),
            ("lever", "Lever ATS (Direct Postings & API Apply)", True),
            ("adzuna", "Adzuna (Global Job Search API)", False)
        ]
        for name, display_name, enabled in default_connectors:
            setting = db.query(ConnectorSetting).filter(ConnectorSetting.name == name).first()
            if not setting:
                setting = ConnectorSetting(name=name, display_name=display_name, enabled=enabled, config={})
                db.add(setting)

        db.commit()
    finally:
        db.close()

seed_initial_data()

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up JobPulse AI Assistant...")
    start_scheduler()
    yield
    logger.info("Shutting down JobPulse AI Assistant...")
    stop_scheduler()

app = FastAPI(title="JobPulse AI Assistant", lifespan=lifespan)
app.add_middleware(SecurityHeadersAndCSRFMiddleware)

# Templates
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))

# --- Page Routes ---

@app.get("/", response_class=HTMLResponse)
async def index():
    return RedirectResponse(url="/dashboard")

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(
    request: Request,
    status: Optional[str] = "review_pending",
    q: Optional[str] = None,
    min_score: int = 0,
    db: Session = Depends(get_db)
):
    # Calculate stats
    total_count = db.query(Job).count()
    review_pending_count = db.query(Job).filter(Job.status == "review_pending").count()
    applied_count = db.query(Job).filter(Job.status == "applied").count()
    interviewing_count = db.query(Job).filter(Job.status == "interviewing").count()
    skipped_count = db.query(Job).filter(Job.status == "skipped").count()
    needs_look_count = db.query(Job).filter(Job.eligibility_status == "unclear").count()

    stats = {
        "total": total_count,
        "review_pending": review_pending_count,
        "applied": applied_count,
        "interviewing": interviewing_count,
        "skipped": skipped_count,
        "needs_look": needs_look_count
    }

    # Base query
    query = db.query(Job)

    if status == "needs_look":
        query = query.filter(Job.eligibility_status == "unclear")
    elif status and status != "all":
        query = query.filter(Job.status == status)

    if q:
        search_fmt = f"%{q.strip()}%"
        query = query.filter(
            (Job.title.ilike(search_fmt)) |
            (Job.company.ilike(search_fmt)) |
            (Job.location.ilike(search_fmt)) |
            (Job.description.ilike(search_fmt))
        )

    if min_score > 0:
        query = query.filter(Job.match_score >= min_score)

    # Order by match score descending, then date posted descending
    jobs = query.order_by(Job.match_score.desc().nullslast(), Job.date_posted.desc()).limit(100).all()

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "active_page": "dashboard",
            "stats": stats,
            "jobs": jobs,
            "current_status": status,
            "current_query": q or "",
            "current_min_score": min_score
        }
    )

@app.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request, message: Optional[str] = None, db: Session = Depends(get_db)):
    profile = db.query(CandidateProfile).first()
    return templates.TemplateResponse(
        request=request,
        name="profile.html",
        context={
            "active_page": "profile",
            "profile": profile,
            "message": message
        }
    )

@app.post("/profile", response_class=HTMLResponse)
async def save_profile(
    request: Request,
    full_name: str = Form(...),
    email: str = Form(...),
    phone: Optional[str] = Form(""),
    location: Optional[str] = Form(""),
    linkedin_url: Optional[str] = Form(""),
    github_url: Optional[str] = Form(""),
    target_titles: Optional[str] = Form(""),
    skills: Optional[str] = Form(""),
    years_of_experience: Optional[str] = Form("3.0"),
    work_authorization: Optional[str] = Form(""),
    notice_period: Optional[str] = Form(""),
    expected_salary: Optional[str] = Form(""),
    summary: Optional[str] = Form(""),
    resume_file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db)
):
    profile = db.query(CandidateProfile).first()
    if not profile:
        profile = CandidateProfile()
        db.add(profile)

    profile.full_name = full_name
    profile.email = email
    profile.phone = phone or ""
    profile.location = location or ""
    profile.linkedin_url = linkedin_url or ""
    profile.github_url = github_url or ""
    profile.target_titles = target_titles or ""
    profile.skills = skills or ""
    try:
        profile.years_of_experience = float(years_of_experience) if years_of_experience else 3.0
    except (ValueError, TypeError):
        profile.years_of_experience = 3.0
    profile.work_authorization = work_authorization or ""
    profile.notice_period = notice_period or ""
    profile.expected_salary = expected_salary or ""
    profile.summary = summary or ""

    # Handle resume upload if provided
    if resume_file and resume_file.filename and resume_file.filename.lower().endswith(".pdf"):
        saved_filename = f"master_resume_{int(utc_now().timestamp())}.pdf"
        target_path = UPLOADS_DIR / saved_filename
        with open(target_path, "wb") as buffer:
            shutil.copyfileobj(resume_file.file, buffer)

        extracted_text = resume_service.extract_text_from_pdf(target_path)
        profile.master_resume_filename = saved_filename
        profile.master_resume_text = extracted_text

    db.commit()

    return templates.TemplateResponse(
        request=request,
        name="profile.html",
        context={
            "active_page": "profile",
            "profile": profile,
            "message": "Candidate Profile and Master Resume updated successfully!"
        }
    )

@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request, message: Optional[str] = None, db: Session = Depends(get_db)):
    connectors = db.query(ConnectorSetting).all()
    # Enrich connector models with connector capability metadata
    enriched_connectors = []
    for c in connectors:
        conn_instance = connector_manager.get_connector(c.name)
        has_submit_api = conn_instance.has_submit_api if conn_instance else False
        enriched_connectors.append({
            "name": c.name,
            "display_name": c.display_name,
            "enabled": c.enabled,
            "last_synced_at": c.last_synced_at,
            "has_submit_api": has_submit_api
        })

    # Query and sync key pool
    key_pool_service.get_healthy_keys(db)
    ai_keys = db.query(AIKey).order_by(AIKey.id.desc()).all()

    return templates.TemplateResponse(
        request=request,
        name="settings.html",
        context={
            "active_page": "settings",
            "connectors": enriched_connectors,
            "ai_keys": ai_keys,
            "ai_provider": settings.AI_PROVIDER,
            "ai_api_key": settings.AI_API_KEY,
            "ai_model": settings.AI_MODEL,
            "ai_base_url": settings.AI_BASE_URL,
            "ai_key_set": len(ai_keys) > 0 or bool(settings.AI_API_KEY or settings.GEMINI_API_KEY),
            "gemini_api_key": settings.GEMINI_API_KEY,
            "adzuna_app_id": settings.ADZUNA_APP_ID,
            "adzuna_app_key": settings.ADZUNA_APP_KEY,
            "auto_sync_enabled": settings.AUTO_SYNC_ENABLED,
            "sync_interval_minutes": settings.SYNC_INTERVAL_MINUTES,
            "notification_min_score": settings.NOTIFICATION_MIN_SCORE,
            "message": message
        }
    )

@app.post("/settings", response_class=HTMLResponse)
async def save_settings(
    request: Request,
    ai_provider: Optional[str] = Form("gemini"),
    ai_api_key: Optional[str] = Form(""),
    ai_model: Optional[str] = Form(""),
    ai_base_url: Optional[str] = Form(""),
    gemini_api_key: Optional[str] = Form(""),
    adzuna_app_id: Optional[str] = Form(""),
    adzuna_app_key: Optional[str] = Form(""),
    auto_sync_enabled: str = Form("true"),
    sync_interval_minutes: int = Form(120),
    notification_min_score: int = Form(80),
    db: Session = Depends(get_db)
):
    form_data = await request.form()

    # Only update runtime AI settings if explicitly provided in form
    if ai_provider and "ai_provider" in form_data:
        settings.AI_PROVIDER = ai_provider.lower().strip()
    submitted_key = (ai_api_key or gemini_api_key or "").strip()
    if submitted_key:
        settings.AI_API_KEY = submitted_key
        settings.GEMINI_API_KEY = submitted_key
    if ai_model and "ai_model" in form_data:
        settings.AI_MODEL = ai_model.strip()
    if ai_base_url and "ai_base_url" in form_data:
        settings.AI_BASE_URL = ai_base_url.strip()

    settings.ADZUNA_APP_ID = (adzuna_app_id or "").strip()
    settings.ADZUNA_APP_KEY = (adzuna_app_key or "").strip()
    settings.AUTO_SYNC_ENABLED = (auto_sync_enabled.lower() == "true")
    settings.SYNC_INTERVAL_MINUTES = max(15, sync_interval_minutes)
    settings.NOTIFICATION_MIN_SCORE = max(50, min(100, notification_min_score))

    # Reset AI client
    ai_service._gemini_client = None

    # Write back to .env
    env_path = BASE_DIR / ".env"
    env_content = f"""AI_PROVIDER={settings.AI_PROVIDER}
AI_API_KEY={settings.AI_API_KEY}
AI_MODEL={settings.AI_MODEL}
AI_BASE_URL={settings.AI_BASE_URL}
GEMINI_API_KEY={settings.GEMINI_API_KEY}
ADZUNA_APP_ID={settings.ADZUNA_APP_ID}
ADZUNA_APP_KEY={settings.ADZUNA_APP_KEY}
PORT={settings.PORT}
HOST={settings.HOST}
DEBUG={settings.DEBUG}
SYNC_INTERVAL_MINUTES={settings.SYNC_INTERVAL_MINUTES}
AUTO_SYNC_ENABLED={settings.AUTO_SYNC_ENABLED}
NOTIFICATION_MIN_SCORE={settings.NOTIFICATION_MIN_SCORE}
"""
    with open(env_path, "w") as f:
        f.write(env_content)

    # Update connectors enabled statuses
    connectors = db.query(ConnectorSetting).all()
    for c in connectors:
        is_checked = f"connector_{c.name}" in form_data
        c.enabled = is_checked
    db.commit()

    return RedirectResponse(url="/settings?message=Configuration+saved+successfully!", status_code=303)

# --- API Endpoints ---

@app.post("/api/sync")
async def trigger_manual_sync(db: Session = Depends(get_db)):
    """Triggers immediate synchronization across all enabled connectors."""
    try:
        summary = await connector_manager.sync_all_jobs(db)
        return {"status": "ok", **summary}
    except Exception as e:
        logger.error(f"Manual sync error: {e}")
        return {"status": "error", "message": str(e)}

@app.get("/api/job/{job_id}/review")
async def get_job_review_package(job_id: int, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    profile = db.query(CandidateProfile).first()
    pkg = db.query(ApplicationPackage).filter(ApplicationPackage.job_id == job_id).first()

    # If package doesn't exist yet, create one
    if not pkg:
        cover_letter = ai_service.generate_cover_letter(
            job_title=job.title,
            company=job.company,
            job_description=job.description,
            candidate_name=profile.full_name if profile else "Applicant",
            profile_summary=profile.summary if profile else "",
            skills_str=profile.skills if profile else "",
            resume_text=profile.master_resume_text if profile else ""
        )
        conn = connector_manager.get_connector(job.platform)
        has_submit_api = conn.has_submit_api if conn else False

        pkg = ApplicationPackage(
            job_id=job.id,
            tailored_cover_letter=cover_letter,
            screening_answers={},
            resume_path=profile.master_resume_filename if profile else "",
            submission_method="api" if has_submit_api else "direct_link",
            submission_status="draft"
        )
        db.add(pkg)
        db.commit()

    return {
        "status": "ok",
        "job": {
            "id": job.id,
            "title": job.title,
            "company": job.company,
            "location": job.location,
            "platform": job.platform,
            "url": job.url,
            "match_score": job.match_score
        },
        "profile": {
            "full_name": profile.full_name if profile else "",
            "email": profile.email if profile else "",
            "phone": profile.phone if profile else "",
            "work_authorization": profile.work_authorization if profile else "",
            "master_resume_filename": profile.master_resume_filename if profile else ""
        },
        "package": {
            "tailored_cover_letter": pkg.tailored_cover_letter,
            "submission_method": pkg.submission_method,
            "submission_status": pkg.submission_status
        }
    }

class ApplyRequest(BaseModel):
    cover_letter: Optional[str] = None

@app.post("/api/job/{job_id}/apply")
async def apply_to_job(job_id: int, req: ApplyRequest, db: Session = Depends(get_db)):
    """
    1-Click Semi-Autonomous Apply:
    - If direct ATS API connector (Greenhouse / Lever): submits payload with resume & cover letter.
    - If external job board: copies cover letter, marks as applied/in-progress, and returns external link.
    """
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    profile = db.query(CandidateProfile).first()
    pkg = db.query(ApplicationPackage).filter(ApplicationPackage.job_id == job_id).first()

    if req.cover_letter and pkg:
        pkg.tailored_cover_letter = req.cover_letter

    platform = (job.platform or "").lower()
    answers = {ans.question_pattern: ans.answer_text for ans in db.query(AnswerBank).all()}

    # Case 1: Workday / Hosted ATS Form -> Assisted Headed Browser with Structural Stop
    if "workday" in platform or "workday" in job.url.lower():
        job.status = "review_pending"
        if pkg:
            pkg.submission_method = "assisted_browser"
            pkg.submission_status = "review_pending"
            pkg.submitted_at = utc_now()
        db.commit()

        return {
            "status": "ok",
            "submission_method": "assisted_browser",
            "message": "Workday assisted autofill initiated in headed browser. Structural stop is active before submit.",
            "answers": answers,
            "external_url": job.url
        }

    # Case 2: Direct ATS API submission (Greenhouse / Lever) with graceful fallback
    conn = connector_manager.get_connector(platform)
    if conn and getattr(conn, "has_submit_api", False):
        resume_full_path = None
        if profile and profile.master_resume_filename:
            candidate_resume = UPLOADS_DIR / profile.master_resume_filename
            if candidate_resume.exists():
                resume_full_path = str(candidate_resume)

        profile_dict = {
            "full_name": profile.full_name if profile else "Applicant",
            "email": profile.email if profile else "",
            "phone": profile.phone if profile else "",
            "linkedin_url": profile.linkedin_url if profile else "",
            "github_url": profile.github_url if profile else "",
            "portfolio_url": profile.portfolio_url if profile else "",
            "work_authorization": profile.work_authorization if profile else "",
            "notice_period": profile.notice_period if profile else "",
            "expected_salary": profile.expected_salary if profile else "",
        }

        try:
            result = await conn.submit_application(
                job_external_id=job.external_id,
                profile_data=profile_dict,
                resume_path=resume_full_path,
                cover_letter=req.cover_letter or (pkg.tailored_cover_letter if pkg else ""),
                answers=answers
            )
            if result.get("success"):
                job.status = "applied"
                if pkg:
                    pkg.submission_method = "api"
                    pkg.submission_status = "submitted"
                    pkg.submitted_at = utc_now()
                    pkg.submission_response = str(result.get("raw_response", ""))
                db.commit()
                return {
                    "status": "ok",
                    "submission_method": "api",
                    "message": result.get("message", "Application submitted via ATS API!"),
                    "external_url": job.url
                }
        except Exception as e:
            logger.warning(f"ATS API submit encountered error: {e}. Falling back to assisted apply.")

    # Case 3: LinkedIn, Naukri, or External Board -> Assist-Only Mode
    # Zero DOM automation: Direct URL + 1-Click Clipboard Answers from Answer Bank
    job.status = "applied"
    if pkg:
        pkg.submission_method = "clipboard_assist"
        pkg.submission_status = "external_opened"
        pkg.submitted_at = utc_now()
    db.commit()

    return {
        "status": "ok",
        "submission_method": "clipboard_assist",
        "message": "Assist-only mode: Pre-matched answers ready for 1-click clipboard copy. Opening direct portal...",
        "answers": answers,
        "external_url": job.url
    }

class StatusRequest(BaseModel):
    status: str

ALLOWED_STATUSES = {"discovered", "review_pending", "applied", "interviewing", "skipped", "rejected"}

@app.post("/api/job/{job_id}/status")
async def update_status(job_id: int, req: StatusRequest, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if req.status not in ALLOWED_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status '{req.status}'. Must be one of: {', '.join(sorted(ALLOWED_STATUSES))}")

    job.status = req.status
    db.commit()
    return {"status": "ok"}

@app.post("/api/job/{job_id}/regenerate-cover-letter")
async def regenerate_cover_letter(job_id: int, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    profile = db.query(CandidateProfile).first()
    cover_letter = ai_service.generate_cover_letter(
        job_title=job.title,
        company=job.company,
        job_description=job.description,
        candidate_name=profile.full_name if profile else "Applicant",
        profile_summary=profile.summary if profile else "",
        skills_str=profile.skills if profile else "",
        resume_text=profile.master_resume_text if profile else ""
    )

    pkg = db.query(ApplicationPackage).filter(ApplicationPackage.job_id == job_id).first()
    if pkg:
        pkg.tailored_cover_letter = cover_letter
        db.commit()

    return {"status": "ok", "cover_letter": cover_letter}

# --- Key Pool API Endpoints ---

class AddKeyRequest(BaseModel):
    label: str
    provider: str
    api_key: str
    model: Optional[str] = ""
    base_url: Optional[str] = ""

@app.post("/api/keys")
async def add_ai_key(req: AddKeyRequest, db: Session = Depends(get_db)):
    """Add a new API key to the AI Key Pool."""
    if not req.api_key.strip():
        raise HTTPException(status_code=400, detail="API Key cannot be empty.")

    prov = req.provider.lower().strip()
    preset = PROVIDER_PRESETS.get(prov, {})
    model = req.model.strip() if req.model else preset.get("default_model", "llama-3.3-70b-versatile")
    base_url = req.base_url.strip() if req.base_url else preset.get("base_url", "")

    new_key = AIKey(
        label=req.label.strip() or f"{prov.title()} Key",
        provider=prov,
        model=model,
        base_url=base_url,
        enabled=True
    )
    new_key.set_secret(req.api_key.strip())
    db.add(new_key)
    db.commit()
    db.refresh(new_key)
    return {"status": "ok", "message": f"Added {new_key.label} to AI Key Pool!", "key_id": new_key.id}

@app.delete("/api/keys/{key_id}")
async def delete_ai_key(key_id: int, db: Session = Depends(get_db)):
    """Delete an API key from the pool."""
    key = db.query(AIKey).filter(AIKey.id == key_id).first()
    if not key:
        raise HTTPException(status_code=404, detail="Key not found.")
    if key.keyring_id:
        from app.core.security import delete_keyring_secret, KEYRING_SERVICE_VAULT
        delete_keyring_secret(KEYRING_SERVICE_VAULT, key.keyring_id)
    db.delete(key)
    db.commit()
    return {"status": "ok", "message": "Key removed from pool."}

@app.post("/api/keys/{key_id}/toggle")
async def toggle_ai_key(key_id: int, db: Session = Depends(get_db)):
    """Toggle enabled/disabled state of a key."""
    key = db.query(AIKey).filter(AIKey.id == key_id).first()
    if not key:
        raise HTTPException(status_code=404, detail="Key not found.")
    key.enabled = not key.enabled
    db.commit()
    return {"status": "ok", "enabled": key.enabled}

@app.post("/api/keys/{key_id}/reset-cooldown")
async def reset_key_cooldown(key_id: int, db: Session = Depends(get_db)):
    """Manually clear cooldown for a rate-limited key."""
    key = db.query(AIKey).filter(AIKey.id == key_id).first()
    if not key:
        raise HTTPException(status_code=404, detail="Key not found.")
    key.is_in_cooldown = False
    key.cooldown_until = None
    key.last_error_message = ""
    db.commit()
    return {"status": "ok", "message": f"Cooldown reset for {key.label}."}

@app.post("/api/keys/{key_id}/test")
async def test_ai_key(key_id: int, db: Session = Depends(get_db)):
    """Ping provider endpoint to test key latency and validity."""
    key = db.query(AIKey).filter(AIKey.id == key_id).first()
    if not key:
        raise HTTPException(status_code=404, detail="Key not found.")
    result = key_pool_service.test_key(key)
    return result

# --- Answer Bank Endpoints (Phase 5 Assist-Only Mode) ---

class AddAnswerRequest(BaseModel):
    question_pattern: str
    answer_text: str
    category: Optional[str] = "general"
    is_factual: Optional[bool] = True

@app.get("/api/answers")
async def list_answers(db: Session = Depends(get_db)):
    """List pre-verified answers from the Answer Bank."""
    answers = db.query(AnswerBank).order_by(AnswerBank.id.desc()).all()
    return [
        {
            "id": a.id,
            "question_pattern": a.question_pattern,
            "answer_text": a.answer_text,
            "category": a.category,
            "is_factual": a.is_factual,
            "source": a.source
        }
        for a in answers
    ]

@app.post("/api/answers")
async def create_answer(req: AddAnswerRequest, db: Session = Depends(get_db)):
    """Add a new answer to the Answer Bank."""
    if not req.question_pattern.strip() or not req.answer_text.strip():
        raise HTTPException(status_code=400, detail="Pattern and answer cannot be empty.")

    new_ans = AnswerBank(
        question_pattern=req.question_pattern.strip(),
        answer_text=req.answer_text.strip(),
        category=req.category or "general",
        is_factual=req.is_factual if req.is_factual is not None else True,
        source="user_verified"
    )
    db.add(new_ans)
    db.commit()
    db.refresh(new_ans)
    return {"status": "ok", "message": "Answer added to bank!", "id": new_ans.id}

@app.delete("/api/answers/{answer_id}")
async def delete_answer(answer_id: int, db: Session = Depends(get_db)):
    """Delete an answer from the Answer Bank."""
    ans = db.query(AnswerBank).filter(AnswerBank.id == answer_id).first()
    if not ans:
        raise HTTPException(status_code=404, detail="Answer not found.")
    db.delete(ans)
    db.commit()
    return {"status": "ok", "message": "Answer removed from bank."}


