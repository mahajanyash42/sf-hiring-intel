import json
from pathlib import Path

from hiring_intel import collect as collect_mod

FIXTURES = Path(__file__).parent / "fixtures"


def test_collect_end_to_end(tmp_path, monkeypatch):
    """Run the full collector with fake API responses and check the output files."""
    config = tmp_path / "companies.yaml"
    config.write_text("ashby: [acme]\ngreenhouse: [acme]\nlever: [acme, missingco]\n")

    def fake_fetch(source, slug, session, retries=3):
        if slug == "missingco":
            return None
        return json.loads((FIXTURES / f"{source}.json").read_text())

    monkeypatch.setattr(collect_mod, "fetch", fake_fetch)
    monkeypatch.setattr(collect_mod, "DELAY_SECONDS", 0)
    monkeypatch.setattr(collect_mod.time, "sleep", lambda s: None)

    df = collect_mod.collect(config, tmp_path)

    assert len(df) == 6
    assert set(df["source"]) == {"ashby", "greenhouse", "lever"}
    assert df["salary_min"].notna().sum() == 5
    assert len(list((tmp_path / "raw").rglob("*.json"))) == 3
    assert len(list((tmp_path / "processed").glob("jobs_*.csv"))) == 1
