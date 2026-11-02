import pytest
from pathlib import Path
from playwright.async_api import async_playwright
from app.autofill.ats.workday import WorkdayAutofillEngine
from app.domain.candidate import CandidateIdentityDomain

MOCK_WORKDAY_HTML = """
<!DOCTYPE html>
<html>
<head><title>Workday Mock Application</title></head>
<body>
    <form id="workday-app">
        <h2>My Information</h2>
        <input data-automation-id="legalNameSection_firstName" name="firstName" placeholder="First Name" />
        <input data-automation-id="legalNameSection_lastName" name="lastName" placeholder="Last Name" />
        <input data-automation-id="email" type="email" placeholder="Email" />
        <input data-automation-id="phone-number" placeholder="Phone Number" />

        <h2>Application Questions</h2>
        <textarea aria-label="years of experience with python" placeholder="Explain your experience"></textarea>
        <input aria-label="require sponsorship" placeholder="Sponsorship need" />

        <h2>Review</h2>
        <button data-automation-id="bottom-navigation-submit-button" id="submit-btn">Submit Application</button>
    </form>
</body>
</html>
"""

@pytest.mark.anyio
async def test_workday_autofill_and_structural_stop(tmp_path):
    # Setup mock html file
    mock_html_file = tmp_path / "mock_workday.html"
    mock_html_file.write_text(MOCK_WORKDAY_HTML, encoding="utf-8")

    candidate = CandidateIdentityDomain(
        full_name="Mahadev Candidate",
        email="mahadev@domain.com",
        phone="+91-9988776655",
        location="India"
    )

    answers = {
        "years of experience with python": "3.5 years in production",
        "require sponsorship": "No sponsorship required"
    }

    engine = WorkdayAutofillEngine()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(f"file:///{str(mock_html_file).replace('\\', '/')}")

        result = await engine.run_assisted_fill(page, candidate=candidate, answers=answers)

        # 1. Assert Contact Details were accurately filled
        first_val = await page.locator('input[data-automation-id="legalNameSection_firstName"]').input_value()
        last_val = await page.locator('input[data-automation-id="legalNameSection_lastName"]').input_value()
        email_val = await page.locator('input[data-automation-id="email"]').input_value()
        phone_val = await page.locator('input[data-automation-id="phone-number"]').input_value()

        assert first_val == "Mahadev"
        assert last_val == "Candidate"
        assert email_val == "mahadev@domain.com"
        assert phone_val == "+91-9988776655"

        # 2. Assert Screening questions were answered from AnswerBank
        exp_val = await page.locator('textarea[aria-label="years of experience with python"]').input_value()
        spons_val = await page.locator('input[aria-label="require sponsorship"]').input_value()
        assert exp_val == "3.5 years in production"
        assert spons_val == "No sponsorship required"

        # 3. Assert Structural Stop was triggered and Submit button was NEVER clicked
        assert result["status"] == "STOP_BEFORE_SUBMIT"
        assert result["at_review_page"] is True
        assert "STRUCTURAL STOP" in result["message"]

        await browser.close()
