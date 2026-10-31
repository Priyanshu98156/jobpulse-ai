import httpx
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from app.connectors.base import BaseConnector

logger = logging.getLogger(__name__)

class TheMuseConnector(BaseConnector):
    name = "themuse"
    display_name = "The Muse (Top Tech & Enterprise Companies)"
    has_submit_api = False

    API_URL = "https://www.themuse.com/api/public/jobs"

    async def fetch_jobs(self, query: Optional[str] = None, location: Optional[str] = None, limit: int = 25) -> List[Dict[str, Any]]:
        params = {"page": 1}
        if location:
            params["location"] = location

        results = []
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(self.API_URL, params=params)
                if resp.status_code != 200:
                    logger.error(f"The Muse API returned status {resp.status_code}")
                    return []
                
                data = resp.json()
                raw_jobs = data.get("results", [])
                
                for item in raw_jobs:
                    title = item.get("name", "")
                    description = item.get("contents", "")
                    company_obj = item.get("company", {})
                    company_name = company_obj.get("name", "Unknown Company")
                    
                    if query:
                        q_lower = query.lower()
                        if q_lower not in title.lower() and q_lower not in description.lower() and q_lower not in company_name.lower():
                            continue

                    ext_id = str(item.get("id"))
                    pub_date_str = item.get("publication_date", "")
                    try:
                        pub_date = datetime.fromisoformat(pub_date_str.replace("Z", "+00:00")) if pub_date_str else datetime.utcnow()
                    except Exception:
                        pub_date = datetime.utcnow()

                    loc_objs = item.get("locations", [])
                    locations = [l.get("name") for l in loc_objs if l.get("name")]
                    loc_str = ", ".join(locations) if locations else "Flexible / Remote"

                    levels = [lvl.get("name") for lvl in item.get("levels", []) if lvl.get("name")]
                    job_type_str = ", ".join(levels) if levels else "Full-time"

                    refs = item.get("refs", {})
                    landing_page = refs.get("landing_page", "")

                    results.append({
                        "external_id": ext_id,
                        "platform": self.name,
                        "title": title or "Untitled Role",
                        "company": company_name,
                        "location": loc_str,
                        "job_type": job_type_str,
                        "salary_range": "Not disclosed",
                        "url": landing_page,
                        "description": description,
                        "date_posted": pub_date
                    })

                    if len(results) >= limit:
                        break
        except Exception as e:
            logger.error(f"Error fetching from The Muse API: {e}")

        return results

