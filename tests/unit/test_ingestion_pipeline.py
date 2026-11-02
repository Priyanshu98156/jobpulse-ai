import pytest
from app.db.session import SessionLocal
from app.db.models import Job, ConnectorSetting
from app.connectors.manager import ConnectorManager

@pytest.mark.anyio
async def test_ingestion_eligibility_gating_and_deduplication():
    db = SessionLocal()
    manager = ConnectorManager()

    # Mock connector returning 3 distinct job cases
    mock_jobs = [
        {
            "external_id": "job-ineligible-1",
            "platform": "mock_platform",
            "title": "Defense Analyst",
            "company": "Lockheed",
            "location": "US Remote",
            "job_type": "Full-time",
            "salary_range": "$120k",
            "url": "https://example.com/job1",
            "description": "Active Secret clearance and US citizenship required."
        },
        {
            "external_id": "job-eligible-1",
            "platform": "mock_platform",
            "title": "Senior Python Engineer",
            "company": "Global Distributed Co",
            "location": "Remote - Worldwide",
            "job_type": "Full-time",
            "salary_range": "$90k - $120k",
            "url": "https://example.com/job2",
            "description": "Work from anywhere in the world. Python and FastAPI stack."
        },
        {
            "external_id": "job-unclear-1",
            "platform": "mock_platform",
            "title": "Cloud Architect",
            "company": "Apex Global",
            "location": "Remote",
            "job_type": "Contract",
            "salary_range": "$100k",
            "url": "https://example.com/job3",
            "description": "US work authorization required without sponsorship or international contractor B2B considered."
        }
    ]

    try:
        # Override connector with mock
        class MockConnector:
            has_submit_api = False
            async def fetch_jobs(self, query=None, location=None, limit=15):
                return mock_jobs

        manager.connectors = {"mock_platform": MockConnector()}

        # Run sync
        summary = await manager.sync_all_jobs(db, limit_per_connector=10)
        assert summary["total_fetched"] == 3
        assert summary["new_jobs_added"] >= 1

        # Check job 1: ineligibility dropped to skipped
        j1 = db.query(Job).filter(Job.external_id == "job-ineligible-1").first()
        assert j1 is not None
        assert j1.eligibility_status == "ineligible"
        assert j1.status == "skipped"

        # Check job 2: eligible
        j2 = db.query(Job).filter(Job.external_id == "job-eligible-1").first()
        assert j2 is not None
        assert j2.eligibility_status == "eligible"
        assert j2.status in ("review_pending", "discovered")
        assert j2.match_score is not None

        # Check job 3: unclear / conflicting signals -> Needs a Look
        j3 = db.query(Job).filter(Job.external_id == "job-unclear-1").first()
        assert j3 is not None
        assert j3.eligibility_status == "unclear"
        assert j3.status == "review_pending"

        # Test deduplication: running sync again must add 0 jobs
        summary_repeat = await manager.sync_all_jobs(db, limit_per_connector=10)
        assert summary_repeat["new_jobs_added"] == 0

        # Clean up
        db.delete(j1)
        db.delete(j2)
        db.delete(j3)
        db.commit()
    finally:
        db.close()
