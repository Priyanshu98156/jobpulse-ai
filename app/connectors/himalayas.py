import httpx
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from app.connectors.base import BaseConnector

logger = logging.getLogger(__name__)

class HimalayasConnector(BaseConnector):
    name = "himalayas"
    display_name = "Himalayas (Global Remote Tech Jobs)"
    has_submit_api = False

    API_URL = "https://himalayas.app/jobs/api"

    async def fetch_jobs(self, query: Optional[str] = None, location: Optional[str] = None, limit: int = 25) -> List[Dict[str, Any]]:
        results = []
        params = {"limit": limit}

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.get(self.API_URL, params=params)
                if res.status_code != 200:
                    logger.warning(f"Himalayas API returned HTTP {res.status_code}")
                    return results

                data = res.json()
                items = data.get("jobs", [])

                for item in items:
                    title = item.get("title", "")
                    description = item.get("description", "") or item.get("excerpt", "")
                    company = item.get("companyName", "Unknown")
                    guid = item.get("guid") or str(item.get("id", ""))
                    if not guid:
                        guid = f"{company}_{title}"

                    # Filter by search query if provided
                    if query:
                        q_lower = query.lower()
                        if q_lower not in title.lower() and q_lower not in description.lower():
                            continue

                    # Location restrictions
                    loc_restrictions = item.get("locationRestrictions") or []
                    loc_str = ", ".join(loc_restrictions) if loc_restrictions else "Remote - Worldwide"

                    # Salary range
                    min_s = item.get("minSalary")
                    max_s = item.get("maxSalary")
                    curr = item.get("currency") or "USD"
                    salary_str = f"{curr} {min_s} - {max_s}" if (min_s and max_s) else "Not disclosed"

                    # Parse pub date
                    pub_date = datetime.now(timezone.utc)
                    if item.get("pubDate"):
                        try:
                            pub_date = datetime.fromtimestamp(item["pubDate"], tz=timezone.utc)
                        except Exception:
                            pass

                    results.append({
                        "external_id": f"himalayas_{guid}",
                        "platform": self.name,
                        "title": title,
                        "company": company,
                        "location": loc_str,
                        "job_type": item.get("employmentType") or "Full-time",
                        "salary_range": salary_str,
                        "url": item.get("applicationLink") or f"https://himalayas.app/jobs/{guid}",
                        "description": description,
                        "date_posted": pub_date
                    })

        except Exception as e:
            logger.error(f"Error fetching from Himalayas API: {e}")

        return results

