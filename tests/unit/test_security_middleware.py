from starlette.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_security_headers_present():
    response = client.get("/dashboard", headers={"Host": "127.0.0.1:8000"})
    assert response.status_code == 200
    assert response.headers.get("X-Content-Type-Options") == "nosniff"
    assert response.headers.get("X-Frame-Options") == "DENY"
    assert response.headers.get("Referrer-Policy") == "same-origin"

def test_untrusted_host_blocked():
    response = client.get("/dashboard", headers={"Host": "evil-phishing-site.com"})
    assert response.status_code == 400
    assert "Invalid Host header" in response.text

def test_cross_origin_state_changing_request_blocked():
    # POST to API endpoint with untrusted Origin should be blocked by security policy
    response = client.post(
        "/api/job/1/status",
        json={"status": "applied"},
        headers={"Host": "127.0.0.1:8000", "Origin": "http://evil-site.com"}
    )
    assert response.status_code == 403
    assert "Cross-Origin request blocked" in response.text
