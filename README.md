# TalentScope — Advanced Job Market Intelligence & Recruitment Portal

A full-stack academic project using **Flask, MySQL, Bootstrap, and Chart.js**. It extends a simple job listing site into a role-based recruitment portal with analytics, job applications, bookmarks, profile management, filters, and CSV export.

## Features
- Secure registration and sign-in with hashed passwords and CSRF protection
- Admin dashboard with job/company/user/application KPIs and interactive charts
- Job search with keyword, location, industry, skill, salary filters, sorting and pagination
- Job details, bookmark/save, apply with optional cover note, application tracking
- User profile with headline, phone, skills and bio
- Admin job CRUD and applicant status management
- Export job data to CSV
- Responsive Bootstrap UI

## Existing database compatibility
The app expects your existing `job_market_db` to contain `COMPANY(company_id, company_name, industry)`, `JOB(job_id, company_id, job_title, location, salary)` and `SKILL(skill_id, job_id, skill_name)`. It does **not** drop or recreate those tables. On startup it creates only app-specific tables (`users`, `job_applications`, `saved_jobs`, `user_profiles`).

If you do not have the original tables, run `database.sql` in MySQL Workbench after checking the schema. If they already exist with data, do not drop them or rerun destructive SQL.

## Setup (Windows + VS Code)
1. Extract the ZIP and open this folder in VS Code.
2. Copy `.env.example` to a new file named `.env`.
3. Set `DB_PASSWORD`, a long random `FLASK_SECRET_KEY`, `ADMIN_EMAIL`, and a strong `ADMIN_PASSWORD` in `.env`.
4. Start the MySQL80 service and make sure `job_market_db` is available.
5. In VS Code terminal:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python app.py
```

6. Open `http://127.0.0.1:5000`.
7. Sign in with the admin email/password configured in `.env`. The first run seeds that admin if the email does not already exist.
8. Register a separate user account to test the user experience.

## Important notes
- Never commit `.env` to GitHub. `.gitignore` excludes it.
- The admin role is not selectable during registration; only the configured admin is seeded automatically.
- The project uses manual `MAX(id)+1` IDs for `JOB` and `SKILL` to support the original academic schema. This is okay for a small local demo but should be migrated to `AUTO_INCREMENT` with proper transactions for multi-user production use.
- `debug` is off by default. Do not deploy this demo with debug mode enabled.
- Bootstrap and Chart.js are loaded from CDNs, so an internet connection is needed for those visual assets.

## Suggested demo sequence
1. Sign in as admin → inspect analytics → add/edit a job → export CSV.
2. Register as a user → search/filter jobs → save a role → apply with a cover note.
3. Sign in as admin → open Applicants → change the application's status.
4. Sign back in as user → open My Applications and confirm the status update.
