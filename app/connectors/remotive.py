import httpx
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from app.connectors.base import BaseConnector

logger = logging.getLogger(__name__)

class RemotiveConnector(BaseConnector):
    name = "remotive"
    display_name = "Remotive (Remote Tech & Data)"
    has_submit_api = False

    API_URL = "https://remotive.com/api/remote-jobs"

    async def fetch_jobs(self, query: Optional[str] = None, location: Optional[str] = None, limit: int = 25) -> List[Dict[str, Any]]:
        params = {}
        if query:
            params["search"] = query
        params["limit"] = str(limit)

        results = []
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(self.API_URL, params=params)
                if resp.status_code != 200:
                    logger.error(f"Remotive API returned status {resp.status_code}")
                    return []
                
                data = resp.json()
                raw_jobs = data.get("jobs", [])
                
                for item in raw_jobs[:limit]:
                    ext_id = str(item.get("id"))
                    pub_date_str = item.get("publication_date", "")
                    try:
                        pub_date = datetime.fromisoformat(pub_date_str.replace("Z", "+00:00")) if pub_date_str else datetime.utcnow()
                    except Exception:
                        pub_date = datetime.utcnow()

                    results.append({
                        "external_id": ext_id,
                        "platform": self.name,
                        "title": item.get("title", "Untitled Role"),
                        "company": item.get("company_name", "Unknown Company"),
                        "location": item.get("candidate_required_location") or "Worldwide / Remote",
                        "job_type": item.get("job_type", "Full-time").replace("_", " ").title(),
                        "salary_range": item.get("salary") or "Not disclosed",
                        "url": item.get("url", ""),
                        "description": item.get("description", ""),
                        "date_posted": pub_date
                    })
        except Exception as e:
            logger.error(f"Error fetching from Remotive API: {e}")

        return results

