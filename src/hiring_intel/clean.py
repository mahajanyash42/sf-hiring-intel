"""Clean the collected jobs and build the salary training set.

Usage:
    python -m hiring_intel.clean                  # uses the newest data/processed/jobs_<date>.csv
    python -m hiring_intel.clean --file data/processed/jobs_2026-10-27.csv
"""
from __future__ import annotations

import argparse
import logging
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
PROCESSED = ROOT / "data" / "processed"
CLEAN = ROOT / "data" / "clean"

# Different platforms spell "per year" differently.
YEARLY = {"1 YEAR", "YEAR", "YEARLY", "ANNUAL", "PER-YEAR-SALARY"}

# Interns and contractors are paid on a different scale; keep them out of the salary model.
EXCLUDE_TITLE = re.compile(r"\b(?:intern|internship|co-?op|contract|contractor|temp)\b", re.I)

# Anything outside this range is almost surely a parsing mistake.
MIN_SALARY, MAX_SALARY = 30_000, 1_500_000

log = logging.getLogger("clean")


def clean_jobs(df: pd.DataFrame) -> pd.DataFrame:
    """General cleaning for every job, with or without salary."""
    df = df.copy()
    for col in ["title", "department", "location", "description"]:
        df[col] = df[col].astype("string").str.strip()
    df["posted_at"] = pd.to_datetime(df["posted_at"], errors="coerce", utc=True)
    df["salary_interval"] = df["salary_interval"].astype("string").str.upper().str.strip()
    df["salary_currency"] = df["salary_currency"].astype("string").str.upper().str.strip()
    df = df.dropna(subset=["title"])
    df = df.drop_duplicates(subset=["source", "company", "job_id"])
    return df.reset_index(drop=True)


def salary_training_set(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Keep only rows we can trust as US yearly salaries for full-time roles.

    Returns the filtered table plus a count of rows dropped at each step,
    so we can see (and report) exactly where data went.
    """
    dropped = {}

    def keep(mask, reason):
        nonlocal df
        dropped[reason] = int((~mask).sum())
        df = df[mask]

    keep(df["salary_min"].notna(), "no salary")
    keep(df["salary_currency"] == "USD", "not USD")
    keep(df["salary_interval"].isin(YEARLY), "not yearly")
    keep(~df["title"].str.contains(EXCLUDE_TITLE, na=False), "intern/contract")
    keep(df["salary_max"] >= df["salary_min"], "max below min")
    keep(df["salary_min"].between(MIN_SALARY, MAX_SALARY)
         & df["salary_max"].between(MIN_SALARY, MAX_SALARY), "out of range")

    df = df.copy()
    df["salary_mid"] = (df["salary_min"] + df["salary_max"]) / 2
    df["salary_spread"] = df["salary_max"] - df["salary_min"]
    return df.reset_index(drop=True), dropped


def newest_file() -> Path:
    files = sorted(PROCESSED.glob("jobs_*.csv"))
    if not files:
        raise SystemExit("No data/processed/jobs_*.csv found. Run the collector first.")
    return files[-1]


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", type=Path, help="processed CSV to clean (default: newest)")
    args = parser.parse_args()

    src = args.file or newest_file()
    jobs = clean_jobs(pd.read_csv(src))
    train, dropped = salary_training_set(jobs)

    CLEAN.mkdir(parents=True, exist_ok=True)
    stamp = src.stem.replace("jobs_", "")
    jobs.to_csv(CLEAN / f"jobs_{stamp}.csv", index=False)
    train.to_csv(CLEAN / f"salary_train_{stamp}.csv", index=False)

    log.info("All jobs: %d", len(jobs))
    for reason, n in dropped.items():
        log.info("  dropped %-16s %5d", reason, n)
    median = train["salary_mid"].median() if len(train) else 0
    log.info("Salary training rows: %d (median midpoint $%s)", len(train), f"{median:,.0f}")


if __name__ == "__main__":
    main()