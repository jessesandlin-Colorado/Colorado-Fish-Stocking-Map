#!/usr/bin/env python3
"""Build Colorado Fish Stocking Map data from CPW and the Fishing Atlas.

Version 5 adds production species extraction, persistent species fallbacks,
manual species overrides, richer validation, and UI-ready summary statistics.
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
REGION_LABELS = {"northeast", "northwest", "southeast", "southwest"}
CO_BOUNDS = {"south": 36.8, "north": 41.2, "west": -109.2, "east": -101.8}
PROJECT_ROOT = Path(__file__).parents[1]
DEFAULT_OVERRIDES_PATH = PROJECT_ROOT / "config" / "atlas_overrides.json"
DEFAULT_SPECIES_OVERRIDES_PATH = PROJECT_ROOT / "config" / "species_overrides.json"

# Species names used only to recognize names in official Atlas-linked HTML.
# The importer never infers species from habitat, water type, or stocking text.
KNOWN_COLORADO_SPECIES = (
    "Arctic char", "Black bullhead", "Black crappie", "Bluegill",
    "Brook trout", "Brown trout", "Channel catfish", "Common carp",
    "Cutbow", "Cutthroat trout", "Golden trout", "Grass carp",
    "Green sunfish", "Kokanee salmon", "Lake trout", "Largemouth bass",
    "Longnose sucker", "Mountain whitefish", "Northern pike", "Rainbow trout",
    "Rio Grande chub", "Roundtail chub", "Sacramento perch", "Sauger",
    "Smallmouth bass", "Splake", "Tiger muskie", "Tiger trout",
    "Walleye", "White crappie", "White sucker", "Yellow perch"
)



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

    def get_text_cached(self, url: str, namespace: str = "html", allow_stale: bool = True) -> tuple[str, str]:
        path = self._cache_path(namespace, url)
        cached = self._read_cache(path)
        if cached and self._fresh(cached):
            return str(cached["data"].get("text", "")), "cache-fresh"
        try:
            text = self.get_text(url)
            write_json(path, {"saved_at": datetime.now(timezone.utc).isoformat(), "url": url, "data": {"text": text}})
            return text, "network"
        except RuntimeError:
            if cached and allow_stale:
                return str(cached["data"].get("text", "")), "cache-stale"
            raise


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
        excluded = {"atlas", match.group(1), *REGION_LABELS}
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


def _sql_text(value: str) -> str:
    return value.replace("'", "''")


def _feature_to_water(feature: dict[str, Any], layer_id: int, source: str, errors: list[str], match_method: str, match_score: float) -> dict[str, Any]:
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
        "match_method": match_method,
        "match_score": match_score,
    }


def load_overrides(path: Path) -> dict[str, Any]:
    payload = read_json(path, {})
    if not isinstance(payload, dict):
        return {}
    return payload.get("waters", payload) if isinstance(payload.get("waters", payload), dict) else {}


def query_atlas(client: PoliteHttpClient, uid: int, report_names: list[str], override: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Match an Atlas water by ID, reviewed aliases, then an explicit override.

    ID lookup remains authoritative. Name lookup is intentionally conservative:
    it only accepts a unique result whose Atlas name normalizes to one of the
    reviewed candidate names. Manual coordinate overrides are the final fallback.
    """
    errors: list[str] = []

    for layer_id in ATLAS_LAYERS:
        try:
            features, source = arcgis_query(client, ATLAS_MAIN, layer_id, f"UNI_ID={uid}", f"main:{layer_id}:{uid}")
        except RuntimeError as exc:
            errors.append(f"layer {layer_id} ID lookup: {exc}")
            continue
        if features:
            return _feature_to_water(features[0], layer_id, source, errors, "atlas-id", 1.0)

    override = override or {}
    candidates = [*report_names, *override.get("aliases", [])]
    normalized_candidates = {normalized_name(name) for name in candidates if clean(name)}
    seen_queries: set[tuple[int, str]] = set()

    for candidate in candidates:
        candidate = clean(candidate)
        if not candidate:
            continue
        for layer_id in ATLAS_LAYERS:
            query_key = (layer_id, normalized_name(candidate))
            if query_key in seen_queries:
                continue
            seen_queries.add(query_key)
            escaped = _sql_text(candidate)
            where = f"FA_NAME='{escaped}' OR FA_NAME2='{escaped}' OR DOW_NAME='{escaped}'"
            try:
                features, source = arcgis_query(client, ATLAS_MAIN, layer_id, where, f"name:{layer_id}:{normalized_name(candidate)}")
            except RuntimeError as exc:
                errors.append(f"layer {layer_id} name lookup: {exc}")
                continue

            acceptable = []
            for feature in features:
                attrs = feature.get("attributes", {})
                atlas_names = {
                    normalized_name(attrs.get("FA_NAME") or ""),
                    normalized_name(attrs.get("FA_NAME2") or ""),
                    normalized_name(attrs.get("DOW_NAME") or ""),
                }
                if normalized_candidates & atlas_names:
                    acceptable.append(feature)
            if len(acceptable) == 1:
                return _feature_to_water(acceptable[0], layer_id, source, errors, "reviewed-name-alias", 0.98)
            if len(acceptable) > 1:
                errors.append(f"layer {layer_id} name lookup for {candidate!r} returned multiple acceptable features")

    if isinstance(override.get("lat"), (int, float)) and isinstance(override.get("lng"), (int, float)):
        manual = dict(override)
        manual.pop("aliases", None)
        manual.setdefault("atlas_name", override.get("canonical_name") or report_names[0])
        manual.setdefault("alternate_name", None)
        manual.setdefault("atlas_layer", override.get("atlas_layer"))
        manual["atlas_data_source"] = "reviewed-manual-override"
        manual["atlas_errors"] = errors
        manual["match_method"] = "manual-override"
        manual["match_score"] = 1.0
        return manual

    return None


def _split_species_values(value: Any) -> list[str]:
    """Split a field only when it contains plausible human-readable names."""
    if value is None or isinstance(value, (int, float, bool)):
        return []
    text = clean(value)
    if not text or text.lower().startswith(("http://", "https://")):
        return []
    return [clean(part) for part in re.split(r"[,;/|\n]+", text) if clean(part)]


def _species_from_attributes(features: list[dict[str, Any]]) -> tuple[list[str], dict[str, Any]]:
    preferred = re.compile(r"(?:species|common.?name|fish.?name|spp)", re.I)
    ignored = {"fa_name", "fa_name2", "dow_name", "prop_name", "loc_type", "countyname"}
    names: list[str] = []
    examined: set[str] = set()
    urls: list[str] = []
    for feature in features:
        attrs = feature.get("attributes", {})
        for field, value in attrs.items():
            field_key = str(field).lower()
            if field_key in {"spoturl", "species_url", "fish_url"} and clean(value):
                urls.append(clean(value))
            if field_key in ignored or not preferred.search(str(field)):
                continue
            examined.add(str(field))
            names.extend(_split_species_values(value))
    return sorted(set(names), key=str.casefold), {"fields_examined": sorted(examined), "detail_urls": sorted(set(urls))}


def _species_from_html(page_html: str) -> list[str]:
    text = BeautifulSoup(page_html, "html.parser").get_text(" ", strip=True)
    found = []
    for species in KNOWN_COLORADO_SPECIES:
        if re.search(rf"(?<![A-Za-z]){re.escape(species)}(?![A-Za-z])", text, re.I):
            found.append(species)
    return found


def query_species_record(
    client: PoliteHttpClient,
    uid: int,
    atlas_url: str,
    override: dict[str, Any] | None = None,
    prior_species: list[str] | None = None,
) -> dict[str, Any]:
    """Collect verified species names from official Atlas records and detail HTML.

    The public layer currently identifies waters but does not consistently expose
    a plainly named species field. We therefore inspect all species-like fields,
    follow official detail URLs when present, and retain the last published result
    during temporary outages. No species are inferred from water type or habitat.
    """
    override = override or {}
    manual = sorted({clean(x) for x in override.get("species", []) if clean(x)}, key=str.casefold)
    if manual:
        return {"status": "available", "species": manual, "data_source": "reviewed-manual-override", "atlas_record": {"override": True}}

    errors: list[str] = []
    try:
        features, source = arcgis_query(client, ATLAS_DATA, ATLAS_SPECIES_LAYER, f"UNI_ID={uid}", f"species:v2:{uid}")
    except RuntimeError as exc:
        features, source = [], "unavailable"
        errors.append(str(exc))

    names, metadata = _species_from_attributes(features)
    detail_sources: list[str] = []
    candidate_urls = [*metadata.get("detail_urls", []), atlas_url]
    for url in dict.fromkeys(url for url in candidate_urls if clean(url)):
        try:
            page, page_source = client.get_text_cached(url, namespace="species-pages")
            html_names = _species_from_html(page)
            if html_names:
                names.extend(html_names)
                detail_sources.append(f"{url} ({page_source})")
        except RuntimeError as exc:
            errors.append(f"detail page {url}: {exc}")

    names = sorted(set(names), key=str.casefold)
    if names:
        return {"status": "available", "species": names, "data_source": source, "atlas_record": {**metadata, "detail_sources": detail_sources, "errors": errors}}
    if prior_species:
        return {"status": "retained-prior", "species": sorted(set(prior_species), key=str.casefold), "data_source": "prior-published-data", "atlas_record": {**metadata, "errors": errors}}
    return {"status": "no-species-exposed", "species": [], "data_source": source, "atlas_record": {**metadata, "errors": errors}}


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


def validate(
    events: list[dict[str, Any]],
    waters: list[dict[str, Any]],
    unmatched: list[dict[str, Any]],
    prior_count: int,
    prior_history_count: int = 0,
    history_count: int = 0,
) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []

    def add(level: str, code: str, message: str) -> None:
        findings.append({"level": level, "code": code, "message": message})

    if len(events) < 10:
        add("critical", "report-too-small", f"Only {len(events)} report rows were parsed.")
    if prior_count and len(events) < max(10, int(prior_count * 0.35)):
        report_dates = []
        for event in events:
            try:
                report_dates.append(datetime.fromisoformat(str(event.get("report_date"))).date())
            except (TypeError, ValueError):
                pass
        latest_report_date = max(report_dates) if report_dates else None
        today = datetime.now(timezone.utc).date()
        report_is_current = (
            latest_report_date is not None
            and today - timedelta(days=14) <= latest_report_date <= today + timedelta(days=1)
        )
        history_is_preserved = prior_history_count > 0 and history_count >= prior_history_count
        fully_matched = not unmatched and len(waters) == len({event.get("atlas_id") for event in events})

        if report_is_current and history_is_preserved and fully_matched:
            add(
                "warning",
                "rolling-window-reset",
                f"Current CPW report window fell from {prior_count} to {len(events)} rows; "
                f"accepted because the report is current, all waters matched, and "
                f"history was preserved ({prior_history_count} to {history_count} events).",
            )
        else:
            add("critical", "large-report-drop", f"Report row count fell from {prior_count} to {len(events)}.")
    if unmatched:
        add("warning", "unmatched-events", f"{len(unmatched)} current events remain unmatched.")

    species_available = sum(1 for water in waters if water.get("species"))
    if waters and species_available == 0:
        add("warning", "species-empty", "No matched water contains verified species names; inspect Atlas species extraction.")
    elif waters and species_available < max(1, int(len(waters) * 0.25)):
        add("warning", "species-low-coverage", f"Only {species_available} of {len(waters)} matched waters contain species names.")

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
        f"<tr><td>{html_lib.escape(str(w.get('name', '')))}</td>"
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
<h2>Matched waters</h2><table><thead><tr><th>Report name</th><th>Latest</th><th>Atlas ID</th><th>Atlas name</th><th>Layer</th><th>Species status</th></tr></thead><tbody>{water_rows}</tbody></table>
</body></html>"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=str(Path(__file__).parents[1] / "data"))
    parser.add_argument("--limit", type=int)
    parser.add_argument("--strict", action="store_true", help="Exit non-zero on critical validation findings")
    parser.add_argument("--cache-ttl-hours", type=int, default=24)
    parser.add_argument("--overrides", default=str(DEFAULT_OVERRIDES_PATH), help="Reviewed Atlas aliases and manual coordinate overrides")
    parser.add_argument("--species-overrides", default=str(DEFAULT_SPECIES_OVERRIDES_PATH), help="Reviewed manual species overrides")
    args = parser.parse_args()

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(timezone.utc).isoformat()
    observed_date = datetime.now(timezone.utc).date().isoformat()

    client = PoliteHttpClient(PROJECT_ROOT / ".cache", cache_ttl_hours=args.cache_ttl_hours)
    overrides = load_overrides(Path(args.overrides))
    species_overrides = load_overrides(Path(args.species_overrides))

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
        override = overrides.get(str(uid), {}) if uid is not None else {}
        report_names = sorted({item["name"] for item in group})
        info = query_atlas(client, uid, report_names, override) if uid is not None else None
        if not info or info.get("lat") is None or info.get("lng") is None:
            prior = prior_waters.get(uid)
            if prior and prior.get("lat") is not None and prior.get("lng") is not None:
                info = {key: value for key, value in prior.items() if key not in {"stocking_dates", "latest_report_date", "current_event_count", "historical_event_count", "species", "species_status"}}
                info["atlas_data_source"] = "prior-published-data"
                info["atlas_warning"] = "Atlas unavailable; retained previously published location details."
            else:
                unmatched.extend(group)
                continue

        dates = sorted({item["report_date"] for item in group}, reverse=True)
        base = group[0]
        species_result = query_species_record(
            client, uid, base["atlas_url"], species_overrides.get(str(uid), {}), prior_waters.get(uid, {}).get("species", [])
        )
        water = {
            "key": f"atlas-{uid}",
            "atlas_id": uid,
            "name": base["name"],
            "normalized_name": normalized_name(base["name"]),
            "atlas_url": base["atlas_url"],
            "latest_report_date": dates[0],
            "stocking_dates": dates,
            "current_event_count": len(group),
            "historical_event_count": sum(1 for event in history if event.get("atlas_id") == uid),
            "match_method": info.get("match_method", "atlas-id"),
            "match_score": info.get("match_score", 1.0),
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
            saved["match_method"] = water["match_method"]
            saved["match_confidence"] = water["match_score"]
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
        "latest_report_date": latest_date,
        "latest_report_events": len(latest_events),
        "latest_report_unique_waters": len({e.get("atlas_id") for e in latest_events}),
        "waters_with_species": sum(1 for water in matched if water.get("species")),
        "unique_species": len({species for water in matched for species in water.get("species", [])}),
    }
    print("STEP 5/6 — Validate generated data")
    findings = validate(
        current_events,
        matched,
        unmatched,
        prior_current_count,
        prior_history_count=len(existing_history),
        history_count=len(history),
    )
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
        "schema_version": 5,
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
            "status": "available" if any(water.get("species") for water in matched) else "no-species-exposed",
            "note": "Species are collected from official Atlas fields/detail pages or reviewed manual overrides; no habitat inference is used.",
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
