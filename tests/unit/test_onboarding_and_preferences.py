import pytest
from pydantic import ValidationError
from app.domain.candidate import CandidateOnboardingDomain

def test_candidate_onboarding_domain_enforces_max_three_titles():
    # 1 title is valid
    data1 = {
        "full_name": "Priyanshu Gupta",
        "base_city": "Bengaluru",
        "base_country": "India",
        "target_titles": ["Data Scientist"],
        "skills": "Python, SQL, Machine Learning"
    }
    model1 = CandidateOnboardingDomain(**data1)
    assert len(model1.target_titles) == 1

    # 3 titles is valid
    data3 = {
        "full_name": "Priyanshu Gupta",
        "base_city": "Bengaluru",
        "base_country": "India",
        "target_titles": ["Data Scientist", "ML Engineer", "Python Developer"],
        "skills": "Python, SQL"
    }
    model3 = CandidateOnboardingDomain(**data3)
    assert len(model3.target_titles) == 3

    # > 3 titles raises ValidationError
    data4 = {
        "full_name": "Priyanshu Gupta",
        "base_city": "Bengaluru",
        "base_country": "India",
        "target_titles": ["Data Scientist", "ML Engineer", "Python Developer", "AI Engineer"],
        "skills": "Python, SQL"
    }
    with pytest.raises(ValidationError) as exc:
        CandidateOnboardingDomain(**data4)
    assert "Maximum 3 target job titles allowed" in str(exc.value)

def test_candidate_onboarding_domain_strips_empty_titles():
    data = {
        "full_name": "Priyanshu Gupta",
        "base_city": "Bengaluru",
        "base_country": "India",
        "target_titles": ["  Data Scientist  ", "", "  ", "ML Engineer"],
        "skills": "Python, SQL"
    }
    model = CandidateOnboardingDomain(**data)
    assert model.target_titles == ["Data Scientist", "ML Engineer"]
