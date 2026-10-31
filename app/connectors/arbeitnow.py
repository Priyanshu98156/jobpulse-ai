import httpx
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from app.connectors.base import BaseConnector

logger = logging.getLogger(__name__)

class ArbeitnowConnector(BaseConnector):
    name = "arbeitnow"
    display_name = "Arbeitnow (Global & Remote Tech)"
    has_submit_api = False

    API_URL = "https://www.arbeitnow.com/api/job-board-api"

    async def fetch_jobs(self, query: Optional[str] = None, location: Optional[str] = None, limit: int = 25) -> List[Dict[str, Any]]:
        results = []
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(self.API_URL)
                if resp.status_code != 200:
                    logger.error(f"Arbeitnow API returned status {resp.status_code}")
                    return []
                
                data = resp.json()
                raw_jobs = data.get("data", [])
                
                for item in raw_jobs:
                    title = item.get("title", "")
                    description = item.get("description", "")
                    
                    # Filter query locally if query specified
                    if query:
                        q_lower = query.lower()
                        if q_lower not in title.lower() and q_lower not in description.lower():
                            continue

                    ext_id = str(item.get("slug"))
                    created_at_ts = item.get("created_at")
                    try:
                        pub_date = datetime.fromtimestamp(created_at_ts) if created_at_ts else datetime.utcnow()
                    except Exception:
                        pub_date = datetime.utcnow()

                    job_types = item.get("job_types", [])
                    job_type_str = ", ".join(job_types) if job_types else "Full-time"
                    loc = item.get("location", "Remote")
                    if item.get("remote", False):
                        loc = f"{loc} (Remote)" if loc else "Remote"

                    results.append({
                        "external_id": ext_id,
                        "platform": self.name,
                        "title": title or "Untitled Role",
                        "company": item.get("company_name", "Unknown Company"),
                        "location": loc,
                        "job_type": job_type_str,
                        "salary_range": "Not disclosed",
                        "url": item.get("url", ""),
                        "description": description,
                        "date_posted": pub_date
                    })

                    if len(results) >= limit:
                        break
        except Exception as e:
            logger.error(f"Error fetching from Arbeitnow API: {e}")

        return results
