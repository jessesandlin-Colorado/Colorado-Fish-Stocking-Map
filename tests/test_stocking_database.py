from pathlib import Path
import json
import sqlite3
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
from stocking_database import StockingEvent, event_key, import_source, export_json
from bootstrap_archive_csv import parse_year_sheet, validate_summary

FIXTURE = Path(__file__).parent / "fixtures" / "archive_sample.html"


def test_key_is_stable_and_normalized():
    a = StockingEvent("Twin  Lakes Reservoir", "2014-06-14", "Rainbow Trout", 10000, 10.2)
    b = StockingEvent("TWIN-LAKES RESERVOIR", "2014-06-14", "rainbow trout", 10000, 10.2)
    assert event_key(a) == event_key(b)


def test_archive_import_deduplicates_and_preserves_sources(tmp_path):
    db = tmp_path / "stocking.sqlite3"
    result = import_source(db, "archive", "fixture", fixture=FIXTURE)
    assert result["events_seen"] == 3
    assert result["new_events"] == 2
    with sqlite3.connect(db) as conn:
        assert conn.execute("select count(*) from stocking_events").fetchone()[0] == 2
        assert conn.execute("select count(*) from event_sources").fetchone()[0] == 3


def test_second_import_is_idempotent(tmp_path):
    db = tmp_path / "stocking.sqlite3"
    import_source(db, "archive", "fixture", fixture=FIXTURE)
    second = import_source(db, "archive", "fixture", fixture=FIXTURE)
    assert second["new_events"] == 0
    assert second["duplicates"] == 3


def test_export_summary(tmp_path):
    db = tmp_path / "stocking.sqlite3"
    out = tmp_path / "events.json"
    import_source(db, "archive", "fixture", fixture=FIXTURE)
    summary = export_json(db, out)
    assert summary["stocking_events"] == 2
    assert summary["events_by_year"] == {"2014": 1, "2015": 1}
    assert json.loads(out.read_text())["summary"]["earliest_date"] == "2014-06-14"


def test_annual_sheet_extracts_water_date_and_atlas_id():
    html = """
    <table><tr>
      <td>06/14/2014</td><td>northeast</td>
      <td><a href="https://ndismaps.nrel.colostate.edu/index.html?app=FishingAtlas&value=680">Wrights Lake</a></td>
    </tr></table>
    """
    rows = parse_year_sheet(html, 2014)
    assert len(rows) == 1
    event, row_number, raw, atlas_id, atlas_url = rows[0]
    assert event.water_name == "Wrights Lake"
    assert event.stocking_date == "2014-06-14"
    assert event.region == "northeast"
    assert atlas_id == 680
    assert raw["atlas_id"] == 680
    assert "value=680" in atlas_url


def test_archive_validation_rejects_current_year_only_output():
    with pytest.raises(RuntimeError, match="earliest date"):
        validate_summary({"earliest_date": "2026-01-16", "stocking_events": 514})
