import json
from pathlib import Path

import pytest

from hiring_intel.normalize import (
    COLUMNS, is_bay_area, normalize_ashby, normalize_greenhouse,
    normalize_lever, parse_salary_text,
)

FIXTURES = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize("text,expected", [
    ("Base pay $150,000 - $190,000 per year", (150000, 190000)),
    ("$180K – $240K", (180000, 240000)),
    ("$140k to $175k", (140000, 175000)),
    ("Hourly $25 - $30", (None, None)),
    ("No salary here", (None, None)),
    (None, (None, None)),
])
def test_parse_salary_text(text, expected):
    assert parse_salary_text(text) == expected


@pytest.mark.parametrize("loc,expected", [
    ("San Francisco, CA", True), ("Palo Alto", True), ("SF", True),
    ("Remote (US)", False), ("New York", False), (None, False),
])
def test_is_bay_area(loc, expected):
    assert is_bay_area(loc) is expected


def test_ashby():
    rows = normalize_ashby(load("ashby.json"), "acme")
    assert len(rows) == 2  # unlisted job dropped
    ml, ds = rows
    assert set(ml) == set(COLUMNS)
    assert (ml["salary_min"], ml["salary_max"], ml["salary_source"]) == (180000, 240000, "structured")
    assert ml["is_bay_area"] and ml["location"] == "San Francisco; New York"
    assert (ds["salary_min"], ds["salary_source"]) == (150000, "text")
    assert ds["is_remote"] and not ds["is_bay_area"]


def test_greenhouse():
    fde, support = normalize_greenhouse(load("greenhouse.json"), "acme")
    assert "<" not in fde["description"] and "messy data" in fde["description"]
    assert (fde["salary_min"], fde["salary_max"]) == (160000, 210000)
    assert fde["posted_at"].startswith("2026-10-15")
    assert fde["is_bay_area"]
    assert support["salary_min"] is None  # hourly range ignored


def test_lever():
    ai, analytics = normalize_lever(load("lever.json"), "acme")
    assert ai["title"] == "AI Engineer" and ai["salary_source"] == "structured"
    assert "FastAPI" in ai["description"] and ai["is_bay_area"]
    assert ai["posted_at"].startswith("2025")  # epoch ms converted
    assert (analytics["salary_min"], analytics["salary_max"]) == (140000, 175000)
    assert analytics["is_remote"]
