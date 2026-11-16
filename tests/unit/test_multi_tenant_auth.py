import pytest
from starlette.testclient import TestClient
from app.main import app
from app.db.session import SessionLocal
from app.db.models import User, CandidateProfile

client = TestClient(app, base_url="http://127.0.0.1:8000")


def clean_test_user(email: str):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if user:
            db.query(CandidateProfile).filter(CandidateProfile.user_id == user.id).delete()
            db.delete(user)
            db.commit()
    finally:
        db.close()


def test_auth_signup_validation_and_success():
    test_email = "tester_multitenant_1@jobpulse.ai"
    clean_test_user(test_email)

    try:
        # 1. Test short password rejection
        resp_short = client.post("/api/auth/signup", json={
            "email": test_email,
            "password": "short",
            "full_name": "Test Candidate"
        })
        assert resp_short.status_code == 400
        assert "at least 8 characters" in resp_short.json()["detail"]

        # 2. Test successful signup
        resp_success = client.post("/api/auth/signup", json={
            "email": test_email,
            "password": "StrongPassword!2026",
            "full_name": "Priyanshu Tester"
        })
        assert resp_success.status_code == 200
        data = resp_success.json()
        assert data["status"] == "success"
        assert data["user"]["email"] == test_email
        assert data["user"]["full_name"] == "Priyanshu Tester"
        assert "access_token" in resp_success.cookies

        # Verify candidate profile was automatically provisioned
        db = SessionLocal()
        user_in_db = db.query(User).filter(User.email == test_email).first()
        assert user_in_db is not None
        assert user_in_db.hashed_password != "StrongPassword!2026"
        assert user_in_db.hashed_password.startswith("$2b$") or user_in_db.hashed_password.startswith("$2a$")
        profile_in_db = db.query(CandidateProfile).filter(CandidateProfile.user_id == user_in_db.id).first()
        assert profile_in_db is not None
        db.close()

        # 3. Test duplicate email rejection
        resp_dup = client.post("/api/auth/signup", json={
            "email": test_email,
            "password": "AnotherPassword!2026",
            "full_name": "Duplicate Candidate"
        })
        assert resp_dup.status_code == 400
        assert "already exists" in resp_dup.json()["detail"]

    finally:
        clean_test_user(test_email)


def test_auth_login_and_session_lifecycle():
    test_email = "tester_session_2@jobpulse.ai"
    clean_test_user(test_email)

    try:
        # Create user via signup
        signup_resp = client.post("/api/auth/signup", json={
            "email": test_email,
            "password": "SecurePassword!2026",
            "full_name": "Session Candidate"
        })
        assert signup_resp.status_code == 200

        # Create unauthenticated client
        fresh_client = TestClient(app, base_url="http://127.0.0.1:8000")

        # Test unauthenticated /api/auth/me
        me_unauth = fresh_client.get("/api/auth/me")
        assert me_unauth.status_code == 200
        assert me_unauth.json()["authenticated"] is False

        # Test invalid password login
        wrong_login = fresh_client.post("/api/auth/login", json={
            "email": test_email,
            "password": "WrongPassword!2026"
        })
        assert wrong_login.status_code == 401
        assert "Invalid email or password" in wrong_login.json()["detail"]

        # Test correct login
        valid_login = fresh_client.post("/api/auth/login", json={
            "email": test_email,
            "password": "SecurePassword!2026"
        })
        assert valid_login.status_code == 200
        assert "access_token" in valid_login.cookies

        # Test authenticated /api/auth/me using session cookie
        me_auth = fresh_client.get("/api/auth/me")
        assert me_auth.status_code == 200
        me_data = me_auth.json()
        assert me_data["authenticated"] is True
        assert me_data["user"]["email"] == test_email

        # Test logout clears session cookie
        logout_resp = fresh_client.post("/api/auth/logout")
        assert logout_resp.status_code == 200
        
        # Calling /api/auth/me after logout is unauthenticated
        me_after = fresh_client.get("/api/auth/me")
        assert me_after.json()["authenticated"] is False

    finally:
        clean_test_user(test_email)
