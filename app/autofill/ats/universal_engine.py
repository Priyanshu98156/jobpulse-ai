import logging
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional, List
import yaml
from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError

from app.domain.candidate import CandidateIdentityDomain

logger = logging.getLogger(__name__)

SELECTORS_PATH = Path(__file__).parent.parent / "selectors" / "universal.yaml"

class UniversalAutofillEngine:
    """
    Universal ATS & Web Form Autofill Driver.
    Fills Personal Info, Social Links, Resume Upload, and Custom Answers in Headed Browser.
    Enforces Structural Stop before final submission.
    """
    def __init__(self, selectors_path: Path = SELECTORS_PATH):
        self.selectors_path = selectors_path
        self.selectors = self._load_selectors()

    def _load_selectors(self) -> Dict[str, Any]:
        if not self.selectors_path.exists():
            return {}
        with open(self.selectors_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    async def _fill_field(self, page: Page, selector_list: List[str], value: str) -> bool:
        if not value:
            return False
        for sel in selector_list:
            try:
                locator = page.locator(sel).first
                if await locator.is_visible(timeout=1000):
                    await locator.fill(value)
                    logger.debug(f"Autofilled {sel}")
                    return True
            except Exception:
                continue
        return False

    async def autofill_candidate_package(
        self,
        page: Page,
        candidate_data: Dict[str, Any],
        resume_path: Optional[str] = None,
        cover_letter: Optional[str] = None,
        answers: Optional[Dict[str, str]] = None
    ) -> Dict[str, bool]:
        """
        Executes end-to-end form autofill on current active page:
        1. Full name or First/Last name
        2. Email & Phone
        3. Social Links (LinkedIn, GitHub, Portfolio)
        4. Resume PDF File Upload
        5. Cover Letter Textarea
        6. Pre-matched Screening Questions from Answer Bank
        """
        forms = self.selectors.get("forms", {})
        results = {}

        # 1. Names
        full_name = candidate_data.get("full_name", "")
        parts = full_name.split()
        first_name = parts[0] if parts else ""
        last_name = " ".join(parts[1:]) if len(parts) > 1 else (parts[0] if parts else "")

        # Try full_name first, then split first/last
        filled_name = await self._fill_field(page, forms.get("full_name", []), full_name)
        if not filled_name:
            await self._fill_field(page, forms.get("first_name", []), first_name)
            await self._fill_field(page, forms.get("last_name", []), last_name)
        results["name"] = True

        # 2. Email & Phone
        await self._fill_field(page, forms.get("email", []), candidate_data.get("email", ""))
        await self._fill_field(page, forms.get("phone", []), candidate_data.get("phone", ""))
        results["contact"] = True

        # 3. Socials
        if candidate_data.get("linkedin_url"):
            await self._fill_field(page, forms.get("linkedin", []), candidate_data["linkedin_url"])
        if candidate_data.get("github_url"):
            await self._fill_field(page, forms.get("github", []), candidate_data["github_url"])
        if candidate_data.get("portfolio_url"):
            await self._fill_field(page, forms.get("portfolio", []), candidate_data["portfolio_url"])
        results["socials"] = True

        # 4. Resume Attachment
        if resume_path and Path(resume_path).exists():
            for sel in forms.get("resume_upload", []):
                try:
                    locator = page.locator(sel).first
                    # File inputs may be visually hidden behind custom styling
                    await locator.set_input_files(resume_path, timeout=2000)
                    results["resume_uploaded"] = True
                    break
                except Exception:
                    continue

        # 5. Tailored Cover Letter
        if cover_letter:
            await self._fill_field(page, forms.get("cover_letter", []), cover_letter)
            results["cover_letter"] = True

        # 6. Screening Questions from Answer Bank
        if answers:
            for pattern, answer_text in answers.items():
                try:
                    # Match inputs or textareas containing question pattern in placeholder, aria-label, or preceding label
                    question_locator = page.locator(f"textarea[aria-label*='{pattern}' i], input[aria-label*='{pattern}' i]").first
                    if await question_locator.is_visible(timeout=500):
                        await question_locator.fill(answer_text)
                except Exception:
                    continue

        return results

universal_autofill_engine = UniversalAutofillEngine()
