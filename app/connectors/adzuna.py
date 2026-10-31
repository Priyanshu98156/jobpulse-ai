import httpx
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from app.connectors.base import BaseConnector
from app.config import settings

logger = logging.getLogger(__name__)

class AdzunaConnector(BaseConnector):
    name = "adzuna"
    display_name = "Adzuna (Global Job Search API)"
    has_submit_api = False

    def __init__(self, country: str = "us"):
        self.country = country

    async def fetch_jobs(self, query: Optional[str] = None, location: Optional[str] = None, limit: int = 25) -> List[Dict[str, Any]]:
        app_id = settings.ADZUNA_APP_ID
        app_key = settings.ADZUNA_APP_KEY

        if not app_id or not app_key:
            logger.info("Adzuna API credentials not configured in .env (ADZUNA_APP_ID & ADZUNA_APP_KEY). Skipping Adzuna connector.")
            return []

        url = f"https://api.adzuna.com/v1/api/jobs/{self.country}/search/1"
        params = {
            "app_id": app_id,
            "app_key": app_key,
            "results_per_page": min(limit, 50),
            "what": query or "software engineer",
            "content-type": "application/json"
        }
        if location:
            params["where"] = location

        results = []
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(url, params=params)
                if resp.status_code != 200:
                    logger.error(f"Adzuna API returned status {resp.status_code}")
                    return []
                
                data = resp.json()
                raw_jobs = data.get("results", [])
                
                for item in raw_jobs:
                    company_obj = item.get("company", {})
                    company_name = company_obj.get("display_name", "Unknown Company")
                    loc_obj = item.get("location", {})
                    loc_name = loc_obj.get("display_name", "Flexible")
                    
                    salary_min = item.get("salary_min")
                    salary_max = item.get("salary_max")
                    if salary_min and salary_max:
                        salary_str = f"${int(salary_min):,} - ${int(salary_max):,}"
                    elif salary_min:
                        salary_str = f"From ${int(salary_min):,}"
                    else:
                        salary_str = "Not disclosed"

                    created_str = item.get("created", "")
                    try:
                        pub_date = datetime.fromisoformat(created_str.replace("Z", "+00:00")) if created_str else datetime.utcnow()
                    except Exception:
                        pub_date = datetime.utcnow()

                    results.append({
                        "external_id": str(item.get("id")),
                        "platform": self.name,
                        "title": item.get("title", "Untitled Role"),
                        "company": company_name,
                        "location": loc_name,
                        "job_type": item.get("contract_time", "Full-time").replace("_", " ").title(),
                        "salary_range": salary_str,
                        "url": item.get("redirect_url", ""),
                        "description": item.get("description", ""),
                        "date_posted": pub_date
                    })

                    if len(results) >= limit:
                        break
        except Exception as e:
            logger.error(f"Error fetching from Adzuna API: {e}")

        return results
