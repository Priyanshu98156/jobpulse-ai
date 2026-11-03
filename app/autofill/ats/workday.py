import logging
import re
from pathlib import Path
from typing import Dict, Any, Optional, List
import yaml
from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError

from app.domain.candidate import CandidateIdentityDomain

logger = logging.getLogger(__name__)

SELECTORS_PATH = Path(__file__).parent.parent / "selectors" / "workday.yaml"

class WorkdayAutofillEngine:
    """
    Workday ATS Wizard Autofill Driver.
    Strictly enforces Structural Stop before final submission per CODING_STANDARDS.md.
    """
    def __init__(self, selectors_path: Path = SELECTORS_PATH):
        self.selectors_path = selectors_path
        self.selectors = self._load_selectors()

    def _load_selectors(self) -> Dict[str, Any]:
        if not self.selectors_path.exists():
            logger.warning(f"Selector map not found at {self.selectors_path}")
            return {}
        with open(self.selectors_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    async def _try_fill_first_match(self, page: Page, selector_list: List[str], value: str) -> bool:
        """Tries filling the first selector that resolves on the page."""
        if not value:
            return False
        for sel in selector_list:
            try:
                locator = page.locator(sel).first
                if await locator.is_visible(timeout=1000):
                    await locator.fill(value)
                    logger.debug(f"Filled {sel} with value.")
                    return True
            except Exception:
                continue
        return False

    async def fill_my_information(self, page: Page, candidate: CandidateIdentityDomain) -> bool:
        """Fills the first wizard step: Personal contact details."""
        info_sel = self.selectors.get("pages", {}).get("my_information", {})
        
        # Split full name into first and last
        name_parts = candidate.full_name.strip().split()
        first_name = name_parts[0] if name_parts else ""
        last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else name_parts[0] if name_parts else ""

        await self._try_fill_first_match(page, info_sel.get("first_name", []), first_name)
        await self._try_fill_first_match(page, info_sel.get("last_name", []), last_name)
        await self._try_fill_first_match(page, info_sel.get("email", []), candidate.email)
        await self._try_fill_first_match(page, info_sel.get("phone", []), candidate.phone)

        logger.info(f"Filled contact information for {candidate.full_name}")
        return True

    async def upload_resume(self, page: Page, resume_path: Path) -> bool:
        """Attaches master resume if file input is available."""
        if not resume_path.exists():
            logger.warning(f"Resume file not found at {resume_path}")
            return False

        exp_sel = self.selectors.get("pages", {}).get("my_experience", {})
        for sel in exp_sel.get("resume_dropzone", []):
            try:
                input_elem = page.locator(sel).first
                if await input_elem.count() > 0:
                    await input_elem.set_input_files(str(resume_path))
                    logger.info(f"Attached resume from {resume_path}")
                    return True
            except Exception as e:
                logger.debug(f"Selector {sel} failed for resume upload: {e}")
                continue
        return False

    async def answer_screening_questions(self, page: Page, answers: Dict[str, str]) -> int:
        """
        Fuzzy matches question labels on the page with pre-approved answers from AnswerBank.
        """
        filled_count = 0
        try:
            # Query all text-capable inputs and textareas (handles implicit text inputs)
            text_inputs = await page.locator("input:not([type]), input[type='text'], textarea").all()
            for inp in text_inputs:
                try:
                    aria_label = (await inp.get_attribute("aria-label")) or ""
                    placeholder = (await inp.get_attribute("placeholder")) or ""
                    name_attr = (await inp.get_attribute("name")) or ""
                    label_text = f"{aria_label} {placeholder} {name_attr}".lower()

                    for pattern, ans in answers.items():
                        if pattern.lower() in label_text:
                            await inp.fill(ans)
                            filled_count += 1
                            break
                except Exception:
                    continue
        except Exception as e:
            logger.warning(f"Error while answering screening questions: {e}")

        return filled_count

    async def is_at_review_or_submit_page(self, page: Page) -> bool:
        """
        Detects whether the wizard has advanced to the final Review step.
        """
        review_selectors = [
            'button[data-automation-id="bottom-navigation-submit-button"]',
            'button:has-text("Submit Application")',
            'button:has-text("Review and Submit")',
            'h2:has-text("Review")',
            'div[data-automation-id="reviewPage"]'
        ]
        for sel in review_selectors:
            try:
                if await page.locator(sel).first.is_visible(timeout=1000):
                    return True
            except Exception:
                continue
        return False

    async def run_assisted_fill(
        self,
        page: Page,
        candidate: CandidateIdentityDomain,
        resume_path: Optional[Path] = None,
        answers: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Executes assisted form filling with STRUCTURAL STOP BEFORE SUBMIT.
        NEVER clicks Submit. Hands control over to user with headed browser visible.
        """
        logger.info("Starting Workday assisted fill...")
        answers = answers or {}

        # 1. Fill personal info
        await self.fill_my_information(page, candidate)

        # 2. Upload resume if available
        if resume_path:
            await self.upload_resume(page, resume_path)

        # 3. Answer screening questions
        answered = await self.answer_screening_questions(page, answers)

        # 4. Check if review page reached
        at_review = await self.is_at_review_or_submit_page(page)

        # SAFETY PROTOCOL: Structural Stop
        return {
            "status": "STOP_BEFORE_SUBMIT",
            "at_review_page": at_review,
            "questions_answered": answered,
            "message": (
                "Workday application successfully filled! "
                "STRUCTURAL STOP: Antigravity has paused automation. "
                "Please review the filled fields on your headed browser and click Submit yourself."
            )
        }
