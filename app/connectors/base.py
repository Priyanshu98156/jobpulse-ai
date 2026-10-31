from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from datetime import datetime

class BaseConnector(ABC):
    name: str = "base"
    display_name: str = "Base Connector"
    has_submit_api: bool = False

    @abstractmethod
    async def fetch_jobs(self, query: Optional[str] = None, location: Optional[str] = None, limit: int = 25) -> List[Dict[str, Any]]:
        """
        Fetch normalized job listings from the platform.
        Must return list of dicts with:
        - external_id: str
        - platform: str
        - title: str
        - company: str
        - location: str
        - job_type: str
        - salary_range: str
        - url: str
        - description: str
        - date_posted: datetime
        """
        pass

    async def submit_application(
        self,
        job_external_id: str,
        profile_data: Dict[str, Any],
        resume_path: Optional[str] = None,
        cover_letter: Optional[str] = None,
        answers: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Optional: Submit application directly via platform ATS API.
        Returns:
        {
            "success": bool,
            "submission_id": Optional[str],
            "message": str,
            "raw_response": Any
        }
        """
        raise NotImplementedError("Direct API submission not supported for this connector.")

