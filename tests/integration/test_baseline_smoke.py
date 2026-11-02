import pytest
from starlette.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app.models import CandidateProfile, ConnectorSetting
from app.services.ai_service import ai_service

@pytest.fixture(scope="module")
def client():
    return TestClient(app)

def test_routes_smoke(client):
    """Characterization test: All main endpoints return HTTP 200."""
    res_dash = client.get("/dashboard")
    assert res_dash.status_code == 200

    res_profile = client.get("/profile")
    assert res_profile.status_code == 200

    res_settings = client.get("/settings")
    assert res_settings.status_code == 200

def test_database_seeded_data():
    """Characterization test: Candidate profile and connectors exist in DB."""
    db = SessionLocal()
    try:
        profile = db.query(CandidateProfile).first()
        assert profile is not None
        assert profile.full_name != ""

        connectors = db.query(ConnectorSetting).all()
        assert len(connectors) > 0
    finally:
        db.close()

def test_ai_matching_heuristic_smoke():
    """Characterization test: AI service heuristic matching runs without error."""
    result = ai_service.score_and_match(
        job_title="Junior Python Data Scientist",
        job_description="Seeking a Python developer with SQL and Machine Learning knowledge.",
        profile_summary="Passionate Python and ML developer.",
        skills_str="Python, SQL, Machine Learning",
        resume_text="Extensive experience in Python, SQL, and data analysis."
    )
    assert "match_score" in result
    assert 0 <= result["match_score"] <= 100
    assert "match_reason" in result
    assert isinstance(result["matching_skills"], list)

