import httpx
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from app.connectors.base import BaseConnector

logger = logging.getLogger(__name__)

# Default prominent companies with verified active Lever boards
DEFAULT_LEVER_COMPANIES = [
    "spotify", "palantir", "kinsta"
]

class LeverConnector(BaseConnector):
    name = "lever"
    display_name = "Lever ATS (Direct Postings & API Apply)"
    has_submit_api = True

    API_BASE = "https://api.lever.co/v0/postings"

    def __init__(self, companies: Optional[List[str]] = None):
        self.companies = companies or DEFAULT_LEVER_COMPANIES

    async def fetch_jobs(self, query: Optional[str] = None, location: Optional[str] = None, limit: int = 30) -> List[Dict[str, Any]]:
        results = []
        async with httpx.AsyncClient(timeout=15.0) as client:
            for company in self.companies:
                try:
                    url = f"{self.API_BASE}/{company}?mode=json"
                    resp = await client.get(url)
                    if resp.status_code != 200:
                        continue
                    
                    postings = resp.json()
                    company_name = company.replace("-", " ").title()

                    for item in postings:
                        title = item.get("text", "")
                        description = item.get("descriptionPlain", "") or item.get("description", "")
                        
                        if query:
                            q_lower = query.lower()
                            if q_lower not in title.lower() and q_lower not in description.lower():
                                continue

                        ext_id = f"{company}_{item.get('id')}"
                        categories = item.get("categories", {})
                        loc = categories.get("location") or "Remote / Flexible"
                        commitment = categories.get("commitment") or "Full-time"

                        created_at_ts = item.get("createdAt")
                        try:
                            pub_date = datetime.fromtimestamp(created_at_ts / 1000.0) if created_at_ts else datetime.utcnow()
                        except Exception:
                            pub_date = datetime.utcnow()

                        results.append({
                            "external_id": ext_id,
                            "platform": self.name,
                            "title": title or "Untitled Role",
                            "company": company_name,
                            "location": loc,
                            "job_type": commitment,
                            "salary_range": "Disclosed upon application",
                            "url": item.get("hostedUrl", f"https://jobs.lever.co/{company}/{item.get('id')}"),
                            "description": description,
                            "date_posted": pub_date
                        })

                        if len(results) >= limit:
                            return results
                except Exception as e:
                    logger.warning(f"Error fetching Lever postings for '{company}': {e}")

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
        Submit candidate application directly to Lever Postings endpoint.
        """
        if "_" not in job_external_id:
            return {"success": False, "message": "Invalid Lever external job ID format (expected company_jobid)."}

        company, job_id = job_external_id.split("_", 1)
        submit_url = f"{self.API_BASE}/{company}/{job_id}"

        data = {
            "name": profile_data.get("full_name", "Applicant"),
            "email": profile_data.get("email", ""),
            "phone": profile_data.get("phone", ""),
        }

        if profile_data.get("linkedin_url"):
            data["urls[LinkedIn]"] = profile_data.get("linkedin_url")
        if profile_data.get("github_url"):
            data["urls[GitHub]"] = profile_data.get("github_url")
        if profile_data.get("portfolio_url"):
            data["urls[Portfolio]"] = profile_data.get("portfolio_url")

        if cover_letter:
            data["comments"] = cover_letter

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
                        "submission_id": f"lever_{job_id}_{int(datetime.utcnow().timestamp())}",
                        "message": f"Successfully submitted application directly to {company.title()} via Lever API!",
                        "raw_response": resp.json() if resp.headers.get("content-type", "").startswith("application/json") else resp.text
                    }
                else:
                    return {
                        "success": False,
                        "message": f"Lever API returned status {resp.status_code}: {resp.text[:300]}",
                        "raw_response": resp.text
                    }
        except Exception as e:
            logger.error(f"Lever direct submit error: {e}")
            return {"success": False, "message": f"Connection error: {str(e)}"}

