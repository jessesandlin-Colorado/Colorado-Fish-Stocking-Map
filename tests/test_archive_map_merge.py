from io import BytesIO
from pathlib import Path
import sys

from openpyxl import Workbook

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))

import merge_archive_waters
import import_atlas_catalog
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


def test_catalog_match_clears_stale_unmapped_warning():
    target = {
        "name": "Pinewood Reservoir",
        "stocking_status": "location-not-matched",
        "match_method": "atlas-id-unresolved",
        "location_warning": "Location not yet mapped.",
        "lat": None,
        "lng": None,
    }
    source = {
        "atlas_id": 284,
        "lat": 40.362682,
        "lng": -105.284362,
    }

    import_atlas_catalog.merge_missing(target, source)

    assert target["stocking_status"] == "matched-to-fishing-atlas"
    assert target["match_method"] == "atlas-catalog-exact-name"
    assert "location_warning" not in target


def test_watercode_alias_consolidation_merges_reordered_lake_name():
    mapped = {
        "key": "atlas-795",
        "atlas_id": 795,
        "watercode": "54801",
        "name": "LAKE ESTES",
        "canonical_name": "Lake Estes",
        "lat": 40.375619,
        "lng": -105.493118,
        "stocking_dates": ["2024-09-12"],
        "stocking_events": [
            {
                "event_id": "older",
                "stocking_date": "2024-09-12",
                "water_name": "Lake Estes",
                "source_kind": "archive",
            }
        ],
        "historical_event_count": 1,
        "species": ["Rainbow Trout"],
    }
    unmapped = {
        "key": "unmapped-estes",
        "name": "Estes Lake",
        "canonical_name": "Estes Lake",
        "stocking_status": "location-not-matched",
        "stocking_dates": ["2026-06-19"],
        "stocking_events": [
            {
                "event_id": "newer",
                "stocking_date": "2026-06-19",
                "water_name": "Estes Lake",
                "source_kind": "archive",
            }
        ],
        "historical_event_count": 1,
        "species": [],
    }

    waters, count = import_atlas_catalog.consolidate_watercode_aliases(
        [mapped, unmapped]
    )

    assert count == 1
    assert waters == [mapped]
    assert mapped["watercode"] == "54801"
    assert mapped["latest_report_date"] == "2026-06-19"
    assert mapped["historical_event_count"] == 2
    assert mapped["stocking_name_aliases"] == ["Estes Lake", "LAKE ESTES"]


def test_watercode_alias_consolidation_requires_unique_target():
    unmapped = {
        "name": "Mirror Lake",
        "stocking_status": "location-not-matched",
    }
    mapped = [
        {
            "name": "Lake Mirror",
            "watercode": str(code),
            "lat": 40.0,
            "lng": -105.0,
        }
        for code in (1, 2)
    ]

    waters, count = import_atlas_catalog.consolidate_watercode_aliases(
        [*mapped, unmapped]
    )

    assert count == 0
    assert unmapped in waters


def test_watercode_alias_consolidation_rejects_different_regions():
    mapped = {
        "name": "LAKE EXAMPLE",
        "watercode": "123",
        "lat": 40.0,
        "lng": -105.0,
        "stocking_events": [{"region": "northeast"}],
    }
    unmapped = {
        "name": "Example Lake",
        "stocking_status": "location-not-matched",
        "stocking_events": [{"region": "southwest"}],
    }

    waters, count = import_atlas_catalog.consolidate_watercode_aliases(
        [mapped, unmapped]
    )

    assert count == 0
    assert waters == [mapped, unmapped]


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
                "species": "Rainbow Trout",
                "quantity": 1000,
                "event_id": "rainbow-event",
                "atlas_url": "https://example.test/?value=680",
            },
            {
                "atlas_id": 680,
                "water_name": "Wrights Lake",
                "stocking_date": "2014-06-14",
                "species": "Cutthroat Trout",
                "quantity": 500,
                "event_id": "cutthroat-event",
                "atlas_url": "https://example.test/?value=680",
            },
            {
                "atlas_id": 999,
                "water_name": "Historic Reservoir",
                "stocking_date": "2015-05-01",
                "atlas_url": "https://example.test/?value=999",
            },
            {
                "water_name": "Unmapped Pond",
                "stocking_date": "2016-06-01",
                "species": "Rainbow Trout",
                "event_id": "unmapped-event",
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
    assert by_id[680]["historical_event_count"] == 3
    assert len(by_id[680]["stocking_events"]) == 3
    same_day = [
        event for event in by_id[680]["stocking_events"]
        if event["stocking_date"] == "2014-06-14"
    ]
    assert {event["species"] for event in same_day} == {
        "Rainbow Trout",
        "Cutthroat Trout",
    }
    assert by_id[999]["current_event_count"] == 0
    assert by_id[999]["stocking_dates"] == ["2015-05-01"]
    assert report["archive_only_waters_added"] == 1
    assert merged["summary"]["matched_waters"] == 2
    unmapped = next(
        water for water in merged["waters"]
        if water.get("stocking_status") == "location-not-matched"
    )
    assert unmapped["name"] == "Unmapped Pond"
    assert unmapped["historical_event_count"] == 1
    assert report["archive_events_displayed"] == 4
    assert merged["summary"]["unmapped_stocking_waters"] == 1
