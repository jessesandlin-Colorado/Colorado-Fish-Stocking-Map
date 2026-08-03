import json


def test_report_catalog_prefers_local_sources_and_valid_urls():
    data = json.load(open("config/fishing_reports.json", encoding="utf-8"))
    reports = [report for items in data["waters"].values() for report in items]
    assert reports
    assert all(report["local"] is True for report in reports)
    assert all(report["url"].startswith("https://") for report in reports)
    assert any(report["source"] == "Steamboat Flyfisher" for report in reports)
    assert any(report["source"] == "Minturn Anglers" for report in reports)
    assert any(report["source"] == "Vail Valley Anglers" for report in reports)


def test_report_catalog_only_references_known_waters():
    catalog = json.load(open("config/fishing_reports.json", encoding="utf-8"))["waters"]
    waters = json.load(open("data/waters.json", encoding="utf-8"))["waters"]
    known_keys = {water["key"] for water in waters}
    assert set(catalog).issubset(known_keys)


def test_report_card_bundle_is_loaded_and_safe():
    loader = open("share-links.js", encoding="utf-8").read()
    bundle = open("fishing-reports.js", encoding="utf-8").read()
    assert "fishingReportScript.src = 'fishing-reports.js'" in loader
    assert "config/fishing_reports.json" in bundle
    assert 'rel="noopener noreferrer"' in bundle
    assert "Fishing reports" in bundle
