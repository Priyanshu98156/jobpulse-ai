import httpx
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from app.connectors.base import BaseConnector

logger = logging.getLogger(__name__)

# Default prominent tech companies using Greenhouse
DEFAULT_GREENHOUSE_BOARDS = [
    "github", "figma", "discord", "reddit", "elastic", "canonical", "hashicorp", "automattic"
]

class GreenhouseConnector(BaseConnector):
    name = "greenhouse"
    display_name = "Greenhouse ATS (Direct Boards & API Apply)"
    has_submit_api = True

    API_BASE = "https://boards-api.greenhouse.io/v1/boards"

    def __init__(self, boards: Optional[List[str]] = None):
        self.boards = boards or DEFAULT_GREENHOUSE_BOARDS

    async def fetch_jobs(self, query: Optional[str] = None, location: Optional[str] = None, limit: int = 30) -> List[Dict[str, Any]]:
        results = []
        async with httpx.AsyncClient(timeout=15.0) as client:
            for board in self.boards:
                try:
                    url = f"{self.API_BASE}/{board}/jobs?content=true"
                    resp = await client.get(url)
                    if resp.status_code != 200:
                        continue
                    
                    data = resp.json()
                    jobs = data.get("jobs", [])
                    company_name = board.replace("-", " ").title()

                    for item in jobs:
                        title = item.get("title", "")
                        content = item.get("content", "")
                        
                        if query:
                            q_lower = query.lower()
                            if q_lower not in title.lower() and q_lower not in content.lower():
                                continue

                        ext_id = f"{board}_{item.get('id')}"
                        loc_obj = item.get("location", {})
                        loc_name = loc_obj.get("name") if isinstance(loc_obj, dict) else "Remote / Flexible"

                        pub_date_str = item.get("updated_at", "")
                        try:
                            pub_date = datetime.fromisoformat(pub_date_str.replace("Z", "+00:00")) if pub_date_str else datetime.utcnow()
                        except Exception:
                            pub_date = datetime.utcnow()

                        results.append({
                            "external_id": ext_id,
                            "platform": self.name,
                            "title": title or "Untitled Role",
                            "company": company_name,
                            "location": loc_name or "Remote",
                            "job_type": "Full-time",
                            "salary_range": "Disclosed upon application",
                            "url": item.get("absolute_url", f"https://boards.greenhouse.io/{board}/jobs/{item.get('id')}"),
                            "description": content,
                            "date_posted": pub_date
                        })

                        if len(results) >= limit:
                            return results
                except Exception as e:
                    logger.warning(f"Error fetching greenhouse board '{board}': {e}")

        return results

    async def submit_application(
        self,
        job_external_id: str,
        profile_data: Dict[str, Any],
        resume_path: Optional[str] = None,
        cover_letter: Optional[str] = None,
        answers: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Submit candidate application directly to Greenhouse Job Board endpoint.
        """
        if "_" not in job_external_id:
            return {"success": False, "message": "Invalid Greenhouse external job ID format (expected board_jobid)."}

        board, job_id = job_external_id.split("_", 1)
        submit_url = f"{self.API_BASE}/{board}/jobs/{job_id}"

        # Split full name into first and last
        full_name = profile_data.get("full_name", "").strip()
        name_parts = full_name.split(" ", 1)
        first_name = name_parts[0] if name_parts else "Applicant"
        last_name = name_parts[1] if len(name_parts) > 1 else ""

        data = {
            "first_name": first_name,
            "last_name": last_name or "Candidate",
            "email": profile_data.get("email", ""),
            "phone": profile_data.get("phone", ""),
        }

        if cover_letter:
            data["cover_letter_text"] = cover_letter

        # Add optional social profiles if requested by greenhouse
        if profile_data.get("linkedin_url"):
            data["question_linkedin"] = profile_data.get("linkedin_url")
        if profile_data.get("github_url"):
            data["question_github"] = profile_data.get("github_url")

        files = {}
        if resume_path and Path(resume_path).exists():
            files["resume"] = (Path(resume_path).name, open(resume_path, "rb"), "application/pdf")

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(submit_url, data=data, files=files if files else None)
                if files:
                    for f in files.values():
                        f[1].close()

                if resp.status_code in (200, 201):
                    return {
                        "success": True,
                        "submission_id": f"gh_{job_id}_{int(datetime.utcnow().timestamp())}",
                        "message": f"Successfully submitted application directly to {board.title()} via Greenhouse API!",
                        "raw_response": resp.json() if resp.headers.get("content-type", "").startswith("application/json") else resp.text
                    }
                else:
                    return {
                        "success": False,
                        "message": f"Greenhouse API returned status {resp.status_code}: {resp.text[:300]}",
                        "raw_response": resp.text
                    }
        except Exception as e:
            logger.error(f"Greenhouse direct submit error: {e}")
            return {"success": False, "message": f"Connection error: {str(e)}"}

