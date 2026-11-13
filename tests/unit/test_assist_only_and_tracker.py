import pytest
from starlette.testclient import TestClient
from app.main import app
from app.db.session import SessionLocal
from app.db.models import Job, ApplicationPackage, AnswerBank

client = TestClient(app)

def test_workday_apply_initiates_assisted_browser_with_stop():
    db = SessionLocal()
    try:
        job = Job(
            external_id="workday-test-1",
            platform="workday",
            title="Senior ML Engineer",
            company="Salesforce",
            url="https://salesforce.wd1.myworkdayjobs.com/en-US/jobs/123",
            status="discovered"
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        response = client.post(
            f"/api/job/{job.id}/apply",
            json={"cover_letter": "I am thrilled to apply..."},
            headers={"Host": "127.0.0.1:8000"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["submission_method"] == "assisted_browser"
        assert "Structural stop is active" in data["message"]

        db.delete(job)
        db.commit()
    finally:
        db.close()

def test_linkedin_assist_only_mode():
    db = SessionLocal()
    try:
        job = Job(
            external_id="li-test-1",
            platform="linkedin",
            title="Python Developer",
            company="Microsoft",
            url="https://www.linkedin.com/jobs/view/999888",
            status="discovered"
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        response = client.post(
            f"/api/job/{job.id}/apply",
            json={},
            headers={"Host": "127.0.0.1:8000"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["submission_method"] == "clipboard_assist"
        assert "copied to clipboard" in data["message"].lower() or "portal" in data["message"].lower()
        assert "answers" in data

        # Verify honest status tracking: job transitions to 'applying', not prematurely 'applied'
        db.refresh(job)
        assert job.status == "applying"

        # Explicit candidate confirmation moves it to 'applied'
        res_confirm = client.post(
            f"/api/job/{job.id}/status",
            json={"status": "applied"},
            headers={"Host": "127.0.0.1:8000"}
        )
        assert res_confirm.status_code == 200
        db.refresh(job)
        assert job.status == "applied"

        db.delete(job)
        db.commit()
    finally:
        db.close()

def test_answer_bank_crud_endpoints():
    # 1. Create Answer
    res_create = client.post(
        "/api/answers",
        json={
            "question_pattern": "notice period",
            "answer_text": "30 Days maximum",
            "category": "legal",
            "is_factual": True
        },
        headers={"Host": "127.0.0.1:8000"}
    )
    assert res_create.status_code == 200
    ans_id = res_create.json()["id"]

    # 2. List Answers
    res_list = client.get("/api/answers", headers={"Host": "127.0.0.1:8000"})
    assert res_list.status_code == 200
    items = res_list.json()
    assert any(a["id"] == ans_id and a["answer_text"] == "30 Days maximum" for a in items)

    # 3. Delete Answer
    res_del = client.delete(f"/api/answers/{ans_id}", headers={"Host": "127.0.0.1:8000"})
    assert res_del.status_code == 200

