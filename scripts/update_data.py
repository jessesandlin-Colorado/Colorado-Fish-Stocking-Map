#!/usr/bin/env python3
"""Build Version 4 data files from CPW's stocking report and Fishing Atlas.

Version 4 adds durable stocking history, import-run auditing, multi-layer Atlas
matching, richer location attributes, and validation safeguards.
"""
from __future__ import annotations

import argparse
import hashlib
import html as html_lib
import json
import re
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import requests
from bs4 import BeautifulSoup

CPW = "https://cpw.state.co.us/activities/fishing/fishing-awards-and-records/fish-stocking-report"
ATLAS_MAIN = "https://ndismaps.nrel.colostate.edu/arcgis/rest/services/FishingAtlas/FishingAtlas_Main_Map/MapServer"
ATLAS_DATA = "https://ndismaps.nrel.colostate.edu/arcgis/rest/services/FishingAtlas/FishingAtlas_Data/MapServer"
ATLAS_LAYERS = (59, 61, 63, 65, 67)
ATLAS_SPECIES_LAYER = 2
DATE_RE = re.compile(r"\b(\d{1,2}/\d{1,2}/\d{4})\b")
REGIONS = {"northeast", "northwest", "southeast", "southwest"}
CO_BOUNDS = {"south": 36.8, "north": 41.2, "west": -109.2, "east": -101.8}


def clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def normalized_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", clean(value).lower()).strip()


def get_atlas_id(url: str) -> int | None:
    try:
        return int(parse_qs(urlparse(url).query).get("value", [None])[0])
    except (TypeError, ValueError):
        return None


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def parse_report(page_html: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(page_html, "html.parser")
    rows: list[dict[str, Any]] = []

    for anchor in soup.select('a[href*="fishingatlas"][href*="value="]'):
        row = anchor.find_parent("tr")
        if not row:
            continue
        cells = [clean(cell.get_text(" ", strip=True)) for cell in row.find_all(["td", "th"])]
        text = " | ".join(cells)
        match = DATE_RE.search(text)
        if not match:
            continue

        report_date = datetime.strptime(match.group(1), "%m/%d/%Y").date().isoformat()
        region = next((cell.lower() for cell in cells if cell.lower() in REGIONS), "unknown")
        excluded = {"atlas", region, match.group(1)}
        name = next(
            (cell for cell in cells if cell and cell.lower() not in excluded and not DATE_RE.fullmatch(cell)),
            cells[0] if cells else "Unknown",
        )
        url = anchor.get("href", "")
        if url.startswith("/"):
            url = "https://cpw.state.co.us" + url
        uid = get_atlas_id(url)
        event_id = f"atlas-{uid or 'unknown'}-{report_date}"
        rows.append(
            {
                "event_id": event_id,
                "name": name,
                "normalized_name": normalized_name(name),
                "region": region,
                "report_date": report_date,
                "source_url": CPW,
                "atlas_url": url,
                "atlas_id": uid,
            }
        )

    unique: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for record in rows:
        key = (record["atlas_id"], record["report_date"], record["normalized_name"])
        if key not in seen:
            seen.add(key)
            unique.append(record)
    return unique


def arcgis_query(session: requests.Session, service: str, layer_id: int, where: str) -> list[dict[str, Any]]:
    response = session.get(
        f"{service}/{layer_id}/query",
        params={
            "where": where,
            "outFields": "*",
            "returnGeometry": "true",
            "outSR": "4326",
            "f": "json",
        },
        timeout=45,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("error"):
        raise RuntimeError(payload["error"].get("message", "ArcGIS query failed"))
    return payload.get("features", [])


def query_atlas(session: requests.Session, uid: int) -> dict[str, Any] | None:
    for layer_id in ATLAS_LAYERS:
        try:
            features = arcgis_query(session, ATLAS_MAIN, layer_id, f"UNI_ID={uid}")
        except (requests.RequestException, ValueError, RuntimeError) as exc:
            print(f"  Warning: layer {layer_id} failed: {exc}")
            continue
        if not features:
            continue

        feature = features[0]
        attrs = feature.get("attributes", {})
        geometry = feature.get("geometry", {})
        return {
            "lat": geometry.get("y"),
            "lng": geometry.get("x"),
            "watercode": attrs.get("WATERCODE"),
            "atlas_name": attrs.get("FA_NAME") or attrs.get("DOW_NAME"),
            "alternate_name": attrs.get("FA_NAME2"),
            "property_name": attrs.get("PROP_NAME"),
            "county": attrs.get("COUNTYNAME"),
            "location_type": attrs.get("LOC_TYPE"),
            "elevation_ft": attrs.get("ELEV_FT") or attrs.get("ELEV_FT_TXT"),
            "boating": attrs.get("BOATING"),
            "access_ease": attrs.get("ACCESS_EASE"),
            "fishing_pressure": attrs.get("FISH_PRESSURE"),
            "family_friendly": attrs.get("OPP_FAMILY"),
            "rustic": attrs.get("OPP_RUSTIC"),
            "ice_fishing": attrs.get("OPP_ICE"),
            "accessible_pier": attrs.get("HANDI_PIER"),
            "stocked_description": attrs.get("STOCKED"),
            "survey_url": attrs.get("SURVEY_URL") or attrs.get("REPORTS_URL"),
            "driving_url": attrs.get("DRIVING_URL"),
            "property_url": attrs.get("PROP_URL"),
            "gold_medal": bool(attrs.get("GoldMedal")),
            "special_opportunity": attrs.get("SUP_Desc") if attrs.get("SUP") else None,
            "atlas_layer": layer_id,
        }
    return None


def query_species_record(session: requests.Session, uid: int) -> dict[str, Any]:
    """Return official Atlas attributes that accompany its species display layer.

    The public layer currently exposes opportunity/location metadata but no
    explicit species-name field. We preserve the official record and report an
    unavailable status instead of fabricating species from water names.
    """
    try:
        features = arcgis_query(session, ATLAS_DATA, ATLAS_SPECIES_LAYER, f"UNI_ID={uid}")
    except (requests.RequestException, ValueError, RuntimeError) as exc:
        return {"status": "query-error", "species": [], "error": str(exc)}
    if not features:
        return {"status": "no-record", "species": []}

    attrs = features[0].get("attributes", {})
    possible_fields = (
        "SPECIES", "SPECIES_NAME", "FISH_SPECIES", "COMMON_NAME", "COM_NAME",
        "SPP_NAME", "Species", "FishSpecies",
    )
    names: list[str] = []
    for field in possible_fields:
        value = attrs.get(field)
        if value:
            names.extend(part.strip() for part in re.split(r"[,;/]", str(value)) if part.strip())
    return {
        "status": "available" if names else "official-layer-has-no-species-name-field",
        "species": sorted(set(names)),
        "atlas_record": {
            key: attrs.get(key)
            for key in ("OPP_FAMILY", "OPP_RUSTIC", "OPP_ICE", "HANDI_PIER", "STOCKED", "GoldMedal", "SUP_Desc")
            if attrs.get(key) not in (None, "")
        },
    }


def build_history(existing: list[dict[str, Any]], current: list[dict[str, Any]], observed_at: str) -> tuple[list[dict[str, Any]], int]:
    by_id = {item.get("event_id"): item for item in existing if item.get("event_id")}
    added = 0
    for event in current:
        item = dict(event)
        item["first_observed"] = by_id.get(item["event_id"], {}).get("first_observed", observed_at)
        item["last_observed"] = observed_at
        item["match_status"] = "pending"
        item["match_method"] = None
        item["match_confidence"] = 0.0
        if item["event_id"] not in by_id:
            added += 1
        by_id[item["event_id"]] = {**by_id.get(item["event_id"], {}), **item}
    return sorted(by_id.values(), key=lambda x: (x.get("report_date", ""), x.get("name", "")), reverse=True), added


def validate(events: list[dict[str, Any]], waters: list[dict[str, Any]], unmatched: list[dict[str, Any]], prior_count: int) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []

    def add(level: str, code: str, message: str) -> None:
        findings.append({"level": level, "code": code, "message": message})

    if len(events) < 10:
        add("critical", "report-too-small", f"Only {len(events)} report rows were parsed.")
    if prior_count and len(events) < max(10, int(prior_count * 0.35)):
        add("critical", "large-report-drop", f"Report row count fell from {prior_count} to {len(events)}.")
    unknown_regions = sum(1 for event in events if event.get("region") == "unknown")
    if unknown_regions:
        add("warning", "unknown-regions", f"{unknown_regions} current events have an unknown region.")
    if unmatched:
        add("warning", "unmatched-events", f"{len(unmatched)} current events remain unmatched.")

    for water in waters:
        lat, lng = water.get("lat"), water.get("lng")
        if not isinstance(lat, (int, float)) or not isinstance(lng, (int, float)):
            add("critical", "missing-coordinate", f"{water.get('name')} has no usable coordinates.")
        elif not (CO_BOUNDS["south"] <= lat <= CO_BOUNDS["north"] and CO_BOUNDS["west"] <= lng <= CO_BOUNDS["east"]):
            add("critical", "outside-colorado", f"{water.get('name')} is outside the Colorado validation bounds: {lat}, {lng}.")

    if not findings:
        add("info", "validation-clean", "No validation issues were detected.")
    return findings


def make_validation_html(generated_at: str, summary: dict[str, Any], findings: list[dict[str, str]], waters: list[dict[str, Any]]) -> str:
    finding_rows = "".join(
        f"<tr class='{html_lib.escape(item['level'])}'><td>{html_lib.escape(item['level'].upper())}</td>"
        f"<td>{html_lib.escape(item['code'])}</td><td>{html_lib.escape(item['message'])}</td></tr>"
        for item in findings
    )
    water_rows = "".join(
        f"<tr><td>{html_lib.escape(str(w.get('name', '')))}</td><td>{html_lib.escape(str(w.get('region', '')))}</td>"
        f"<td>{html_lib.escape(str(w.get('latest_report_date', '')))}</td><td>{w.get('atlas_id', '')}</td>"
        f"<td>{html_lib.escape(str(w.get('atlas_name') or ''))}</td><td>{w.get('atlas_layer', '')}</td>"
        f"<td>{html_lib.escape(str(w.get('species_status', '')))}</td></tr>"
        for w in waters
    )
    return f"""<!doctype html><html><head><meta charset='utf-8'><title>Version 4 Validation Report</title>
<style>body{{font:15px system-ui;margin:2rem;max-width:1400px}}table{{border-collapse:collapse;width:100%;margin:1rem 0 2rem}}th,td{{border:1px solid #ccd3d8;padding:.5rem;text-align:left}}th{{background:#f3f6f8;position:sticky;top:0}}.critical{{background:#ffe5e5}}.warning{{background:#fff5d6}}.info{{background:#e8f5ec}}code{{background:#f3f3f3;padding:.1rem .3rem}}</style></head><body>
<h1>Colorado Fish Stocking Map — Version 4 Validation</h1><p>Generated <code>{html_lib.escape(generated_at)}</code>.</p>
<h2>Import summary</h2><pre>{html_lib.escape(json.dumps(summary, indent=2))}</pre>
<h2>Findings</h2><table><thead><tr><th>Level</th><th>Code</th><th>Message</th></tr></thead><tbody>{finding_rows}</tbody></table>
<h2>Matched waters</h2><table><thead><tr><th>Report name</th><th>Region</th><th>Latest</th><th>Atlas ID</th><th>Atlas name</th><th>Layer</th><th>Species status</th></tr></thead><tbody>{water_rows}</tbody></table>
</body></html>"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=str(Path(__file__).parents[1] / "data"))
    parser.add_argument("--limit", type=int)
    parser.add_argument("--strict", action="store_true", help="Exit non-zero on critical validation findings")
    args = parser.parse_args()

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(timezone.utc).isoformat()
    observed_date = datetime.now(timezone.utc).date().isoformat()

    session = requests.Session()
    session.headers["User-Agent"] = "ColoradoFishMap/4.0 contact: project-maintainer"

    print("Downloading CPW report…")
    response = session.get(CPW, timeout=45)
    response.raise_for_status()
    current_events = parse_report(response.text)
    if args.limit:
        current_events = current_events[: args.limit]
    if not current_events:
        sys.exit("No stocking rows found. CPW markup may have changed.")

    prior_imports = read_json(output / "import-history.json", [])
    prior_current_count = prior_imports[-1].get("rows_downloaded", 0) if prior_imports else 0
    existing_history = read_json(output / "stocking-history.json", [])
    history, new_events = build_history(existing_history, current_events, observed_date)

    grouped: dict[int | None, list[dict[str, Any]]] = defaultdict(list)
    for event in current_events:
        grouped[event["atlas_id"]].append(event)

    matched: list[dict[str, Any]] = []
    unmatched: list[dict[str, Any]] = []
    history_by_id = {item["event_id"]: item for item in history}

    for index, (uid, group) in enumerate(grouped.items(), start=1):
        print(f"[{index}/{len(grouped)}] Atlas ID {uid}: {group[0]['name']}")
        info = query_atlas(session, uid) if uid is not None else None
        if not info or info.get("lat") is None or info.get("lng") is None:
            unmatched.extend(group)
            continue

        species_result = query_species_record(session, uid)
        dates = sorted({item["report_date"] for item in group}, reverse=True)
        base = group[0]
        water = {
            "key": f"atlas-{uid}",
            "atlas_id": uid,
            "name": base["name"],
            "normalized_name": normalized_name(base["name"]),
            "region": base["region"],
            "atlas_url": base["atlas_url"],
            "latest_report_date": dates[0],
            "stocking_dates": dates,
            "current_event_count": len(group),
            "historical_event_count": sum(1 for event in history if event.get("atlas_id") == uid),
            "match_method": "atlas-id",
            "match_score": 1.0,
            "species": species_result.get("species", []),
            "species_status": species_result.get("status"),
            "species_source_layer": ATLAS_SPECIES_LAYER,
            "atlas_species_metadata": species_result.get("atlas_record", {}),
            **info,
        }
        matched.append(water)
        for event in group:
            saved = history_by_id[event["event_id"]]
            saved["match_status"] = "matched"
            saved["match_method"] = "atlas-id"
            saved["match_confidence"] = 1.0
            saved["watercode"] = info.get("watercode")
            saved["matched_layer"] = info.get("atlas_layer")
        time.sleep(0.03)

    for event in unmatched:
        saved = history_by_id.get(event["event_id"])
        if saved:
            saved["match_status"] = "unmatched"

    history = sorted(history_by_id.values(), key=lambda x: (x.get("report_date", ""), x.get("name", "")), reverse=True)
    matched.sort(key=lambda item: (item["latest_report_date"], item["name"]), reverse=True)

    summary = {
        "stocking_events": len(current_events),
        "unique_atlas_ids": len(grouped),
        "matched_waters": len(matched),
        "unmatched_events": len(unmatched),
        "historical_events": len(history),
        "new_historical_events": new_events,
        "unknown_region_events": sum(1 for event in current_events if event.get("region") == "unknown"),
    }
    findings = validate(current_events, matched, unmatched, prior_current_count)
    critical_count = sum(1 for finding in findings if finding["level"] == "critical")
    warning_count = sum(1 for finding in findings if finding["level"] == "warning")
    run_id = hashlib.sha1(generated_at.encode("utf-8")).hexdigest()[:12]
    import_record = {
        "run_id": run_id,
        "generated_at": generated_at,
        "source_url": CPW,
        "rows_downloaded": len(current_events),
        "new_events_added": new_events,
        "historical_events_total": len(history),
        "matched_unique_waters": len(matched),
        "unmatched_events": len(unmatched),
        "critical_findings": critical_count,
        "warning_findings": warning_count,
        "status": "failed-validation" if critical_count else "success-with-warnings" if warning_count else "success",
    }
    prior_imports.append(import_record)
    prior_imports = prior_imports[-250:]

    payload = {
        "schema_version": 4,
        "generated_at": generated_at,
        "source_url": CPW,
        "summary": summary,
        "validation": {"critical": critical_count, "warnings": warning_count},
        "waters": matched,
    }

    write_json(output / "waters.json", payload)
    write_json(output / "unmatched.json", unmatched)
    write_json(output / "stocking-history.json", history)
    write_json(output / "import-history.json", prior_imports)
    write_json(output / "validation.json", {"generated_at": generated_at, "summary": summary, "findings": findings})
    write_json(
        output / "species.json",
        {
            "generated_at": generated_at,
            "status": "partial",
            "note": "Species names are included only when explicitly returned by the official Atlas service; the current public layer may not expose them as attributes.",
            "waters_with_species": [
                {"atlas_id": water["atlas_id"], "name": water["name"], "species": water["species"]}
                for water in matched
                if water["species"]
            ],
        },
    )
    (output / "validation-report.html").write_text(
        make_validation_html(generated_at, summary, findings, matched), encoding="utf-8"
    )
    # Retain the old filename so existing bookmarks and workflows continue to work.
    (output / "match-report.html").write_text(
        make_validation_html(generated_at, summary, findings, matched), encoding="utf-8"
    )

    print(json.dumps({**summary, "critical_findings": critical_count, "warning_findings": warning_count}, indent=2))
    if args.strict and critical_count:
        sys.exit(f"Validation failed with {critical_count} critical finding(s).")


if __name__ == "__main__":
    main()
