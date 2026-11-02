import pytest
from app.domain.models import JobPosting, RemoteType, EligibilityStatus, ApplicationStatus
from app.domain.candidate import CandidateIdentityDomain, AnswerBankDomain, SkillDomain

def test_job_posting_domain_model_defaults():
    job = JobPosting(
        external_id="ext-999",
        platform="greenhouse",
        title="Senior Python Backend Engineer",
        company="Anthropic",
        url="https://boards.greenhouse.io/anthropic/jobs/999"
    )
    assert job.location == "Remote"
    assert job.remote_type == RemoteType.UNKNOWN
    assert job.eligibility_status == EligibilityStatus.ELIGIBLE
    assert job.status == ApplicationStatus.DISCOVERED
    assert isinstance(job.regions_allowed, list)

def test_answer_bank_factual_guardrail():
    # Questions marked is_factual=True are protected factual answers
    answer = AnswerBankDomain(
        question_pattern="years of experience with python",
        answer_text="3.5 years of production experience",
        is_factual=True,
        source="user_verified"
    )
    assert answer.is_factual is True
    assert answer.source == "user_verified"

def test_skill_claimable_guardrail():
    skill = SkillDomain(
        name="PyTorch",
        category="frameworks",
        years_experience=3.0,
        claimable=True
    )
    assert skill.claimable is True
