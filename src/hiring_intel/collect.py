"""Collect job postings from Ashby, Greenhouse and Lever public APIs.

Usage:
    python -m hiring_intel.collect                      # collect everything in config/companies.yaml
    python -m hiring_intel.collect --discover vercel    # find which platform a company uses
"""
from __future__ import annotations

import argparse
import json
import logging
import time
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import requests
import yaml

from hiring_intel.normalize import COLUMNS, NORMALIZERS

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config" / "companies.yaml"
DATA = ROOT / "data"

URLS = {
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true",
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true",
    "lever": "https://api.lever.co/v0/postings/{slug}?mode=json",
}

HEADERS = {"User-Agent": "sf-hiring-intel/0.1 (student research project)"}
DELAY_SECONDS = 1.0

log = logging.getLogger("collect")


def fetch(source: str, slug: str, session: requests.Session, retries: int = 3):
    """Return parsed JSON, or None if the company isn't on this platform."""
    url = URLS[source].format(slug=slug)
    for attempt in range(1, retries + 1):
        try:
            resp = session.get(url, headers=HEADERS, timeout=30)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json()  # Lever can sometimes send HTML; .json() raises and we retry
        except (requests.RequestException, ValueError) as err:
            log.warning("%s/%s attempt %d failed: %s", source, slug, attempt, err)
            time.sleep(2 ** attempt)
    return None


def has_jobs(source: str, payload) -> bool:
    if payload is None:
        return False
    if source == "lever":
        return isinstance(payload, list) and len(payload) > 0
    return isinstance(payload, dict) and len(payload.get("jobs", [])) > 0


def discover(slugs: list[str]) -> None:
    session = requests.Session()
    for slug in slugs:
        found = []
        for source in URLS:
            payload = fetch(source, slug, session, retries=1)
            if has_jobs(source, payload):
                count = len(payload) if source == "lever" else len(payload["jobs"])
                found.append(f"{source} ({count} jobs)")
            time.sleep(DELAY_SECONDS)
        print(f"{slug:25s} -> {', '.join(found) or 'not found on Ashby/Greenhouse/Lever'}")


def collect(config_path: Path = CONFIG, out_dir: Path = DATA) -> pd.DataFrame:
    companies = yaml.safe_load(config_path.read_text())
    today = date.today().isoformat()
    raw_dir = out_dir / "raw" / today
    raw_dir.mkdir(parents=True, exist_ok=True)
    collected_at = datetime.now(timezone.utc).isoformat()

    session = requests.Session()
    rows, failures = [], []
    for source, slugs in companies.items():
        for slug in slugs or []:
            payload = fetch(source, slug, session)
            time.sleep(DELAY_SECONDS)
            if payload is None:
                failures.append(f"{source}/{slug}")
                continue
            (raw_dir / f"{source}__{slug}.json").write_text(json.dumps(payload))
            new_rows = NORMALIZERS[source](payload, slug)
            log.info("%-10s %-20s %4d jobs", source, slug, len(new_rows))
            rows.extend(new_rows)

    df = pd.DataFrame(rows, columns=COLUMNS)
    df["collected_at"] = collected_at
    df = df.drop_duplicates(subset=["source", "company", "job_id"])

    processed = out_dir / "processed"
    processed.mkdir(parents=True, exist_ok=True)
    out_file = processed / f"jobs_{today}.csv"
    df.to_csv(out_file, index=False)

    with_salary = df["salary_min"].notna().sum()
    log.info("Saved %d jobs (%d with salary, %d in Bay Area) to %s",
             len(df), with_salary, df["is_bay_area"].sum(), out_file)
    if failures:
        log.warning("No data for: %s", ", ".join(failures))
    return df


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--discover", nargs="+", metavar="SLUG",
                        help="check which platform each company slug uses")
    parser.add_argument("--config", type=Path, default=CONFIG)
    args = parser.parse_args()
    if args.discover:
        discover(args.discover)
    else:
        collect(args.config)


if __name__ == "__main__":
    main()
