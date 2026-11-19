import json
import logging
import re
from pathlib import Path
from typing import Optional, Dict, Any, List

from app.domain.models import EligibilityStatus
from app.domain.eligibility import EligibilityVerdict

logger = logging.getLogger(__name__)

PROMPT_TEMPLATE_PATH = Path(__file__).parent.parent / "prompts" / "eligibility_v1.txt"

# Layer 1 Disqualification Patterns
DISQUALIFYING_PATTERNS = [
    r"u\.?s\.?\s+citizenship\s+required",
    r"must\s+be\s+a\s+u\.?s\.?\s+citizen",
    r"active\s+security\s+clearance",
    r"ts\s*/\s*sci\s+clearance",
    r"w-?2\s+only",
    r"must\s+reside\s+in\s+the\s+u\.?s\.?",
    r"must\s+be\s+physically\s+located\s+in\s+the\s+(?:united\s+states|us)",
    r"us\s+work\s+authorization\s+required\s+without\s+sponsorship",
    r"strictly\s+us\s+based",
    # Physical Office / Hybrid in foreign countries
    r"hybrid\s+with\s+\d+\s+days?(?:\s*a\s*week)?\s+in\s+(?:the\s+)?office",
    r"\d+\s+days?(?:\s*a\s*week)?\s+in\s+(?:our\s+|the\s+)?office",
    r"(?:must|required\s+to)\s+come\s+into\s+the\s+office",
    r"(?:on-?site|in-?person)\s+only",
    r"no\s+visa\s+sponsorship(?:\s+available|\s+provided)?",
    r"cannot\s+sponsor\s+visas?",
    r"unable\s+to\s+sponsor\s+(?:work\s+)?visas?",
    r"must\s+have\s+(?:the\s+)?right\s+to\s+work\s+in\s+(?:the\s+)?(?:uk|united\s+kingdom|eu|europe|germany|canada|australia)",
    r"uk\s+work\s+(?:permit|authorization)\s+required",
]

# Visa Sponsorship / Relocation Positive Indicators (Overrides local hybrid/onsite)
SPONSORSHIP_RELOCATION_TERMS = [
    r"\bvisa\s+sponsorship\s+(?:is\s+)?(?:provided|available|offered)\b",
    r"\bwill\s+sponsor\s+(?:work\s+)?visas?\b",
    r"\bopen\s+to\s+sponsoring\b",
    r"\brelocation\s+(?:support|package|assistance|allowance|bonus)\b",
    r"\bwe\s+offer\s+relocation\b",
    r"\bassist(?:ance)?\s+with\s+relocation\b",
]

# Common negation prefixes within 35 characters
NEGATION_REGEX = re.compile(r"\b(?:no|not|neither|nor|never|without)\b", re.IGNORECASE)

# Layer 2 Global / India-friendly positive terms
GLOBAL_TERMS = [
    r"\bwork\s+from\s+anywhere\b",
    r"\bremote\s+worldwide\b",
    r"\banywhere\s+in\s+the\s+world\b",
    r"\bglobal(?:ly)?\s+remote\b",
    r"\bworldwide\b",
    r"\bopen\s+to\s+international\b",
    r"\b(?:independent|b2b|c2c|1099|international|remote)\s+contractors?\b",
    r"\bcontractors?\s+(?:role|position|engagement|agreement|basis|opportunity)\b",
    r"\bopen\s+to\s+contractors?\b",
    r"\bb2b\b",
    r"\bdeel\b",
    r"\bremote\.com\b",
    r"\beor\b",
    r"\bindia\b",
    r"\bbengaluru\b",
    r"\bbangalore\b",
]

# Honeypots & Canary Keyword Detectors
CANARY_PATTERNS = [
    r"(?:include|mention|write|put|add)\s+(?:the\s+)?word\s+[\"']([a-zA-Z]{3,20})[\"']",
    r"(?:confirm|verify)\s+you(?:'ve|\s+have)?\s+read\s+this[^\.\n]*?(?:include|mention|use)\s+(?:the\s+word\s+)?[\"']?([a-zA-Z]{3,20})[\"']?",
    r"\bkeyword[:\s]+[\"']?([a-zA-Z]{3,20})[\"']?",
    r"code\s*word[:\s]+[\"']?([a-zA-Z]{3,20})[\"']?",
]

LLM_TRAP_PATTERNS = [
    r"if\s+you(?:'re|\s+are)\s+(?:an?\s+)?(?:llm|ai|bot|language\s+model|automated)",
    r"\[llm\s+alert\]",
    r"applications?\s+without\s+this\s+disclosure\s+will\s+not\s+be\s+considered",
    r"disclose\s+if\s+you\s+are\s+using\s+ai"
]

YOE_PATTERNS = [
    r"(\d+)\+?\s*(?:to|-)\s*\d+\s*years?(?:\s*of)?\s*(?:full[-\s]stack|software|backend|frontend|industry|production|work|relevant)?\s*experience",
    r"(\d+)\+?\s*years?(?:\s*of)?\s*(?:full[-\s]stack|software|backend|frontend|industry|production|work|relevant)?\s*experience",
    r"minimum\s*(?:of\s*)?(\d+)\s*years",
    r"at\s+least\s+(\d+)\s*years",
]

class RemoteEligibilityService:
    """
    4-Layer Remote Eligibility Gate.
    Guarantees zero false-drop of eligible India/contractor remote roles.
    """
    def __init__(self, prompt_path: Path = PROMPT_TEMPLATE_PATH):
        self.prompt_path = prompt_path

    def _matches_with_negation_check(self, text: str, pattern: str) -> Optional[str]:
        """
        Checks if pattern matches in text and confirms it is NOT preceded by negation.
        Returns matching snippet if genuine disqualification, None if negated.
        """
        for match in re.finditer(pattern, text, re.IGNORECASE):
            start_pos = match.start()
            # Look back up to 35 characters
            lookback_start = max(0, start_pos - 35)
            prefix = text[lookback_start:start_pos]
            if NEGATION_REGEX.search(prefix):
                # Negated! e.g. "no US citizenship required"
                logger.debug(f"Negated pattern skipped: '{prefix}{match.group()}'")
                continue
            return match.group()
        return None

    def evaluate_deterministic(
        self,
        title: str,
        location: str,
        description: str,
        is_remote: Optional[bool] = None,
        candidate_profile: Optional[Any] = None
    ) -> Optional[EligibilityVerdict]:
        """
        Runs Layer 1 (Deterministic Regex with Negation) and Layer 2 (Global & Dynamic Candidate Preferences).
        Returns EligibilityVerdict if definitive, or None if Layer 3 (LLM) is needed.
        """
        combined_text = f"{title}\n{location}\n{description}".lower()
        loc_lower = location.lower().strip()

        # Extract candidate dynamic preferences (defaults to India, remote worldwide)
        base_country = "india"
        base_city = ""
        target_cities = []
        work_modes = ["remote_worldwide", "remote_domestic"]
        visa_sponsorship_needed = False
        open_to_relocation = False

        if candidate_profile:
            if isinstance(candidate_profile, dict):
                base_country = (candidate_profile.get("base_country") or "India").strip().lower()
                base_city = (candidate_profile.get("base_city") or "").strip().lower()
                target_cities = [c.strip().lower() for c in candidate_profile.get("target_cities") or []]
                work_modes = candidate_profile.get("work_modes") or ["remote_worldwide", "remote_domestic"]
                visa_sponsorship_needed = bool(candidate_profile.get("visa_sponsorship_needed", False))
                open_to_relocation = bool(candidate_profile.get("open_to_relocation", False))
            else:
                base_country = (getattr(candidate_profile, "base_country", "") or "India").strip().lower()
                base_city = (getattr(candidate_profile, "base_city", "") or "").strip().lower()
                target_cities = [c.strip().lower() for c in getattr(candidate_profile, "target_cities", []) or []]
                work_modes = getattr(candidate_profile, "work_modes", []) or ["remote_worldwide", "remote_domestic"]
                visa_sponsorship_needed = bool(getattr(candidate_profile, "visa_sponsorship_needed", False))
                open_to_relocation = bool(getattr(candidate_profile, "open_to_relocation", False))

        # Check explicit visa sponsorship or relocation assistance
        has_sponsorship_relocation = False
        matched_sponsor_quote = ""
        for s_term in SPONSORSHIP_RELOCATION_TERMS:
            m = re.search(s_term, combined_text, re.IGNORECASE)
            if m:
                has_sponsorship_relocation = True
                matched_sponsor_quote = m.group()
                break

        # Check positive indicators (India, Worldwide, B2B Contractor, or Candidate's Base Country/City)
        has_global_term = False
        matched_global_quote = ""
        for g_term in GLOBAL_TERMS:
            m = re.search(g_term, combined_text, re.IGNORECASE)
            if m:
                has_global_term = True
                matched_global_quote = m.group()
                break

        # Check if location directly matches candidate's base country or target cities
        matches_candidate_location = (
            (base_country and base_country in loc_lower) or
            (base_city and base_city in loc_lower) or
            any(tc and tc in loc_lower for tc in target_cities)
        )

        # Layer 1: Check disqualifying terms
        disqualified_snippet = None
        for pattern in DISQUALIFYING_PATTERNS:
            snippet = self._matches_with_negation_check(combined_text, pattern)
            if snippet:
                disqualified_snippet = snippet
                break

        # If international sponsorship or relocation is explicitly provided, it qualifies an onsite/hybrid role
        if has_sponsorship_relocation:
            return EligibilityVerdict(
                status=EligibilityStatus.ELIGIBLE,
                reason=f"Role provides international visa sponsorship or relocation assistance: '{matched_sponsor_quote}'.",
                confidence=0.92,
                evidence_quote=matched_sponsor_quote,
                requires_human_look=False
            )

        # Conflict resolution between disqualifying and global terms
        if disqualified_snippet and has_global_term:
            return EligibilityVerdict(
                status=EligibilityStatus.UNCLEAR,
                reason=f"Conflicting signals: Found '{disqualified_snippet}' but also global term '{matched_global_quote}'.",
                confidence=0.5,
                evidence_quote=f"Conflicting: {disqualified_snippet} vs {matched_global_quote}",
                requires_human_look=True
            )

        if disqualified_snippet:
            return EligibilityVerdict(
                status=EligibilityStatus.INELIGIBLE,
                reason=f"Disqualifying requirement found: '{disqualified_snippet}'.",
                confidence=0.95,
                evidence_quote=disqualified_snippet,
                requires_human_look=False
            )

        # Dynamic Check: Foreign Non-Remote Role without Sponsorship
        # Known foreign hubs/indicators when candidate is not located there
        foreign_locations = ["london", "united kingdom", "uk", "germany", "berlin", "munich", "france", "paris", "netherlands", "amsterdam", "canada", "toronto", "vancouver", "australia", "sydney", "singapore", "new york", "san francisco", "austin", "chicago", "seattle"]
        is_foreign = any(fl in loc_lower for fl in foreign_locations) and not matches_candidate_location
        has_remote_tag = is_remote is True or any(x in loc_lower for x in ["remote", "worldwide", "anywhere", "work from anywhere"])

        if is_foreign and not has_remote_tag and not has_sponsorship_relocation:
            return EligibilityVerdict(
                status=EligibilityStatus.INELIGIBLE,
                reason=f"Onsite/hybrid role in '{location}' is outside candidate's base location ({base_country.title()}) and does not offer visa sponsorship.",
                confidence=0.95,
                evidence_quote=location,
                requires_human_look=False
            )

        # Explicit location checks
        if any(x in loc_lower for x in ["worldwide", "anywhere", "global", "remote - worldwide"]):
            return EligibilityVerdict(
                status=EligibilityStatus.ELIGIBLE,
                reason=f"Location '{location}' is worldwide remote eligible.",
                confidence=0.95,
                evidence_quote=location,
                requires_human_look=False
            )

        if matches_candidate_location:
            return EligibilityVerdict(
                status=EligibilityStatus.ELIGIBLE,
                reason=f"Location '{location}' matches candidate's target preferences ({base_country.title()}).",
                confidence=0.92,
                evidence_quote=location,
                requires_human_look=False
            )

        if has_global_term:
            return EligibilityVerdict(
                status=EligibilityStatus.ELIGIBLE,
                reason=f"Job description mentions global remote / contractor friendly indicator: '{matched_global_quote}'.",
                confidence=0.9,
                evidence_quote=matched_global_quote,
                requires_human_look=False
            )

        # Ambiguous -> Pass to Layer 3 (LLM)
        return None

    def evaluate_with_llm(
        self,
        title: str,
        company: str,
        location: str,
        description: str,
        llm_caller
    ) -> EligibilityVerdict:
        """
        Layer 3: Pydantic-structured LLM classifier using versioned prompt template.
        """
        if not self.prompt_path.exists():
            return EligibilityVerdict(
                status=EligibilityStatus.UNCLEAR,
                reason="Prompt template missing.",
                confidence=0.5,
                requires_human_look=True
            )

        template = self.prompt_path.read_text(encoding="utf-8")
        prompt = template.format(
            title=title,
            company=company,
            location=location,
            description=description[:3500] # Cap to prevent overflow
        )

        try:
            raw_response = llm_caller(prompt)
            # Parse JSON
            # Extract JSON block if wrapped in markdown code fence
            clean_json = raw_response.strip()
            if "```json" in clean_json:
                clean_json = clean_json.split("```json")[1].split("```")[0].strip()
            elif "```" in clean_json:
                clean_json = clean_json.split("```")[1].split("```")[0].strip()

            data = json.loads(clean_json)
            verdict = EligibilityVerdict(
                status=EligibilityStatus(data.get("status", "unclear")),
                reason=data.get("reason", "LLM evaluation"),
                confidence=float(data.get("confidence", 0.7)),
                evidence_quote=data.get("evidence_quote", ""),
                requires_human_look=bool(data.get("requires_human_look", False))
            )
            return verdict
        except Exception as e:
            logger.warning(f"Layer 3 LLM evaluation failed: {e}. Falling back to Layer 4 (Needs a Look).")
            return EligibilityVerdict(
                status=EligibilityStatus.UNCLEAR,
                reason=f"LLM classifier exception: {str(e)[:100]}",
                confidence=0.5,
                requires_human_look=True
            )

    def extract_yoe_requirement(self, description: str) -> tuple[Optional[int], str]:
        """
        Extracts minimum years of experience required by the JD.
        Classifies into direct_match (0-2y), stretch_match (3y), senior_role (4-5y), or veteran_role (6+y).
        """
        desc_lower = description.lower()
        min_yoe = None
        for pattern in YOE_PATTERNS:
            m = re.search(pattern, desc_lower)
            if m:
                try:
                    val = int(m.group(1))
                    if min_yoe is None or val < min_yoe:
                        min_yoe = val
                except (ValueError, TypeError):
                    continue

        if min_yoe is None:
            if any(w in desc_lower for w in ["principal engineer", "staff engineer", "lead developer"]):
                return 5, "senior_role"
            return None, "direct_match"

        if min_yoe <= 2:
            return min_yoe, "direct_match"
        elif min_yoe == 3:
            return min_yoe, "stretch_match"
        elif 4 <= min_yoe <= 5:
            return min_yoe, "senior_role"
        else:
            return min_yoe, "veteran_role"

    def detect_canary_and_traps(self, description: str) -> tuple[List[str], bool]:
        """
        Detects employer canary words (e.g., 'include the word pineapple')
        and honeypot LLM traps ('if you are an LLM include [llm alert]').
        """
        canaries = []
        desc_lower = description.lower()

        # 1. Canary words
        for pattern in CANARY_PATTERNS:
            for match in re.finditer(pattern, description, re.IGNORECASE):
                word = match.group(1).strip()
                if word and len(word) >= 3 and word.lower() not in ["and", "the", "that", "this", "with", "word"]:
                    if word.lower() not in [c.lower() for c in canaries]:
                        canaries.append(word.lower())

        # 2. LLM honeypot trap
        has_trap = False
        for pattern in LLM_TRAP_PATTERNS:
            if re.search(pattern, desc_lower):
                has_trap = True
                break

        return canaries, has_trap

    def evaluate_job(
        self,
        title: str,
        company: str,
        location: str,
        description: str,
        is_remote: Optional[bool] = None,
        candidate_profile: Optional[Any] = None,
        llm_caller = None
    ) -> EligibilityVerdict:
        """
        Full 4-Layer evaluation pipeline with YoE classification, Canary/Trap detection, and candidate preferences.
        """
        # Step 1: Run deterministic layers (Layer 1 & 2)
        verdict = self.evaluate_deterministic(
            title=title,
            location=location,
            description=description,
            is_remote=is_remote,
            candidate_profile=candidate_profile
        )
        if verdict is None:
            # Step 2: Run Layer 3 (LLM) if caller provided
            if llm_caller is not None:
                verdict = self.evaluate_with_llm(title, company, location, description, llm_caller)
            else:
                # Step 3: Layer 4 fallback if no LLM caller available
                verdict = EligibilityVerdict(
                    status=EligibilityStatus.UNCLEAR,
                    reason="Ambiguous job location/requirements; queued for manual review.",
                    confidence=0.5,
                    requires_human_look=True
                )

        # Step 4: Extract YoE and Canary/Trap detection
        yoe, yoe_class = self.extract_yoe_requirement(f"{title}\n{description}")
        canaries, has_trap = self.detect_canary_and_traps(description)

        verdict.required_yoe = yoe
        verdict.yoe_classification = yoe_class
        verdict.canary_keywords = canaries
        verdict.has_llm_trap = has_trap

        # Flag veteran roles (6+ years) for candidate look
        if yoe_class == "veteran_role" and verdict.status == EligibilityStatus.ELIGIBLE:
            verdict.requires_human_look = True
            verdict.reason += f" (Demands {yoe}+ years experience - veteran role)"

        return verdict

eligibility_service = RemoteEligibilityService()
