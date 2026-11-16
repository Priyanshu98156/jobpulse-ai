import pytest
from app.services.eligibility_service import RemoteEligibilityService
from app.domain.models import EligibilityStatus
from app.services.gmail_service import GmailReaderService

def test_hybrid_office_disqualification_without_sponsorship():
    service = RemoteEligibilityService()
    
    # Abound UK role: London, Hybrid 3 days in office, no sponsorship mentioned
    abound_jd = """
    Python Software Engineer at Abound, London.
    What we offer: Hybrid with 3 days a week in the office. 25 days holiday.
    Build and ship high-quality backend features using Python, Django, Postgres.
    """
    verdict = service.evaluate_deterministic("Python Software Engineer", "London", abound_jd)
    assert verdict is not None
    assert verdict.status == EligibilityStatus.INELIGIBLE
    assert "hybrid with 3 days a week in the office" in verdict.reason.lower()

def test_hybrid_office_eligible_with_explicit_visa_sponsorship():
    service = RemoteEligibilityService()
    
    # London role with explicit visa sponsorship
    sponsored_jd = """
    Senior Python Developer in London.
    Office model: 2 days a week in our London office.
    Benefits: Full international visa sponsorship provided and relocation package offered!
    """
    verdict = service.evaluate_deterministic("Senior Python Developer", "London", sponsored_jd)
    assert verdict is not None
    assert verdict.status == EligibilityStatus.ELIGIBLE
    assert "visa sponsorship" in verdict.reason.lower() or "relocation" in verdict.reason.lower()

def test_gmail_otp_and_magic_link_extraction():
    service = GmailReaderService()
    
    # Case 1: 6-digit numeric OTP in message snippet
    snippet_otp = "Your Workday security code is 849201. Please enter this code within 10 minutes."
    code = service.extract_otp_or_link_from_text(snippet_otp)
    assert code == "849201"
    
    # Case 2: 4-digit PIN
    snippet_4digit = "Your verification PIN is: 9382."
    code_4 = service.extract_otp_or_link_from_text(snippet_4digit)
    assert code_4 == "9382"
    
    # Case 3: Magic login URL
    snippet_link = "Click here to login to your application: https://jobs.lever.co/auth/verify?token=xyz987abc"
    link = service.extract_otp_or_link_from_text(snippet_link)
    assert "https://jobs.lever.co/auth/verify?token=xyz987abc" in link
