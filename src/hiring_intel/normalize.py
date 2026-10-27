"""Turn raw API responses from each hiring platform into one common row format.

Every function here is pure (no network, no files) so it's easy to test.
"""
from __future__ import annotations

import html
import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup

# One schema for every source. Keep this list in sync with the tests.
COLUMNS = [
    "source", "company", "job_id", "title", "department", "location",
    "is_remote", "is_bay_area", "employment_type", "posted_at", "url",
    "description", "salary_min", "salary_max", "salary_currency",
    "salary_interval", "salary_source",
]

BAY_AREA_TERMS = [
    "san francisco", "sf,", "sf ", "bay area", "oakland", "berkeley",
    "palo alto", "mountain view", "menlo park", "sunnyvale", "san jose",
    "redwood city", "san mateo", "santa clara", "cupertino", "emeryville",
    "south san francisco", "foster city", "burlingame", "los altos",
]


def is_bay_area(location: str | None) -> bool:
    if not location:
        return False
    loc = f"{location.lower()} "
    return any(term in loc for term in BAY_AREA_TERMS) or loc.strip() == "sf"


def html_to_text(raw: str | None) -> str:
    """Greenhouse sends HTML that is itself HTML-escaped, so unescape first."""
    if not raw:
        return ""
    text = BeautifulSoup(html.unescape(raw), "html.parser").get_text(" ")
    return re.sub(r"\s+", " ", text).strip()


# ---------- salary parsing from free text ----------

_MONEY = r"\$\s?(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s?([kK])?"
_RANGE = re.compile(_MONEY + r"\s*(?:-|–|—|to)\s*" + _MONEY)


def _to_number(digits: str, k: str | None) -> float:
    value = float(digits.replace(",", ""))
    return value * 1000 if k else value


def parse_salary_text(text: str | None) -> tuple[float | None, float | None]:
    """Find the first yearly USD range like '$150,000 - $200,000' or '$150K–$200K'.

    Ranges below $20k are skipped since they're usually hourly rates or bonuses.
    """
    if not text:
        return None, None
    for match in _RANGE.finditer(text):
        low = _to_number(match.group(1), match.group(2))
        high = _to_number(match.group(3), match.group(4))
        if low >= 20_000 and high >= low and high <= 2_000_000:
            return low, high
    return None, None


def _iso_from_ms(ms: int | None) -> str | None:
    if ms is None:
        return None
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()


def _empty_row(source: str, company: str) -> dict:
    row = dict.fromkeys(COLUMNS)
    row.update(source=source, company=company, is_remote=False, is_bay_area=False)
    return row


# ---------- Ashby ----------

def normalize_ashby(payload: dict, company: str) -> list[dict]:
    rows = []
    for job in payload.get("jobs", []):
        if job.get("isListed") is False:
            continue
        row = _empty_row("ashby", company)
        locations = [job.get("location")] + [
            loc.get("location") for loc in job.get("secondaryLocations") or []
        ]
        location = "; ".join(l for l in locations if l)
        row.update(
            job_id=str(job.get("id")),
            title=job.get("title"),
            department=job.get("department") or job.get("team"),
            location=location,
            is_remote=bool(job.get("isRemote")) or job.get("workplaceType") == "Remote",
            is_bay_area=is_bay_area(location),
            employment_type=job.get("employmentType"),
            posted_at=job.get("publishedAt"),
            url=job.get("jobUrl"),
            description=job.get("descriptionPlain") or html_to_text(job.get("descriptionHtml")),
        )
        # Structured salary first, then fall back to the description text.
        for part in (job.get("compensation") or {}).get("summaryComponents") or []:
            if part.get("compensationType") == "Salary" and part.get("minValue"):
                row.update(
                    salary_min=float(part["minValue"]),
                    salary_max=float(part.get("maxValue") or part["minValue"]),
                    salary_currency=part.get("currencyCode"),
                    salary_interval=part.get("interval"),
                    salary_source="structured",
                )
                break
        if row["salary_min"] is None:
            _fill_from_text(row)
        rows.append(row)
    return rows


# ---------- Greenhouse ----------

def normalize_greenhouse(payload: dict, company: str) -> list[dict]:
    rows = []
    for job in payload.get("jobs", []):
        row = _empty_row("greenhouse", company)
        location = (job.get("location") or {}).get("name") or ""
        departments = [d.get("name") for d in job.get("departments") or [] if d.get("name")]
        row.update(
            job_id=str(job.get("id")),
            title=job.get("title"),
            department=", ".join(departments) or None,
            location=location,
            is_remote="remote" in location.lower(),
            is_bay_area=is_bay_area(location),
            posted_at=job.get("first_published") or job.get("updated_at"),
            url=job.get("absolute_url"),
            description=html_to_text(job.get("content")),
        )
        _fill_from_text(row)
        rows.append(row)
    return rows


# ---------- Lever ----------

def normalize_lever(payload: list, company: str) -> list[dict]:
    rows = []
    for job in payload or []:
        row = _empty_row("lever", company)
        cats = job.get("categories") or {}
        location = cats.get("location") or "; ".join(cats.get("allLocations") or [])
        sections = [job.get("descriptionPlain") or ""]
        for block in job.get("lists") or []:
            sections.append(f"{block.get('text', '')}: {html_to_text(block.get('content'))}")
        sections.append(job.get("additionalPlain") or "")
        row.update(
            job_id=str(job.get("id")),
            title=job.get("text"),
            department=cats.get("department") or cats.get("team"),
            location=location,
            is_remote=job.get("workplaceType") == "remote" or "remote" in location.lower(),
            is_bay_area=is_bay_area(location),
            employment_type=cats.get("commitment"),
            posted_at=_iso_from_ms(job.get("createdAt")),
            url=job.get("hostedUrl"),
            description=re.sub(r"\s+", " ", " ".join(sections)).strip(),
        )
        salary = job.get("salaryRange") or {}
        if salary.get("min"):
            row.update(
                salary_min=float(salary["min"]),
                salary_max=float(salary.get("max") or salary["min"]),
                salary_currency=salary.get("currency"),
                salary_interval=salary.get("interval"),
                salary_source="structured",
            )
        else:
            _fill_from_text(row)
        rows.append(row)
    return rows


def _fill_from_text(row: dict) -> None:
    low, high = parse_salary_text(row.get("description"))
    if low is not None:
        row.update(
            salary_min=low, salary_max=high, salary_currency="USD",
            salary_interval="1 YEAR", salary_source="text",
        )


NORMALIZERS = {
    "ashby": normalize_ashby,
    "greenhouse": normalize_greenhouse,
    "lever": normalize_lever,
}
