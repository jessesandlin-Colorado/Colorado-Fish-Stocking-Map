from io import BytesIO
from pathlib import Path
import sys

from openpyxl import Workbook

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))

import merge_archive_waters
from build_archive_snapshot import extract_workbook_rows


def workbook_bytes() -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "2014"
    sheet.append(["Date", "Region", "Water", "Link"])
    sheet.append(["06/14/2014", "northeast", "Wrights Lake", "Atlas"])
    sheet["D2"].hyperlink = (
        "https://ndismaps.nrel.colostate.edu/fishingatlas/"
        "index.aspx?keyword=fspot&value=680"
    )
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def test_archive_uses_neighboring_water_name_when_link_label_is_atlas():
    rows, diagnostics = extract_workbook_rows(workbook_bytes())
    assert diagnostics[0]["rows_imported"] == 1
    event, sheet, row_number, raw, atlas_id, atlas_url = rows[0]
    assert event.water_name == "Wrights Lake"
    assert event.stocking_date == "2014-06-14"
    assert event.region == "northeast"
    assert atlas_id == 680
    assert "value=680" in atlas_url


def test_merge_adds_archive_dates_and_historical_only_waters(monkeypatch):
    waters_payload = {
        "generated_at": "2026-07-27T00:00:00+00:00",
        "summary": {"stocking_events": 2, "matched_waters": 1},
        "waters": [
            {
                "key": "atlas-680",
                "atlas_id": 680,
                "name": "Wrights Lake",
                "atlas_url": "https://example.test/?value=680",
                "latest_report_date": "2026-07-24",
                "stocking_dates": ["2026-07-24"],
                "historical_event_count": 1,
                "lat": 38.7,
                "lng": -106.1,
                "species": [],
            }
        ],
    }
    archive_payload = {
        "summary": {"earliest_date": "2014-06-14", "latest_date": "2025-12-31"},
        "events": [
            {
                "atlas_id": 680,
                "water_name": "Wrights Lake",
                "stocking_date": "2014-06-14",
                "atlas_url": "https://example.test/?value=680",
            },
            {
                "atlas_id": 999,
                "water_name": "Historic Reservoir",
                "stocking_date": "2015-05-01",
                "atlas_url": "https://example.test/?value=999",
            },
        ],
    }

    def fake_query_atlas(client, uid, names, override):
        assert uid == 999
        return {
            "lat": 39.0,
            "lng": -105.0,
            "atlas_name": "Historic Reservoir",
            "county": "Test",
            "match_method": "atlas-id",
            "match_score": 1.0,
        }

    monkeypatch.setattr(merge_archive_waters, "query_atlas", fake_query_atlas)
    merged, report = merge_archive_waters.merge_archive(
        waters_payload, archive_payload, object(), {}
    )

    by_id = {water["atlas_id"]: water for water in merged["waters"]}
    assert by_id[680]["stocking_dates"] == ["2026-07-24", "2014-06-14"]
    assert by_id[680]["historical_event_count"] == 2
    assert by_id[999]["current_event_count"] == 0
    assert by_id[999]["stocking_dates"] == ["2015-05-01"]
    assert report["archive_only_waters_added"] == 1
    assert merged["summary"]["matched_waters"] == 2
