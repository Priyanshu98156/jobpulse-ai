import pytest
from app.connectors.himalayas import HimalayasConnector

@pytest.mark.anyio
async def test_himalayas_connector_fetch(respx_mock):
    connector = HimalayasConnector()
    mock_payload = {
        "jobs": [
            {
                "guid": "test-guid-123",
                "title": "Staff Backend Engineer",
                "companyName": "TechCorp Global",
                "employmentType": "Full-time",
                "minSalary": 120000,
                "maxSalary": 160000,
                "currency": "USD",
                "locationRestrictions": ["Worldwide"],
                "description": "Python, FastAPI, and Go microservices backend.",
                "applicationLink": "https://himalayas.app/jobs/test-guid-123",
                "pubDate": 1710000000
            }
        ]
    }
    respx_mock.get("https://himalayas.app/jobs/api").respond(200, json=mock_payload)

    jobs = await connector.fetch_jobs(limit=10)
    assert len(jobs) == 1
    job = jobs[0]
    assert job["external_id"] == "himalayas_test-guid-123"
    assert job["title"] == "Staff Backend Engineer"
    assert job["company"] == "TechCorp Global"
    assert job["location"] == "Worldwide"
    assert "120000" in job["salary_range"]
