import json
import logging
import re
import httpx
from typing import Dict, Any, List, Optional
from app.config import settings

logger = logging.getLogger(__name__)

# Predefined provider presets
PROVIDER_PRESETS = {
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "default_model": "llama-3.3-70b-versatile"
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "default_model": "meta-llama/llama-3.3-70b-instruct:free"
    },
    "mistral": {
        "base_url": "https://api.mistral.ai/v1",
        "default_model": "mistral-small-latest"
    },
    "cerebras": {
        "base_url": "https://api.cerebras.ai/v1",
        "default_model": "llama3.1-8b"
    },
    "gemini": {
        "base_url": "",
        "default_model": "gemini-2.5-flash"
    }
}

class AIService:
    def __init__(self):
        self._gemini_client = None

    def _get_api_key(self) -> str:
        return (settings.AI_API_KEY or settings.GEMINI_API_KEY or "").strip()

    def _get_provider(self) -> str:
        provider = (settings.AI_PROVIDER or "gemini").lower().strip()
        return provider

    def _get_model_and_url(self):
        provider = self._get_provider()
        preset = PROVIDER_PRESETS.get(provider, {})
        base_url = settings.AI_BASE_URL.strip() if settings.AI_BASE_URL else preset.get("base_url", "")
        model = settings.AI_MODEL.strip() if settings.AI_MODEL else preset.get("default_model", "llama-3.3-70b-versatile")
        return provider, base_url, model

    def _call_llm(self, prompt: str) -> Optional[str]:
        """
        Unified LLM invoker supporting Gemini, Groq, OpenRouter, Mistral, Cerebras, and OpenAI-compatible endpoints.
        """
        api_key = self._get_api_key()
        if not api_key:
            return None

        provider, base_url, model = self._get_model_and_url()

        # Google Gemini via official SDK
        if provider == "gemini":
            try:
                if self._gemini_client is None:
                    from google import genai
                    self._gemini_client = genai.Client(api_key=api_key)
                
                resp = self._gemini_client.models.generate_content(
                    model=model or "gemini-2.5-flash",
                    contents=prompt
                )
                return resp.text.strip()
            except Exception as e:
                logger.warning(f"Gemini API call error: {e}")
                return None

        # OpenAI-compatible providers: Groq, OpenRouter, Mistral, Cerebras, Custom
        try:
            target_url = f"{base_url.rstrip('/')}/chat/completions"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            if provider == "openrouter":
                headers["HTTP-Referer"] = "http://localhost:8000"
                headers["X-Title"] = "JobPulse AI"

            payload = {
                "model": model,
                "messages": [
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.3
            }

            with httpx.Client(timeout=30.0) as client:
                res = client.post(target_url, headers=headers, json=payload)
                if res.status_code != 200:
                    logger.warning(f"{provider.upper()} API returned status {res.status_code}: {res.text[:300]}")
                    return None
                
                data = res.json()
                choices = data.get("choices", [])
                if choices and len(choices) > 0:
                    msg = choices[0].get("message", {})
                    return msg.get("content", "").strip()
        except Exception as e:
            logger.warning(f"Error calling {provider.upper()} API: {e}")

        return None

    def score_and_match(self, job_title: str, job_description: str, profile_summary: str, skills_str: str, resume_text: str) -> Dict[str, Any]:
        """
        Calculates match score (0-100), matching skills, missing keywords, and match reasoning.
        """
        prompt = f"""
You are an expert technical recruiter and career coach.
Analyze the fit between this Candidate Profile / Resume and the Job Description.

CANDIDATE DETAILS:
Target Skills: {skills_str}
Candidate Summary: {profile_summary}
Candidate Resume excerpt:
{resume_text[:2500]}

JOB TO EVALUATE:
Job Title: {job_title}
Job Description:
{job_description[:3000]}

Return ONLY a valid JSON object matching this exact schema:
{{
  "match_score": <integer from 0 to 100>,
  "match_reason": "<1-2 concise sentences explaining why the candidate is or isn't a strong match>",
  "matching_skills": ["<skill1>", "<skill2>", ...],
  "missing_keywords": ["<keyword1>", "<keyword2>", ...]
}}
Do not include markdown codeblocks or extra text.
"""
        response_text = self._call_llm(prompt)
        if response_text:
            try:
                clean_text = response_text.strip()
                if clean_text.startswith("```json"):
                    clean_text = clean_text[7:]
                if clean_text.startswith("```"):
                    clean_text = clean_text[3:]
                if clean_text.endswith("```"):
                    clean_text = clean_text[:-3]
                parsed = json.loads(clean_text.strip())
                return {
                    "match_score": max(0, min(100, int(parsed.get("match_score", 50)))),
                    "match_reason": parsed.get("match_reason", "AI match evaluation completed."),
                    "matching_skills": parsed.get("matching_skills", []),
                    "missing_keywords": parsed.get("missing_keywords", [])
                }
            except Exception as e:
                logger.warning(f"Error parsing AI response: {e}. Falling back to heuristic.")

        # Heuristic matching fallback
        return self._heuristic_match(job_title, job_description, profile_summary, skills_str, resume_text)

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

    def generate_cover_letter(self, job_title: str, company: str, job_description: str, candidate_name: str, profile_summary: str, skills_str: str, resume_text: str) -> str:
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
        response_text = self._call_llm(prompt)
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

    def answer_screening_questions(self, questions: List[str], profile_dict: Dict[str, Any]) -> Dict[str, str]:
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
        response_text = self._call_llm(prompt)
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
