---
name: playwright-automation
description: >-
  Playwright browser automation playbook for ATS application portals (Workday,
  Greenhouse, Lever, Ashby), headed form filling, human-in-the-loop review stops, and anti-bot mitigation.
---

# Playwright Browser Automation & ATS Playbook

Use this skill when developing, refactoring, or executing Playwright browser automation scripts, autofill engines, selector mappings, and multi-step job application wizards.

---

## 1. Ethical Automation & The Structural Review Stop

1. **Non-Negotiable Rule: Zero Blind Submissions**:
   * The automated engine fills personal details, contact info, resumes, work history, and screening answers.
   * **The engine must strictly pause before clicking "Submit" or "Apply"**:
     ```python
     logger.info("Autofill complete. Stopping before submit for candidate review.")
     # Let the user review all filled fields and manually submit the application
     ```
2. **Headed vs Headless Execution**:
   * Use `headless=False` for user-assisted job applications so the candidate sees the browser and can verify all entries before submission.
   * Use `headless=True` only for headless data extraction, health checks, or non-interactive page rendering.

---

## 2. Resilient Selector Strategy

Modern ATS platforms (Workday, Greenhouse, Ashby, Lever) dynamically mutate class names, IDs, and internal component identifiers. Follow this priority order when authoring selector mappings:

1. **Accessible Roles & ARIA Attributes (Highest Priority)**:
   * `page.get_by_role("button", name="Continue")`
   * `page.get_by_label("First Name")`
   * `page.get_by_placeholder("e.g. 555-123-4567")`
2. **Data Attributes**:
   * `[data-automation-id="legalNameSection_firstName"]` (Workday standard)
   * `[data-qa="resume-upload"]`
3. **Normalized Text Selectors**:
   * `button:has-text("Review and Submit")`
4. **Avoid Brittle CSS**:
   * Never use auto-generated CSS paths like `div.css-1r8p4j > button.btn-primary-3`.

---

## 3. Handling Complex ATS Patterns

### A. Resume PDF Upload
Always use `set_input_files` directly on the underlying `input[type="file"]`:
```python
file_input = page.locator('input[type="file"]')
await file_input.set_input_files(str(resume_path))
# Wait for the ATS parsing indicator to settle
await page.wait_for_selector('.upload-complete, [data-automation-id="file-upload-success"]', timeout=10000)
```

### B. Custom Dropdowns & Search Comboboxes
Many ATS platforms (e.g. Workday country/state pickers) don't use standard `<select>` elements:
```python
# 1. Click the custom dropdown trigger
await page.locator('[data-automation-id="country-dropdown"]').click()
# 2. Type into the generated search input
await page.locator('[data-automation-id="search-input"]').fill("India")
await page.keyboard.press("Enter")
```

### C. Canary Prompts & Trap Detection
* Before typing generated cover letters into application fields, run a canary/trap inspection to strip hidden bot honeypots.
* Ensure employer-requested canary keywords (e.g. "Pineapple") are preserved in the text.

---

## 4. Anti-Bot & Fingerprint Hygiene

1. Set a standard realistic viewport size: `viewport={"width": 1280, "height": 800}`.
2. Provide a genuine user-agent string:
   ```python
   user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
   ```
3. Introduce subtle human typing delays when populating high-value fields:
   ```python
   await page.locator("#notes").press_sequentially(cover_letter_text, delay=20)
   ```
