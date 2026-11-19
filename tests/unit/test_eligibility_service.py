import json
import pytest
from app.domain.models import EligibilityStatus
from app.services.eligibility_service import RemoteEligibilityService

@pytest.fixture
def service():
    return RemoteEligibilityService()

def test_layer1_hard_disqualification(service):
    text = "We are an aerospace contractor. Active security clearance and US citizenship required."
    verdict = service.evaluate_deterministic(
        title="Software Engineer",
        location="Remote, US",
        description=text
    )
    assert verdict is not None
    assert verdict.status == EligibilityStatus.INELIGIBLE
    assert "citizenship" in verdict.reason.lower()

def test_layer1_negation_handling_citizenship(service):
    # Negation: "no US citizenship required" must NOT trigger disqualification
    text = "Great opportunity for global developers. No US citizenship required! Open to international applicants."
    verdict = service.evaluate_deterministic(
        title="Python Backend Developer",
        location="Remote Worldwide",
        description=text
    )
    assert verdict is not None
    assert verdict.status == EligibilityStatus.ELIGIBLE
    assert verdict.status != EligibilityStatus.INELIGIBLE

def test_layer1_negation_handling_w2(service):
    # Negation: "not W2 only" must NOT trigger disqualification
    text = "We hire globally via Deel. We are not W2 only and welcome B2B contractor arrangements."
    verdict = service.evaluate_deterministic(
        title="Machine Learning Engineer",
        location="Anywhere",
        description=text
    )
    assert verdict is not None
    assert verdict.status == EligibilityStatus.ELIGIBLE

def test_layer2_worldwide_eligible(service):
    verdict = service.evaluate_deterministic(
        title="Senior Data Scientist",
        location="Remote - Worldwide",
        description="We are a fully distributed team. You can work from anywhere in the world."
    )
    assert verdict is not None
    assert verdict.status == EligibilityStatus.ELIGIBLE
    assert verdict.requires_human_look is False

def test_layer1_and_2_conflicting_signals_route_to_needs_look(service):
    # Disqualification term present alongside global contractor indicator
    text = "Client requires TS/SCI clearance or contractor B2B engagement outside US."
    verdict = service.evaluate_deterministic(
        title="DevOps Engineer",
        location="Remote",
        description=text
    )
    assert verdict is not None
    # Conflicting signals must be routed to UNCLEAR with requires_human_look=True
    assert verdict.status == EligibilityStatus.UNCLEAR
    assert verdict.requires_human_look is True

def test_layer3_llm_structured_parsing(service):
    # Mock LLM caller returning valid JSON schema
    mock_llm_response = json.dumps({
        "status": "eligible",
        "reason": "Allows global candidates with 4h EST overlap",
        "confidence": 0.92,
        "evidence_quote": "Flexible hours with 4 hours US overlap required",
        "requires_human_look": False
    })

    verdict = service.evaluate_with_llm(
        title="Full Stack Engineer",
        company="GlobalTech",
        location="Remote",
        description="We need 4 hours of overlap with New York.",
        llm_caller=lambda p: mock_llm_response
    )
    assert verdict.status == EligibilityStatus.ELIGIBLE
    assert verdict.confidence == 0.92
    assert verdict.requires_human_look is False

def test_deliveroo_london_ineligible_for_india_candidate(service):
    """
    Verifies Deliveroo London (onsite UK role) is strictly INELIGIBLE
    for an Indian candidate who is remote-only or lacks UK visa sponsorship.
    """
    india_candidate = {
        "base_country": "India",
        "base_city": "Bengaluru",
        "target_cities": ["Bengaluru", "Hyderabad"],
        "work_modes": ["remote_worldwide", "remote_domestic"],
        "visa_sponsorship_needed": False,
        "open_to_relocation": False
    }

    deliveroo_jd = """
    We're now looking for a Backend Engineer (Golang) to join us in building scalable,
    low-latency systems that power these tools and shape the future of customer support.
    3+ years of professional software engineering experience.
    """

    verdict = service.evaluate_deterministic(
        title="Software Engineer",
        location="London, England, United Kingdom",
        description=deliveroo_jd,
        is_remote=False,
        candidate_profile=india_candidate
    )

    assert verdict is not None
    assert verdict.status == EligibilityStatus.INELIGIBLE
    assert "outside candidate's base location" in verdict.reason.lower()

def test_deliveroo_london_eligible_for_uk_candidate(service):
    """
    Verifies that the exact same Deliveroo London role IS ELIGIBLE
    for a UK-based candidate.
    """
    uk_candidate = {
        "base_country": "United Kingdom",
        "base_city": "London",
        "target_cities": ["London"],
        "work_modes": ["hybrid", "onsite"],
        "visa_sponsorship_needed": False,
        "open_to_relocation": False
    }

    deliveroo_jd = """
    We're now looking for a Backend Engineer (Golang) to join us in building scalable,
    low-latency systems that power these tools.
    """

    verdict = service.evaluate_deterministic(
        title="Software Engineer",
        location="London, England, United Kingdom",
        description=deliveroo_jd,
        is_remote=False,
        candidate_profile=uk_candidate
    )

    assert verdict is not None
    assert verdict.status == EligibilityStatus.ELIGIBLE
    assert "matches candidate's target preferences" in verdict.reason.lower()

