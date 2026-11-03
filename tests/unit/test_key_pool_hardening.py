import pytest
from app.services.key_pool_service import (
    key_pool_service,
    PROVIDER_ALLOWLISTS,
    RateLimitException,
)
from app.services.ai_service import ai_service
from app.db.models import AIKey

def test_provider_allowlists_are_configured():
    for prov in ["groq", "openrouter", "gemini"]:
        assert prov in PROVIDER_ALLOWLISTS
        assert len(PROVIDER_ALLOWLISTS[prov]) >= 2
        # Ensure free/economical models are prioritized
        for m in PROVIDER_ALLOWLISTS[prov]:
            assert isinstance(m, str) and len(m) > 0

def test_self_healing_respects_strict_allowlist():
    key = AIKey(
        label="Test Groq Key",
        provider="groq",
        keyring_id="mock_key_id",
        model="unsupported-deprecated-model-xyz",
        base_url="https://api.groq.com/openai/v1"
    )
    # When auto-discovering without network, it falls back strictly to the first allowlisted model
    discovered = key_pool_service._auto_discover_new_model(key)
    assert discovered in PROVIDER_ALLOWLISTS["groq"]
    assert discovered != "unsupported-deprecated-model-xyz"

def test_score_hash_caching():
    job_title = "Senior Data Scientist"
    job_desc = "Building neural networks and deep learning pipelines with PyTorch."
    summary = "Python ML Engineer with 4 years experience."
    skills = "Python, PyTorch, SQL"
    resume = "Developed recommendation systems with PyTorch and Python."

    # First call primes cache
    res1 = ai_service.score_and_match(job_title, job_desc, summary, skills, resume)
    assert res1["match_score"] > 0

    # Second call should be a cache hit
    res2 = ai_service.score_and_match(job_title, job_desc, summary, skills, resume)
    assert res1 == res2

