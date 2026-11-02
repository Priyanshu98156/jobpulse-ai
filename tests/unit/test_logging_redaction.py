from app.core.logging import redact_pii_processor

def test_redact_sensitive_keys():
    event_dict = {
        "event": "processing_request",
        "api_key": "sk-1234567890abcdef",
        "user_secret": "my_top_secret_token",
        "resume_text": "Experienced Python Developer with 5 years in AWS...",
        "status": "success"
    }
    redacted = redact_pii_processor(None, "info", event_dict)
    assert redacted["api_key"] == "[REDACTED]"
    assert redacted["user_secret"] == "[REDACTED]"
    assert redacted["resume_text"] == "[REDACTED]"
    assert redacted["status"] == "success"

def test_redact_embedded_emails_and_phones():
    event_dict = {
        "event": "User logged in with email john.doe@company.org and phone +1-555-123-4567"
    }
    redacted = redact_pii_processor(None, "info", event_dict)
    assert "john.doe@company.org" not in redacted["event"]
    assert "[EMAIL_REDACTED]" in redacted["event"]
    assert "+1-555-123-4567" not in redacted["event"]
    assert "[PHONE_REDACTED]" in redacted["event"]

