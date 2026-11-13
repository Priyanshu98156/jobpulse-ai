import asyncio
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from app.models import Job, CandidateProfile, ApplicationPackage, ConnectorSetting, utc_now
from app.connectors.remotive import RemotiveConnector
from app.connectors.arbeitnow import ArbeitnowConnector
from app.connectors.themuse import TheMuseConnector
from app.connectors.greenhouse import GreenhouseConnector
from app.connectors.lever import LeverConnector
from app.connectors.adzuna import AdzunaConnector
from app.connectors.himalayas import HimalayasConnector
from app.services.ai_service import ai_service
from app.services.eligibility_service import eligibility_service
from app.domain.models import EligibilityStatus
from app.services.notifier import desktop_notifier
from app.config import settings

logger = logging.getLogger(__name__)

class ConnectorManager:
    def __init__(self):
        self.connectors = {
            "remotive": RemotiveConnector(),
            "arbeitnow": ArbeitnowConnector(),
            "themuse": TheMuseConnector(),
            "himalayas": HimalayasConnector(),
            "greenhouse": GreenhouseConnector(),
            "lever": LeverConnector(),
            "adzuna": AdzunaConnector()
        }

    def get_connector(self, name: str):
        return self.connectors.get(name)

    async def sync_all_jobs(self, db: Session, query: Optional[str] = None, location: Optional[str] = None, limit_per_connector: int = 15) -> Dict[str, Any]:
        """
        Queries all enabled connectors, deduplicates incoming jobs,
        scores them with Gemini AI against the candidate profile,
        stores them in SQLite, and fires desktop notifications for high matches.
        """
        profile = db.query(CandidateProfile).first()
        search_query = query
        if not search_query and profile and profile.target_titles:
            # Pick primary target role
            search_query = profile.target_titles.split(",")[0].strip()

        tasks = []
        connector_keys = []
        for key, connector in self.connectors.items():
            # Check if disabled in DB setting
            db_setting = db.query(ConnectorSetting).filter(ConnectorSetting.name == key).first()
            if db_setting and not db_setting.enabled:
                continue
            tasks.append(connector.fetch_jobs(query=search_query, location=location, limit=limit_per_connector))
            connector_keys.append(key)

        results = await asyncio.gather(*tasks, return_exceptions=True)

        total_fetched = 0
        new_jobs_added = 0
        high_matches = []

        for idx, res in enumerate(results):
            connector_key = connector_keys[idx]
            if isinstance(res, Exception):
                logger.error(f"Connector {connector_key} encountered error: {res}")
                continue
            
            jobs_list = res if isinstance(res, list) else []
            total_fetched += len(jobs_list)

            # Update connector setting timestamp
            db_setting = db.query(ConnectorSetting).filter(ConnectorSetting.name == connector_key).first()
            if db_setting:
                db_setting.last_synced_at = utc_now()
                db.commit()

            for job_data in jobs_list:
                ext_id = job_data["external_id"]
                platform = job_data["platform"]

                # Deduplicate: check if job already exists
                existing = db.query(Job).filter(Job.external_id == ext_id, Job.platform == platform).first()
                if existing:
                    continue

                # Step 1: Remote Eligibility Gate (4 Layers)
                el_verdict = eligibility_service.evaluate_job(
                    title=job_data["title"],
                    company=job_data["company"],
                    location=job_data["location"],
                    description=job_data["description"]
                )

                # If hard ineligible, drop to skipped to save AI scoring tokens
                if el_verdict.status == EligibilityStatus.INELIGIBLE:
                    new_job = Job(
                        external_id=ext_id,
                        platform=platform,
                        title=job_data["title"],
                        company=job_data["company"],
                        location=job_data["location"],
                        job_type=job_data["job_type"],
                        salary_range=job_data["salary_range"],
                        url=job_data["url"],
                        description=job_data["description"],
                        date_posted=job_data.get("date_posted", utc_now()),
                        eligibility_status="ineligible",
                        eligibility_evidence=el_verdict.reason,
                        status="skipped"
                    )
                    db.add(new_job)
                    continue

                # Step 2: AI Matching & Scoring for Eligible & Unclear (Needs a Look) Jobs
                profile_summary = profile.summary if profile else ""
                skills_str = profile.skills if profile else ""
                resume_text = profile.master_resume_text if profile else ""

                match_result = ai_service.score_and_match(
                    job_title=job_data["title"],
                    job_description=job_data["description"],
                    profile_summary=profile_summary,
                    skills_str=skills_str,
                    resume_text=resume_text,
                    db=db
                )

                score = match_result.get("match_score", 50)
                reason = match_result.get("match_reason", "")
                matching_skills = match_result.get("matching_skills", [])
                missing_keywords = match_result.get("missing_keywords", [])

                is_unclear = (el_verdict.status == EligibilityStatus.UNCLEAR or el_verdict.requires_human_look)
                initial_status = "review_pending" if (score >= 70 or is_unclear) else "discovered"

                new_job = Job(
                    external_id=ext_id,
                    platform=platform,
                    title=job_data["title"],
                    company=job_data["company"],
                    location=job_data["location"],
                    job_type=job_data["job_type"],
                    salary_range=job_data["salary_range"],
                    url=job_data["url"],
                    description=job_data["description"],
                    date_posted=job_data.get("date_posted", utc_now()),
                    eligibility_status="unclear" if is_unclear else "eligible",
                    eligibility_evidence=el_verdict.reason,
                    match_score=score,
                    match_reason=reason,
                    matching_skills=matching_skills,
                    missing_keywords=missing_keywords,
                    status=initial_status
                )
                db.add(new_job)
                db.flush() # get new_job.id

                # If score is good, pre-generate draft application package
                if score >= 70:
                    cover_letter = ai_service.generate_cover_letter(
                        job_title=new_job.title,
                        company=new_job.company,
                        job_description=new_job.description,
                        candidate_name=profile.full_name if profile else "Applicant",
                        profile_summary=profile_summary,
                        skills_str=skills_str,
                        resume_text=resume_text,
                        canary_keywords=el_verdict.canary_keywords,
                        db=db
                    )
                    app_pkg = ApplicationPackage(
                        job_id=new_job.id,
                        tailored_cover_letter=cover_letter,
                        screening_answers={},
                        resume_path=profile.master_resume_filename if profile else "",
                        submission_method="api" if connector.has_submit_api else "direct_link",
                        submission_status="draft"
                    )
                    db.add(app_pkg)

                new_jobs_added += 1

                if score >= settings.NOTIFICATION_MIN_SCORE:
                    high_matches.append(new_job)

        db.commit()

        # Fire desktop notification if high match jobs found
        if high_matches:
            top_job = high_matches[0]
            desktop_notifier.send_notification(
                title=f"🎯 New High Match Job ({top_job.match_score}%)!",
                message=f"{top_job.title} at {top_job.company} is ready for 1-click review."
            )

        return {
            "total_fetched": total_fetched,
            "new_jobs_added": new_jobs_added,
            "high_matches_count": len(high_matches)
        }

connector_manager = ConnectorManager()

