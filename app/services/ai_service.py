import json
import logging
import re
import hashlib
from pathlib import Path
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.services.key_pool_service import key_pool_service
from app.domain.eligibility import ScoringVerdict

logger = logging.getLogger(__name__)

SCORING_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "scoring_v1.txt"

class AIService:
    def __init__(self):
        # In-memory LRU/hash cache to avoid burning LLM calls on identical postings
        self._score_cache: Dict[str, Dict[str, Any]] = {}

    def _call_llm_with_pool(self, prompt: str, db: Optional[Session] = None) -> Optional[str]:
        """
        Executes prompt via KeyPoolService with round-robin load balancing,
        rate-limit detection, and instant failover across all stored keys.
        """
        if db is not None:
            text, used_key = key_pool_service.call_with_failover(prompt, db)
            return text
        else:
            session = SessionLocal()
            try:
                text, used_key = key_pool_service.call_with_failover(prompt, session)
                return text
            finally:
                session.close()

    def score_and_match(
        self,
        job_title: str,
        job_description: str,
        profile_summary: str,
        skills_str: str,
        resume_text: str,
        db: Optional[Session] = None
    ) -> Dict[str, Any]:
        """
        Calculates match score (0-100), matching skills, missing keywords, and match reasoning.
        Uses SHA-256 caching and versioned prompt template.
        """
        # 1. Check SHA-256 content hash cache
        content_hash = hashlib.sha256(
            f"{job_title}|{job_description[:1000]}|{skills_str}|{resume_text[:1000]}".encode("utf-8")
        ).hexdigest()

        if content_hash in self._score_cache:
            logger.info(f"Score cache HIT for job '{job_title}' (hash: {content_hash[:8]})")
            return self._score_cache[content_hash]

        # 2. Format versioned prompt
        if SCORING_PROMPT_PATH.exists():
            template = SCORING_PROMPT_PATH.read_text(encoding="utf-8")
            prompt = template.format(
                candidate_name="Applicant",
                target_titles="Software Engineer / Data Scientist",
                skills=skills_str,
                years_of_experience=3.5,
                summary=profile_summary,
                resume_highlights=resume_text[:2500],
                job_title=job_title,
                company="Company",
                location="Remote",
                job_description=job_description[:3000]
            )
        else:
            prompt = f"""
Analyze the fit between this Candidate Profile / Resume and the Job Description.
CANDIDATE: {profile_summary} {skills_str}
JOB: {job_title} - {job_description[:3000]}
Return ONLY JSON: {{"match_score": 85, "match_reason": "...", "matching_skills": [], "missing_keywords": []}}
"""
        response_text = self._call_llm_with_pool(prompt, db=db)
        if response_text:
            try:
                clean_text = response_text.strip()
                if "```json" in clean_text:
                    clean_text = clean_text.split("```json")[1].split("```")[0].strip()
                elif "```" in clean_text:
                    clean_text = clean_text.split("```")[1].split("```")[0].strip()
                parsed = json.loads(clean_text.strip())

                verdict = {
                    "match_score": max(0, min(100, int(parsed.get("match_score", 50)))),
                    "match_reason": parsed.get("match_reason", "AI match evaluation completed."),
                    "matching_skills": parsed.get("matching_skills", []),
                    "missing_keywords": parsed.get("missing_keywords", [])
                }
                self._score_cache[content_hash] = verdict
                return verdict
            except Exception as e:
                logger.warning(f"Error parsing AI response: {e}. Falling back to heuristic.")

        # Heuristic matching fallback
        heuristic_res = self._heuristic_match(job_title, job_description, profile_summary, skills_str, resume_text)
        self._score_cache[content_hash] = heuristic_res
        return heuristic_res

    def _heuristic_match(self, job_title: str, job_description: str, profile_summary: str, skills_str: str, resume_text: str) -> Dict[str, Any]:
        full_cand_text = f"{profile_summary} {skills_str} {resume_text}".lower()
        full_job_text = f"{job_title} {job_description}".lower()

        raw_skills = [s.strip().lower() for s in re.split(r"[,|\n/]", skills_str) if s.strip()]
        if not raw_skills:
            raw_skills = ["python", "sql", "machine learning", "data analysis", "docker", "fastapi", "git"]

        matching = []
        missing = []
        for s in raw_skills:
            if s in full_job_text:
                matching.append(s.title())
            else:
                missing.append(s.title())

        title_words = [w for w in re.findall(r"\w+", job_title.lower()) if len(w) > 3]
        title_hits = sum(1 for w in title_words if w in full_cand_text)
        title_ratio = (title_hits / len(title_words)) if title_words else 0.5

        skill_ratio = (len(matching) / len(raw_skills)) if raw_skills else 0.5
        calculated_score = int((skill_ratio * 60) + (title_ratio * 40))
        calculated_score = max(20, min(95, calculated_score))

        reason = (
            f"Matches {len(matching)} target skills ({', '.join(matching[:3])}). "
            f"Title alignment: {int(title_ratio * 100)}%."
        )

        return {
            "match_score": calculated_score,
            "match_reason": reason,
            "matching_skills": matching[:6],
            "missing_keywords": missing[:5]
        }

    def generate_cover_letter(
        self,
        job_title: str,
        company: str,
        job_description: str,
        candidate_name: str,
        profile_summary: str,
        skills_str: str,
        resume_text: str,
        db: Optional[Session] = None
    ) -> str:
        prompt = f"""
Write a professional, compelling, and concise cover letter (3-4 focused paragraphs, under 300 words) for the following job application.

CANDIDATE INFO:
Name: {candidate_name or "Applicant"}
Summary: {profile_summary}
Key Skills: {skills_str}
Resume Background:
{resume_text[:2000]}

JOB ROLE:
Company: {company}
Title: {job_title}
Job Description:
{job_description[:2500]}

TONE & STYLE:
- Enthusiastic, direct, authentic, confident.
- Highlight specific candidate skills directly applicable to the job description requirements.
- Avoid generic buzzwords.
- Do not use placeholders like '[Insert Date]' or '[Company Address]'. Start directly with 'Dear Hiring Team at {company},' and end with 'Sincerely,\n{candidate_name or "Applicant"}'.
"""
        response_text = self._call_llm_with_pool(prompt, db=db)
        if response_text:
            return response_text.strip()

        # Fallback template
        name = candidate_name or "Applicant"
        skills = skills_str or "Python, Data Engineering, and modern software development"
        return f"""Dear Hiring Team at {company},

I am writing to express my strong enthusiasm for the {job_title} position at {company}. With a proven background in {skills}, I am excited by the opportunity to contribute to your team's ongoing success and engineering goals.

Throughout my experience, I have focused on delivering scalable, high-performance solutions and solving complex analytical challenges. The requirements outlined in your job posting closely align with my hands-on background and technical toolkit.

Thank you for your time and consideration. I welcome the opportunity to discuss how my skill set and dedication can add immediate value to {company}.

Sincerely,
{name}"""

    def answer_screening_questions(
        self,
        questions: List[str],
        profile_dict: Dict[str, Any],
        db: Optional[Session] = None
    ) -> Dict[str, str]:
        results = {}
        if not questions:
            return results

        prompt = f"""
Answer these job application screening questions for this candidate accurately and concisely:

CANDIDATE PROFILE:
Name: {profile_dict.get('full_name')}
Experience: {profile_dict.get('years_of_experience')} years
Authorization: {profile_dict.get('work_authorization')}
Notice Period: {profile_dict.get('notice_period')}
Expected Salary: {profile_dict.get('expected_salary')}
Skills: {profile_dict.get('skills')}
Summary: {profile_dict.get('summary')}

QUESTIONS:
{json.dumps(questions, indent=2)}

Return a JSON mapping of each question string to the candidate's concise answer. Format:
{{"Question text": "Concise answer"}}
"""
        response_text = self._call_llm_with_pool(prompt, db=db)
        if response_text:
            try:
                clean_text = response_text.strip()
                if clean_text.startswith("```json"):
                    clean_text = clean_text[7:]
                if clean_text.startswith("```"):
                    clean_text = clean_text[3:]
                if clean_text.endswith("```"):
                    clean_text = clean_text[:-3]
                return json.loads(clean_text.strip())
            except Exception as e:
                logger.warning(f"Screening questions parsing error: {e}")

        # Fallback answers
        for q in questions:
            ql = q.lower()
            if "authorized" in ql or "sponsorship" in ql or "visa" in ql or "eligible" in ql:
                results[q] = profile_dict.get("work_authorization", "Yes, authorized to work.")
            elif "notice" in ql or "start" in ql:
                results[q] = profile_dict.get("notice_period", "Immediate / 30 Days")
            elif "salary" in ql or "compensation" in ql:
                results[q] = profile_dict.get("expected_salary", "Open to negotiation based on total package")
            elif "years" in ql or "experience" in ql:
                results[q] = f"{profile_dict.get('years_of_experience', 3)} years"
            else:
                results[q] = "Yes, extensive practical experience."
        return results

ai_service = AIService()
