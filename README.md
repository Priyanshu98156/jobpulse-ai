# JobPulse AI - Automated Job Finder & 1-Click Application Assistant

An automated, local-first platform designed to conquer job-hunting fatigue. JobPulse AI integrates directly with public job search APIs and ATS platforms (Greenhouse, Lever, Remotive, Arbeitnow, The Muse, Adzuna) to continuously discover matching opportunities, evaluate your fit with Google Gemini, generate tailored application packages, and let you apply in a single click.

---

## ✨ Features

- **Multi-Platform Connector Engine**:
  - **Open Tech/Remote APIs**: Remotive, Arbeitnow, and The Muse (no API keys required).
  - **Direct ATS Connectors**: Greenhouse & Lever (live candidate application endpoints).
  - **Global Job Search**: Adzuna (multi-country search with salary intelligence).
- **Google Gemini Fit & Scoring**:
  - Compares candidate skills, experience, and uploaded master resume against job descriptions.
  - Scores match percentage (0–100%) and provides clear reasoning and matching skills breakdown.
  - Generates custom, high-impact cover letters tailored to every job description.
  - Intelligent local heuristic fallback if API key is not yet set.
- **Semi-Autonomous 1-Click Apply**:
  - High-match roles are automatically queued for review.
  - Preview tailored cover letters, screening answers, and attached master resume PDF.
  - Click **Submit via Direct ATS API** to send your application straight to the employer's ATS endpoint, or use assisted one-click apply for standard job portals with automatic cover-letter clipboard copy.
- **Local Control & Scheduling**:
  - Background scheduler (APScheduler) runs sync routines at your desired interval.
  - Instant on-demand "Fetch Now" button on the dashboard.
  - Native Windows desktop notifications when top matching roles ($\ge$ 80%) are discovered.

---

## 🚀 Quick Start Guide

### 1. Requirements
- Python 3.10+ (Tested on Python 3.12)
- Windows / macOS / Linux

### 2. Setup Virtual Environment & Dependencies
```bash
# In the project directory:
python -m venv .venv
.venv\Scripts\activate   # On Windows
pip install -r requirements.txt
```

### 3. Configure API Credentials (Optional)
Copy `.env.example` to `.env` or configure directly from the web dashboard:
```env
GEMINI_API_KEY=your_gemini_api_key_here
ADZUNA_APP_ID=
ADZUNA_APP_KEY=
```

### 4. Run the Application
```bash
.venv\Scripts\python run.py
```
Open your browser to: **[http://localhost:8000](http://localhost:8000)**

---

## 🧭 How to Use

1. **Candidate Profile (`/profile`)**:
   - Fill in your contact info, target job titles (e.g. *Data Scientist, Machine Learning Engineer*), and core skills.
   - Upload your master resume PDF. JobPulse automatically parses and extracts text for Gemini AI analysis.
2. **Settings (`/settings`)**:
   - Enter your Gemini API key (or use the built-in heuristic matching fallback).
   - Toggle individual platform connectors on/off.
   - Set your automated background sync interval (e.g. every 120 minutes).
3. **Dashboard (`/dashboard`)**:
   - Click **Fetch Now** to search all enabled job connectors in parallel.
   - Filter jobs by status (`Pending Review`, `Applied`, `Interviewing`), role, or match score threshold.
   - Click **1-Click Review & Apply** on any role:
     - Review the Gemini-tailored cover letter (or click *Regenerate with Gemini*).
     - Hit **Confirm & Apply Now** to submit!

