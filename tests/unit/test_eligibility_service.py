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

