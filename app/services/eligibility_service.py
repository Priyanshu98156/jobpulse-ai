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

    def evaluate_deterministic(self, title: str, location: str, description: str) -> Optional[EligibilityVerdict]:
        """
        Runs Layer 1 (Deterministic Regex with Negation) and Layer 2 (Global & Contractor Rules).
        Returns EligibilityVerdict if definitive, or None if Layer 3 (LLM) is needed.
        """
        combined_text = f"{title}\n{location}\n{description}".lower()

        # Check positive indicators first (India, Worldwide, B2B Contractor)
        has_global_term = False
        matched_global_quote = ""
        for g_term in GLOBAL_TERMS:
            m = re.search(g_term, combined_text, re.IGNORECASE)
            if m:
                has_global_term = True
                matched_global_quote = m.group()
                break

        # Layer 1: Check disqualifying terms
        disqualified_snippet = None
        for pattern in DISQUALIFYING_PATTERNS:
            snippet = self._matches_with_negation_check(combined_text, pattern)
            if snippet:
                disqualified_snippet = snippet
                break

        # Conflict resolution between disqualifying and global terms
        if disqualified_snippet and has_global_term:
            # Conflicting signals -> Route to Layer 4 (Needs a Look)
            return EligibilityVerdict(
                status=EligibilityStatus.UNCLEAR,
                reason=f"Conflicting signals: Found '{disqualified_snippet}' but also global term '{matched_global_quote}'.",
                confidence=0.5,
                evidence_quote=f"Conflicting: {disqualified_snippet} vs {matched_global_quote}",
                requires_human_look=True
            )

        if disqualified_snippet:
            # Definitive ineligibility
            return EligibilityVerdict(
                status=EligibilityStatus.INELIGIBLE,
                reason=f"Disqualifying requirement found: '{disqualified_snippet}'.",
                confidence=0.95,
                evidence_quote=disqualified_snippet,
                requires_human_look=False
            )

        # Explicit location checks
        loc_lower = location.lower().strip()
        if any(x in loc_lower for x in ["worldwide", "anywhere", "global", "india", "remote - worldwide"]):
            return EligibilityVerdict(
                status=EligibilityStatus.ELIGIBLE,
                reason=f"Location '{location}' is worldwide/India remote eligible.",
                confidence=0.95,
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
        llm_caller = None
    ) -> EligibilityVerdict:
        """
        Full 4-Layer evaluation pipeline with YoE classification and Canary/Trap detection.
        """
        # Step 1: Run deterministic layers (Layer 1 & 2)
        verdict = self.evaluate_deterministic(title, location, description)
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
