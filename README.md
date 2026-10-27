# SF Hiring Intelligence

A live system that tracks what Bay Area startups are hiring for, predicts salary ranges from job descriptions, and shows candidates which skills they're missing for a role.

## Problem statement

Job seekers and founders in the Bay Area are both guessing.

- **Candidates** don't know what a role should pay, which skills actually matter for it, or how their resume compares.
- **Founders and recruiters** at early-stage startups don't know what similar companies pay for a role, or which skills are getting harder to hire for.

The data to answer these questions is public. Startups post jobs on hiring platforms (Ashby, Greenhouse, Lever), and California law requires a pay range on job postings. But the data is scattered across hundreds of career pages, written in free text, and changes every day.

**This project turns that scattered data into answers:**

1. **Salary prediction** — paste a job description, get a predicted salary range (trained on postings that list real pay ranges).
2. **Skill demand** — which skills show up most in Bay Area AI/ML/data roles, and how that changes week to week.
3. **Role clustering** — group postings by the skills they really need, not by job title (a "Forward Deployed Engineer" at one company may be an "AI Engineer" at another).
4. **Resume gap check** — compare a resume against a posting and list missing skills.

## Success criteria

- At least 3,000 postings from 100+ Bay Area companies, refreshed daily
- Salary model beats a "median salary for this job title" baseline on mean absolute error
- Public URL anyone can try, deployed automatically on every push to `main`
- Data refresh and model retrain run on a schedule without manual steps

## Architecture

```
Ashby / Greenhouse / Lever public APIs
        │  (daily scheduled job)
        ▼
  collect.py ──► raw JSON snapshots ──► normalized table (Postgres)
                                              │
                          cleaning + skill extraction + features
                                              │
                         model training (tracked in MLflow)
                                              │
                         FastAPI service  ◄── trained model
                                              │
                             Web frontend (public URL)
                                              │
                          drift + data quality monitoring
```

## Stack

Python, pandas, Postgres, scikit-learn / XGBoost, MLflow, FastAPI, Streamlit (or Next.js), Docker, GitHub Actions, GCP Cloud Run, Evidently.

## Data sources

All three are official, public, no-login APIs that power companies' own career pages:

| Source | Endpoint |
|---|---|
| Ashby | `https://api.ashbyhq.com/posting-api/job-board/{board}?includeCompensation=true` |
| Greenhouse | `https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true` |
| Lever | `https://api.lever.co/v0/postings/{site}?mode=json` |

The collector waits 1 second between requests and identifies itself with a clear User-Agent.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Collect postings for every company in config/companies.yaml
python -m hiring_intel.collect

# Find out which hiring platform a company uses
python -m hiring_intel.collect --discover vercel replit modal

# Run tests
pytest
```

Output:
- `data/raw/<date>/<source>__<company>.json` — untouched API responses (so we can re-process later)
- `data/processed/jobs_<date>.csv` — one clean row per posting

## Roadmap

- [x] Day 1–3: problem statement, collector, first dataset
- [ ] Day 4–7: cleaning, skill extraction, baseline + real salary model, MLflow
- [ ] Day 8–10: FastAPI + frontend, Docker, docker-compose with Postgres
- [ ] Day 11–14: GitHub Actions CI/CD, deploy to Cloud Run, scheduled refresh
- [ ] Day 15–18: drift monitoring, demo video, write-up
