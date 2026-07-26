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
import os
import random
import re
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
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



class PoliteHttpClient:
    """Small cached HTTP client with throttling and bounded retries.

    Cache entries are reused for ``cache_ttl_hours`` and can also be used as a
    stale fallback when the Atlas is temporarily unavailable.
    """

    def __init__(self, cache_dir: Path, min_delay: float = 0.30, max_delay: float = 0.50, retries: int = 3, cache_ttl_hours: int = 24):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.retries = retries
        self.cache_ttl = timedelta(hours=cache_ttl_hours)
        self.session = requests.Session()
        self.session.headers["User-Agent"] = "ColoradoFishMap/4.1 (+https://github.com/jessesandlin-Colorado/colorado-fish-stocking-map)"
        self._last_request_at = 0.0

    def _cache_path(self, namespace: str, key: str) -> Path:
        digest = hashlib.sha1(key.encode("utf-8")).hexdigest()
        folder = self.cache_dir / namespace
        folder.mkdir(parents=True, exist_ok=True)
        return folder / f"{digest}.json"

    def _read_cache(self, path: Path) -> dict[str, Any] | None:
        payload = read_json(path, None)
        return payload if isinstance(payload, dict) and "data" in payload else None

    def _fresh(self, payload: dict[str, Any]) -> bool:
        try:
            saved = datetime.fromisoformat(payload["saved_at"])
            return datetime.now(timezone.utc) - saved <= self.cache_ttl
        except (KeyError, TypeError, ValueError):
            return False

    def _wait(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        required = random.uniform(self.min_delay, self.max_delay)
        if elapsed < required:
            time.sleep(required - elapsed)

    def get_json(self, url: str, params: dict[str, Any], namespace: str, cache_key: str, allow_stale: bool = True) -> tuple[dict[str, Any], str]:
        path = self._cache_path(namespace, cache_key)
        cached = self._read_cache(path)
        if cached and self._fresh(cached):
            return cached["data"], "cache-fresh"

        last_error: Exception | None = None
        for attempt in range(1, self.retries + 1):
            try:
                self._wait()
                response = self.session.get(url, params=params, timeout=45)
                self._last_request_at = time.monotonic()
                response.raise_for_status()
                data = response.json()
                write_json(path, {"saved_at": datetime.now(timezone.utc).isoformat(), "url": url, "params": params, "data": data})
                return data, "network"
            except (requests.RequestException, ValueError) as exc:
                last_error = exc
                if attempt < self.retries:
                    time.sleep(2 ** (attempt - 1))

        if cached and allow_stale:
            return cached["data"], "cache-stale"
        raise RuntimeError(f"Request failed after {self.retries} attempts: {last_error}")

    def get_text(self, url: str) -> str:
        last_error: Exception | None = None
        for attempt in range(1, self.retries + 1):
            try:
                self._wait()
                response = self.session.get(url, timeout=45)
                self._last_request_at = time.monotonic()
                response.raise_for_status()
                return response.text
            except requests.RequestException as exc:
                last_error = exc
                if attempt < self.retries:
                    time.sleep(2 ** (attempt - 1))
        raise RuntimeError(f"Request failed after {self.retries} attempts: {last_error}")


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


def arcgis_query(client: PoliteHttpClient, service: str, layer_id: int, where: str, cache_key: str) -> tuple[list[dict[str, Any]], str]:
    payload, source = client.get_json(
        f"{service}/{layer_id}/query",
        params={
            "where": where,
            "outFields": "*",
            "returnGeometry": "true",
            "outSR": "4326",
            "f": "json",
        },
        namespace="atlas",
        cache_key=cache_key,
    )
    if payload.get("error"):
        raise RuntimeError(payload["error"].get("message", "ArcGIS query failed"))
    return payload.get("features", []), source


def query_atlas(client: PoliteHttpClient, uid: int) -> dict[str, Any] | None:
    errors: list[str] = []
    for layer_id in ATLAS_LAYERS:
        try:
            features, source = arcgis_query(client, ATLAS_MAIN, layer_id, f"UNI_ID={uid}", f"main:{layer_id}:{uid}")
        except RuntimeError as exc:
            errors.append(f"layer {layer_id}: {exc}")
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
            "atlas_data_source": source,
            "atlas_errors": errors,
        }
    return None


def query_species_record(client: PoliteHttpClient, uid: int, enabled: bool = False) -> dict[str, Any]:
    """Species probing is disabled until CPW's supported source is verified."""
    if not enabled:
        return {"status": "not-yet-integrated", "species": []}
    try:
        features, source = arcgis_query(client, ATLAS_DATA, ATLAS_SPECIES_LAYER, f"UNI_ID={uid}", f"species:{uid}")
    except RuntimeError as exc:
        return {"status": "temporarily-unavailable", "species": [], "error": str(exc)}
    if not features:
        return {"status": "no-record", "species": [], "data_source": source}
    attrs = features[0].get("attributes", {})
    possible_fields = ("SPECIES", "SPECIES_NAME", "FISH_SPECIES", "COMMON_NAME", "COM_NAME", "SPP_NAME", "Species", "FishSpecies")
    names: list[str] = []
    for field in possible_fields:
        value = attrs.get(field)
        if value:
            names.extend(part.strip() for part in re.split(r"[,;/]", str(value)) if part.strip())
    return {
        "status": "available" if names else "source-does-not-expose-species-names",
        "species": sorted(set(names)),
        "data_source": source,
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
    parser.add_argument("--enable-species-probe", action="store_true", help="Probe the unverified Atlas species layer")
    parser.add_argument("--cache-ttl-hours", type=int, default=24)
    args = parser.parse_args()

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(timezone.utc).isoformat()
    observed_date = datetime.now(timezone.utc).date().isoformat()

    client = PoliteHttpClient(Path(__file__).parents[1] / ".cache", cache_ttl_hours=args.cache_ttl_hours)

    print("STEP 1/6 — Download CPW stocking report")
    current_events = parse_report(client.get_text(CPW))
    if args.limit:
        current_events = current_events[: args.limit]
    if not current_events:
        sys.exit("No stocking rows found. CPW markup may have changed.")

    print("STEP 2/6 — Normalize and archive stocking events")
    prior_imports = read_json(output / "import-history.json", [])
    prior_current_count = prior_imports[-1].get("rows_downloaded", 0) if prior_imports else 0
    existing_history = read_json(output / "stocking-history.json", [])
    history, new_events = build_history(existing_history, current_events, observed_date)

    grouped: dict[int | None, list[dict[str, Any]]] = defaultdict(list)
    for event in current_events:
        grouped[event["atlas_id"]].append(event)

    print("STEP 3/6 — Match and enrich Atlas waters")
    prior_waters_payload = read_json(output / "waters.json", {"waters": []})
    prior_waters = {w.get("atlas_id"): w for w in prior_waters_payload.get("waters", []) if w.get("atlas_id") is not None}
    matched: list[dict[str, Any]] = []
    unmatched: list[dict[str, Any]] = []
    history_by_id = {item["event_id"]: item for item in history}

    for index, (uid, group) in enumerate(grouped.items(), start=1):
        print(f"[{index}/{len(grouped)}] Atlas ID {uid}: {group[0]['name']}")
        info = query_atlas(client, uid) if uid is not None else None
        if not info or info.get("lat") is None or info.get("lng") is None:
            prior = prior_waters.get(uid)
            if prior and prior.get("lat") is not None and prior.get("lng") is not None:
                info = {key: value for key, value in prior.items() if key not in {"stocking_dates", "latest_report_date", "current_event_count", "historical_event_count", "species", "species_status"}}
                info["atlas_data_source"] = "prior-published-data"
                info["atlas_warning"] = "Atlas unavailable; retained previously published location details."
            else:
                unmatched.extend(group)
                continue

        species_result = query_species_record(client, uid, enabled=args.enable_species_probe)
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

    for event in unmatched:
        saved = history_by_id.get(event["event_id"])
        if saved:
            saved["match_status"] = "unmatched"

    history = sorted(history_by_id.values(), key=lambda x: (x.get("report_date", ""), x.get("name", "")), reverse=True)
    matched.sort(key=lambda item: (item["latest_report_date"], item["name"]), reverse=True)

    print("STEP 4/6 — Build weekly-change summary")
    latest_date = max((e["report_date"] for e in current_events), default=None)
    latest_events = [e for e in current_events if e.get("report_date") == latest_date]

    summary = {
        "stocking_events": len(current_events),
        "unique_atlas_ids": len(grouped),
        "matched_waters": len(matched),
        "unmatched_events": len(unmatched),
        "historical_events": len(history),
        "new_historical_events": new_events,
        "unknown_region_events": sum(1 for event in current_events if event.get("region") == "unknown"),
        "latest_report_date": latest_date,
        "latest_report_events": len(latest_events),
        "latest_report_unique_waters": len({e.get("atlas_id") for e in latest_events}),
    }
    print("STEP 5/6 — Validate generated data")
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

    print("STEP 6/6 — Publish JSON and reports")
    write_json(output / "waters.json", payload)
    write_json(output / "unmatched.json", unmatched)
    write_json(output / "stocking-history.json", history)
    write_json(output / "import-history.json", prior_imports)
    write_json(output / "validation.json", {"generated_at": generated_at, "summary": summary, "findings": findings})
    write_json(
        output / "species.json",
        {
            "generated_at": generated_at,
            "status": "not-yet-integrated" if not args.enable_species_probe else "experimental",
            "note": "Species display is intentionally disabled until a stable, verified official source is available.",
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
