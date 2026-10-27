import pandas as pd

from hiring_intel.clean import clean_jobs, salary_training_set


def row(**overrides):
    base = dict(
        source="ashby", company="acme", job_id="1", title="ML Engineer",
        department="Eng", location="San Francisco", description="Python",
        posted_at="2026-10-20T00:00:00Z", salary_min=180000.0, salary_max=240000.0,
        salary_currency="USD", salary_interval="1 YEAR",
    )
    base.update(overrides)
    return base


def test_salary_filters_match_real_problems():
    df = clean_jobs(pd.DataFrame([
        row(job_id="good"),
        row(job_id="lever", salary_interval="per-year-salary"),        # Lever spelling, keep
        row(job_id="sek", salary_currency="SEK", salary_min=770000, salary_max=1060000),
        row(job_id="hourly", salary_interval="1 HOUR", salary_min=57, salary_max=70),
        row(job_id="intern", title="Software Engineering Intern",
            salary_interval="1 MONTH", salary_min=12500, salary_max=12500),
        row(job_id="contract", title="Recruiting Coordinator - Contract"),
        row(job_id="nosalary", salary_min=None, salary_max=None,
            salary_currency=None, salary_interval=None),
    ]))
    train, dropped = salary_training_set(df)

    assert sorted(train["job_id"]) == ["good", "lever"]
    assert dropped["no salary"] == 1 and dropped["not USD"] == 1
    assert train.loc[0, "salary_mid"] == 210000


def test_clean_jobs_dedupes_and_parses_dates():
    df = clean_jobs(pd.DataFrame([row(), row(), row(job_id="2", posted_at="not a date")]))
    assert len(df) == 2
    assert df["posted_at"].isna().sum() == 1