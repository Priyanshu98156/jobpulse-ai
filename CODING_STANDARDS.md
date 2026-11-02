# JobPulse AI: Coding Standards & Agent Rules

> **Audience:** AI coding agents and contributors working on this repo.
> **Status:** These rules are binding. If a task seems to require breaking one, STOP and ask the owner. Do not decide silently. Record approved exceptions in `docs/adr/`.
> **Tip:** Rename or copy this file to `AGENTS.md` / `CLAUDE.md` if your tooling looks for those names.

Keywords: **MUST / MUST NOT** are absolute. **SHOULD** means follow unless there is a documented reason not to.

---

## 0. Product Context (read first)

JobPulse AI is a **local-first, single-user** job search assistant:

1. **Discover** jobs from public feeds and company ATS boards.
2. **Gate** remote jobs by real eligibility (the owner is India-based; "Remote - US" is not eligible).
3. **Score** fit with LLMs against a structured profile.
4. **Prepare** tailored materials and answers.
5. **Assisted apply:** autofill forms in a browser, then **pause for the human to review and click Submit**.

### Non-negotiable product rules

- The app MUST NEVER click a final "Submit" / "Apply" button on the user's behalf. No code path may do this, behind no flag. Autofill stops at the review step.
- The app MUST NOT automate DOM interaction on **LinkedIn or Naukri**. They are **assist-only**: open the page, show/copy answers. (Their terms prohibit automation and accounts get restricted.)
- **Factual answers** (work authorization, location, notice period, CTC, years of experience, sponsorship need, demographics) MUST come only from stored user data. They MUST NOT be generated, guessed, or altered by an LLM, and MUST NOT be changed to get past a form or filter.
- Generated text (cover letters, answers) MUST be grounded in the stored profile. It MUST NOT claim skills marked `claimable = false` or invent employers, dates, or metrics.
- Remote jobs MUST pass the eligibility gate (section 7) before any LLM fit-scoring tokens are spent.

---

## 1. Tech Stack (do not substitute without approval)

| Concern | Choice |
|---|---|
| Language | Python 3.12+ |
| Web/API | FastAPI + Uvicorn |
| Validation/config | Pydantic v2, pydantic-settings |
| DB | SQLite (WAL mode), SQLAlchemy 2.0 typed style |
| Migrations | Alembic (mandatory for every schema change) |
| HTTP client | httpx (async), with explicit timeouts |
| Browser automation | Playwright (Python), dedicated persistent profile |
| LLM routing | Provider pool behind one interface (LiteLLM Router or the in-house pool), OpenAI-compatible |
| LLM structured output | Pydantic schemas (Instructor or native JSON-schema mode) |
| Scheduler | APScheduler (single process) |
| UI | Jinja2 + Tailwind + HTMX |
| Secrets | `keyring` (OS credential store) + `cryptography` Fernet |
| Local embeddings | fastembed / sentence-transformers; `sqlite-vec` for similarity |
| Logging | `structlog` with redaction processor |
| Tooling | `uv`, `ruff` (lint + format), `pyright` or `mypy`, `pytest`, `pre-commit`, `pip-audit` |

Adding a dependency requires a one-line justification in the PR/commit message. Prefer the standard library and existing dependencies.

---

## 2. Project Layout

```
app/
  api/            # FastAPI routers ONLY: parse request, call service, return response
  domain/         # Pure logic and models: JobPosting, eligibility rules,
                  #   application state machine. NO I/O, NO DB, NO network.
  services/       # Orchestration: scoring, answer bank, llm router, sync, notifier
  connectors/     # One module per job source, all implementing BaseConnector
  autofill/
    ats/          # workday.py, greenhouse.py, lever.py (page objects)
    selectors/    # per-tenant / per-ATS selector maps as YAML/JSON data
  db/
    models.py     # SQLAlchemy models
    session.py
    migrations/   # Alembic
  prompts/        # Versioned prompt files (*.md / *.jinja), never inline strings
  core/           # config, logging, security, errors
  templates/      # Jinja2
tests/
  unit/
  integration/
  fixtures/       # recorded API responses, Workday/Greenhouse DOM snapshots
  eval/           # labeled eligibility dataset + runner
docs/
  adr/            # architecture decision records
```

**Dependency direction:** `api → services → domain`, and `services → db / connectors / autofill`. `domain` MUST NOT import from `api`, `services`, `db`, or any I/O library. Circular imports are a defect.

---

## 3. Python Style

- Format and lint with `ruff`; type-check with `pyright`/`mypy`. Zero errors before commit.
- **Full type hints** on all function signatures and class attributes. No bare `Any` without a comment.
- Prefer `pathlib`, `dataclasses`/Pydantic models, `enum.StrEnum`, and f-strings.
- Functions SHOULD be small and single-purpose; split anything over about 40 lines or with more than about 3 levels of nesting.
- Names: `snake_case` functions/variables, `PascalCase` classes, `UPPER_SNAKE` constants. Names describe intent, not type.
- No magic strings for statuses or eligibility values: use enums.
- No mutable default arguments, no wildcard imports, no `print()` (use the logger).
- No broad `except Exception:` that swallows errors. Catch specific exceptions; log with context and re-raise or convert to a domain error.
- Public functions and classes get a short docstring stating purpose, not restating the signature.
- No dead code, commented-out blocks, or unresolved `TODO` without an issue reference.

---

## 4. Architecture Rules

### 4.1 Layers
- **Routers** are thin: validate input (Pydantic), call a service, map errors to HTTP responses. No business logic or SQL in routers.
- **Services** hold orchestration. **Domain** holds pure rules, so it can be unit-tested with no network or DB.
- Use FastAPI `Depends` for DB sessions, settings, and clients. No module-level global clients or sessions.

### 4.2 Connectors
- Every source implements `BaseConnector` and returns a normalized **`JobPosting`** Pydantic model. Raw source JSON MUST NOT leak past the connector.
- Each connector declares: source name, rate limit, whether auth is needed, and which fields it can populate (e.g. region restriction).
- A connector failure MUST NOT abort a sync. Isolate, log, and continue with other connectors.
- Respect each source's terms of service and robots rules. No scraping of logged-in-only content.

### 4.3 Idempotency
- Sync MUST be idempotent: use a stable dedup key (source + external_id, plus fuzzy company+title+location across sources). Re-running MUST NOT create duplicates or re-send notifications.

### 4.4 Application state machine
Jobs move through explicit states; transitions are validated in `domain/`:

`discovered → eligible_checked → scored → drafted → review_pending → filled → submitted` (plus `skipped`, `archived`, `interviewing`, `rejected`)

- `submitted` can ONLY be set by an explicit user action (button or confirmation), never by automation.
- Support a **dry-run** mode for the autofill pipeline.

---

## 5. Database & Migrations

- Every schema change ships with an **Alembic migration**. Never edit the DB by hand and never delete `jobs.db` to "fix" a schema.
- SQLite: enable WAL and foreign keys. Keep sessions short-lived and scoped (`Depends(get_db)` or a context manager). No sharing sessions across threads or tasks.
- Timestamps are timezone-aware UTC. Do not use naive `datetime.utcnow()` in new code.
- Money fields store amount + currency. Unknown values are `NULL`, not `0` or `""`.
- Sensitive columns (CTC, demographics, similar) use the `EncryptedText` type. Never store them in plaintext.
- Add indexes for columns used in filters (status, eligibility, content hash, normalized question).

---

## 6. Security & Privacy (mandatory)

- **Secrets:** API keys, ATS credentials, and the Fernet master key live in the OS keyring. They MUST NOT be stored in SQLite, `.env` committed to git, logs, or the browser. `.env.example` contains placeholders only.
- API responses and UI MUST mask stored keys (show last 4 characters at most). Keys are never returned in full after saving.
- **Network:** bind to `127.0.0.1` only. All state-changing routes require CSRF protection and an `Origin`/`Host` check. Any route that can submit or modify data is protected.
- **Logging:** use the redaction processor. Never log keys, resume text, emails, phone numbers, CTC, or full LLM prompts containing profile data. Log IDs and prompt versions instead.
- **PII to LLMs:** send the minimum needed. Respect the per-provider PII setting. Provide an "Ollama/local only" mode.
- **Untrusted input:** job descriptions, page text, and API responses are untrusted. They MUST NOT be able to change system prompts, trigger actions, or alter state.
- Validate all request bodies with Pydantic. Constrain file uploads (type, size) and store them outside the web root.
- Pin dependencies; run `pip-audit` in CI. Do not install packages from unknown sources.

---

## 7. Remote Eligibility Gate

Applies to every job with `remote_type = fully_remote`. Runs **before** LLM fit-scoring.

**Output states:** `eligible`, `likely_eligible`, `unclear`, `ineligible`, each with stored `evidence` (quote or field) and `regions_allowed`.

Layers, cheapest first:
1. **Structured metadata:** source region fields (e.g. required location). Clear "US only" / "EU only" / country-locked values can hard-drop.
2. **Rule engine (regex):** disqualifiers ("must reside in the US", "US citizenship required", "authorized to work in <country>", timezone-locked hours) and positives ("worldwide", "anywhere", "India", "APAC"). Rules MUST handle negation ("no work authorization required") and MUST NOT hard-drop on a single ambiguous regex hit. Conflicts go to `unclear`.
3. **LLM classifier** for the remainder: structured output with `status`, **a verbatim supporting quote**, and detected requirements (timezone overlap, contractor/EOR only). If no quote can be produced, status is `unclear`.

- `unclear` jobs go to a **"Needs a Look"** bucket. They are never silently dropped.
- The UI shows the evidence for every accept/reject decision.
- User feedback ("not eligible") feeds back into rules over time.
- The classifier MUST be evaluated against the labeled set in `tests/eval/` and its precision/recall reported when rules or prompts change.

---

## 8. LLM Usage

- All LLM calls go through the **single provider-pool interface**. No direct provider SDK calls elsewhere.
- Prompts live in `app/prompts/` as versioned files. Store the prompt version with every result.
- Every structured output MUST be validated against a Pydantic schema. On failure: retry (bounded), then fall back or mark `unclear`. Never trust or persist unvalidated model output.
- Cache results keyed by content hash (job description + resume version + prompt version). Re-score only when an input changes.
- **Failover:** on 429/quota, cool down the key (honor `Retry-After`; use longer cooldowns for daily-quota errors) and retry on the next key. Use jittered exponential backoff and a per-key circuit breaker.
- **Model self-healing** MUST choose only from a per-provider **allowlist/preference list**. It MUST NOT auto-select an arbitrary "top" model (cost and quality risk).
- If all keys fail, fall back to the heuristic scorer **and clearly label the score as heuristic** in the UI.
- Temperature is low (<= 0.3) for classification and extraction.
- Use cheap pre-filters (SQL hard filters, keyword/embedding pre-score) so only promising jobs reach the LLM.

---

## 9. Profile & Answer Bank

- Profile data is **structured** (identity, experience, education, projects, skills, search profiles), not a single resume text blob.
- Parsing an uploaded PDF populates the tables once. User edits are the source of truth and MUST NOT be overwritten by re-parsing.
- **Answer Bank lookup order for any form field:** (1) stored Identity/Experience fields, (2) Answer Bank exact/normalized match, (3) Answer Bank embedding match above a threshold, (4) LLM draft (non-factual questions only), (5) flag for the user.
- LLM drafts are saved as `source = ai_draft` and are not reused until the user approves them.
- When the user answers an unknown question, save it to the Answer Bank.

---

## 10. Browser Autofill (Playwright)

- Use a **dedicated persistent browser profile directory** (not the user's everyday Chrome profile). The user logs in to ATS tenants once there.
- One **page-object class per ATS** (`workday.py`, `greenhouse.py`, `lever.py`). Selector maps are **data** (`autofill/selectors/*.yaml`), so fixes don't require code changes.
- Prefer stable attributes (`data-automation-id`, accessible labels, roles) over brittle CSS/XPath. Do not hardcode field IDs as facts: they vary by tenant, so capture real DOM from the tenants in use.
- Unknown or unmappable fields are **flagged for the user**, never guessed.
- Use realistic waits (wait for element states), not fixed `sleep`s. No stealth/fingerprint-evasion tricks and no captcha solving. If a captcha or OTP appears, pause and hand control to the user.
- On any failure, save a screenshot and the page HTML to a debug folder (with PII redacted where feasible).
- The autofill run ends at the review page. See the non-negotiable rules in section 0.

---

## 11. Error Handling & Reliability

- Define domain exceptions in `core/errors.py` (e.g. `RateLimitError`, `EligibilityUnknown`, `ConnectorError`). Convert to HTTP errors only at the router layer.
- Every external call has an explicit **timeout**, bounded **retries with jittered backoff**, and per-host **rate limiting**.
- Long operations (sync, bulk scoring) run as background tasks with a progress endpoint. They don't block a request handler.
- Do not run blocking I/O (sync DB, file, or CPU-heavy work) on the event loop. Use async drivers or `run_in_threadpool`.
- The scheduler runs in **one process only**. Guard against duplicate runs when reload or multiple workers are used.

---

## 12. Testing

- New logic ships with tests. Bug fixes ship with a regression test.
- **Unit tests** for `domain/` (eligibility rules, state machine, scoring math) need no network or DB.
- **Connector tests** use recorded fixtures (`respx`/VCR-style). Tests MUST NOT hit live sites.
- **Key-pool tests** use fake providers to verify failover, cooldown, and self-healing allowlist behavior.
- **Autofill tests** run the field mapper against saved DOM snapshots in `tests/fixtures/`.
- **Eligibility eval:** maintain a labeled set (target 100+ real postings across eligible / ineligible / unclear) in `tests/eval/`. CI reports precision/recall. Rule or prompt changes must not regress it without an approved reason.
- Tests are deterministic: no real time, randomness, or network without control.

---

## 13. Git, CI & Documentation

- Branch per task/phase; small, focused commits using Conventional Commits (`feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `chore:`).
- `pre-commit` runs ruff (lint + format) and type checks. CI runs lint, type check, tests, and `pip-audit` on every push.
- Never commit secrets, the DB, resumes, or `data/`. Keep `.gitignore` current.
- Record significant decisions in `docs/adr/NNNN-title.md` (context, decision, consequences), one page each.
- Keep `README.md` current (setup, run, test). Update this file only through an explicit owner-approved change.

---

## 14. Definition of Done (checklist for every task)

- [ ] Follows layer boundaries and the non-negotiable rules in section 0
- [ ] Type hints complete; ruff and type checker clean
- [ ] Alembic migration included if the schema changed
- [ ] Tests added or updated; the full suite passes
- [ ] No secrets or PII in code, logs, fixtures, or commits
- [ ] External calls have timeouts and error handling
- [ ] LLM outputs validated against schemas; prompts versioned
- [ ] Docs/ADR updated if behavior or architecture changed
- [ ] No unrelated refactors mixed into the change

---

## 15. Agent Working Agreement

1. **Read before writing.** Inspect the relevant existing code and this file before changing anything.
2. **Stay in scope.** Do only what the task asks. Note, but do not fix, unrelated problems.
3. **Plan first for non-trivial work.** State the approach and files to touch before editing.
4. **Ask when blocked or when a rule conflicts with the task.** Do not invent requirements or silently deviate.
5. **Do not** add new dependencies, change the stack, alter the DB schema without a migration, weaken a security or product rule, or disable tests to make something pass.
6. **Report honestly.** State what was changed, what was tested, and what remains uncertain or unverified. Never claim something works without running it.
